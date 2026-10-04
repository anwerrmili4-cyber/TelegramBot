"""Customer reviews for delivered Tunisian site orders.

A review stays pending until an admin publishes it. Public responses expose
the account name, the email, the score, the comment and the service mark.
They never include a phone number or a postal address.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime
from html import escape
from typing import Any

from pymongo.errors import DuplicateKeyError

import database as db
from app.constants import OrderStatus
from app.domain import email_service, site_logo_service

_PENDING = "pending"
_APPROVED = "approved"
_REJECTED = "rejected"


class ReviewError(ValueError):
    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


_TOKEN_TTL_SECONDS = 180 * 24 * 3600
_TOKEN_INVALID = "Ce lien d'avis n'est plus valable."


def _secret() -> bytes:
    for name in ("HP_WEBHOOK_SECRET", "HP_INVENTORY_KEY", "CRON_SECRET"):
        value = os.environ.get(name, "").strip()
        if value and value.upper() not in {"[SENSITIVE]", "SENSITIVE"}:
            return value.encode()
    return b"blackmarket-review-dev"


def issue_token(order_id: int, *, expires_at: int | None = None) -> str:
    """Signed token that lets the delivery email post one review for this order."""
    exp = int(expires_at if expires_at is not None else time.time() + _TOKEN_TTL_SECONDS)
    payload = f"{int(order_id)}.{exp}"
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{signature}"


def order_id_from_token(token: str) -> int:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise ReviewError(_TOKEN_INVALID)
    order_raw, exp_raw, signature = parts
    if not order_raw.isdigit() or not exp_raw.isdigit() or len(signature) != 32:
        raise ReviewError(_TOKEN_INVALID)
    try:
        bytes.fromhex(signature)
    except ValueError as exc:
        raise ReviewError(_TOKEN_INVALID) from exc
    if int(exp_raw) < int(time.time()):
        raise ReviewError(_TOKEN_INVALID)
    expected = hmac.new(_secret(), f"{order_raw}.{exp_raw}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        raise ReviewError(_TOKEN_INVALID)
    return int(order_raw)


def _stamp(value: Any) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp())
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ensure(conn: Any) -> None:
    conn.storefront_reviews.create_index("order_id", unique=True)
    conn.storefront_reviews.create_index([("status", 1), ("created_at", -1)])
    conn.storefront_review_requests.create_index("cart_reference", unique=True)


def _service_mark(offer_id: Any) -> dict[str, str]:
    """Small service identity for a published review. Empty when the offer is gone."""
    try:
        offer = db.get_offer(int(offer_id or 0))
    except (TypeError, ValueError):
        offer = None
    if not offer:
        return {"service_name": "", "service_logo_url": ""}
    service = db.get_service(int(offer.get("service_id") or 0))
    if not service:
        return {"service_name": "", "service_logo_url": ""}
    logo = ""
    if db.is_official_subscriptions_service(service):
        logo = site_logo_service.category_logo_url(
            offer.get("site_category_logo_id"),
            offer.get("site_category_logo_version"),
        ) or ""
    if not logo:
        logo = site_logo_service.logo_url(service)
    return {
        "service_name": str(service.get("name") or ""),
        "service_logo_url": logo,
    }


def _public(row: dict[str, Any]) -> dict[str, Any]:
    mark = _service_mark(row.get("offer_id"))
    return {
        "name": str(row.get("name") or ""),
        "email": str(row.get("email") or ""),
        "score": int(row.get("score") or 0),
        "comment": str(row.get("comment") or ""),
        "offer_name": str(row.get("offer_name") or ""),
        "service_name": mark["service_name"],
        "service_logo_url": mark["service_logo_url"],
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


def _store(order: dict[str, Any], score: int, comment: str, *, source: str) -> dict[str, Any]:
    order_id = int(order["id"])
    conn = db.get_conn()
    _ensure(conn)
    existing = conn.storefront_reviews.find_one({"order_id": order_id})
    if existing:
        return {"ok": True, "already": True, "review": _own(existing)}
    customer_id = int(order.get("customer_id") or 0)
    customer = conn.storefront_customers.find_one({"id": customer_id}) or {}
    now = int(time.time())
    document = {
        "id": db._next_id("storefront_reviews"),
        "order_id": order_id,
        "cart_reference": str(order.get("cart_reference") or ""),
        "offer_id": int(order.get("offer_id") or 0),
        "offer_name": str(order.get("offer_name") or ""),
        "customer_id": customer_id,
        "name": str(customer.get("name") or order.get("customer_name") or ""),
        "email": str(customer.get("email") or order.get("customer_email") or ""),
        "phone": str(customer.get("phone") or order.get("customer_phone") or ""),
        "score": score,
        "comment": comment,
        "source": source,
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
            return {"ok": True, "already": True, "review": _own(existing)}
        raise
    return {"ok": True, "already": False, "review": _own(document)}


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
    stored = _store(order, score, comment, source="account")
    return {"ok": True, "review": stored["review"]}


def submit_from_email(token: str, score: Any, comment: Any) -> dict[str, Any]:
    """Save a review posted from the delivery email. No shop login."""
    order_id = order_id_from_token(token)
    score = _score(score)
    comment = _comment(comment)
    order = db.get_conn().orders.find_one({
        "id": order_id,
        "sales_channel": "tn_site",
        "status": OrderStatus.DELIVERED,
    })
    if not order:
        raise ReviewError(_TOKEN_INVALID)
    stored = _store(order, score, comment, source="email")
    if stored["already"]:
        message = "Tu as déjà envoyé un avis pour cette commande."
    else:
        message = "Merci, ton avis a été envoyé. Il sera publié après validation."
    return {"ok": True, "already": stored["already"], "message": message}


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


def _client_dossier(row: dict[str, Any]) -> dict[str, Any]:
    """Everything the admin needs about the person who wrote the review."""
    conn = db.get_conn()
    customer_id = int(row.get("customer_id") or 0)
    customer = conn.storefront_customers.find_one({"id": customer_id}) or {}
    order = conn.orders.find_one({"id": int(row.get("order_id") or 0)}) or {}
    from app.domain import site_orders_service

    method = str(order.get("payment_method") or "")
    return {
        "customer_id": customer_id,
        "name": str(row.get("name") or customer.get("name") or order.get("customer_name") or ""),
        "email": str(row.get("email") or customer.get("email") or order.get("customer_email") or ""),
        "phone": str(row.get("phone") or customer.get("phone") or order.get("customer_phone") or ""),
        "email_verified": bool(customer.get("email_verified")),
        "customer_created_at": _stamp(customer.get("created_at")),
        "cart_reference": str(row.get("cart_reference") or order.get("cart_reference") or ""),
        "offer_id": int(row.get("offer_id") or order.get("offer_id") or 0),
        "offer_name": str(row.get("offer_name") or order.get("offer_name") or ""),
        "service_name": str(order.get("service_name") or ""),
        "payment_method": method,
        "payment_label": site_orders_service.method_label(method) if method else "",
        "line_total_millimes": int(order.get("total_millimes") or 0),
        "cart_total_millimes": int(order.get("cart_total_millimes") or order.get("total_millimes") or 0),
        "delivered_at": _stamp(order.get("delivered_at")),
        "source": str(row.get("source") or "account"),
    }


def admin_list() -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    items = []
    for row in conn.storefront_reviews.find().sort("created_at", -1).limit(100):
        dossier = _client_dossier(row)
        items.append({
            "id": int(row["id"]),
            "order_id": int(row["order_id"]),
            "score": int(row.get("score") or 0),
            "comment": str(row.get("comment") or ""),
            "status": str(row.get("status") or _PENDING),
            "admin_note": str(row.get("admin_note") or ""),
            "created_at": _stamp(row.get("created_at")),
            "published_at": _stamp(row.get("published_at")),
            **dossier,
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


def delete(review_id: int) -> dict[str, Any]:
    """Remove a review in any status. The public page stops showing it."""
    try:
        review_id = int(review_id)
    except (TypeError, ValueError) as exc:
        raise ReviewError("Avis introuvable.", status=404) from exc
    row = db.get_conn().storefront_reviews.find_one({"id": review_id})
    if not row:
        raise ReviewError("Avis introuvable.", status=404)
    db.get_conn().storefront_reviews.delete_one({"id": review_id})
    return {"ok": True, "id": review_id, "deleted": True}


def claim_delivery_review(reference: str) -> str:
    """Reserve the single review form of this cart and return its token.

    An empty string means the form was already reserved, or nothing delivered
    can be reviewed yet.
    """
    reference = str(reference or "").strip()
    if not reference:
        return ""
    conn = db.get_conn()
    _ensure(conn)
    if conn.storefront_review_requests.find_one({"cart_reference": reference}):
        return ""
    line = conn.orders.find_one({
        "cart_reference": reference,
        "sales_channel": "tn_site",
        "status": OrderStatus.DELIVERED,
    })
    if not line:
        return ""
    email = str(line.get("customer_email") or "").strip()
    if not email:
        return ""
    try:
        conn.storefront_review_requests.insert_one({
            "cart_reference": reference,
            "email": email,
            "order_id": int(line["id"]),
            "sent_at": int(time.time()),
        })
    except DuplicateKeyError:
        return ""
    return issue_token(int(line["id"]))


def notify_cart(reference: str) -> bool:
    """Email one standalone review form. A second call does not send again."""
    reference = str(reference or "").strip()
    token = claim_delivery_review(reference)
    if not token:
        return False
    line = db.get_conn().orders.find_one({
        "cart_reference": reference,
        "sales_channel": "tn_site",
        "status": OrderStatus.DELIVERED,
    })
    if not line:
        return False
    email_service.send_review_request(
        str(line.get("customer_email") or ""),
        str(line.get("customer_name") or ""),
        reference,
        token,
    )
    return True


def email_review_page(
    *,
    token: str = "",
    score: Any = "",
    comment: str = "",
    error: str = "",
    done: str = "",
) -> str:
    """Small page opened by the email form. It is not the shop."""
    try:
        selected = int(score)
    except (TypeError, ValueError):
        selected = 0
    if done:
        stars = email_service.review_stars_static(selected)
        return _review_page("Avis envoyé", f"{stars}<p>{escape(done)}</p>")
    if error and not str(token or "").strip():
        return _review_page("Avis", f'<p class="error">{escape(error)}</p>')
    try:
        order_id = order_id_from_token(token) if token else None
    except ReviewError as exc:
        return _review_page("Avis", f"<p>{escape(str(exc))}</p>")
    if order_id is None:
        return _review_page("Avis", f"<p>{escape(_TOKEN_INVALID)}</p>")
    existing = db.get_conn().storefront_reviews.find_one({"order_id": order_id})
    if existing and not error:
        return _review_page("Avis déjà envoyé", "<p>Tu as déjà envoyé un avis pour cette commande.</p>")
    alert = f'<p class="error">{escape(error)}</p>' if error else ""
    action = escape(f"{email_service.site_url()}{email_service.REVIEW_EMAIL_PATH}?token={token}")
    form = (
        f"{alert}"
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{escape(token)}">'
        '<input type="hidden" name="send" value="1">'
        f'<div class="bm-rate">{email_service.review_stars_html(selected)}</div>'
        f'<textarea class="bm-comment" name="comment" required minlength="8" maxlength="600" rows="5" '
        'placeholder="Ton commentaire" '
        'style="background-color:#ffffff;color:#1f1f1f;color-scheme:light;border:1px solid #dadce0">'
        f"{escape(comment)}</textarea>"
        '<button type="submit">Envoyer</button>'
        "</form>"
    )
    return _review_page(
        "Ton avis",
        "<p>Choisis tes étoiles, écris ton commentaire, puis appuie sur Envoyer. "
        "Rien n'est envoyé avant ce bouton.</p>" + form,
    )


def _review_page(title: str, inner: str) -> str:
    return (
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{escape(title)}</title>"
        f"{email_service.review_stars_css()}"
        "<style>"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#0b0b0d;color:#f4f4f5;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif}"
        "main{width:min(440px,calc(100% - 32px));background:#131316;border:1px solid #25252b;border-radius:20px;padding:28px}"
        "p{margin:0 0 16px;line-height:1.55;color:#c4c4cc}"
        ".error{color:#f87171}"
        "form{display:flex;flex-direction:column;gap:12px}"
        ".bm-rate{margin:0 0 4px}"
        "textarea{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid #dadce0;"
        "background:#ffffff;color:#1f1f1f;color-scheme:light;padding:12px 14px;font:inherit}"
        "button{border:0;border-radius:12px;background:#e03a30;color:#fff;font-weight:700;font-size:15px;"
        "padding:14px 18px;cursor:pointer}"
        "small{display:block;margin-top:18px;color:#8b8b95}"
        "</style></head><body><main>"
        f"<h1 style=\"margin:0 0 12px;font-size:24px\">{escape(title)}</h1>"
        f"{inner}<small>BLACKMARKET Tunisie</small></main></body></html>"
    )


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
