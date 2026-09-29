"""Admin handling of Tunisian storefront carts.

A storefront cart is stored as one order document per line, all sharing a
``cart_reference``. The admin always acts on the whole cart: the customer paid
one D17/Flouci total for it, so its lines are confirmed, delivered or cancelled
together, and the customer gets one email per step. Carts created before
checkout asked for an email simply get no email.
"""

from __future__ import annotations

import re
import time
from typing import Any

import database as db
from app.constants import OrderStatus
from app.domain import email_service

SALES_CHANNEL = "tn_site"

_TO_VERIFY = str(OrderStatus.MANUAL_REVIEW)
_CONFIRMED = {str(OrderStatus.PAYMENT_CONFIRMED), str(OrderStatus.PAID)}
_DELIVERED = str(OrderStatus.DELIVERED)
_CANCELLED = str(OrderStatus.CANCELLED)

STATUS_FILTERS: dict[str, list[str]] = {
    "to_verify": [_TO_VERIFY],
    "confirmed": sorted(_CONFIRMED),
    "delivered": [_DELIVERED],
    "cancelled": [_CANCELLED],
}

_MAX_SCANNED_LINES = 5000


class SiteOrderError(ValueError):
    """Raised with a French message the admin UI shows as-is."""


def _cart_status(lines: list[dict[str, Any]]) -> str:
    statuses = {str(line.get("status") or "") for line in lines}
    if statuses <= _CONFIRMED:
        return "confirmed"
    if statuses == {_TO_VERIFY}:
        return "to_verify"
    if statuses == {_DELIVERED}:
        return "delivered"
    if statuses == {_CANCELLED}:
        return "cancelled"
    return "mixed"


