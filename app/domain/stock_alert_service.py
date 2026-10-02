"""Email a customer when a sold-out storefront product is back in stock.

A request is one address per product. Asking again while the request is still
waiting does not create a second email. The message goes out once, the first
time the offer has stock again.
"""

from __future__ import annotations

import time
from typing import Any

import database as db
from app.domain import email_service, storefront_auth_service, storefront_service

_MAX_WAITING = 20


def _listed(offer_id: int) -> dict[str, Any] | None:
    """The public catalog row, or nothing if the site does not sell this offer."""
    for service in storefront_service.catalog()["services"]:
        for offer in service["offers"]:
            if int(offer["id"]) == offer_id:
                return offer
    return None


def _in_stock(offer: dict[str, Any]) -> bool:
    return bool(offer.get("unlimited_stock")) or int(offer.get("stock") or 0) > 0


def subscribe(payload: dict[str, Any], token: Any = "") -> dict[str, Any]:
    """Remember an address until this product can be bought again."""
    if token:
        customer = storefront_auth_service.customer_for_token(token)
        email = str(customer["email"])
        name = str(customer.get("name") or "")
    else:
        email = storefront_auth_service._email(payload.get("email"))
        name = ""
    try:
        offer_id = int(payload.get("offer_id"))
    except (TypeError, ValueError) as exc:
        raise storefront_auth_service.AuthError("Ce produit est introuvable.", status=404) from exc

    listed = _listed(offer_id)
    if listed is None:
        raise storefront_auth_service.AuthError("Ce produit est introuvable.", status=404)
    if listed.get("available"):
        return {"ok": True, "already_available": True}

    conn = db.get_conn()
    waiting = conn.storefront_stock_alerts.count_documents({"email": email, "notified_at": None})
    existing = conn.storefront_stock_alerts.find_one({"offer_id": offer_id, "email": email, "notified_at": None})
    if existing is None and waiting >= _MAX_WAITING:
        raise storefront_auth_service.AuthError("Tu suis déjà beaucoup de produits. Réessaie plus tard.")
    now = int(time.time())
    conn.storefront_stock_alerts.update_one(
        {"offer_id": offer_id, "email": email, "notified_at": None},
        {"$setOnInsert": {"offer_id": offer_id, "email": email, "name": name, "created_at": now, "notified_at": None}},
        upsert=True,
    )
    return {"ok": True}


def release(offer_id: int) -> int:
    """Send the waiting emails if this offer can be bought right now."""
    conn = db.get_conn()
    pending = list(conn.storefront_stock_alerts.find({"offer_id": int(offer_id), "notified_at": None}))
    if not pending:
        return 0
    offer = db.get_offer(int(offer_id))
    if not offer or not _in_stock(offer):
        return 0
    listed = _listed(int(offer_id))
    if listed is None or not listed.get("available"):
        return 0
    link = f"{email_service.site_url()}/produit/{int(offer_id)}"
    name = str(listed.get("name") or offer.get("name") or "Ce produit")
    now = int(time.time())
    sent = 0
    for alert in pending:
        email_service.send_back_in_stock(str(alert.get("email") or ""), str(alert.get("name") or ""), name, link)
        conn.storefront_stock_alerts.update_one({"_id": alert["_id"]}, {"$set": {"notified_at": now}})
        sent += 1
    return sent
