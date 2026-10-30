"""Advanced lookup used by the Telegram admin panel."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import database as db

SCOPES = ("all", "orders", "customers", "products", "tickets")
FIELDS = ("all", "order_id", "user_id", "txid", "product", "name", "message")
STATUSES = (
    "",
    "pending_payment",
    "paid",
    "payment_confirmed",
    "delivered",
    "manual_review",
    "cancelled",
)
_DATE_TOKEN = re.compile(r"^(?:du|au|from|to):(\d{4}-\d{2}-\d{2})$", re.I)
_LIMIT = 5


def search_filters(raw=None) -> dict[str, str]:
    """Keep only the filters the admin keyboard can set."""
    source = raw if isinstance(raw, dict) else {}
    scope = str(source.get("scope") or "all")
    field = str(source.get("field") or "all")
    status = str(source.get("status") or "")
    return {
        "scope": scope if scope in SCOPES else "all",
        "field": field if field in FIELDS else "all",
        "status": status if status in STATUSES else "",
    }


def parse_search_text(text: str) -> tuple[str, dict[str, str]]:
    """Split a typed lookup from optional ``du:`` and ``au:`` dates."""
    dates: dict[str, str] = {}
    words = []
    for token in str(text or "").split():
        match = _DATE_TOKEN.match(token)
        if not match:
            words.append(token)
            continue
        key = "date_from" if token.lower().startswith(("du:", "from:")) else "date_to"
        dates[key] = match.group(1)
    return " ".join(words).strip()[:120], dates


def _stamp(value: str, *, end: bool) -> int | None:
    try:
        moment = datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None
    if end:
        moment = moment.replace(hour=23, minute=59, second=59)
    return int(moment.timestamp())


def _pattern(query: str) -> dict[str, str]:
    return {"$regex": re.escape(query), "$options": "i"}


def _orders(query: str, field: str, status: str, dates: dict[str, str]) -> list[dict]:
    if field not in {"all", "order_id", "user_id", "txid", "product", "name"} and not dates and not status:
        return []
    if field not in {"all", "order_id", "user_id", "txid", "product", "name"}:
        return []
    clauses = []
    if query and field in {"all", "name", "product"}:
        pattern = _pattern(query)
        clauses.extend(({"offer_name": pattern}, {"service_name": pattern}))
    if query and field in {"all", "txid"}:
        clauses.append({"txid": _pattern(query)})
    if query.isdigit() and field in {"all", "order_id"}:
        clauses.append({"id": int(query)})
    if query.isdigit() and field in {"all", "user_id"}:
        clauses.append({"user_id": int(query)})
    if query and not clauses and not dates and not status:
        return []
    mongo: dict = {"sales_channel": {"$ne": "tn_site"}}
    if status:
        mongo["status"] = status
    created: dict[str, int] = {}
    start = _stamp(dates.get("date_from", ""), end=False)
    end = _stamp(dates.get("date_to", ""), end=True)
    if start is not None:
        created["$gte"] = start
    if end is not None:
        created["$lte"] = end
    if created:
        mongo["created_at"] = created
    if clauses:
        mongo["$or"] = clauses
    elif query:
        return []
    rows = db.get_conn().orders.find(mongo).sort("created_at", -1).limit(_LIMIT)
    return [db._public(row) for row in rows]


def _customers(query: str, field: str) -> list[dict]:
    if not query or field not in {"all", "user_id", "name"}:
        return []
    clauses = []
    pattern = _pattern(query)
    if field in {"all", "name", "user_id"}:
        clauses.append({"username": pattern})
    if field in {"all", "name"}:
        clauses.extend((
            {"first_name": pattern},
            {"last_name": pattern},
            {"full_name": pattern},
        ))
    if query.isdigit() and field in {"all", "user_id"}:
        clauses.append({"telegram_id": int(query)})
    if not clauses:
        return []
    rows = db.get_conn().users.find({"$or": clauses}).sort("telegram_id", -1).limit(_LIMIT)
    return [db._public(row) for row in rows]


def _products(query: str, field: str) -> list[dict]:
    if not query or field not in {"all", "product", "name"}:
        return []
    conn = db.get_conn()
    services = {
        int(row["id"]): row
        for row in conn.services.find({}, {"id": 1, "name": 1})
        if row.get("id") is not None
    }
    needle = query.casefold()
    items = []
    seen = set()
    for service_id, service in services.items():
        if needle in str(service.get("name") or "").casefold():
            items.append({
                "kind": "service",
                "id": service_id,
                "name": str(service.get("name") or f"Service #{service_id}"),
            })
            seen.add(("service", service_id))
    pattern = _pattern(query)
    service_ids = [
        service_id for service_id, service in services.items()
        if needle in str(service.get("name") or "").casefold()
    ]
    clauses = [
        {"name": pattern},
        {"supplier_provider": pattern},
        {"supplier_product_id": pattern},
    ]
    if service_ids:
        clauses.append({"service_id": {"$in": service_ids}})
    if query.isdigit():
        clauses.append({"id": int(query)})
    offers = conn.offers.find(
        {"archived": {"$ne": 1}, "$or": clauses},
    ).sort("id", 1).limit(_LIMIT)
    for offer in offers:
        offer_id = int(offer.get("id") or 0)
        if ("offer", offer_id) in seen:
            continue
        service = services.get(int(offer.get("service_id") or 0), {})
        items.append({
            "kind": "offer",
            "id": offer_id,
            "name": str(offer.get("name") or f"Offre #{offer_id}"),
            "service_name": str(service.get("name") or ""),
        })
        seen.add(("offer", offer_id))
        if len(items) >= _LIMIT:
            break
    return items[:_LIMIT]


def _tickets(query: str, field: str) -> list[dict]:
    if not query or field not in {"all", "message", "user_id"}:
        return []
    clauses = []
    pattern = _pattern(query)
    if field in {"all", "message"}:
        clauses.append({"message": pattern})
    if query.isdigit() and field == "all":
        clauses.append({"id": int(query)})
    if query.isdigit() and field in {"all", "user_id"}:
        clauses.append({"user_id": int(query)})
    if not clauses:
        return []
    rows = db.get_conn().support_tickets.find({
        "channel": {"$ne": "tn_site"},
        "$or": clauses,
    }).sort("updated_at", -1).limit(_LIMIT)
    return [db._public(row) for row in rows]


def search(text: str, *, scope: str = "all", field: str = "all", status: str = "") -> dict | None:
    """Return grouped admin results, or None when the message has nothing to find."""
    filters = search_filters({"scope": scope, "field": field, "status": status})
    query, dates = parse_search_text(text)
    if not query and not dates and not filters["status"]:
        return None
    selected = filters["scope"]
    groups = []
    if selected in {"all", "orders"}:
        groups.append({
            "key": "orders",
            "title": "Commandes",
            "items": _orders(query, filters["field"], filters["status"], dates),
        })
    if selected in {"all", "customers"} and query:
        groups.append({
            "key": "customers",
            "title": "Clients",
            "items": _customers(query, filters["field"]),
        })
    if selected in {"all", "products"} and query:
        groups.append({
            "key": "products",
            "title": "Produits",
            "items": _products(query, filters["field"]),
        })
    if selected in {"all", "tickets"} and query:
        groups.append({
            "key": "tickets",
            "title": "Tickets",
            "items": _tickets(query, filters["field"]),
        })
    return {
        "query": query,
        "dates": dates,
        "filters": filters,
        "groups": [group for group in groups if group["items"]],
    }


def customer_lookup(telegram_id: int) -> dict | None:
    """Return one Telegram customer and the latest bot orders."""
    try:
        user_id = int(telegram_id)
    except (TypeError, ValueError):
        return None
    user = db.get_conn().users.find_one({"telegram_id": user_id})
    if not user:
        return None
    orders = [
        db._public(row)
        for row in db.get_conn().orders.find({
            "user_id": user_id,
            "sales_channel": {"$ne": "tn_site"},
        }).sort("created_at", -1).limit(_LIMIT)
    ]
    return {"user": db._public(user), "orders": orders}
