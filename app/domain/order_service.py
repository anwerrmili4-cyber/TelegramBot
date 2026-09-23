"""Service métier pour les commandes.

Centralise la logique de création, confirmation, expiration et annulation
des commandes. Les handlers Telegram appellent ces fonctions au lieu de
manipuler directement la base de données.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import database as db
from app.constants import PAID_STATUSES, TERMINAL_STATUSES, InventoryStatus, OrderStatus
from app.domain import loyalty_service, wallet_service, warranty_service
from config import CURRENCY, ORDER_EXPIRY_SECONDS, PENDING_PAYMENT_TIMEOUT_SECONDS

log = logging.getLogger(__name__)
PREORDER_SURCHARGE_RATE = 0.10


def preorder_unit_price(price: float) -> float:
    """Return the customer-facing pre-order price including its 10% surcharge."""
    return round(float(price) * (1 + PREORDER_SURCHARGE_RATE), 2)


def unit_price_for_quantity(offer: dict, qty: int, *, preorder: bool = False) -> float:
    """Return the regular, bulk, or pre-order unit price for a quantity."""
    regular_price = float(offer["price"])
    if preorder:
        return preorder_unit_price(regular_price)
    try:
        threshold = int(offer.get("bulk_quantity") or 0)
        bulk_price = float(offer.get("bulk_unit_price"))
    except (TypeError, ValueError):
        return regular_price
    if threshold > 0 and int(qty) >= threshold and 0 <= bulk_price < regular_price:
        return round(bulk_price, 2)
    return regular_price


# ---------------------------------------------------------------------------
# Création de commande
# ---------------------------------------------------------------------------

def check_duplicate_pending_order(user_id: int, offer_id: int) -> dict | None:
    """Renvoie une commande pending récente pour la même offre, ou None."""
    orders = db.list_user_orders(user_id, limit=10)
    for order in orders:
        if (
            order.get("offer_id") == offer_id
            and order.get("status") in (OrderStatus.PENDING_PAYMENT, OrderStatus.AWAITING_VERIFICATION)
        ):
            # Vérifier qu'elle n'est pas expirée
            expires_at = order.get("expires_at")
            if expires_at and expires_at < int(time.time()):
                expire_order(order["id"])
                continue
            return order
    return None


def cancel_incomplete_orders(user_id: int, exclude_order_id: int | None = None) -> list[int]:
    """Cancel a customer's older unfinished orders before creating a new one."""
    cancelled = []
    incomplete = {
        OrderStatus.PENDING_PAYMENT,
        OrderStatus.AWAITING_VERIFICATION,
        OrderStatus.VERIFICATION_FAILED,
    }
    for order in db.list_user_orders(user_id, limit=500):
        if order.get("id") != exclude_order_id and order.get("status") in incomplete and cancel_order(
            order["id"], reason="Automatically replaced by a new order"
        ):
            cancelled.append(order["id"])
    return cancelled


