"""Saved products for a Tunisian site customer.

One row per account and product. Saving a product does not send an email.
"""

from __future__ import annotations

import time
from typing import Any

from pymongo.errors import DuplicateKeyError

import database as db
from app.domain import storefront_service

_MAX_FAVORITES = 40


class FavoriteError(ValueError):
    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _ensure(conn: Any) -> None:
    conn.storefront_favorites.create_index([("customer_id", 1), ("offer_id", 1)], unique=True)


def _catalog() -> dict[int, dict[str, Any]]:
    found: dict[int, dict[str, Any]] = {}
    for service in storefront_service.catalog()["services"]:
        for offer in service["offers"]:
            found[int(offer["id"])] = offer
    return found


def _snapshot(offer: dict[str, Any]) -> dict[str, Any]:
    return {
        "offer_name": str(offer.get("name") or ""),
        "service_name": str(offer.get("service_name") or ""),
        "price_millimes": int(offer.get("price_millimes") or 0),
        "service_logo_url": str(offer.get("service_logo_url") or ""),
        "image_url": str(offer.get("image_url") or ""),
        "period_days": int(offer.get("period_days") or 0),
        "warranty": str(offer.get("warranty") or ""),
        "delivery_delay": str(offer.get("delivery_delay") or ""),
        "description": str(offer.get("description") or "")[:1500],
        "remark": str(offer.get("remark") or "")[:400],
        "badge": str(offer.get("badge") or "")[:48],
        "stock": int(offer.get("stock") or 0),
        "available": bool(offer.get("available")),
    }


def _public(row: dict[str, Any], live: dict[str, Any] | None) -> dict[str, Any]:
    source = live or row
    return {
        "offer_id": int(row["offer_id"]),
        "saved_at": int(row.get("created_at") or 0),
        "in_catalog": live is not None,
        "name": str(source.get("name") or source.get("offer_name") or ""),
        "service_name": str(source.get("service_name") or ""),
        "price_millimes": int(source.get("price_millimes") or 0),
        "stock": int(source.get("stock") or 0) if live else int(row.get("stock") or 0),
        "available": bool(source.get("available")) if live else False,
        "period_days": int(source.get("period_days") or 0),
        "warranty": str(source.get("warranty") or ""),
        "delivery_delay": str(source.get("delivery_delay") or ""),
        "description": str(source.get("description") or ""),
        "remark": str(source.get("remark") or ""),
        "badge": str(source.get("badge") or ""),
        "service_logo_url": str(source.get("service_logo_url") or ""),
        "image_url": str(source.get("image_url") or ""),
    }


def for_customer(customer_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    live = _catalog()
    rows = conn.storefront_favorites.find({"customer_id": int(customer_id)}).sort("created_at", -1)
    return {"ok": True, "favorites": [_public(row, live.get(int(row["offer_id"]))) for row in rows]}


def set_saved(customer: dict[str, Any], offer_id: Any, saved: bool) -> dict[str, Any]:
    try:
        offer_id = int(offer_id)
    except (TypeError, ValueError) as exc:
        raise FavoriteError("Ce produit est introuvable.", status=404) from exc
    if saved:
        return _add(customer, offer_id)
    return _remove(int(customer["id"]), offer_id)


def _add(customer: dict[str, Any], offer_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    customer_id = int(customer["id"])
    existing = conn.storefront_favorites.find_one({"customer_id": customer_id, "offer_id": offer_id})
    live = _catalog()
    if existing:
        return {"ok": True, "saved": True, "emailed": False, "favorite": _public(existing, live.get(offer_id))}
    offer = live.get(offer_id)
    if not offer:
        raise FavoriteError("Ce produit est introuvable.", status=404)
    if not str(offer.get("description") or "").strip():
        raw = db.get_offer(offer_id) or {}
        offer = {
            **offer,
            "description": str(raw.get("site_description_fr") or raw.get("description") or "")[:1500],
        }
    waiting = conn.storefront_favorites.count_documents({"customer_id": customer_id})
    if waiting >= _MAX_FAVORITES:
        raise FavoriteError(f"{_MAX_FAVORITES} favoris maximum. Retires-en un pour en ajouter un autre.")
    now = int(time.time())
    row = {
        "id": db._next_id("storefront_favorites"),
        "customer_id": customer_id,
        "offer_id": offer_id,
        "created_at": now,
        **_snapshot(offer),
    }
    try:
        conn.storefront_favorites.insert_one(dict(row))
    except DuplicateKeyError:
        existing = conn.storefront_favorites.find_one({"customer_id": customer_id, "offer_id": offer_id}) or row
        return {"ok": True, "saved": True, "emailed": False, "favorite": _public(existing, offer)}
    return {"ok": True, "saved": True, "emailed": False, "favorite": _public(row, offer)}


def _remove(customer_id: int, offer_id: int) -> dict[str, Any]:
    conn = db.get_conn()
    _ensure(conn)
    conn.storefront_favorites.delete_one({"customer_id": customer_id, "offer_id": offer_id})
    return {"ok": True, "saved": False, "emailed": False}
