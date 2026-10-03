"""In-site notifications for verified Tunisian shop customers.

One document is the announcement. Read state is stored per customer. Nothing
is emailed: Courrier remains the only mail tool.
"""

from __future__ import annotations

import time
from typing import Any

import database as db
from app.domain import storefront_service

_MAX_AUDIENCE = 100
_KINDS = {
    "novelty": "Nouveauté",
    "admin": "Message",
    "news": "Actualité",
}


class NotificationError(ValueError):
    """French message safe to show in the admin panel or the shop."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _ensure(conn: Any) -> None:
    conn.storefront_notifications.create_index("id", unique=True)
    conn.storefront_notifications.create_index("created_at")
    conn.storefront_notification_reads.create_index(
        [("customer_id", 1), ("notification_id", 1)],
        unique=True,
    )


def _verified_count(conn: Any) -> int:
    count = 0
    for account in conn.storefront_customers.find({"email_verified": {"$ne": False}}, {"email": 1}):
        if str(account.get("email") or "").strip():
            count += 1
    return count


def _catalog_ids() -> set[int]:
    found: set[int] = set()
    for service in storefront_service.catalog()["services"]:
        for offer in service["offers"]:
            found.add(int(offer["id"]))
    return found


def _visible(conn: Any, customer: dict[str, Any]) -> list[dict[str, Any]]:
    if customer.get("email_verified") is False:
        return []
    since = int(customer.get("created_at") or 0)
    return list(
        conn.storefront_notifications.find({"created_at": {"$gte": since}})
        .sort([("created_at", -1), ("id", -1)])
        .limit(50)
    )


def _item(row: dict[str, Any], read_ids: set[int], catalog_ids: set[int]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    offer_id = int(row.get("offer_id") or 0)
    href = f"/produit/{offer_id}" if kind == "novelty" and offer_id in catalog_ids else ""
    return {
        "id": int(row["id"]),
        "kind": kind,
        "kind_label": _KINDS.get(kind, kind),
        "title": str(row.get("title") or ""),
        "body": str(row.get("body") or ""),
        "created_at": int(row.get("created_at") or 0),
        "read": int(row["id"]) in read_ids,
        "href": href,
    }


def for_customer(customer: dict[str, Any]) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    rows = _visible(conn, customer)
    read_ids = {
        int(mark["notification_id"])
        for mark in conn.storefront_notification_reads.find(
            {"customer_id": int(customer["id"])},
            {"notification_id": 1},
        )
    }
    catalog_ids = _catalog_ids() if any(row.get("kind") == "novelty" for row in rows) else set()
    items = [_item(row, read_ids, catalog_ids) for row in rows]
    return {"ok": True, "unread": sum(1 for item in items if not item["read"]), "items": items}


def _require_visible(customer: dict[str, Any], notification_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    for row in _visible(conn, customer):
        if int(row["id"]) == notification_id:
            return row
    raise NotificationError("Notification introuvable.", status=404)


def mark_read(customer: dict[str, Any], notification_id: Any) -> dict[str, Any]:
    try:
        notification_id = int(notification_id)
    except (TypeError, ValueError) as exc:
        raise NotificationError("Notification introuvable.", status=404) from exc
    _require_visible(customer, notification_id)
    conn = db.get_conn()
    conn.storefront_notification_reads.update_one(
        {"customer_id": int(customer["id"]), "notification_id": notification_id},
        {"$setOnInsert": {
            "customer_id": int(customer["id"]),
            "notification_id": notification_id,
            "read_at": int(time.time()),
        }},
        upsert=True,
    )
    return for_customer(customer)


def mark_all_read(customer: dict[str, Any]) -> dict[str, Any]:
    conn = db.get_conn()
    now = int(time.time())
    for row in _visible(conn, customer):
        conn.storefront_notification_reads.update_one(
            {"customer_id": int(customer["id"]), "notification_id": int(row["id"])},
            {"$setOnInsert": {
                "customer_id": int(customer["id"]),
                "notification_id": int(row["id"]),
                "read_at": now,
            }},
            upsert=True,
        )
    return for_customer(customer)


def publish(form: dict[str, Any]) -> dict[str, Any]:
    """Publish one notification for every verified site customer. No email is sent."""
    kind = str(form.get("kind") or "").strip()
    title = str(form.get("title") or "").strip()
    body = str(form.get("body") or form.get("message") or "").strip()
    if kind not in _KINDS:
        raise NotificationError("Choisis un type : nouveauté, message ou actualité.")
    if not 3 <= len(title) <= 120:
        raise NotificationError("Le titre doit faire entre 3 et 120 caractères.")
    if not 8 <= len(body) <= 2000:
        raise NotificationError("Le message doit faire entre 8 et 2 000 caractères.")

    offer_id = 0
    if kind == "novelty":
        try:
            offer_id = int(form.get("offer_id"))
        except (TypeError, ValueError) as exc:
            raise NotificationError("Choisis un produit du catalogue.") from exc
        if offer_id not in _catalog_ids():
            raise NotificationError("Ce produit n'est plus au catalogue.")

    conn = db.get_conn()
    _ensure(conn)
    audience = _verified_count(conn)
    if audience < 1:
        raise NotificationError("Aucun client vérifié pour le moment.")
    if audience > _MAX_AUDIENCE:
        raise NotificationError(f"{_MAX_AUDIENCE} clients maximum par publication.")

    conn.storefront_notifications.insert_one({
        "id": db._next_id("storefront_notifications"),
        "kind": kind,
        "title": title,
        "body": body,
        "created_at": int(time.time()),
        "audience": "verified",
        "audience_count": audience,
        "offer_id": offer_id,
    })
    noun = "client" if audience == 1 else "clients"
    return {"ok": True, "message": f"Notification publiée pour {audience} {noun}."}


def admin_list() -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    offers = []
    for service in storefront_service.catalog()["services"]:
        for offer in service["offers"]:
            offers.append({
                "id": int(offer["id"]),
                "name": str(offer.get("name") or ""),
                "service_name": str(offer.get("service_name") or ""),
            })
    offers.sort(key=lambda row: (row["service_name"].casefold(), row["name"].casefold()))
    items = []
    for row in conn.storefront_notifications.find().sort([("created_at", -1), ("id", -1)]).limit(50):
        kind = str(row.get("kind") or "")
        items.append({
            "id": int(row["id"]),
            "kind": kind,
            "kind_label": _KINDS.get(kind, kind),
            "title": str(row.get("title") or ""),
            "body": str(row.get("body") or ""),
            "created_at": int(row.get("created_at") or 0),
            "audience_count": int(row.get("audience_count") or 0),
        })
    return {"ok": True, "offers": offers, "items": items}