def create_order(
    user_id: int,
    offer: dict,
    qty: int = 1,
    payment_method: str = "binance",
    preorder: bool = False,
) -> dict:
    """Crée une commande avec expiration et renvoie l'objet complet.

    Raises:
        ValueError: si l'offre est inactive, sans prix, ou en rupture de stock.
    """
    if payment_method == "bybit":
        raise ValueError("Bybit payments are disabled.")
    if not offer or offer.get("price") is None or not offer.get("active", 1):
        raise ValueError("Cette offre n'est pas disponible à l'achat.")
    if not preorder and not db.offer_has_stock(offer):
        raise ValueError("Cette offre est en rupture de stock.")
    if qty < 1:
        raise ValueError("La quantité doit être au minimum 1.")
    if preorder and qty > 100:
        raise ValueError("The maximum pre-order quantity is 100.")
    if not preorder and not db.offer_has_stock(offer, qty):
        raise ValueError("La quantité demandée dépasse le stock disponible.")
    if preorder and db.offer_has_stock(offer):
        raise ValueError("This offer is back in stock. Buy it at the regular price.")

    now = int(time.time())
    unit_price = unit_price_for_quantity(offer, qty, preorder=preorder)
    gross_total = round(unit_price * qty, 2)
    discount = loyalty_service.discount_for_order(user_id, gross_total)
    discount_amount = discount["amount"]
    after_discount = round(max(0, gross_total - discount_amount), 2)
    wallet_used = 0.0
    if payment_method == "wallet":
        available_cents = wallet_service.balance_cents(user_id)
        if available_cents <= 0:
            raise ValueError(
                f"Insufficient balance: 0.00 {CURRENCY} available."
            )
        wallet_used = wallet_service.apply_balance(user_id, after_discount)
        if wallet_used <= 0:
            raise ValueError(
                "Your balance could not be charged. Please try again."
            )
    service = db.get_service(offer["service_id"])
    description_language = db.get_user_lang(user_id) or "en"
    product_description = (
        offer.get("description_ar")
        if description_language == "ar" and offer.get("description_ar")
        else offer.get("description")
    )
    warranty_label = warranty_service.offer_warranty_label(offer)
    warranty_snapshot = (
        "FW" if warranty_label == "FW"
        else str(offer.get("note") or "").strip() or warranty_label
    )

    order_id = db._next_id("orders")
    order_doc: dict[str, Any] = {
        "id": order_id,
        "user_id": user_id,
        "offer_id": offer["id"],
        "service_name": service["name"] if service else "",
        "offer_name": offer["name"],
        "product_description_snapshot": str(product_description or "")[:2000],
        "product_description_language": description_language,
        "warranty": warranty_snapshot,
        "warranty_days": int(offer.get("warranty_days") or 0),
        "warranty_value": offer.get("warranty_value"),
        "warranty_unit": offer.get("warranty_unit", "days"),
        "period_days": int(offer.get("period_days") or 0),
        "period_value": offer.get("period_value"),
        "period_unit": offer.get("period_unit", "days"),
        "qty": qty,
        "is_preorder": bool(preorder),
        "preorder_surcharge_percent": 10 if preorder else 0,
        "unit_price": unit_price,
        "regular_unit_price": float(offer["price"]),
        "bulk_pricing_applied": bool(
            not preorder and unit_price < float(offer["price"])
        ),
        "gross_total": gross_total,
        "loyalty_level": discount["level"],
        "loyalty_discount_percent": discount["discount_percent"],
        "loyalty_discount_amount": discount_amount,
        "wallet_amount": wallet_used,
        "wallet_refunded": False,
        "payment_method": (
            "wallet"
            if payment_method == "wallet" and wallet_used >= after_discount
            else "wallet_binance"
            if payment_method == "wallet"
            else payment_method
        ),
        "total_price": round(max(0, after_discount - wallet_used), 2),
        "currency": CURRENCY,
        "status": OrderStatus.PENDING_PAYMENT,
        "txid": "",
        "verify_method": "",
        "delivery_text": "",
        "inventory_item_ids": [],
        "admin_note": "",
        "created_at": now,
        "payment_deadline_at": now + PENDING_PAYMENT_TIMEOUT_SECONDS,
        "expires_at": now + ORDER_EXPIRY_SECONDS,
        "paid_at": None,
        "delivered_at": None,
        "cancelled_at": None,
        "updated_at": now,
    }
    db.get_conn().orders.insert_one(order_doc)

    db.audit_event(
        "order.created",
        actor_id=user_id,
        details={"order_id": order_id, "offer_id": offer["id"], "total": order_doc["total_price"]},
    )
    log.info("Commande #%d créée pour user %d (offre %s)", order_id, user_id, offer["name"])
    return db.get_order(order_id)


