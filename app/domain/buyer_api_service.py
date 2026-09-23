"""Public buyer API backed by the bot's native wallet and order services."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import database as db
from app.domain import inventory_service, order_service, payment_service, reseller_service, warranty_service
from config import CURRENCY

KEY_PREFIX = "tgb_"
RATE_LIMITS = {
    "global_key": 60,
    "global_ip": 120,
    "products_key": 10,
    "balance_key": 30,
    "purchase_key": 5,
    "status_key": 30,
    "auth_ip": 15,
}


class BuyerApiError(RuntimeError):
    """Safe public API failure with an HTTP status and stable error code."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "code": self.code,
            "message": self.message,
        }
        if self.retry_after is not None:
            result["retryable"] = True
            result["rateLimit"] = {"retryAfter": self.retry_after}
        return result


def _key_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_key(user_id: int, *, label: str = "Buyer API") -> dict[str, Any]:
    """Issue a buyer key once; only its hash is persisted."""
    user_id = int(user_id)
    conn = db.get_conn()
    if not conn.users.find_one({"telegram_id": user_id}, {"_id": 1}):
        raise ValueError("Utilisateur Telegram introuvable.")
    raw_key = KEY_PREFIX + secrets.token_hex(24)
    now = int(time.time())
    key_id = db._next_id("buyer_api_keys")
    conn.buyer_api_keys.insert_one({
        "id": key_id,
        "key_hash": _key_hash(raw_key),
        "prefix": raw_key[:12],
        "user_id": user_id,
        "label": str(label or "Buyer API").strip()[:80],
        "active": True,
        "created_at": now,
        "updated_at": now,
        "last_used_at": None,
    })
    db.audit_event(
        "buyer_api.key_created",
        details={"key_id": key_id, "user_id": user_id},
    )
    return {
        "id": key_id,
        "key": raw_key,
        "prefix": raw_key[:12],
        "user_id": user_id,
        "label": str(label or "Buyer API").strip()[:80],
        "created_at": now,
    }


def list_keys() -> list[dict[str, Any]]:
    """Return admin-safe key metadata without hashes or full credentials."""
    rows = []
    for item in db.get_conn().buyer_api_keys.find({}).sort("id", -1):
        rows.append({
            "id": int(item["id"]),
            "prefix": str(item.get("prefix") or ""),
            "user_id": int(item["user_id"]),
            "label": str(item.get("label") or ""),
            "active": bool(item.get("active")),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_used_at"),
        })
    return rows


def active_key_for_user(user_id: int) -> dict[str, Any] | None:
    """Return safe metadata for a user's current key, never its hash or secret."""
    item = db.get_conn().buyer_api_keys.find_one(
        {"user_id": int(user_id), "active": True},
        sort=[("created_at", -1), ("id", -1)],
    )
    if not item:
        return None
    return {
        "id": int(item["id"]),
        "prefix": str(item.get("prefix") or ""),
        "user_id": int(item["user_id"]),
        "label": str(item.get("label") or ""),
        "active": True,
        "created_at": item.get("created_at"),
        "last_used_at": item.get("last_used_at"),
    }


def issue_user_key(user_id: int, *, regenerate: bool = False) -> dict[str, Any]:
    """Self-service key issue with at most one active credential per Telegram user."""
    user_id = int(user_id)
    current = active_key_for_user(user_id)
    if current and not regenerate:
        raise BuyerApiError(
            409,
            "API_KEY_ALREADY_EXISTS",
            "An active API key already exists. Regenerate it to receive a new one.",
        )
    if current:
        now = int(time.time())
        db.get_conn().buyer_api_keys.update_many(
            {"user_id": user_id, "active": True},
            {"$set": {"active": False, "revoked_at": now, "updated_at": now}},
        )
        db.audit_event(
            "buyer_api.key_regenerated",
            actor_id=user_id,
            details={"previous_key_id": current["id"]},
        )
    return create_key(user_id, label="Reseller API")


