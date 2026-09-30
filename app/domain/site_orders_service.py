"""Admin handling of Tunisian storefront carts.

A storefront cart is stored as one order document per line, all sharing a
``cart_reference``. A cart is paid in one go, either from the customer's wallet
or by a D17/Flouci/IZI/Wafa Cash transfer whose receipt the admin verifies.

Once paid, each line is delivered from the shared inventory, or purchased from
the same reseller API the bot uses when the offer is linked to a supplier.
Lines without stock wait for the admin
to type the access details, which are emailed to the customer and shown in
their account. Cancelling a paid line refunds it to the customer's wallet.
"""

from __future__ import annotations

import re
import time
from typing import Any

import database as db
from app.constants import OrderStatus
from app.domain import (
    email_service,
    inventory_service,
    reseller_service,
    site_settings_service,
    storefront_invoice_service,
    storefront_wallet_service,
)

SALES_CHANNEL = "tn_site"
AUTOMATIC_DELIVERY = "[encrypted automatic delivery]"
WALLET_METHOD = "wallet"

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


def method_label(method: str) -> str:
    if method == WALLET_METHOD:
        return "Portefeuille"
    return site_settings_service.PAYMENT_METHOD_LABELS.get(method, method.upper())


def cart_status(lines: list[dict[str, Any]]) -> str:
    statuses = {str(line.get("status") or "") for line in lines}
    if statuses <= _CONFIRMED:
        return "confirmed"
    if statuses == {_TO_VERIFY}:
        return "to_verify"
    if statuses == {_DELIVERED}:
        return "delivered"
    if statuses == {_CANCELLED}:
        return "cancelled"
    # Paid carts where only some lines came out of inventory still need the admin.
    if statuses & _CONFIRMED and not statuses & {_TO_VERIFY}:
        return "partial"
    return "mixed"


def line_delivery(line: dict[str, Any], *, audit: bool = False) -> str:
    """The access details of a delivered line, decrypting inventory when needed."""
    return deliveries_for([line], audit=audit).get(int(line["id"]), "")


def deliveries_for(lines: list[dict[str, Any]], *, audit: bool = False) -> dict[int, str]:
    """Resolve delivery text for many lines with one inventory read."""
    result: dict[int, str] = {}
    automatic: list[int] = []
    for line in lines:
        if str(line.get("status") or "") != _DELIVERED:
            continue
        order_id = int(line["id"])
        text = str(line.get("delivery_text") or "")
        if text == AUTOMATIC_DELIVERY:
            automatic.append(order_id)
        else:
            result[order_id] = text
    if automatic:
        grouped = inventory_service.delivered_contents(automatic, audit=audit)
        for order_id in automatic:
            result[order_id] = "\n".join(grouped.get(order_id, []))
    return result


