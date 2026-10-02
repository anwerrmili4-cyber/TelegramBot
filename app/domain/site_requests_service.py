"""Support tickets, product requests and warranty claims opened on the site.

They share the bot's collections but carry ``channel: tn_site`` and a
storefront ``customer_id``. The bot workspace never lists them, and a reply
stays in the customer account instead of being sent on Telegram.
"""

from __future__ import annotations

import time
from typing import Any

import database as db
from app.constants import OrderStatus, TicketCategory, TicketStatus
from app.domain import storefront_receipt_service, support_service

SITE_CHANNEL = "tn_site"
MAX_WARRANTY_PROOFS = 3
_SUPPORT_CATEGORIES = {
    TicketCategory.PAYMENT,
    TicketCategory.DELIVERY,
    TicketCategory.ORDER,
    TicketCategory.OTHER,
    "catalog_request",
}


class SiteRequestError(ValueError):
    """French message safe to show to the customer or the admin UI."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _customer_lines(customer_id: int) -> list[dict[str, Any]]:
    return list(db.get_conn().orders.find({
        "sales_channel": SITE_CHANNEL,
        "customer_id": int(customer_id),
    }))


def _own_order(customer_id: int, order_id: int) -> dict[str, Any]:
    order = db.get_conn().orders.find_one({
        "id": int(order_id),
        "sales_channel": SITE_CHANNEL,
        "customer_id": int(customer_id),
    })
    if not order:
        raise SiteRequestError("Commande introuvable.")
    return order


def create_ticket(customer: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or "").strip()
    if len(message) < 8:
        raise SiteRequestError("Décris ta demande en quelques mots (8 caractères minimum).")
    category = str(payload.get("category") or TicketCategory.OTHER).strip()
    if category not in _SUPPORT_CATEGORIES:
        raise SiteRequestError("Catégorie inconnue.")
    order_id = None
    raw_order = payload.get("order_id")
    if raw_order not in (None, ""):
        try:
            order_id = int(raw_order)
        except (TypeError, ValueError) as exc:
            raise SiteRequestError("Commande invalide.") from exc
        _own_order(int(customer["id"]), order_id)
    ticket = support_service.create_ticket(
        0,
        message[:2000],
        category=category,
        order_id=order_id,
        channel=SITE_CHANNEL,
        customer_id=int(customer["id"]),
    )
    return {"ok": True, "ticket": _public_ticket(ticket)}


def reply_ticket(customer: dict[str, Any], ticket_id: Any, message: str) -> dict[str, Any]:
    """Append a customer follow-up. Closed threads stay closed, and nothing is sent on Telegram."""
    text = str(message or "").strip()
    if not text or len(text) > 2000:
        raise SiteRequestError("Écris un message (2 000 caractères maximum).")
    try:
        tid = int(ticket_id)
    except (TypeError, ValueError) as exc:
        raise SiteRequestError("Demande introuvable.", status=404) from exc
    ticket = db.get_conn().support_tickets.find_one({
        "id": tid,
        "channel": SITE_CHANNEL,
        "customer_id": int(customer["id"]),
    })
    if not ticket:
        raise SiteRequestError("Demande introuvable.", status=404)
    if str(ticket.get("status") or "") in {TicketStatus.CLOSED, TicketStatus.RESOLVED}:
        raise SiteRequestError("Cette conversation est fermée.")
    support_service.add_message(tid, 0, text, sender_type="client")
    updated = db.get_conn().support_tickets.find_one({"id": tid}) or ticket
    return {"ok": True, "ticket": _public_ticket(db._public(updated))}


def list_tickets(customer_id: int, *, category: str | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {"channel": SITE_CHANNEL, "customer_id": int(customer_id)}
    if category == "catalog_request":
        query["category"] = "catalog_request"
    else:
        query["category"] = {"$ne": "catalog_request"}
    rows = db.get_conn().support_tickets.find(query).sort("updated_at", -1).limit(50)
    return {"ok": True, "tickets": [_public_ticket(db._public(row)) for row in rows]}


def _public_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    messages = support_service.get_messages(int(ticket["id"]))
    return {
        "id": int(ticket["id"]),
        "category": ticket.get("category") or "",
        "status": ticket.get("status") or "",
        "order_id": ticket.get("order_id"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "messages": [
            {
                "id": int(message["id"]),
                "sender": "admin" if message.get("sender_type") == "admin" else "client",
                "content": message.get("content") or "",
                "created_at": message.get("created_at"),
            }
            for message in messages
        ],
    }


def _warranty_window_open(order: dict[str, Any]) -> bool:
    days = int(order.get("warranty_days") or 0)
    delivered_at = int(order.get("delivered_at") or 0)
    if str(order.get("status")) != OrderStatus.DELIVERED or days <= 0 or not delivered_at:
        return False
    return int(time.time()) <= delivered_at + days * 86400


def _warranty_proofs(customer_id: int, payload: dict[str, Any]) -> list[int]:
    raw = payload.get("proofs")
    if not isinstance(raw, list) or not raw:
        raise SiteRequestError("Ajoute au moins une preuve : une capture ou une photo du problème.")
    if len(raw) > MAX_WARRANTY_PROOFS:
        raise SiteRequestError(f"Tu peux joindre {MAX_WARRANTY_PROOFS} preuves au maximum.")
    proof_ids = []
    for item in raw:
        try:
            proof_ids.append(storefront_receipt_service.store(
                item, customer_id=customer_id, purpose="warranty",
            ))
        except storefront_receipt_service.ReceiptError as exc:
            message = str(exc).replace("reçu", "preuve").replace("Joins une capture de ton preuve", "Joins une preuve")
            raise SiteRequestError(message) from exc
    return proof_ids


def create_warranty(customer: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        order_id = int(payload.get("order_id"))
    except (TypeError, ValueError) as exc:
        raise SiteRequestError("Commande invalide.") from exc
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 8:
        raise SiteRequestError("Indique le problème rencontré (8 caractères minimum).")
    order = _own_order(int(customer["id"]), order_id)
    if not _warranty_window_open(order):
        raise SiteRequestError("La garantie de cette commande n'est plus ouverte.")
    existing = db.get_conn().warranty_requests.find_one({
        "order_id": order_id,
        "channel": SITE_CHANNEL,
    })
    if existing:
        raise SiteRequestError("Une demande de garantie existe déjà pour cette commande.")
    proof_ids = _warranty_proofs(int(customer["id"]), payload)
    delivered_at = int(order.get("delivered_at") or 0)
    days_used = max(0, (int(time.time()) - delivered_at) // 86400)
    warranty_days = int(order.get("warranty_days") or 0)
    remaining = max(0, warranty_days - days_used)
    total = int(order.get("total_millimes") or 0)
    refund_millimes = int(total * remaining / warranty_days) if warranty_days else 0
    request = db.create_warranty_request(
        0,
        order_id,
        days_used,
        0,
        reason[:1000],
        channel=SITE_CHANNEL,
        customer_id=int(customer["id"]),
        refund_millimes=refund_millimes,
        proof_ids=proof_ids,
    )
    return {"ok": True, "warranty": _public_warranty(request, order)}


def list_warranties(customer_id: int) -> dict[str, Any]:
    rows = db.get_conn().warranty_requests.find({
        "channel": SITE_CHANNEL,
        "customer_id": int(customer_id),
    }).sort("updated_at", -1).limit(50)
    orders = {
        int(order["id"]): order
        for order in _customer_lines(customer_id)
    }
    return {
        "ok": True,
        "warranties": [_public_warranty(db._public(row), orders.get(int(row.get("order_id") or 0), {})) for row in rows],
    }


def _public_warranty(request: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(request["id"]),
        "order_id": int(request.get("order_id") or 0),
        "offer_name": order.get("offer_name") or "",
        "status": request.get("status") or "",
        "reason": request.get("reason") or "",
        "admin_note": request.get("admin_note") or "",
        "refund_millimes": int(request.get("refund_millimes") or 0),
        "replacement": request.get("replacement_text") or "",
        "days_used": int(request.get("days_used") or 0),
        "proof_ids": [int(item) for item in request.get("proof_ids") or []],
        "created_at": request.get("created_at"),
        "updated_at": request.get("updated_at"),
    }


def warranty_flags(lines: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Map an order id to the warranty button state shown in the account."""
    order_ids = [int(line["id"]) for line in lines]
    if not order_ids:
        return {}
    requests = {
        int(row["order_id"]): row
        for row in db.get_conn().warranty_requests.find({
            "channel": SITE_CHANNEL,
            "order_id": {"$in": order_ids},
        })
    }
    flags = {}
    for line in lines:
        order_id = int(line["id"])
        request = requests.get(order_id)
        if request:
            flags[order_id] = {
                "warranty_open": False,
                "warranty_status": request.get("status") or "",
                "warranty_id": int(request["id"]),
                "replacement": request.get("replacement_text") or "",
                "warranty_note": request.get("admin_note") or "",
            }
        else:
            flags[order_id] = {
                "warranty_open": _warranty_window_open(line),
                "warranty_status": "",
                "warranty_id": None,
                "replacement": "",
                "warranty_note": "",
            }
    return flags
