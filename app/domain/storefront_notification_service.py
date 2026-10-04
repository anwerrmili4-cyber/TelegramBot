"""In-site notifications for verified Tunisian shop customers.

One document is the announcement. Read state is stored per customer. Nothing
is emailed: Courrier remains the only mail tool.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import database as db
from app.domain import email_service, storefront_service

log = logging.getLogger(__name__)

_MAX_AUDIENCE = 100
_KINDS = {
    "novelty": "Nouveauté",
    "admin": "Message",
    "news": "Actualité",
    "stock": "Stock",
    "price": "Prix",
    "balance": "Solde",
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


def _verified_people(conn: Any) -> list[dict[str, str]]:
    people = []
    for account in conn.storefront_customers.find({"email_verified": {"$ne": False}}):
        email = str(account.get("email") or "").strip()
        if email:
            people.append({"email": email, "name": str(account.get("name") or "")})
    return people


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
    customer_id = int(customer["id"])
    return list(
        conn.storefront_notifications.find({
            "created_at": {"$gte": since},
            "customer_id": {"$in": [None, 0, customer_id]},
        })
        .sort([("created_at", -1), ("id", -1)])
        .limit(50)
    )


def _item(row: dict[str, Any], read_ids: set[int], catalog_ids: set[int]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    offer_id = int(row.get("offer_id") or 0)
    if kind == "balance":
        href = "/mon-compte?onglet=portefeuille"
    elif kind in {"novelty", "stock", "price"} and offer_id in catalog_ids:
        href = f"/produit/{offer_id}"
    else:
        href = ""
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
    catalog_ids = _catalog_ids() if any(row.get("kind") in {"novelty", "stock", "price"} for row in rows) else set()
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


def _money(millimes: int) -> str:
    return f"{int(millimes) / 1000:.3f}".replace(".", ",") + " DT"


def _offer_on_site(offer_id: int) -> dict[str, Any] | None:
    offer = db.get_offer(int(offer_id))
    if not offer or not storefront_service._site_visible(offer):
        return None
    service = db.get_service(int(offer.get("service_id") or 0))
    if service and not storefront_service._site_visible(service):
        return None
    return offer


def _store(*, kind: str, title: str, body: str, offer_id: int = 0, customer_id: int = 0) -> None:
    conn = db.get_conn()
    _ensure(conn)
    conn.storefront_notifications.insert_one({
        "id": db._next_id("storefront_notifications"),
        "kind": kind,
        "title": title,
        "body": body,
        "created_at": int(time.time()),
        "audience": "customer" if customer_id else "verified",
        "audience_count": 1 if customer_id else 0,
        "offer_id": int(offer_id or 0),
        "customer_id": int(customer_id or 0),
    })


def announce_stock(offer_id: int, before: int, after: int) -> None:
    """Tell shoppers when a site product's stock changes, including the last unit."""
    try:
        before = int(before)
        after = int(after)
        offer = _offer_on_site(int(offer_id))
    except (TypeError, ValueError):
        return
    except Exception:
        log.exception("Storefront stock notification failed")
        return
    if not offer or before == after or after < 0:
        return
    name = str(offer.get("site_name") or offer.get("name") or "Ce produit")
    if after == 1:
        title, body = "Plus qu'un seul", f"Il ne reste qu'un exemplaire de {name}."
    elif after == 0:
        title, body = "Rupture de stock", f"{name} n'est plus en stock."
    elif before <= 0:
        title, body = "Retour en stock", f"{name} est de nouveau disponible : {after} en stock."
    else:
        title, body = "Stock mis à jour", f"{name} : {after} en stock."
    try:
        _store(kind="stock", title=title, body=body, offer_id=int(offer["id"]))
    except Exception:
        log.exception("Storefront stock notification failed")


def announce_price(offer_id: int, before: int, after: int) -> None:
    """Tell shoppers when the dinar price of a site product changes."""
    try:
        before = int(before or 0)
        after = int(after or 0)
        offer = _offer_on_site(int(offer_id))
    except (TypeError, ValueError):
        return
    except Exception:
        log.exception("Storefront price notification failed")
        return
    if not offer or before == after or after <= 0:
        return
    name = str(offer.get("site_name") or offer.get("name") or "Ce produit")
    shown = _money(after)
    body = f"{name} passe à {shown}." if before > 0 else f"{name} est proposé à {shown}."
    try:
        _store(kind="price", title="Prix mis à jour", body=body, offer_id=int(offer["id"]))
    except Exception:
        log.exception("Storefront price notification failed")


def announce_balance(customer_id: int, delta: int, balance_after: int) -> None:
    """Tell one customer that their wallet balance moved. No email is sent."""
    try:
        customer_id = int(customer_id)
        delta = int(delta)
        balance_after = int(balance_after)
    except (TypeError, ValueError):
        return
    if not customer_id or not delta:
        return
    if delta > 0:
        title = "Solde crédité"
        body = f"{_money(delta)} ont été ajoutés. Nouveau solde : {_money(balance_after)}."
    else:
        title = "Solde débité"
        body = f"{_money(abs(delta))} ont été retirés. Nouveau solde : {_money(balance_after)}."
    try:
        _store(kind="balance", title=title, body=body, customer_id=customer_id)
    except Exception:
        log.exception("Storefront balance notification failed")


def publish(form: dict[str, Any]) -> dict[str, Any]:
    """Publish one notification and email it to every verified site customer."""
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
    people = _verified_people(conn)
    audience = len(people)
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
    account_link = f"{email_service.site_url()}/mon-compte?onglet=notifications"
    product_link = f"{email_service.site_url()}/produit/{offer_id}" if kind == "novelty" and offer_id else ""
    for person in people:
        email_service.send_notification(
            person["email"],
            person["name"],
            _KINDS[kind],
            title,
            body,
            account_link,
            product_link,
        )
    noun = "client" if audience == 1 else "clients"
    return {"ok": True, "message": f"Notification publiée et envoyée par email à {audience} {noun}."}


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
