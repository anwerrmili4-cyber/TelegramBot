"""Service métier pour les paiements.

Centralise la validation du TXID, les vérifications Binance/Bybit, l'idempotence
et le passage en revue manuelle.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import database as db
from app.constants import OrderStatus
from app.domain import affiliate_service, inventory_service, loyalty_service, reseller_service
from config import ADMIN_ID, CURRENCY, TEST_PAYMENT_ENABLED, USDT_EVM_ADDRESS
from onchain_verifier import verify_onchain_usdt
from payment_verifier import verify_bybit_payment, verify_payment

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation du TXID
# ---------------------------------------------------------------------------

class TxidValidationError(Exception):
    """Erreur de validation du TXID avec un code d'erreur structuré."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_txid_format(txid: str) -> str:
    """Valide et nettoie un TXID.

    Raises:
        TxidValidationError: si le format est invalide.
    """
    txid = txid.strip()

    if len(txid) < 6:
        raise TxidValidationError("too_short", "Le TXID est trop court (minimum 6 caractères).")

    if len(txid) > 128:
        raise TxidValidationError("too_long", "Le TXID est trop long (maximum 128 caractères).")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", txid):
        raise TxidValidationError("invalid_chars", "Le TXID contient des caractères non autorisés.")

    return txid


def check_txid_uniqueness(txid: str, order_id: int) -> None:
    """Vérifie qu'un TXID n'a pas déjà été utilisé par une autre commande.

    Raises:
        TxidValidationError: si le TXID est déjà associé à une autre commande.
    """
    conn = db.get_conn()
    existing = conn.orders.find_one(
        {"txid": txid, "id": {"$ne": order_id}},
    )
    if existing:
        raise TxidValidationError(
            "already_used",
            f"Ce TXID a déjà été utilisé pour la commande #{existing['id']}.",
        )


def _finalize_confirmed_payment(order_id: int, user_id: int, txid: str, method: str) -> dict[str, Any]:
    with db.coalesce_admin_notifications():
        return _finalize_confirmed_payment_now(order_id, user_id, txid, method)


def _finalize_confirmed_payment_now(order_id: int, user_id: int, txid: str, method: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "failed",
        "order": db.get_order(order_id),
        "delivered_content": None,
        "error_code": None,
        "error_message": None,
        "affiliate": None,
    }
    if txid:
        db.update_order(order_id, txid=txid)
    if db.mark_order_paid(order_id, method):
        result["status"] = "confirmed"
        result["affiliate"] = affiliate_service.on_confirmed_payment(user_id, order_id)
        result["loyalty"] = loyalty_service.record_purchase(user_id)
        order = db.get_order(order_id) or {}
        offer = db.get_offer(order.get("offer_id")) if order.get("offer_id") else None
        try:
            if order.get("is_preorder"):
                delivered = None
            elif (
                offer
                and offer.get("feature_key") == "bot_like_mine"
                and str(offer.get("delivery_url") or "").strip()
            ):
                # Deliver only the administrator-configured private repository
                # link after payment has completed successfully.
                delivery_url = str(offer["delivery_url"]).strip()
                delivered = [f"Private GitHub project: {delivery_url}"]
                now = int(time.time())
                db.get_conn().orders.update_one(
                    {"id": int(order_id)},
                    {"$set": {
                        "status": "delivered",
                        "delivery_text": delivered[0],
                        "delivered_at": now,
                        "updated_at": now,
                    }},
                )
            elif offer and offer.get("method_media"):
                # Digital Methods offers have no finite inventory; their media
                # package is delivered once payment is confirmed.
                delivered = ["__method_media__"]
                now = int(time.time())
                db.get_conn().orders.update_one(
                    {"id": int(order_id)},
                    {"$set": {"status": "delivered", "delivered_at": now, "updated_at": now}},
                )
            elif offer and offer.get("supplier_provider"):
                delivered = reseller_service.fulfill_paid_order(order_id)
            else:
                delivered = inventory_service.deliver_for_order(order_id)
        except reseller_service.ResellerApiError as exc:
            delivered = None
            result["error_code"] = (
                "supplier_order_not_created"
                if isinstance(exc, reseller_service.ResellerOrderNotCreatedError)
                else "supplier_delivery_pending"
            )
            result["error_message"] = str(exc)
            log.warning("Supplier delivery pending for order #%s: %s", order_id, exc)
            db.audit_event(
                "order.reseller_delivery_pending",
                actor_id=user_id,
                details={"order_id": order_id, "reason": str(exc)},
            )
        if delivered:
            result["delivered_content"] = delivered
            result["status"] = "delivered"
            result["order"] = db.get_order(order_id)
        else:
            result["status"] = "confirmed_no_delivery"
        db.audit_event(
            "payment.confirmed",
            actor_id=user_id,
            details={"order_id": order_id, "txid": txid, "method": method},
        )
    else:
        result["error_code"] = "payment_failed"
        result["error_message"] = "Le paiement n'a pas pu etre enregistre (stock insuffisant ou erreur)."
    return result


