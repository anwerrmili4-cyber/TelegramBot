"""Keep one live offer when several suppliers sell the same product.

A group is the same customer-facing product: the same name, the same
duration, and the same warranty. The supplier is not part of that match.
Stock wins over price. Among the offers that are still in stock, the lowest
client price (the price the customer pays, never the supplier cost) stays
active. The others are deactivated and kept, so an admin can still see them.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any

import database as db
from app.domain import warranty_service

log = logging.getLogger(__name__)

_state_lock = threading.Lock()
_reconcile_lock = threading.Lock()
_local = threading.local()
_batch_depth = 0
_batch_pending = False

_OFFER_FIELDS = {
    "id": 1,
    "service_id": 1,
    "name": 1,
    "price": 1,
    "stock": 1,
    "unlimited_stock": 1,
    "active": 1,
    "archived": 1,
    "supplier_provider": 1,
    "supplier_product_id": 1,
    "period_days": 1,
    "period_value": 1,
    "period_unit": 1,
    "warranty_days": 1,
    "warranty_value": 1,
    "warranty_unit": 1,
    "product_enabled": 1,
    "stock_enabled": 1,
    "local_copy_of_offer_id": 1,
    "stock_control_hold": 1,
    "feature_key": 1,
}


def normalize_product_name(value: Any) -> str:
    """Compare names ignoring case and repeated spaces."""
    return " ".join(str(value or "").split()).casefold()


def duration_days(offer: dict[str, Any] | None, kind: str) -> int:
    """Return the stored period or warranty as a number of days.

    ``period_value`` / ``warranty_value`` plus their unit is the duration the
    admin saved. Older rows that only have ``*_days`` use that count.
    """
    offer = offer or {}
    value = offer.get(f"{kind}_value")
    unit = offer.get(f"{kind}_unit")
    if value is None:
        value = offer.get(f"{kind}_days")
        unit = "days"
    elif not unit:
        unit = "days"
    try:
        return warranty_service.duration_to_days(value, unit)
    except (TypeError, ValueError):
        try:
            return max(0, int(offer.get(f"{kind}_days") or 0))
        except (TypeError, ValueError):
            return 0


def same_product_group_key(offer: dict[str, Any] | None) -> tuple[str, int, int] | None:
    """Identity of one product: name, duration, warranty. Supplier is ignored."""
    name = normalize_product_name((offer or {}).get("name"))
    if not name:
        return None
    return (name, duration_days(offer, "period"), duration_days(offer, "warranty"))


def client_price(offer: dict[str, Any] | None) -> float | None:
    """Price the customer pays. Supplier wholesale is never read."""
    try:
        price = float((offer or {}).get("price"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return round(price, 4)


def _unlimited(offer: dict[str, Any]) -> bool:
    value = offer.get("unlimited_stock")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value in (True, 1)


def _stock_count(offer: dict[str, Any]) -> int:
    try:
        return max(0, int(offer.get("stock") or 0))
    except (TypeError, ValueError):
        return 0


def offer_in_stock(offer: dict[str, Any] | None) -> bool:
    """True when the offer can still be sold from its saved stock fields.

    ``stock`` and ``unlimited_stock`` are the values already written from the
    supplier catalog or from local inventory. A missing count is not invented:
    it counts as zero. Stock tracking switched off cannot be sold.
    """
    if not isinstance(offer, dict) or not db.stock_is_enabled(offer):
        return False
    if _unlimited(offer):
        return True
    return _stock_count(offer) > 0


def is_held(offer: dict[str, Any] | None) -> bool:
    """True when this offer was parked in favour of another supplier."""
    return isinstance(offer, dict) and offer.get("stock_control_hold") is True


def _is_active(offer: dict[str, Any]) -> bool:
    return offer.get("active", 1) not in (0, False, "0", "false")


def _supplier_key(offer: dict[str, Any]) -> str:
    return str(offer.get("supplier_provider") or "").strip().casefold()


def _service_is_sellable(service: dict[str, Any] | None, *, missing_service: bool) -> bool:
    if missing_service:
        return False
    if service is None:
        return True
    return db.is_bot_visible(service)


@contextmanager
def batch():
    """Coalesce several stock or price writes into one reconciliation."""
    batch_enter()
    try:
        yield
    finally:
        batch_exit()


def batch_enter() -> None:
    global _batch_depth
    with _state_lock:
        _batch_depth += 1


def batch_exit() -> None:
    global _batch_depth, _batch_pending
    should_run = False
    with _state_lock:
        _batch_depth = max(0, _batch_depth - 1)
        if _batch_depth == 0 and _batch_pending:
            _batch_pending = False
            should_run = True
    if should_run:
        reconcile_same_product_offers()


def note_offer_listing_inputs_changed() -> None:
    """Run the switch after a stock or price change, unless a batch is open."""
    global _batch_pending
    if getattr(_local, "running", False):
        return
    with _state_lock:
        if _batch_depth:
            _batch_pending = True
            return
    reconcile_same_product_offers()


def reconcile_same_product_offers() -> dict[str, Any]:
    """Deactivate losing offers and activate the in-stock cheapest sibling."""
    if getattr(_local, "running", False):
        return {"groups": 0, "updated": 0, "activated": [], "deactivated": []}
    _local.running = True
    try:
        with _reconcile_lock:
            return _reconcile()
    finally:
        _local.running = False


def _published_by_offer(conn) -> dict[int, bool]:
    published: dict[int, bool] = {}
    for row in conn.reseller_products.find({}, {"local_offer_id": 1, "enabled": 1}):
        if row.get("local_offer_id") is None:
            continue
        try:
            offer_id = int(row["local_offer_id"])
        except (TypeError, ValueError):
            continue
        enabled = bool(row.get("enabled"))
        if offer_id in published:
            published[offer_id] = published[offer_id] and enabled
        else:
            published[offer_id] = enabled
    return published


def _candidate(offer: dict[str, Any], services: dict[int, dict[str, Any]], published: dict[int, bool]) -> bool:
    if offer.get("archived") == 1 or offer.get("local_copy_of_offer_id") or offer.get("feature_key"):
        return False
    if not _supplier_key(offer) or same_product_group_key(offer) is None:
        return False
    try:
        offer_id = int(offer["id"])
    except (TypeError, ValueError):
        return False
    if published.get(offer_id) is False:
        return False
    if offer.get("service_id") is None:
        return True
    try:
        service_id = int(offer["service_id"])
    except (TypeError, ValueError):
        return False
    return _service_is_sellable(services.get(service_id), missing_service=service_id not in services)


def _winner(offers: list[dict[str, Any]]) -> dict[str, Any] | None:
    available = [
        offer for offer in offers
        if db.product_is_enabled(offer) and offer_in_stock(offer) and client_price(offer) is not None
    ]
    if not available:
        return None

    def sort_key(offer: dict[str, Any]) -> tuple:
        price = client_price(offer) or 0
        # Same client price: keep the offer already on sale. If both are on
        # sale, keep the older row so a new duplicate does not replace it.
        already_listed = 0 if _is_active(offer) and not is_held(offer) else 1
        return (price, already_listed, int(offer["id"]))

    return min(available, key=sort_key)


def _apply(conn, offer: dict[str, Any], *, active: int, hold: bool) -> bool:
    current_hold = is_held(offer)
    if offer.get("active") == active and current_hold == hold:
        return False
    update: dict[str, Any] = {"$set": {"active": active}}
    if active == 1:
        update["$set"]["archived"] = 0
        update["$unset"] = {"archived_at": ""}
    if hold:
        update["$set"]["stock_control_hold"] = True
    else:
        update.setdefault("$unset", {})["stock_control_hold"] = ""
    conn.offers.update_one({"id": int(offer["id"])}, update)
    offer["active"] = active
    if hold:
        offer["stock_control_hold"] = True
    else:
        offer.pop("stock_control_hold", None)
    return True


def _reconcile() -> dict[str, Any]:
    conn = db.get_conn()
    offers = list(conn.offers.find({"archived": {"$ne": 1}}, _OFFER_FIELDS))
    services = {}
    for row in conn.services.find({}, {"id": 1, "active": 1, "archived": 1}):
        try:
            services[int(row["id"])] = row
        except (TypeError, ValueError):
            continue
    published = _published_by_offer(conn)
    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for offer in offers:
        if not _candidate(offer, services, published):
            continue
        key = same_product_group_key(offer)
        if key is not None:
            grouped[key].append(offer)

    qualifying_ids: set[int] = set()
    activated: list[int] = []
    deactivated: list[int] = []
    group_count = 0
    for members in grouped.values():
        suppliers = {_supplier_key(offer) for offer in members}
        if len(members) < 2 or len(suppliers) < 2:
            continue
        group_count += 1
        winner = _winner(members)
        winner_id = int(winner["id"]) if winner else None
        for offer in members:
            offer_id = int(offer["id"])
            qualifying_ids.add(offer_id)
            is_winner = offer_id == winner_id
            if not _apply(conn, offer, active=1 if is_winner else 0, hold=not is_winner):
                continue
            if is_winner:
                activated.append(offer_id)
            else:
                deactivated.append(offer_id)

    for offer in offers:
        if not _supplier_key(offer) or offer.get("local_copy_of_offer_id"):
            continue
        try:
            unpublished_id = int(offer["id"])
        except (TypeError, ValueError):
            continue
        if published.get(unpublished_id) is False and _apply(conn, offer, active=0, hold=False):
            deactivated.append(unpublished_id)

    for offer in offers:
        if not is_held(offer):
            continue
        try:
            offer_id = int(offer["id"])
        except (TypeError, ValueError):
            continue
        if offer_id in qualifying_ids:
            continue
        # The duplicate group is gone. A product the admin unpublished, or
        # switched off, stays inactive. Every other parked offer is listed again.
        published_offer = published.get(offer_id) is not False and db.product_is_enabled(offer)
        service_ok = True
        if offer.get("service_id") is not None:
            try:
                service_id = int(offer["service_id"])
            except (TypeError, ValueError):
                service_ok = False
            else:
                service_ok = _service_is_sellable(
                    services.get(service_id), missing_service=service_id not in services,
                )
        restore = published_offer and service_ok and not offer.get("feature_key")
        if _apply(conn, offer, active=1 if restore else 0, hold=False):
            if restore:
                activated.append(offer_id)
            else:
                deactivated.append(offer_id)

    updated = len(activated) + len(deactivated)
    if updated:
        log.info(
            "same-product stock control updated %s offer(s) across %s group(s)",
            updated,
            group_count,
        )
    return {
        "groups": group_count,
        "updated": updated,
        "activated": activated,
        "deactivated": deactivated,
    }