def delivery_content_for_order(order: dict) -> str:
    """Resolve content delivered to an order owner, including encrypted stock."""
    stored = str(order.get("delivery_text") or "").strip()
    encrypted_markers = {
        "[encrypted automatic delivery]",
        "[encrypted reseller delivery]",
    }
    if stored and stored not in encrypted_markers:
        return stored

    order_id = order.get("id")
    if order_id is None:
        return ""
    rows = list(db.get_conn().inventory.find({
        "$or": [
            {"delivered_order_id": int(order_id)},
            {"order_id": int(order_id), "status": "sold"},
        ]
    }).sort("id", 1))
    if not rows:
        return ""

    cipher = db._fernet()
    values: list[str] = []
    for row in rows:
        payload = row.get("payload")
        if not payload:
            continue
        try:
            value = cipher.decrypt(str(payload).encode()).decode().strip()
        except Exception:
            log.warning(
                "Impossible de déchiffrer le contenu livré de la commande #%s",
                order_id,
            )
            continue
        if value:
            values.append(value)
    return "\n\n".join(values)


# ---------------------------------------------------------------------------
# Expiration
# ---------------------------------------------------------------------------

def expire_order(order_id: int) -> bool:
    """Marque une commande comme expirée et libère l'inventaire réservé."""
    conn = db.get_conn()
    order = conn.orders.find_one({"id": order_id})
    if not order:
        return False
    result = conn.orders.update_one(
        {
            "id": order_id,
            "status": {"$in": [OrderStatus.PENDING_PAYMENT, OrderStatus.AWAITING_VERIFICATION]},
        },
        {
            "$set": {
                "status": OrderStatus.EXPIRED,
                "cancelled_at": int(time.time()),
                "updated_at": int(time.time()),
            }
        },
    )
    if result.modified_count != 1:
        return False

    # Libérer l'inventaire réservé s'il y en a
    _release_reserved_inventory(conn, order_id)
    wallet_service.refund_balance(order["user_id"], order.get("wallet_amount", 0), order_id)

    db.audit_event("order.expired", details={"order_id": order_id})
    log.info("Commande #%d expirée", order_id)
    return True


def expire_stale_orders() -> list[int]:
    """Expire toutes les commandes non payées dépassant le délai.

    Renvoie la liste des IDs de commandes expirées.
    """
    conn = db.get_conn()
    now = int(time.time())
    stale = list(conn.orders.find(
        {
            "status": {"$in": [OrderStatus.PENDING_PAYMENT, OrderStatus.AWAITING_VERIFICATION]},
            "expires_at": {"$lte": now, "$gt": 0},
        },
        {"id": 1},
    ))
    expired_ids = []
    for doc in stale:
        if expire_order(doc["id"]):
            expired_ids.append(doc["id"])
    return expired_ids


def cancel_stale_pending_orders(now: int | None = None) -> list[int]:
    """Cancel orders that stayed unpaid beyond the ten-minute payment window."""
    now = int(time.time()) if now is None else int(now)
    legacy_cutoff = now - PENDING_PAYMENT_TIMEOUT_SECONDS
    stale = list(db.get_conn().orders.find(
        {
            "status": OrderStatus.PENDING_PAYMENT,
            "$or": [
                {"payment_deadline_at": {"$lte": now, "$gt": 0}},
                {
                    "payment_deadline_at": {"$in": [None, 0]},
                    "created_at": {"$lte": legacy_cutoff},
                },
            ],
        },
        {"id": 1},
    ))
    cancelled_ids = []
    for order in stale:
        if cancel_order(
            int(order["id"]),
            reason="Payment window expired after 10 minutes",
        ):
            cancelled_ids.append(int(order["id"]))
    return cancelled_ids


# ---------------------------------------------------------------------------
# Annulation
# ---------------------------------------------------------------------------

def cancel_order(order_id: int, reason: str = "") -> bool:
    """Annule manuellement une commande non terminale."""
    conn = db.get_conn()
    order = conn.orders.find_one({"id": order_id})
    if not order or order["status"] in TERMINAL_STATUSES:
        return False

    result = conn.orders.update_one(
        {"id": order_id, "status": order["status"]},
        {
            "$set": {
                "status": OrderStatus.CANCELLED,
                "cancelled_at": int(time.time()),
                "updated_at": int(time.time()),
                "admin_note": reason or order.get("admin_note", ""),
            }
        },
    )
    if result.modified_count != 1:
        return False

    # Rétablir le stock si le paiement avait été confirmé
    if order["status"] in PAID_STATUSES and order.get("offer_id"):
        offer = conn.offers.find_one({"id": order["offer_id"]}) or {}
        if not offer.get("unlimited_stock") and not order.get("is_preorder"):
            conn.offers.update_one(
                {"id": order["offer_id"]},
                {"$inc": {"stock": order.get("qty", 1)}},
            )

    _release_reserved_inventory(conn, order_id)
    wallet_service.refund_balance(order["user_id"], order.get("wallet_amount", 0), order_id)

    db.audit_event("order.cancelled", details={"order_id": order_id, "reason": reason})
    log.info("Commande #%d annulée", order_id)
    return True