def _finalize_admin_test_payment(order_id: int, user_id: int, txid: str) -> dict[str, Any]:
    """Complete a test order with obvious samples, never real inventory."""
    order = db.get_order(order_id)
    result: dict[str, Any] = {
        "status": "failed", "order": order, "delivered_content": None,
        "error_code": None, "error_message": None, "affiliate": None,
    }
    if not order:
        result["error_code"] = "order_not_found"
        return result
    qty = max(1, int(order.get("qty", 1)))
    samples = [
        f"SAMPLE TEST PRODUCT {index}/{qty} — NOT A REAL PRODUCT — ORDER #{order_id}"
        for index in range(1, qty + 1)
    ]
    now = int(time.time())
    updated = db.get_conn().orders.update_one(
        {
            "id": order_id,
            "user_id": user_id,
            "status": {"$in": [
                OrderStatus.PENDING_PAYMENT,
                OrderStatus.AWAITING_VERIFICATION,
                OrderStatus.VERIFICATION_FAILED,
                OrderStatus.MANUAL_REVIEW,
            ]},
        },
        {"$set": {
            "status": OrderStatus.DELIVERED,
            "txid": txid,
            "verify_method": "admin_test",
            "delivery_text": "[admin test samples]",
            "paid_at": now,
            "delivered_at": now,
            "updated_at": now,
        }},
    )
    if updated.modified_count != 1:
        result["error_code"] = "payment_failed"
        return result
    db.audit_event(
        "payment.admin_test_delivered", actor_id=user_id,
        details={"order_id": order_id, "items_count": qty},
    )
    result.update({
        "status": "delivered", "order": db.get_order(order_id),
        "delivered_content": samples,
    })
    return result


def confirm_wallet_order(order_id: int, user_id: int) -> dict[str, Any]:
    order = db.get_order(order_id)
    if not order or order.get("user_id") != user_id or float(order.get("total_price", 1)) != 0:
        return {"status": "failed", "order": order, "delivered_content": None, "affiliate": None}
    return _finalize_confirmed_payment(order_id, user_id, "", "wallet")


# ---------------------------------------------------------------------------
# Workflow de paiement
# ---------------------------------------------------------------------------

