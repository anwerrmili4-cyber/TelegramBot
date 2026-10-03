"""Customer reviews for delivered Tunisian site orders.

A review stays pending until an admin publishes it. Public responses expose
the account name, the score and the comment. They never include email, phone
or a postal address.
"""

from __future__ import annotations

import time
from typing import Any

from pymongo.errors import DuplicateKeyError

import database as db
from app.constants import OrderStatus
from app.domain import email_service

_PENDING = "pending"
_APPROVED = "approved"
_REJECTED = "rejected"


class ReviewError(ValueError):
    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _ensure(conn: Any) -> None:
    conn.storefront_reviews.create_index("order_id", unique=True)
    conn.storefront_reviews.create_index([("status", 1), ("created_at", -1)])
    conn.storefront_review_requests.create_index("cart_reference", unique=True)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(row.get("name") or ""),
        "score": int(row.get("score") or 0),
        "comment": str(row.get("comment") or ""),
        "offer_name": str(row.get("offer_name") or ""),
        "created_at": int(row.get("created_at") or 0),
    }


def _own(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": int(row["order_id"]),
        "status": str(row.get("status") or _PENDING),
        "score": int(row.get("score") or 0),
        "comment": str(row.get("comment") or ""),
    }


def _score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ReviewError("Choisis une note de 1 à 5.") from exc
    if score < 1 or score > 5:
        raise ReviewError("Choisis une note de 1 à 5.")
    return score


def _comment(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) < 8:
        raise ReviewError("Écris un commentaire (8 caractères minimum).")
    if len(text) > 600:
        raise ReviewError("Le commentaire fait 600 caractères maximum.")
    return text