def dashboard(user_id: int) -> dict[str, Any]:
    """Build the safe user-facing reseller dashboard summary."""
    user_id = int(user_id)
    conn = db.get_conn()
    wallet = conn.wallets.find_one({"user_id": user_id}) or {}
    cutoff = int(time.time()) - (30 * 24 * 60 * 60)
    successful = {
        "user_id": user_id,
        "response.success": True,
    }
    total_orders = conn.buyer_api_purchases.count_documents(successful)
    spend_30d = 0.0
    for purchase_row in conn.buyer_api_purchases.find({
        **successful,
        "created_at": {"$gte": cutoff},
    }):
        response = purchase_row.get("response") or {}
        spend_30d += float(response.get("amount") or 0)
    active_key = active_key_for_user(user_id)
    return {
        "active": active_key is not None,
        "balance": max(0, int(wallet.get("balance_cents") or 0)) / 100,
        "currency": CURRENCY,
        "total_orders": total_orders,
        "spend_30d": round(spend_30d, 2),
        "key": active_key,
    }


def revoke_key(key_id: int) -> bool:
    result = db.get_conn().buyer_api_keys.update_one(
        {"id": int(key_id), "active": True},
        {"$set": {"active": False, "revoked_at": int(time.time())}},
    )
    if result.modified_count:
        db.audit_event("buyer_api.key_revoked", details={"key_id": int(key_id)})
        return True
    return False