def submit_payment(order_id: int, txid: str, user_id: int) -> dict[str, Any]:
    """Soumet un TXID pour vérification.

    Workflow complet :
    1. Valider le format du TXID
    2. Vérifier l'unicité
    3. Vérifier la propriété de la commande
    4. Vérifier que la commande est dans un état acceptable
    5. Vérifier le TXID avec Binance
    6. Livrer si confirmé, ou passer en revue manuelle

    Returns:
        dict avec les clés: status, order, delivered_content, error_code, error_message
    """
    result: dict[str, Any] = {
        "status": "failed",
        "order": None,
        "delivered_content": None,
        "error_code": None,
        "error_message": None,
        "affiliate": None,
    }

    # 1. Valider le format
    try:
        txid = validate_txid_format(txid)
    except TxidValidationError as exc:
        result["error_code"] = exc.code
        result["error_message"] = exc.message
        return result

    # 2. Récupérer et vérifier la commande
    order = db.get_order(order_id)
    if not order:
        result["error_code"] = "order_not_found"
        result["error_message"] = "Commande introuvable."
        return result

    result["order"] = order

    if order["user_id"] != user_id:
        result["error_code"] = "not_owner"
        result["error_message"] = "Cette commande ne vous appartient pas."
        return result

    # Vérifier que la commande n'est pas déjà payée/livrée
    if order["status"] in (OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED, OrderStatus.DELIVERED):
        result["error_code"] = "already_paid"
        result["error_message"] = "Cette commande a déjà été payée."
        result["status"] = "already_paid"
        return result

    # Vérifier que la commande est dans un état de paiement
    if order["status"] not in (OrderStatus.PENDING_PAYMENT, OrderStatus.AWAITING_VERIFICATION, OrderStatus.VERIFICATION_FAILED):
        result["error_code"] = "invalid_status"
        result["error_message"] = f"La commande est en statut {order['status']} et ne peut pas recevoir de paiement."
        return result

    # Vérifier expiration
    if order.get("expires_at") and order["expires_at"] < int(time.time()):
        from app.domain.order_service import expire_order
        expire_order(order_id)
        result["error_code"] = "expired"
        result["error_message"] = "Cette commande a expiré. Veuillez en créer une nouvelle."
        return result

    # Explicit administrator-only test path. Customers can never use it.
    if txid.upper() == "TEST-PAYMENT":
        database_enabled = str(db.get_setting("admin_test_payment_enabled", "false")).lower() in {
            "1", "true", "yes", "on",
        }
        if user_id != ADMIN_ID or not (TEST_PAYMENT_ENABLED or database_enabled):
            result["error_code"] = "not_found"
            result["error_message"] = "Transaction not found."
            return result
        test_txid = f"TEST-PAYMENT-{order_id}-{int(time.time())}"
        return _finalize_admin_test_payment(order_id, user_id, test_txid)

    # 3. Vérifier unicité du TXID
    try:
        check_txid_uniqueness(txid, order_id)
    except TxidValidationError as exc:
        result["error_code"] = exc.code
        result["error_message"] = exc.message
        return result

    # 4. Enregistrer le TXID et passer en vérification
    db.update_order(order_id, txid=txid, status=OrderStatus.AWAITING_VERIFICATION)

    # 5. Verify the receipt with the provider selected when the order was made.
    verifier = (
        verify_bybit_payment
        if order.get("payment_method") == "bybit"
        else verify_payment
    )
    verification = verifier(
        txid, order["total_price"], CURRENCY, order.get("created_at")
    )

    if verification["status"] == "confirmed":
        verify_method = "bybit_txid" if order.get("payment_method") == "bybit" else "txid"
        result.update(_finalize_confirmed_payment(order_id, user_id, txid, verify_method))
    elif verification["status"] == "manual_review":
        reason = verification.get("reason", "Vérification TXID indisponible")
        db.update_order(
            order_id,
            status=OrderStatus.PENDING_PAYMENT,
            txid="",
            verify_method="txid_unavailable",
        )
        result["status"] = "failed"
        result["error_code"] = verification.get("code", "temporary_error")
        result["error_message"] = reason
        db.audit_event(
            "payment.verification_unavailable",
            actor_id=user_id,
            details={"order_id": order_id, "reason": reason},
        )
    else:
        # Vérification échouée
        reason = verification.get("reason", "Raison inconnue")
        db.update_order(
            order_id,
            status=OrderStatus.PENDING_PAYMENT,
            txid="",
            verify_method="txid_failed",
        )
        result["error_code"] = verification.get("code", "verification_failed")
        result["error_message"] = reason

        db.audit_event(
            "payment.verification_failed",
            actor_id=user_id,
            details={"order_id": order_id, "txid": txid, "reason": reason},
        )

    return result


def submit_onchain_payment(order_id: int, txid: str, user_id: int) -> dict[str, Any]:
    """Verify and finalize a BSC/Polygon USDT payment without admin approval."""
    try:
        txid = validate_txid_format(txid)
        check_txid_uniqueness(txid, order_id)
    except TxidValidationError as exc:
        return {"status": "failed", "error_code": exc.code, "error_message": exc.message}

    if db.get_conn().wallet_topups.find_one({"txid": txid}):
        return {
            "status": "failed", "error_code": "already_used",
            "error_message": "Ce TXID a déjà été utilisé pour un rechargement.",
        }

    order = db.get_order(order_id)
    if not order or order.get("user_id") != user_id:
        return {
            "status": "failed",
            "error_code": "not_owner",
            "error_message": "Commande introuvable ou non autorisée.",
        }
    if order.get("payment_method") not in {"usdt_bsc", "usdt_polygon"}:
        return {
            "status": "failed",
            "error_code": "wrong_payment_method",
            "error_message": "Cette commande n'utilise pas un paiement blockchain.",
        }
    if order.get("status") not in {
        OrderStatus.PENDING_PAYMENT,
        OrderStatus.AWAITING_VERIFICATION,
        OrderStatus.VERIFICATION_FAILED,
    }:
        return {
            "status": "failed",
            "error_code": "invalid_status",
            "error_message": "Cette commande ne peut plus recevoir de transaction.",
        }
    if order.get("expires_at") and order["expires_at"] < int(time.time()):
        from app.domain.order_service import expire_order
        expire_order(order_id)
        return {
            "status": "failed",
            "error_code": "expired",
            "error_message": "Cette commande a expiré.",
        }

    network_key = "bsc" if order["payment_method"] == "usdt_bsc" else "polygon"
    network = "BSC (BEP20)" if network_key == "bsc" else "Polygon"
    db.update_order(
        order_id,
        txid=txid,
        status=OrderStatus.AWAITING_VERIFICATION,
        verify_method=f"auto_{order['payment_method']}",
    )
    verification = verify_onchain_usdt(
        txid, network_key, order["total_price"], USDT_EVM_ADDRESS,
        order.get("created_at"),
    )
    if verification["status"] == "confirmed":
        claimed = db.claim_onchain_transaction(
            txid, network_key, user_id, "order", order_id, order["total_price"],
        )
        if not claimed:
            db.update_order(order_id, status=OrderStatus.PENDING_PAYMENT, txid="")
            return {
                "status": "failed", "error_code": "already_used",
                "error_message": "This transaction has already been used.",
            }
        result = _finalize_confirmed_payment(
            order_id, user_id, txid, f"auto_{order['payment_method']}",
        )
        result["network"] = network
        return result

    if verification["status"] == "pending":
        return {
            "status": "pending", "order": db.get_order(order_id), "network": network,
            "error_code": verification.get("code"),
            "error_message": verification.get("reason"),
        }

    db.update_order(
        order_id,
        status=OrderStatus.PENDING_PAYMENT,
        txid="",
        verify_method=f"failed_{order['payment_method']}",
    )
    db.audit_event(
        "payment.onchain_verification_failed",
        actor_id=user_id,
        details={
            "order_id": order_id, "txid": txid,
            "reason": verification.get("reason", ""),
        },
    )
    return {
        "status": "failed", "order": db.get_order(order_id), "network": network,
        "error_code": verification.get("code", "verification_failed"),
        "error_message": verification.get("reason", "On-chain verification failed."),
    }