def submit(customer: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        order_id = int(payload.get("order_id"))
    except (TypeError, ValueError) as exc:
        raise ReviewError("Commande introuvable.", status=404) from exc
    score = _score(payload.get("score"))
    comment = _comment(payload.get("comment"))
    order = db.get_conn().orders.find_one({
        "id": order_id,
        "sales_channel": "tn_site",
        "customer_id": int(customer["id"]),
        "status": OrderStatus.DELIVERED,
    })
    if not order:
        raise ReviewError("Commande introuvable.", status=404)
    conn = db.get_conn()
    _ensure(conn)
    existing = conn.storefront_reviews.find_one({"order_id": order_id})
    if existing:
        return {"ok": True, "review": _own(existing)}
    now = int(time.time())
    document = {
        "id": db._next_id("storefront_reviews"),
        "order_id": order_id,
        "offer_id": int(order.get("offer_id") or 0),
        "offer_name": str(order.get("offer_name") or ""),
        "customer_id": int(customer["id"]),
        "name": str(customer.get("name") or ""),
        "email": str(customer.get("email") or ""),
        "score": score,
        "comment": comment,
        "status": _PENDING,
        "admin_note": "",
        "created_at": now,
        "published_at": None,
    }
    try:
        conn.storefront_reviews.insert_one(document)
    except DuplicateKeyError:
        existing = conn.storefront_reviews.find_one({"order_id": order_id})
        if existing:
            return {"ok": True, "review": _own(existing)}
        raise
    return {"ok": True, "review": _own(document)}


def for_customer(customer_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    rows = conn.storefront_reviews.find({"customer_id": int(customer_id)}).sort("created_at", -1)
    return {"ok": True, "reviews": [_own(row) for row in rows]}


def public_for_offer(offer_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    try:
        offer_id = int(offer_id)
    except (TypeError, ValueError):
        offer_id = 0
    rows = list(
        conn.storefront_reviews.find({"offer_id": offer_id, "status": _APPROVED}).sort("created_at", -1).limit(20)
    )
    reviews = [_public(row) for row in rows]
    count = len(reviews)
    average = round(sum(item["score"] for item in reviews) / count, 1) if count else 0
    return {"ok": True, "average": average, "count": count, "reviews": reviews}


def public_latest() -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    rows = conn.storefront_reviews.find({"status": _APPROVED}).sort("created_at", -1).limit(12)
    return {"ok": True, "reviews": [_public(row) for row in rows]}


def admin_list() -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    items = []
    for row in conn.storefront_reviews.find().sort("created_at", -1).limit(100):
        items.append({
            "id": int(row["id"]),
            "order_id": int(row["order_id"]),
            "offer_name": str(row.get("offer_name") or ""),
            "name": str(row.get("name") or ""),
            "email": str(row.get("email") or ""),
            "score": int(row.get("score") or 0),
            "comment": str(row.get("comment") or ""),
            "status": str(row.get("status") or _PENDING),
            "admin_note": str(row.get("admin_note") or ""),
            "created_at": int(row.get("created_at") or 0),
        })
    return {"ok": True, "items": items}


def _pending(review_id: int) -> dict[str, Any]:
    try:
        review_id = int(review_id)
    except (TypeError, ValueError) as exc:
        raise ReviewError("Avis introuvable.", status=404) from exc
    row = db.get_conn().storefront_reviews.find_one({"id": review_id, "status": _PENDING})
    if not row:
        raise ReviewError("Cet avis n'est plus en attente.", status=404)
    return row


def approve(review_id: int) -> dict[str, Any]:
    row = _pending(review_id)
    conn = db.get_conn()
    customer = conn.storefront_customers.find_one({"id": int(row.get("customer_id") or 0)})
    name = str((customer or {}).get("name") or row.get("name") or "")
    conn.storefront_reviews.update_one(
        {"id": int(row["id"]), "status": _PENDING},
        {"$set": {"status": _APPROVED, "name": name, "published_at": int(time.time())}},
    )
    return {"ok": True, "id": int(row["id"]), "status": _APPROVED}


def reject(review_id: int, note: str) -> dict[str, Any]:
    text = str(note or "").strip()
    if len(text) < 3:
        raise ReviewError("Indique le motif du refus.")
    row = _pending(review_id)
    db.get_conn().storefront_reviews.update_one(
        {"id": int(row["id"]), "status": _PENDING},
        {"$set": {"status": _REJECTED, "admin_note": text[:400]}},
    )
    return {"ok": True, "id": int(row["id"]), "status": _REJECTED}


def notify_cart(reference: str) -> bool:
    """Email one review request for this cart. A second call does not send again."""
    reference = str(reference or "").strip()
    if not reference:
        return False
    conn = db.get_conn()
    _ensure(conn)
    if conn.storefront_review_requests.find_one({"cart_reference": reference}):
        return False
    line = conn.orders.find_one({
        "cart_reference": reference,
        "sales_channel": "tn_site",
        "status": OrderStatus.DELIVERED,
    })
    if not line:
        return False
    email = str(line.get("customer_email") or "").strip()
    if not email:
        return False
    try:
        conn.storefront_review_requests.insert_one({
            "cart_reference": reference,
            "email": email,
            "sent_at": int(time.time()),
        })
    except DuplicateKeyError:
        return False
    email_service.send_review_request(email, str(line.get("customer_name") or ""), reference)
    return True


def backfill(*, send: bool = False) -> dict[str, Any]:
    """Count review emails still owed. Send them only when ``send`` is true."""
    conn = db.get_conn()
    _ensure(conn)
    refs = conn.orders.distinct("cart_reference", {
        "sales_channel": "tn_site",
        "status": OrderStatus.DELIVERED,
        "cart_reference": {"$exists": True},
    })
    pending: list[str] = []
    for reference in refs:
        reference = str(reference or "").strip()
        if not reference or conn.storefront_review_requests.find_one({"cart_reference": reference}):
            continue
        line = conn.orders.find_one({"cart_reference": reference})
        if line and str(line.get("customer_email") or "").strip():
            pending.append(reference)
    sent = 0
    if send:
        for reference in pending:
            if notify_cart(reference):
                sent += 1
    return {"ok": True, "count": len(pending), "sent": sent}