def _consume_rate_limit(bucket: str, identity: str) -> None:
    limit = RATE_LIMITS[bucket]
    now = int(time.time())
    window = now // 60
    retry_after = 60 - (now % 60)
    key = hashlib.sha256(f"{bucket}:{identity}".encode()).hexdigest()
    conn = db.get_conn()
    try:
        row = conn.buyer_api_rate_limits.find_one_and_update(
            {"bucket": key, "window": window},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "scope": bucket,
                    "expire_at": datetime.now(UTC) + timedelta(minutes=2),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        row = conn.buyer_api_rate_limits.find_one_and_update(
            {"bucket": key, "window": window},
            {"$inc": {"count": 1}},
            return_document=ReturnDocument.AFTER,
        )
    if int((row or {}).get("count") or 0) > limit:
        raise BuyerApiError(
            429,
            "RATE_LIMITED",
            "Too many requests. Please try again later.",
            retry_after=retry_after,
        )


def authenticate(raw_key: str, client_ip: str, endpoint: str) -> dict[str, Any]:
    """Authenticate and apply per-IP, global-key, and endpoint quotas."""
    raw_key = str(raw_key or "").strip()
    client_ip = str(client_ip or "unknown")[:128]
    _consume_rate_limit("global_ip", client_ip)
    if not re.fullmatch(r"tgb_[A-Fa-f0-9]{48}", raw_key):
        _consume_rate_limit("auth_ip", client_ip)
        raise BuyerApiError(401, "INVALID_API_KEY", "Invalid API key.")
    key = db.get_conn().buyer_api_keys.find_one({
        "key_hash": _key_hash(raw_key),
        "active": True,
    })
    if not key:
        _consume_rate_limit("auth_ip", client_ip)
        raise BuyerApiError(401, "INVALID_API_KEY", "Invalid API key.")
    identity = str(key["id"])
    _consume_rate_limit("global_key", identity)
    endpoint_bucket = f"{endpoint}_key"
    if endpoint_bucket in RATE_LIMITS:
        _consume_rate_limit(endpoint_bucket, identity)
    db.get_conn().buyer_api_keys.update_one(
        {"id": key["id"]},
        {"$set": {"last_used_at": int(time.time())}},
    )
    return key


def authenticate_bearer(
    authorization: str, client_ip: str, endpoint: str
) -> dict[str, Any]:
    """Authenticate the standard Authorization: Bearer <key> credential."""
    scheme, separator, raw_key = str(authorization or "").strip().partition(" ")
    if not separator or scheme.lower() != "bearer" or not raw_key.strip():
        return authenticate("", client_ip, endpoint)
    return authenticate(raw_key.strip(), client_ip, endpoint)


def _requester(key: dict[str, Any]) -> dict[str, Any]:
    user = db.get_conn().users.find_one({"telegram_id": key["user_id"]}) or {}
    name = (
        user.get("username")
        or user.get("first_name")
        or user.get("full_name")
        or str(key["user_id"])
    )
    return {"chatId": int(key["user_id"]), "name": str(name)[:100]}


def products(key: dict[str, Any]) -> dict[str, Any]:
    conn = db.get_conn()
    services = {
        row["id"]: row
        for row in db.list_services(active_only=True)
    }
    result = []
    for offer in conn.offers.find({"active": 1}).sort([("sort_order", 1), ("id", 1)]):
        offer = db.get_offer(int(offer["id"])) or {}
        if not offer or not db.offer_has_stock(offer):
            continue
        service = services.get(offer.get("service_id"), {})
        available = -1 if offer.get("unlimited_stock") else int(offer.get("stock") or 0)
        result.append({
            "_id": str(offer["id"]),
            "product_name": str(offer.get("name") or offer["id"]),
            "description": str(offer.get("description") or offer.get("note") or ""),
            "warranty": warranty_service.offer_warranty_label(offer),
            "warrantyValue": int(offer.get("warranty_value") if offer.get("warranty_value") is not None else (offer.get("warranty_days") or 0)),
            "warrantyUnit": str(offer.get("warranty_unit") or "days"),
            "periodDays": int(offer.get("period_days") or 0),
            "periodValue": int(offer.get("period_value") if offer.get("period_value") is not None else (offer.get("period_days") or 0)),
            "periodUnit": str(offer.get("period_unit") or "days"),
            "periodLabel": warranty_service.offer_period_label(offer),
            "service": {
                "id": str(service.get("id") or ""),
                "name": str(service.get("name") or ""),
            },
            "walletCurrency": CURRENCY,
            "walletPricing": float(offer.get("price") or 0),
            "walletPricingText": f"{float(offer.get('price') or 0):.2f} {CURRENCY}",
            "quantityFixed": 1,
            "requiresCustomerEmail": False,
            "manualDelivery": not bool(offer.get("auto_delivery", True)),
            "stats": {
                "available": available,
                "sold": db.offer_sold_count(int(offer["id"])),
            },
        })
    return {
        "success": True,
        "walletCurrency": CURRENCY,
        "requester": _requester(key),
        "products": result,
    }


def balance(key: dict[str, Any]) -> dict[str, Any]:
    cents = max(0, int((db.get_conn().wallets.find_one(
        {"user_id": int(key["user_id"])}
    ) or {}).get("balance_cents", 0)))
    return {
        "success": True,
        "walletCurrency": CURRENCY,
        "requester": _requester(key),
        "balance": cents / 100,
        "balanceText": f"{cents / 100:.2f} {CURRENCY}",
        "updatedAt": datetime.now(UTC).isoformat(),
    }


def _request_hash(product_id: str, quantity: int) -> str:
    canonical = json.dumps(
        {"product_id": product_id, "quantity": quantity},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _delivery_for_order(order: dict[str, Any]) -> list[str]:
    offer = db.get_offer(order.get("offer_id")) if order.get("offer_id") else None
    if offer and offer.get("supplier_provider"):
        return reseller_service.fulfill_paid_order(int(order["id"])) or []
    return inventory_service.delivered_content(int(order["id"]))


def _delivery_items_for_order(order: dict[str, Any]) -> list[str]:
    """Return the final API delivery without exposing encrypted storage markers."""
    stored = str(order.get("delivery_text") or "").strip()
    if stored and stored not in {
        "[encrypted automatic delivery]",
        "[encrypted reseller delivery]",
    }:
        return [stored]
    return inventory_service.delivered_content(int(order["id"]))


def _refresh_purchase(purchase_row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Synchronize a cached buyer response with its authoritative order state."""
    response = dict(purchase_row.get("response") or {})
    order_id = purchase_row.get("order_id")
    order = db.get_order(int(order_id)) if order_id is not None else None
    if not order:
        return int(purchase_row.get("http_status") or 202), response

    order_status = str(order.get("status") or "")
    if order_status == "delivered":
        response.update({
            "success": True,
            "orderCode": f"BM-{int(order['id'])}",
            "status": "delivered",
            "terminal": True,
            "deliveredAccounts": _delivery_items_for_order(order),
        })
        http_status = 200
        stored_status = "completed"
    elif order_status in {"cancelled", "refunded"}:
        response.update({
            "status": order_status,
            "terminal": True,
            "deliveredAccounts": [],
        })
        http_status = 200
        stored_status = order_status
    else:
        response.update({
            "status": "processing",
            "terminal": False,
            "deliveredAccounts": [],
        })
        http_status = 202
        stored_status = "processing_delivery"

    now = int(time.time())
    response["updatedAt"] = datetime.fromtimestamp(
        int(order.get("updated_at") or now), UTC
    ).isoformat()
    if order.get("delivered_at"):
        response["deliveredAt"] = datetime.fromtimestamp(
            int(order["delivered_at"]), UTC
        ).isoformat()
    db.get_conn().buyer_api_purchases.update_one(
        {"buyer_key_id": purchase_row["buyer_key_id"],
         "idempotency_key": purchase_row["idempotency_key"]},
        {"$set": {
            "status": stored_status,
            "http_status": http_status,
            "response": response,
            "updated_at": now,
        }},
    )
    return http_status, response


def sync_order_delivery(order_id: int) -> None:
    """Persist final delivery data for an order created through the buyer API."""
    row = db.get_conn().buyer_api_purchases.find_one({"order_id": int(order_id)})
    if row:
        _refresh_purchase(row)


def order_status(key: dict[str, Any], order_code: str) -> dict[str, Any]:
    """Return one order owned by the authenticated buyer key."""
    match = re.fullmatch(r"BM-([1-9][0-9]*)", str(order_code or "").strip(), re.IGNORECASE)
    if not match:
        raise BuyerApiError(400, "INVALID_ORDER_CODE", "orderCode must use the BM-123 format.")
    row = db.get_conn().buyer_api_purchases.find_one({
        "buyer_key_id": int(key["id"]),
        "order_id": int(match.group(1)),
    })
    if not row:
        # Do not reveal whether an order belonging to another buyer exists.
        raise BuyerApiError(404, "ORDER_NOT_FOUND", "Order not found.")
    _http_status, response = _refresh_purchase(row)
    return response


def purchase(
    key: dict[str, Any],
    *,
    product_id: str,
    quantity: int,
    idempotency_key: str,
) -> tuple[int, dict[str, Any], bool]:
    """Charge a wallet and deliver a product exactly once per idempotency key."""
    product_id = str(product_id or "").strip()
    idempotency_key = str(idempotency_key or "").strip()
    if not product_id.isdigit():
        raise BuyerApiError(400, "INVALID_PRODUCT_ID", "product_id must be a numeric string.")
    if quantity < 1 or quantity > 100:
        raise BuyerApiError(400, "INVALID_QUANTITY", "quantity must be between 1 and 100.")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise BuyerApiError(400, "INVALID_IDEMPOTENCY_KEY", "A valid Idempotency-Key is required.")

    conn = db.get_conn()
    request_hash = _request_hash(product_id, quantity)
    identity = {"buyer_key_id": int(key["id"]), "idempotency_key": idempotency_key}
    existing = conn.buyer_api_purchases.find_one(identity)
    if existing:
        if existing.get("request_hash") != request_hash:
            raise BuyerApiError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "This Idempotency-Key was already used for a different request.",
            )
        if existing.get("response") and existing.get("http_status"):
            status, response = _refresh_purchase(existing)
            return status, response, True
        raise BuyerApiError(409, "PURCHASE_IN_PROGRESS", "This purchase is already in progress.")

    now = int(time.time())
    try:
        conn.buyer_api_purchases.insert_one({
            **identity,
            "request_hash": request_hash,
            "user_id": int(key["user_id"]),
            "status": "processing",
            "created_at": now,
            "updated_at": now,
        })
    except DuplicateKeyError:
        raise BuyerApiError(409, "PURCHASE_IN_PROGRESS", "This purchase is already in progress.") from None

    try:
        offer = db.get_offer(int(product_id))
        if not offer or not offer.get("active", 1):
            raise BuyerApiError(404, "PRODUCT_NOT_FOUND", "Product not found.")
        if not db.offer_has_stock(offer, quantity):
            raise BuyerApiError(409, "INSUFFICIENT_STOCK", "Inventory is not sufficient.")

        gross_cents = round(float(offer.get("price") or 0) * quantity * 100)
        current_balance = int((conn.wallets.find_one(
            {"user_id": int(key["user_id"])}
        ) or {}).get("balance_cents", 0))
        if current_balance < gross_cents:
            raise BuyerApiError(400, "INSUFFICIENT_BALANCE", "Wallet balance is not enough.")

        order = order_service.create_order(
            int(key["user_id"]), offer, qty=quantity, payment_method="wallet"
        )
        conn.buyer_api_purchases.update_one(
            identity,
            {"$set": {"order_id": int(order["id"]), "updated_at": int(time.time())}},
        )
        conn.orders.update_one(
            {"id": int(order["id"])},
            {"$set": {
                "source": "buyer_api",
                "buyer_api_key_id": int(key["id"]),
                "buyer_api_idempotency_key": idempotency_key,
            }},
        )
        if float(order.get("total_price") or 0) != 0:
            order_service.cancel_order(int(order["id"]), "Buyer API requires full wallet payment")
            raise BuyerApiError(400, "INSUFFICIENT_BALANCE", "Wallet balance is not enough.")

        payment = payment_service.confirm_wallet_order(int(order["id"]), int(key["user_id"]))
        if payment.get("status") == "failed":
            order_service.cancel_order(
                int(order["id"]), "Buyer API purchase could not reserve stock"
            )
            raise BuyerApiError(
                409,
                "INSUFFICIENT_STOCK",
                "Inventory changed before the purchase could be completed.",
            )
        delivered = list(payment.get("delivered_content") or [])
        final_order = db.get_order(int(order["id"])) or order
        response_time = int(final_order.get("updated_at") or time.time())
        response = {
            "success": True,
            "walletCurrency": CURRENCY,
            "orderCode": f"BM-{int(order['id'])}",
            "productType": str(offer.get("name") or product_id),
            "quantity": quantity,
            "amount": float(final_order.get("wallet_amount") or 0),
            "amountText": f"{float(final_order.get('wallet_amount') or 0):.2f} {CURRENCY}",
            "balance": balance(key)["balance"],
            "status": "delivered" if delivered else "processing",
            "terminal": bool(delivered),
            "deliveredAccounts": delivered,
            "updatedAt": datetime.fromtimestamp(response_time, UTC).isoformat(),
        }
        if final_order.get("delivered_at"):
            response["deliveredAt"] = datetime.fromtimestamp(
                int(final_order["delivered_at"]), UTC
            ).isoformat()
        http_status = 200 if delivered else 202
        conn.buyer_api_purchases.update_one(
            identity,
            {"$set": {
                "status": "completed" if delivered else "processing_delivery",
                "http_status": http_status,
                "response": response,
                "updated_at": int(time.time()),
            }},
        )
        db.audit_event(
            "buyer_api.purchase",
            actor_id=int(key["user_id"]),
            details={
                "key_id": int(key["id"]),
                "order_id": int(order["id"]),
                "offer_id": int(offer["id"]),
                "quantity": quantity,
            },
        )
        return http_status, response, False
    except BuyerApiError as exc:
        conn.buyer_api_purchases.update_one(
            identity,
            {"$set": {
                "status": "failed",
                "http_status": exc.status,
                "response": exc.payload(),
                "updated_at": int(time.time()),
            }},
        )
        raise