def _cart_summary(reference: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    lines = sorted(lines, key=lambda line: int(line.get("cart_position") or 0))
    first = lines[0]
    method = str(first.get("payment_method") or "")
    items = [
        {
            "order_id": int(line["id"]),
            "service_name": line.get("service_name", ""),
            "offer_name": line.get("offer_name", ""),
            "quantity": int(line.get("qty") or 1),
            "unit_millimes": int(line.get("unit_price_millimes") or 0),
            "total_millimes": int(line.get("total_millimes") or 0),
            "status": str(line.get("status") or ""),
            "automatic": line.get("delivery_text") == AUTOMATIC_DELIVERY,
            "delivery_note": ""
            if line.get("delivery_text") == AUTOMATIC_DELIVERY
            else str(line.get("delivery_text") or ""),
        }
        for line in lines
    ]
    return {
        "reference": reference,
        "status": cart_status(lines),
        "customer_id": first.get("customer_id"),
        "customer_name": first.get("customer_name", ""),
        "customer_email": first.get("customer_email", ""),
        "customer_phone": str(first.get("customer_phone") or ""),
        "customer_note": first.get("customer_note", ""),
        "payment_method": method,
        "payment_label": method_label(method),
        "transaction_reference": first.get("payment_reference", ""),
        "receipt_id": first.get("receipt_id"),
        "total_millimes": int(first.get("cart_total_millimes") or 0)
        or sum(item["total_millimes"] for item in items),
        "refunded_millimes": sum(int(line.get("refunded_millimes") or 0) for line in lines),
        "items": items,
        "created_at": min(int(line.get("created_at") or 0) for line in lines),
        "paid_at": first.get("paid_at"),
        "delivered_at": max((int(line.get("delivered_at") or 0) for line in lines), default=0) or None,
        "cancelled_at": first.get("cancelled_at"),
        "delivery_note": next((item["delivery_note"] for item in items if item["delivery_note"]), ""),
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
            {"payment_reference": pattern},
        ]
        if digits and not re.search(r"[^\d\s+().-]", search):
            clauses.append({"customer_phone": {"$regex": re.escape(digits)}})
        query["$or"] = clauses

    references: list[str] = []
    for line in orders.find(query, {"cart_reference": 1, "_id": 0}).sort("created_at", -1).limit(_MAX_SCANNED_LINES):
        if line["cart_reference"] not in references:
            references.append(line["cart_reference"])
    total = len(references)
    start = (page - 1) * per_page
    shown = references[start : start + per_page]

    # Every line of a shown cart, so a partly delivered cart displays whole.
    grouped: dict[str, list[dict[str, Any]]] = {reference: [] for reference in shown}
    for line in orders.find({**base, "cart_reference": {"$in": shown}}, {"_id": 0}):
        grouped[line["cart_reference"]].append(line)
    carts = [_cart_summary(reference, grouped[reference]) for reference in shown if grouped[reference]]
    invoices = storefront_invoice_service.numbers_for(shown)
    for cart in carts:
        cart["invoice_number"] = invoices.get(cart["reference"], "")
    return {
        "ok": True,
        "items": carts,
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


def _delivery_block(line: dict[str, Any], content: str) -> str:
    return f"{int(line.get('qty') or 1)} × {line.get('offer_name', '')}\n{content}".strip()


def mark_cart_paid(lines: list[dict[str, Any]], verify_method: str) -> list[dict[str, Any]]:
    """Mark every line paid and reserve stock; return the lines that could not be."""
    failed = []
    for line in lines:
        if not db.mark_order_paid(int(line["id"]), verify_method):
            failed.append(line)
    return failed


def fulfill_cart(reference: str) -> dict[str, Any]:
    """Deliver every paid line that has inventory, then email the customer.

    A line without inventory (manual stock, or none left) stays confirmed for
    the admin to deliver by hand.
    """
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    delivered: list[tuple[dict[str, Any], str]] = []
    for line in lines:
        if str(line.get("status")) not in _CONFIRMED:
            continue
        offer = db.get_offer(int(line.get("offer_id") or 0)) or {}
        if offer.get("supplier_provider"):
            try:
                values = reseller_service.fulfill_paid_order(int(line["id"]))
            except reseller_service.ResellerApiError:
                values = None
        else:
            values = inventory_service.deliver_for_order(int(line["id"]))
        if values:
            delivered.append((line, "\n".join(values)))

    first = lines[0]
    email, name = first.get("customer_email", ""), first.get("customer_name", "")
    waiting = [
        line for line in lines
        if str(line.get("status")) in _CONFIRMED and all(line is not done for done, _ in delivered)
    ]
    if delivered:
        email_service.send_order_delivered(
            email,
            name,
            reference,
            _email_items([line for line, _ in delivered]),
            "\n\n".join(_delivery_block(line, content) for line, content in delivered),
            remaining=len(waiting),
        )
    if waiting:
        email_service.send_payment_confirmed(email, name, reference, _email_items(waiting), _cart_total(lines))
    storefront_invoice_service.issue_quietly(reference)
    return {"reference": reference, "delivered": len(delivered), "waiting": len(waiting)}


def confirm_cart(reference: str) -> dict[str, Any]:
    """Confirm a transfer-paid cart after checking its receipt, then deliver what is in stock."""
    with db.coalesce_admin_notifications():
        return _confirm_cart(reference)


def _confirm_cart(reference: str) -> dict[str, Any]:
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
    result = fulfill_cart(reference)
    return {"reference": reference, "lines": len(lines), **result}


def deliver_cart(reference: str, note: str = "") -> dict[str, Any]:
    """Deliver the paid lines still waiting, sending the admin's access details to the customer."""
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    if any(str(line.get("status")) == _TO_VERIFY for line in lines):
        raise SiteOrderError(f"Confirme d'abord le paiement du panier {reference}.")
    waiting = [line for line in lines if str(line.get("status")) in _CONFIRMED]
    if not waiting:
        raise SiteOrderError(f"Le panier {reference} n'a plus rien à livrer.")
    content = str(note or "").strip()[:4000]
    if not content:
        raise SiteOrderError("Saisis les accès à livrer : le client les reçoit par email et dans son espace.")

    now = int(time.time())
    conn = db.get_conn()
    done = []
    for line in waiting:
        result = conn.orders.update_one(
            {"id": line["id"], "status": {"$in": sorted(_CONFIRMED)}},
            {"$set": {"status": _DELIVERED, "delivery_text": content, "delivered_at": now, "updated_at": now}},
        )
        if result.modified_count:
            done.append(line)
    db.audit_event("site_cart.delivered", details={"cart_reference": reference, "lines": len(done)})
    if done:
        first = lines[0]
        email_service.send_order_delivered(
            first.get("customer_email", ""), first.get("customer_name", ""), reference, _email_items(done), content
        )
    return {"reference": reference, "lines": len(done)}


def cancel_cart(reference: str, reason: str = "") -> dict[str, Any]:
    """Cancel every line not delivered yet; paid lines are refunded to the wallet."""
    lines = _cart_lines(reference)
    reference = lines[0]["cart_reference"]
    cancellable = {_TO_VERIFY, *_CONFIRMED}
    targets = [line for line in lines if str(line.get("status")) in cancellable]
    if not targets:
        raise SiteOrderError(f"Le panier {reference} ne peut plus être annulé.")

    conn = db.get_conn()
    now = int(time.time())
    reason = str(reason or "").strip()[:2000]
    customer_id = lines[0].get("customer_id")
    cancelled = 0
    refunded = 0
    for line in targets:
        paid = str(line["status"]) in _CONFIRMED
        refund = int(line.get("total_millimes") or 0) if paid and customer_id else 0
        result = conn.orders.update_one(
            {"id": line["id"], "status": line["status"]},
            {"$set": {
                "status": _CANCELLED,
                "cancelled_at": now,
                "updated_at": now,
                "admin_note": reason,
                "refunded_millimes": refund,
            }},
        )
        if result.modified_count != 1:
            continue
        cancelled += 1
        if paid:
            inventory_service.release_for_order(int(line["id"]))
            _restock(conn, line)
        if refund:
            storefront_wallet_service.credit(
                int(customer_id), refund, kind="refund", reference=reference, note=str(line.get("offer_name") or "")
            )
            refunded += refund
    storefront_invoice_service.record_refund(reference, refunded)

    db.audit_event(
        "site_cart.cancelled",
        details={"cart_reference": reference, "lines": cancelled, "reason": reason, "refunded_millimes": refunded},
    )
    if cancelled:
        first = lines[0]
        email_service.send_order_cancelled(
            first.get("customer_email", ""), first.get("customer_name", ""), reference, reason, refunded
        )
    return {"reference": reference, "lines": cancelled, "refunded_millimes": refunded}