def _cart_summary(reference: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    lines = sorted(lines, key=lambda line: int(line.get("cart_position") or 0))
    first = lines[0]
    items = [
        {
            "order_id": int(line["id"]),
            "service_name": line.get("service_name", ""),
            "offer_name": line.get("offer_name", ""),
            "quantity": int(line.get("qty") or 1),
            "unit_millimes": int(line.get("unit_price_millimes") or 0),
            "total_millimes": int(line.get("total_millimes") or 0),
            "status": str(line.get("status") or ""),
        }
        for line in lines
    ]
    phone = str(first.get("customer_phone") or "")
    phone_digits = re.sub(r"\D", "", phone)
    return {
        "reference": reference,
        "status": _cart_status(lines),
        "customer_name": first.get("customer_name", ""),
        "customer_email": first.get("customer_email", ""),
        "customer_phone": phone,
        "customer_note": first.get("customer_note", ""),
        "whatsapp_url": f"https://wa.me/{phone_digits}" if phone_digits else "",
        "payment_method": first.get("payment_method", ""),
        "total_millimes": int(first.get("cart_total_millimes") or 0)
        or sum(item["total_millimes"] for item in items),
        "items": items,
        "created_at": min(int(line.get("created_at") or 0) for line in lines),
        "paid_at": first.get("paid_at"),
        "delivered_at": first.get("delivered_at"),
        "cancelled_at": first.get("cancelled_at"),
        "delivery_note": first.get("delivery_text", ""),
        "admin_note": first.get("admin_note", ""),
    }


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return str(values[0] or "").strip()


def _bounded(value: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def list_carts(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return storefront carts, newest first, with per-status counts."""
    status = _first(params, "status") or "to_verify"
    search = _first(params, "search")[:80]
    page = _bounded(_first(params, "page"), 1, 1, 10_000)
    per_page = _bounded(_first(params, "per_page"), 20, 1, 100)

    orders = db.get_conn().orders
    base: dict[str, Any] = {"sales_channel": SALES_CHANNEL, "cart_reference": {"$exists": True}}

    counts = {key: 0 for key in STATUS_FILTERS}
    seen: dict[str, set[str]] = {key: set() for key in STATUS_FILTERS}
    for row in orders.find(base, {"cart_reference": 1, "status": 1, "_id": 0}).limit(_MAX_SCANNED_LINES):
        for key, statuses in STATUS_FILTERS.items():
            if row.get("status") in statuses:
                seen[key].add(row["cart_reference"])
    for key in counts:
        counts[key] = len(seen[key])

    query = dict(base)
    if status in STATUS_FILTERS:
        query["status"] = {"$in": STATUS_FILTERS[status]}
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        digits = re.sub(r"\D", "", search)
        clauses: list[dict[str, Any]] = [
            {"cart_reference": pattern},
            {"customer_name": pattern},
            {"customer_email": pattern},
        ]
        if digits and not re.search(r"[^\d\s+().-]", search):
            clauses.append({"customer_phone": {"$regex": re.escape(digits)}})
        query["$or"] = clauses

    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in orders.find(query, {"_id": 0}).sort("created_at", -1).limit(_MAX_SCANNED_LINES):
        grouped.setdefault(line["cart_reference"], []).append(line)

    carts = [_cart_summary(reference, lines) for reference, lines in grouped.items()]
    carts.sort(key=lambda cart: cart["created_at"], reverse=True)
    total = len(carts)
    start = (page - 1) * per_page
    return {
        "ok": True,
        "items": carts[start : start + per_page],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, -(-total // per_page)),
        "counts": counts,
        "status": status,
    }


def _cart_lines(reference: str) -> list[dict[str, Any]]:
    reference = str(reference or "").strip().upper()
    if not reference:
        raise SiteOrderError("Référence de panier manquante.")
    lines = list(db.get_conn().orders.find({"sales_channel": SALES_CHANNEL, "cart_reference": reference}))
    if not lines:
        raise SiteOrderError(f"Panier {reference} introuvable.")
    return sorted(lines, key=lambda line: int(line.get("cart_position") or 0))


def _email_items(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "offer_name": line.get("offer_name", ""),
            "quantity": int(line.get("qty") or 1),
            "total_millimes": int(line.get("total_millimes") or 0),
        }
        for line in lines
    ]


def _cart_total(lines: list[dict[str, Any]]) -> int:
    return int(lines[0].get("cart_total_millimes") or 0) or sum(int(line.get("total_millimes") or 0) for line in lines)


def _restock(conn: Any, line: dict[str, Any]) -> None:
    if not line.get("offer_id") or line.get("is_preorder"):
        return
    offer = conn.offers.find_one({"id": line["offer_id"]}, {"unlimited_stock": 1}) or {}
    if not offer.get("unlimited_stock"):
        conn.offers.update_one({"id": line["offer_id"]}, {"$inc": {"stock": int(line.get("qty") or 1)}})


def confirm_cart(reference: str) -> dict[str, Any]:
    """Confirm the D17/Flouci payment of a cart and reserve its stock."""
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    if any(line.get("status") != _TO_VERIFY for line in lines):
        raise SiteOrderError(f"Le panier {reference} n'est plus en attente de vérification.")

    conn = db.get_conn()
    confirmed: list[dict[str, Any]] = []
    for line in lines:
        if db.mark_order_paid(int(line["id"]), "manual"):
            confirmed.append(line)
            continue
        for done in confirmed:
            conn.orders.update_one(
                {"id": done["id"], "status": {"$in": sorted(_CONFIRMED)}},
                {"$set": {"status": _TO_VERIFY, "paid_at": None, "verify_method": "", "updated_at": int(time.time())}},
            )
            _restock(conn, done)
        name = line.get("offer_name") or f"#{line['id']}"
        raise SiteOrderError(f"Stock insuffisant pour « {name} ». Le panier {reference} n'a pas été confirmé.")

    db.audit_event("site_cart.confirmed", details={"cart_reference": reference, "order_ids": [line["id"] for line in lines]})
    first = lines[0]
    email_service.send_payment_confirmed(
        first.get("customer_email", ""), first.get("customer_name", ""), reference, _email_items(lines), _cart_total(lines)
    )
    return {"reference": reference, "lines": len(lines)}


def deliver_cart(reference: str, note: str = "") -> dict[str, Any]:
    """Deliver a confirmed cart, emailing the admin's note (the access details) to the customer."""
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    if any(str(line.get("status")) not in _CONFIRMED for line in lines):
        raise SiteOrderError(f"Confirme d'abord le paiement du panier {reference}.")

    now = int(time.time())
    content = str(note or "").strip()[:2000]
    result = db.get_conn().orders.update_many(
        {"sales_channel": SALES_CHANNEL, "cart_reference": reference, "status": {"$in": sorted(_CONFIRMED)}},
        {"$set": {
            "status": _DELIVERED,
            "delivery_text": content or "Livré sur WhatsApp",
            "delivered_at": now,
            "updated_at": now,
        }},
    )
    db.audit_event("site_cart.delivered", details={"cart_reference": reference, "lines": result.modified_count})
    if result.modified_count:
        first = lines[0]
        email_service.send_order_delivered(
            first.get("customer_email", ""), first.get("customer_name", ""), reference, _email_items(lines), content
        )
    return {"reference": reference, "lines": result.modified_count}


def cancel_cart(reference: str, reason: str = "") -> dict[str, Any]:
    """Cancel a cart that is not delivered yet, returning any reserved stock."""
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    cancellable = {_TO_VERIFY, *_CONFIRMED}
    if any(str(line.get("status")) not in cancellable for line in lines):
        raise SiteOrderError(f"Le panier {reference} ne peut plus être annulé.")

    conn = db.get_conn()
    now = int(time.time())
    reason = str(reason or "").strip()[:2000]
    cancelled = 0
    for line in lines:
        result = conn.orders.update_one(
            {"id": line["id"], "status": line["status"]},
            {"$set": {"status": _CANCELLED, "cancelled_at": now, "updated_at": now, "admin_note": reason}},
        )
        if result.modified_count != 1:
            continue
        cancelled += 1
        if str(line["status"]) in _CONFIRMED:
            _restock(conn, line)

    db.audit_event("site_cart.cancelled", details={"cart_reference": reference, "lines": cancelled, "reason": reason})
    if cancelled:
        first = lines[0]
        email_service.send_order_cancelled(first.get("customer_email", ""), first.get("customer_name", ""), reference, reason)
    return {"reference": reference, "lines": cancelled}
