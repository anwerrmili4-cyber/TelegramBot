"""Manual D17/Flouci payment verification through WhatsApp.

This module deliberately does not call a payment-provider API and never marks an
order as paid. It only records that proof must be reviewed by an administrator
and generates the customer-facing WhatsApp handoff.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import database as db
from app.constants import OrderStatus
from config import TN_MANUAL_PAYMENT_METHODS, TN_WHATSAPP_NUMBER


def normalize_method(method: str) -> str:
    value = str(method or "").strip().lower()
    if value not in TN_MANUAL_PAYMENT_METHODS:
        raise ValueError("Le moyen de paiement doit être D17 ou Flouci.")
    return value


def whatsapp_url(order: dict[str, Any], method: str) -> str:
    """Return a prefilled WhatsApp link without exposing internal credentials."""
    method = normalize_method(method)
    order_id = int(order["id"])
    amount_millimes = order.get("total_millimes")
    if amount_millimes is None:
        amount_millimes = order.get("tn_total_millimes")
    if amount_millimes is not None:
        amount = f"{int(amount_millimes) / 1000:.3f}".replace(".", ",")
        amount_line = f"\nMontant : {amount} DT"
    else:
        amount_line = ""
    message = (
        "Bonjour, je souhaite faire vérifier mon paiement "
        f"{method.upper()} pour la commande #{order_id}.{amount_line}\n"
        "Je joins le justificatif de paiement à ce message."
    )
    return f"https://wa.me/{TN_WHATSAPP_NUMBER}?text={quote(message)}"


def request_manual_review(order_id: int, method: str) -> dict[str, Any]:
    """Queue an order for human review and return its WhatsApp handoff.

    The transition is idempotent. Crucially, it does not confirm payment or
    reserve/decrement inventory; the existing administrator confirmation step
    remains the only way to mark the order as paid.
    """
    method = normalize_method(method)
    order = db.get_order(int(order_id))
    if not order:
        raise ValueError("Commande introuvable.")
    if order.get("status") not in {
        OrderStatus.PENDING_PAYMENT,
        OrderStatus.MANUAL_REVIEW,
    }:
        raise ValueError("Cette commande ne peut plus recevoir de justificatif.")

    now = int(time.time())
    result = db.get_conn().orders.update_one(
        {
            "id": int(order_id),
            "status": {"$in": [OrderStatus.PENDING_PAYMENT, OrderStatus.MANUAL_REVIEW]},
        },
        {
            "$set": {
                "payment_method": method,
                "status": OrderStatus.MANUAL_REVIEW,
                "verification_channel": "whatsapp",
                "verification_recipient": TN_WHATSAPP_NUMBER,
                "updated_at": now,
            }
        },
    )
    if result.modified_count:
        db.audit_event(
            "payment.manual_review_requested",
            actor_id=order.get("user_id"),
            details={"order_id": int(order_id), "method": method, "channel": "whatsapp"},
        )
    updated = db.get_order(int(order_id)) or order
    return {
        "order_id": int(order_id),
        "payment_method": method,
        "status": str(updated.get("status") or OrderStatus.MANUAL_REVIEW),
        "automatic_confirmation": False,
        "verification_channel": "whatsapp",
        "whatsapp_number": TN_WHATSAPP_NUMBER,
        "whatsapp_url": whatsapp_url(updated, method),
    }