def review_onchain_payment(
    order_id: int, admin_id: int, *, approved: bool,
) -> dict[str, Any]:
    """Atomically accept or reject one pending BSC/Polygon payment."""
    order_id = int(order_id)
    order = db.get_order(order_id)
    if not order or order.get("payment_method") not in {"usdt_bsc", "usdt_polygon"}:
        return {"status": "not_found", "order": order}
    if order.get("status") != OrderStatus.MANUAL_REVIEW:
        return {"status": "already_processed", "order": order}

    if not approved:
        now = int(time.time())
        updated = db.get_conn().orders.update_one(
            {
                "id": order_id,
                "status": OrderStatus.MANUAL_REVIEW,
                "payment_method": {"$in": ["usdt_bsc", "usdt_polygon"]},
            },
            {"$set": {
                "status": OrderStatus.VERIFICATION_FAILED,
                "verify_method": f"rejected_{order['payment_method']}",
                "reviewed_by": int(admin_id),
                "reviewed_at": now,
                "updated_at": now,
            }},
        )
        if updated.modified_count != 1:
            return {"status": "already_processed", "order": db.get_order(order_id)}
        db.audit_event(
            "payment.onchain_rejected",
            actor_id=admin_id,
            details={"order_id": order_id, "txid": order.get("txid", "")},
        )
        return {"status": "rejected", "order": db.get_order(order_id)}

    # _finalize_confirmed_payment performs an atomic paid transition and the
    # standard inventory/supplier delivery workflow.
    result = _finalize_confirmed_payment(
        order_id,
        int(order["user_id"]),
        str(order.get("txid") or ""),
        f"approved_{order['payment_method']}",
    )
    if result["status"] != "failed":
        db.get_conn().orders.update_one(
            {"id": order_id},
            {"$set": {
                "reviewed_by": int(admin_id),
                "reviewed_at": int(time.time()),
            }},
        )
        db.audit_event(
            "payment.onchain_approved",
            actor_id=admin_id,
            details={"order_id": order_id, "txid": order.get("txid", "")},
        )
        result["order"] = db.get_order(order_id)
    return result


# ---------------------------------------------------------------------------
# Confirmation manuelle (admin)
# ---------------------------------------------------------------------------

def confirm_payment_manual(order_id: int) -> bool:
    """Confirme manuellement le paiement d'une commande.

    Idempotent : ne fait rien si la commande est déjà payée.
    """
    order = db.get_order(order_id)
    if not order:
        return False

    if order["status"] in (OrderStatus.PAID, OrderStatus.PAYMENT_CONFIRMED, OrderStatus.DELIVERED):
        log.info("Commande #%d déjà confirmée, confirmation manuelle ignorée", order_id)
        return True  # idempotent

    if db.mark_order_paid(order_id, "manual"):
        db.audit_event(
            "payment.confirmed_manual",
            details={"order_id": order_id},
        )
        return True
    return False


def mark_manual_review(order_id: int, reason: str = "") -> bool:
    """Place une commande en revue manuelle."""
    conn = db.get_conn()
    result = conn.orders.update_one(
        {
            "id": order_id,
            "status": {"$in": [
                OrderStatus.AWAITING_VERIFICATION,
                OrderStatus.VERIFICATION_FAILED,
                OrderStatus.PENDING_PAYMENT,
            ]},
        },
        {
            "$set": {
                "status": OrderStatus.MANUAL_REVIEW,
                "admin_note": reason,
                "updated_at": int(time.time()),
            }
        },
    )
    if result.modified_count:
        db.audit_event("payment.manual_review", details={"order_id": order_id, "reason": reason})
        return True
    return False