# ---------------------------------------------------------------------------
# Changement de statut
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.AWAITING_VERIFICATION, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.AWAITING_VERIFICATION: {OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED, OrderStatus.MANUAL_REVIEW, OrderStatus.VERIFICATION_FAILED, OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.VERIFICATION_FAILED: {OrderStatus.PENDING_PAYMENT, OrderStatus.MANUAL_REVIEW, OrderStatus.CANCELLED},
    OrderStatus.MANUAL_REVIEW: {OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.PAID: {OrderStatus.DELIVERED, OrderStatus.PREPARING_DELIVERY, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.PAYMENT_CONFIRMED: {OrderStatus.DELIVERED, OrderStatus.PREPARING_DELIVERY, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.PREPARING_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
    OrderStatus.EXPIRED: set(),
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Vérifie si une transition de statut est valide."""
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def transition_order(order_id: int, to_status: str, **extra_fields: Any) -> bool:
    """Change le statut d'une commande si la transition est valide.

    Args:
        order_id: ID de la commande.
        to_status: Nouveau statut souhaité.
        **extra_fields: Champs supplémentaires à mettre à jour.

    Returns:
        True si la transition a été effectuée.
    """
    order = db.get_order(order_id)
    if not order:
        return False

    current = order["status"]
    if not is_valid_transition(current, to_status):
        log.warning("Transition invalide: #%d %s → %s", order_id, current, to_status)
        return False

    update: dict[str, Any] = {"status": to_status, "updated_at": int(time.time())}
    if to_status in PAID_STATUSES and "paid_at" not in extra_fields:
        update["paid_at"] = int(time.time())
    if to_status == OrderStatus.DELIVERED and "delivered_at" not in extra_fields:
        update["delivered_at"] = int(time.time())

    update.update(extra_fields)
    result = db.get_conn().orders.update_one(
        {"id": order_id, "status": current},
        {"$set": update},
    )
    if result.modified_count == 1:
        db.audit_event(
            f"order.{to_status}",
            details={"order_id": order_id, "from": current, "to": to_status},
        )
        return True
    return False


def reset_for_payment(order_id: int) -> bool:
    """Return a failed/review payment to the payment waiting state."""
    conn = db.get_conn()
    result = conn.orders.update_one(
        {
            "id": order_id,
            "status": {"$in": [
                OrderStatus.AWAITING_VERIFICATION,
                OrderStatus.VERIFICATION_FAILED,
                OrderStatus.MANUAL_REVIEW,
            ]},
        },
        {
            "$set": {
                "status": OrderStatus.PENDING_PAYMENT,
                "txid": "",
                "verify_method": "",
                "updated_at": int(time.time()),
            }
        },
    )
    if result.modified_count:
        db.audit_event("order.reset_for_payment", details={"order_id": order_id})
        return True
    return False


def mark_refunded(order_id: int, reason: str = "") -> bool:
    """Mark a paid or delivered order as refunded, idempotently."""
    conn = db.get_conn()
    existing = conn.orders.find_one({"id": order_id})
    if not existing:
        return False
    if existing.get("status") == OrderStatus.REFUNDED:
        return True
    result = conn.orders.update_one(
        {
            "id": order_id,
            "status": {"$in": [
                OrderStatus.PAID,
                OrderStatus.PAYMENT_CONFIRMED,
                OrderStatus.PREPARING_DELIVERY,
                OrderStatus.DELIVERED,
                OrderStatus.MANUAL_REVIEW,
            ]},
        },
        {
            "$set": {
                "status": OrderStatus.REFUNDED,
                "refunded_at": int(time.time()),
                "admin_note": reason or existing.get("admin_note", ""),
                "updated_at": int(time.time()),
            }
        },
    )
    if result.modified_count:
        db.audit_event("order.refunded", details={"order_id": order_id, "reason": reason})
        return True
    return False


def admin_update_order(
    order_id: int,
    *,
    status: str | None = None,
    txid: str | None = None,
    qty: int | None = None,
    unit_price: float | None = None,
    total_price: float | None = None,
    admin_note: str | None = None,
) -> dict | None:
    """Update editable order fields from the admin dashboard."""
    conn = db.get_conn()
    order = conn.orders.find_one({"id": order_id})
    if not order:
        return None

    update: dict[str, Any] = {"updated_at": int(time.time())}
    if status is not None:
        valid_statuses = {item.value for item in OrderStatus}
        paid_statuses = {str(item) for item in PAID_STATUSES}
        if status not in valid_statuses:
            raise ValueError("Statut de commande invalide")
        update["status"] = status
        if status in paid_statuses and not order.get("paid_at"):
            update["paid_at"] = int(time.time())
        if status == OrderStatus.DELIVERED.value and not order.get("delivered_at"):
            update["delivered_at"] = int(time.time())
        if status == OrderStatus.CANCELLED.value and not order.get("cancelled_at"):
            update["cancelled_at"] = int(time.time())

    if txid is not None:
        txid = txid.strip()
        if txid:
            duplicate = conn.orders.find_one({"txid": txid, "id": {"$ne": order_id}}, {"id": 1})
            if duplicate:
                raise ValueError(f"TXID dÃ©jÃ  utilisÃ© par la commande #{duplicate['id']}")
        update["txid"] = txid

    if qty is not None:
        if qty < 1:
            raise ValueError("La quantitÃ© doit Ãªtre supÃ©rieure Ã  0")
        update["qty"] = qty

    if unit_price is not None:
        if unit_price < 0:
            raise ValueError("Le prix unitaire ne peut pas Ãªtre nÃ©gatif")
        update["unit_price"] = round(unit_price, 2)

    if total_price is not None:
        if total_price < 0:
            raise ValueError("Le total ne peut pas Ãªtre nÃ©gatif")
        update["total_price"] = round(total_price, 2)

    if admin_note is not None:
        update["admin_note"] = admin_note.strip()[:2000]

    conn.orders.update_one({"id": order_id}, {"$set": update})
    db.audit_event("order.admin_updated", details={"order_id": order_id, "fields": sorted(update)})
    return db.get_order(order_id)


def manual_deliver_order(order_id: int, content: str) -> dict | None:
    """Mark an order delivered with administrator-provided content."""
    content = content.strip()
    if not content:
        raise ValueError("Le contenu de livraison est obligatoire")

    conn = db.get_conn()
    result = conn.orders.update_one(
        {
            "id": order_id,
            "status": {"$in": [OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED]},
        },
        {
            "$set": {
                "status": OrderStatus.DELIVERED,
                "delivery_text": content,
                "delivered_at": int(time.time()),
                "updated_at": int(time.time()),
            }
        },
    )
    if result.matched_count != 1:
        return None
    db.audit_event("order.manual_delivered", details={"order_id": order_id})
    # Keep asynchronous Buyer API responses in sync with manual fulfillment.
    try:
        from app.domain import buyer_api_service
        buyer_api_service.sync_order_delivery(order_id)
    except Exception:
        # Delivery already succeeded; the status endpoint can repair the cache.
        log.exception("Buyer API delivery cache sync failed for order #%s", order_id)
    return db.get_order(order_id)


# ---------------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------------

def _release_reserved_inventory(conn, order_id: int) -> int:
    """Libère tout inventaire réservé pour une commande."""
    result = conn.inventory.update_many(
        {"reserved_order_id": order_id, "status": InventoryStatus.RESERVED},
        {
            "$set": {
                "status": InventoryStatus.AVAILABLE,
                "reserved_order_id": None,
                "reserved_at": None,
            }
        },
    )
    return result.modified_count
