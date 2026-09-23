"""Read-only JSON queries used by the administration dashboard."""

from __future__ import annotations

import html
import re
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import DESCENDING

import database as db


def _admin_order(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose the full charged amount without changing payment-balance fields."""
    result = db._public(row)
    if result is not None:
        result["charged_total"] = db.order_charge_total(result)
    return result


def _telegram_description_plain_text(value: Any) -> str:
    """Return the visible Telegram description without formatting source."""
    rendered = str(value or "").strip()
    if not rendered:
        return ""
    rendered = re.sub(r"^\[\[?HTML\]?\]", "", rendered, flags=re.I)

    def custom_emoji_fallback(match: re.Match[str]) -> str:
        try:
            return bytes.fromhex(match.group(2)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""

    rendered = re.sub(
        r"\[\[TGEMOJI:([0-9A-Za-z_-]+):([0-9a-fA-F]+)\]\]",
        custom_emoji_fallback,
        rendered,
    )
    rendered = re.sub(r"<br\s*/?>", "\n", rendered, flags=re.I)
    rendered = re.sub(
        r"</(?:blockquote|div|p|pre)>\s*",
        "\n",
        rendered,
        flags=re.I,
    )
    rendered = re.sub(r"<[^>]+>", "", rendered)
    rendered = html.unescape(rendered).replace("\r\n", "\n").replace("\r", "\n")
    rendered = "\n".join(line.rstrip() for line in rendered.splitlines())
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def _order_product_description(
    order: dict[str, Any],
    offer: dict[str, Any] | None,
    language: str = "en",
) -> tuple[str, str]:
    """Resolve the description shown to the buyer, preferring the order snapshot."""
    snapshot = order.get("product_description_snapshot")
    if snapshot:
        return _telegram_description_plain_text(snapshot), "order_snapshot"
    source = (
        (offer or {}).get("description_ar")
        if language == "ar" and (offer or {}).get("description_ar")
        else (offer or {}).get("description")
    )
    return _telegram_description_plain_text(source), "current_catalog" if offer else "unavailable"


def _bounded_int(value: str | int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def list_orders(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return a filtered, paginated order collection."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}

    status = _first(params, "status")
    if status == "archived":
        query["archived_at"] = {"$exists": True}
    else:
        query["archived_at"] = {"$exists": False}
    if status and status != "archived":
        query["status"] = status
    queue = _first(params, "queue")
    if queue == "attention":
        delayed_before = int(time.time()) - 900
        query["$or"] = [
            {"status": {"$in": ["manual_review", "verification_failed", "stock_issue"]}},
            {"status": {"$in": ["paid", "payment_confirmed", "preparing_delivery"]}, "created_at": {"$lte": delayed_before}},
        ]
    elif queue == "delivery":
        query["status"] = {"$in": ["paid", "payment_confirmed", "preparing_delivery", "stock_issue"]}
    user_id = _first(params, "user_id")
    if user_id and user_id.isdigit():
        query["user_id"] = int(user_id)
    offer_id = _first(params, "offer_id")
    if offer_id and offer_id.isdigit():
        query["offer_id"] = int(offer_id)
    service_id = _first(params, "service_id")
    if service_id and service_id.isdigit():
        offer_ids = [row["id"] for row in db.get_conn().offers.find({"service_id": int(service_id)}, {"id": 1})]
        query["offer_id"] = {"$in": offer_ids}
    date_filter: dict[str, int] = {}
    for param_name, operator in (("date_from", "$gte"), ("date_to", "$lte")):
        raw = _first(params, param_name)
        if raw:
            with suppress(ValueError):
                date_filter[operator] = int(datetime.fromisoformat(raw).replace(tzinfo=UTC).timestamp())
    if date_filter:
        query["created_at"] = date_filter
    search = _first(params, "search")
    if search:
        field = _first(params, "search_field") or "all"
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = []
        if field in {"all", "name"}:
            clauses.extend(({"offer_name": pattern}, {"service_name": pattern}))
        if field in {"all", "txid"}:
            clauses.append({"txid": pattern})
        if search.isdigit() and field in {"all", "order_id"}:
            clauses.append({"id": int(search)})
        if search.isdigit() and field in {"all", "user_id"}:
            clauses.append({"user_id": int(search)})
        if "$or" in query:
            query["$and"] = [{"$or": query.pop("$or")}, {"$or": clauses}]
        else:
            query["$or"] = clauses

    collection = db.get_conn().orders
    total = collection.count_documents(query)
    sort_field = "total_price" if _first(params, "sort") == "amount" else "created_at"
    sort_direction = 1 if _first(params, "direction") == "asc" else DESCENDING
    if sort_field == "total_price":
        rows = collection.aggregate([
            {"$match": query},
            {"$addFields": {"charged_total": db.order_charge_total_expression()}},
            {"$sort": {"charged_total": sort_direction, "id": sort_direction}},
            {"$skip": (page - 1) * per_page},
            {"$limit": per_page},
        ])
    else:
        rows = collection.find(query).sort(sort_field, sort_direction).skip((page - 1) * per_page).limit(per_page)
    analytics_query = dict(query)
    analytics_query.pop("status", None)
    analytics = _order_analytics(collection, db.customer_order_query(analytics_query))
    items = [_admin_order(row) for row in rows]
    user_ids = {item.get("user_id") for item in items if item and item.get("user_id") is not None}
    users = {
        row["telegram_id"]: row
        for row in db.get_conn().users.find(
            {"telegram_id": {"$in": list(user_ids)}},
            {"telegram_id": 1, "username": 1, "first_name": 1, "last_name": 1, "full_name": 1, "lang": 1},
        )
    } if user_ids else {}
    offer_ids = {item.get("offer_id") for item in items if item and item.get("offer_id") is not None}
    offers = {
        row["id"]: row
        for row in db.get_conn().offers.find(
            {"id": {"$in": list(offer_ids)}},
            {"id": 1, "description": 1, "description_ar": 1},
        )
    } if offer_ids else {}
    now = int(time.time())
    urgent_statuses = {"manual_review", "verification_failed", "stock_issue"}
    delivery_statuses = {"paid", "payment_confirmed", "preparing_delivery"}
    for item in items:
        user = users.get(item.get("user_id"), {})
        first_name = str(user.get("first_name") or "").strip()
        last_name = str(user.get("last_name") or "").strip()
        full_name = str(user.get("full_name") or " ".join(filter(None, (first_name, last_name)))).strip()
        item["username"] = user.get("username") or item.get("username")
        item["first_name"] = first_name
        item["last_name"] = last_name
        item["full_name"] = full_name
        item["customer_name"] = full_name or (f"@{user['username']}" if user.get("username") else f"Client {item.get('user_id')}")
        if item.get("status") == "delivered":
            description, source = _order_product_description(
                item,
                offers.get(item.get("offer_id")),
                str(user.get("lang") or item.get("product_description_language") or "en"),
            )
            item["product_description"] = description
            item["product_description_source"] = source
        created_at = int(_event_timestamp(item.get("paid_at") or item.get("created_at")))
        age_seconds = max(0, now - created_at)
        delayed = item.get("status") in delivery_statuses and age_seconds >= 900
        item["age_seconds"] = age_seconds
        item["needs_attention"] = item.get("status") in urgent_statuses or delayed
        item["attention_reason"] = (
            "Livraison en retard" if delayed
            else "Intervention requise" if item.get("status") in urgent_statuses
            else ""
        )
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "analytics": analytics,
    }


def order_detail(order_id: int) -> dict[str, Any] | None:
    """Return every admin-facing field for one order, including delivered content."""
    conn = db.get_conn()
    order = conn.orders.find_one({"id": order_id})
    if not order:
        return None

    result = _admin_order(order)
    user = conn.users.find_one(
        {"telegram_id": order.get("user_id")},
        {"_id": 0, "telegram_id": 1, "username": 1, "first_name": 1, "last_name": 1, "full_name": 1, "lang": 1},
    ) or {}
    result["customer"] = db._public(user)
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    full_name = str(user.get("full_name") or " ".join(filter(None, (first_name, last_name)))).strip()
    result["customer_name"] = full_name or (f"@{user['username']}" if user.get("username") else f"Client {order.get('user_id')}")
    result["username"] = str(user.get("username") or "")
    result["delivery_content"] = _order_delivery_content(order)
    offer = conn.offers.find_one(
        {"id": order.get("offer_id")},
        {"_id": 0, "id": 1, "description": 1, "description_ar": 1},
    ) if order.get("offer_id") is not None else None
    description, source = _order_product_description(
        order,
        offer,
        str(user.get("lang") or order.get("product_description_language") or "en"),
    )
    result["product_description"] = description
    result["product_description_source"] = source
    return result


def _order_delivery_content(order: dict[str, Any]) -> str:
    """Resolve manual or encrypted inventory delivery for an authenticated admin."""
    stored = str(order.get("delivery_text") or "").strip()
    if stored and stored != "[encrypted automatic delivery]":
        return stored

    order_id = order.get("id")
    if order_id is None:
        return ""
    rows = list(db.get_conn().inventory.find({
        "$or": [
            {"delivered_order_id": order_id},
            {"order_id": order_id, "status": "sold"},
        ]
    }).sort("id", 1))
    if not rows:
        return ""
    cipher = db._fernet()
    values: list[str] = []
    for row in rows:
        payload = row.get("payload")
        if not payload:
            continue
        try:
            value = cipher.decrypt(str(payload).encode()).decode().strip()
        except Exception:
            continue
        if value:
            values.append(value)
    return "\n\n".join(values)


def _order_analytics(collection: Any, query: dict[str, Any]) -> dict[str, Any]:
    """Build compact global metrics for the React orders dashboard."""
    now = datetime.now(UTC)
    start = (now - timedelta(days=6)).date()
    days = {
        (start + timedelta(days=offset)).isoformat(): {"count": 0, "revenue": 0.0}
        for offset in range(7)
    }
    statuses: dict[str, int] = {}
    revenue = 0.0
    paid_statuses = {"paid", "payment_confirmed", "delivered"}
    pending_statuses = {"pending_payment", "awaiting_verification", "manual_review", "preparing_delivery"}
    delivered = pending = attention = 0

    for row in collection.find(query, {"status": 1, "total_price": 1, "wallet_amount": 1, "created_at": 1}):
        status = str(row.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        amount = db.order_charge_total(row)
        if status in paid_statuses:
            revenue += amount
        if status == "delivered":
            delivered += 1
        if status in pending_statuses:
            pending += 1
        try:
            created_timestamp = int(_event_timestamp(row.get("created_at")))
        except (TypeError, ValueError):
            created_timestamp = int(now.timestamp())
        if status in {"manual_review", "verification_failed", "stock_issue"} or (
            status in {"paid", "payment_confirmed", "preparing_delivery"}
            and int(now.timestamp()) - created_timestamp >= 900
        ):
            attention += 1

        created_at = row.get("created_at")
        try:
            created = (
                datetime.fromtimestamp(created_at, UTC)
                if isinstance(created_at, (int, float))
                else created_at.astimezone(UTC)
            )
            key = created.date().isoformat()
            if key in days:
                days[key]["count"] += 1
                if status in paid_statuses:
                    days[key]["revenue"] += amount
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            continue

    total = sum(statuses.values())
    return {
        "total": total,
        "revenue": round(revenue, 2),
        "delivered": delivered,
        "pending": pending,
        "attention": attention,
        "success_rate": round((delivered / total * 100) if total else 0, 1),
        "statuses": statuses,
        "daily": [
            {"date": key, "count": value["count"], "revenue": round(value["revenue"], 2)}
            for key, value in days.items()
        ],
    }


def finance_summary(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return customer revenue, reseller costs, profit, and one calendar month."""
    conn = db.get_conn()
    now = datetime.now(UTC)
    requested_month = _first(params, "month")
    try:
        month_start = datetime.strptime(requested_month, "%Y-%m").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.year < 2000 or month_start > now.replace(day=1) + timedelta(days=366):
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = month_start.replace(year=month_start.year + 1, month=1) if month_start.month == 12 else month_start.replace(month=month_start.month + 1)

    paid_statuses = {"paid", "payment_confirmed", "delivered"}
    orders = list(conn.orders.find(db.customer_order_query({})))
    orders_by_id = {row.get("id"): row for row in orders if row.get("id") is not None}
    product_costs = {
        (str(row.get("provider") or ""), str(row.get("product_id") or "")): float(row.get("wholesale_price") or 0)
        for row in conn.reseller_products.find({}, {"provider": 1, "product_id": 1, "wholesale_price": 1})
    }
    daily: dict[str, dict[str, Any]] = {}
    estimated_cost_orders = exact_cost_orders = unknown_cost_orders = 0

    def day_bucket(value: Any) -> dict[str, Any]:
        timestamp = _event_timestamp(value) or now.timestamp()
        day = datetime.fromtimestamp(timestamp, UTC).date().isoformat()
        return daily.setdefault(day, {"date": day, "revenue": 0.0, "cost": 0.0, "profit": 0.0, "orders": 0})

    for order in orders:
        if str(order.get("status") or "") in paid_statuses:
            bucket = day_bucket(order.get("created_at"))
            bucket["revenue"] += db.order_charge_total(order)
            bucket["orders"] += 1

    for fulfillment in conn.reseller_fulfillments.find({"status": {"$in": ["completed", "delivery_pending"]}}):
        order = orders_by_id.get(fulfillment.get("order_id"))
        if fulfillment.get("order_id") is not None and order is None:
            continue
        quantity = max(1, int(fulfillment.get("quantity") or (order or {}).get("qty") or 1))
        saved_total = fulfillment.get("purchase_cost_total")
        if saved_total is not None:
            cost = max(0.0, float(saved_total or 0))
            exact_cost_orders += 1
        else:
            key = (str(fulfillment.get("provider") or ""), str(fulfillment.get("supplier_product_id") or ""))
            if key in product_costs:
                cost = max(0.0, product_costs[key] * quantity)
                estimated_cost_orders += 1
            else:
                cost = 0.0
                unknown_cost_orders += 1
        day_bucket((order or {}).get("created_at") or fulfillment.get("created_at"))["cost"] += cost

    for bucket in daily.values():
        bucket["revenue"] = round(bucket["revenue"], 2)
        bucket["cost"] = round(bucket["cost"], 2)
        bucket["profit"] = round(bucket["revenue"] - bucket["cost"], 2)

    timestamps = []
    for collection in (conn.orders, conn.users, conn.reseller_fulfillments):
        first = collection.find_one({}, sort=[("created_at", 1)])
        if first and first.get("created_at") is not None:
            with suppress(TypeError, ValueError, OSError, OverflowError):
                timestamp = _event_timestamp(first["created_at"])
                if timestamp > 0:
                    timestamps.append(timestamp)
    started = datetime.fromtimestamp(min(timestamps), UTC) if timestamps else now
    elapsed_days = max(1, (now.date() - started.date()).days + 1)
    elapsed_weeks = max(1.0, elapsed_days / 7)
    total_revenue = round(sum(item["revenue"] for item in daily.values()), 2)
    total_cost = round(sum(item["cost"] for item in daily.values()), 2)
    total_profit = round(total_revenue - total_cost, 2)
    selected_days = []
    cursor = month_start
    while cursor < month_end:
        key = cursor.date().isoformat()
        selected_days.append(daily.get(key, {"date": key, "revenue": 0.0, "cost": 0.0, "profit": 0.0, "orders": 0}))
        cursor += timedelta(days=1)
    active_days = [item for item in daily.values() if item["revenue"] or item["cost"]]
    return {
        "currency": "USDT", "started_at": int(started.timestamp()), "month": month_start.strftime("%Y-%m"),
        "totals": {"revenue": total_revenue, "cost": total_cost, "profit": total_profit},
        "averages": {
            "daily_profit": round(total_profit / elapsed_days, 2), "weekly_profit": round(total_profit / elapsed_weeks, 2),
            "daily_revenue": round(total_revenue / elapsed_days, 2), "weekly_revenue": round(total_revenue / elapsed_weeks, 2),
        },
        "days": selected_days,
        "profitable_days": sum(1 for item in active_days if item["profit"] > 0),
        "loss_days": sum(1 for item in active_days if item["profit"] < 0),
        "cost_quality": {"exact": exact_cost_orders, "estimated": estimated_cost_orders, "unknown": unknown_cost_orders},
    }


def list_tickets(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return filtered, paginated support tickets."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    category = (_first(params, "category") or "").strip()[:64]
    if category:
        query["category"] = category
    user_id = _first(params, "user_id")
    if user_id and user_id.isdigit():
        query["user_id"] = int(user_id)
    scope_query = dict(query)
    status = _first(params, "status")
    if status:
        query["status"] = status
    search = _first(params, "search")
    if search:
        field = _first(params, "search_field") or "all"
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = []
        if field in {"all", "category"}:
            clauses.append({"category": pattern})
        if field in {"all", "message"}:
            clauses.append({"message": pattern})
        if search.isdigit() and field in {"all", "ticket_id"}:
            clauses.append({"id": int(search)})
        if search.isdigit() and field in {"all", "user_id"}:
            clauses.append({"user_id": int(search)})
        query["$or"] = clauses

    conn = db.get_conn()
    collection = conn.support_tickets
    total = collection.count_documents(query)
    summary = {
        "total": collection.count_documents(scope_query),
        "actionable": collection.count_documents({**scope_query, "status": {"$in": ["open", "waiting_admin"]}}),
        "waiting_admin": collection.count_documents({**scope_query, "status": "waiting_admin"}),
        "waiting_customer": collection.count_documents({**scope_query, "status": "waiting_customer"}),
        "completed": collection.count_documents({**scope_query, "status": {"$in": ["closed", "resolved"]}}),
    }
    rows = list(collection.find(query).sort("updated_at", DESCENDING).skip((page - 1) * per_page).limit(per_page))
    user_ids = {int(row["user_id"]) for row in rows if row.get("user_id") is not None}
    users = {
        int(user["telegram_id"]): user
        for user in conn.users.find(
            {"telegram_id": {"$in": list(user_ids)}},
            {"telegram_id": 1, "username": 1, "first_name": 1, "last_name": 1, "full_name": 1},
        )
    } if user_ids else {}
    items = []
    for row in rows:
        item = db._public(row)
        user = users.get(int(item.get("user_id") or 0), {})
        first_name = str(user.get("first_name") or "").strip()
        last_name = str(user.get("last_name") or "").strip()
        item["first_name"] = first_name
        item["last_name"] = last_name
        item["full_name"] = str(user.get("full_name") or " ".join(filter(None, (first_name, last_name)))).strip()
        item["username"] = str(user.get("username") or "").strip()
        items.append(item)
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "summary": summary,
    }


def inventory_summary() -> list[dict[str, Any]]:
    """Return inventory counters per offer without exposing secret payloads."""
    conn = db.get_conn()
    pipeline = [
        {"$group": {"_id": {"offer_id": "$offer_id", "status": "$status"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.offer_id": 1}},
    ]
    grouped: dict[int, dict[str, Any]] = {}
    for row in conn.inventory.aggregate(pipeline):
        offer_id = row["_id"]["offer_id"]
        entry = grouped.setdefault(offer_id, {"offer_id": offer_id, "available": 0, "reserved": 0, "delivered": 0, "disabled": 0})
        entry[row["_id"]["status"]] = row["count"]
    for entry in grouped.values():
        offer = conn.offers.find_one({"id": entry["offer_id"]}, {"name": 1})
        entry["offer_name"] = offer.get("name", "") if offer else ""
        entry["total"] = sum(entry.get(status, 0) for status in ("available", "reserved", "delivered", "disabled"))
    return list(grouped.values())


def list_inventory(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return masked inventory references with server-side filters."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    offer_id = _first(params, "offer_id")
    if offer_id and offer_id.isdigit():
        query["offer_id"] = int(offer_id)
    status = _first(params, "status")
    if status:
        query["status"] = status
    search = _first(params, "search")
    if search:
        field = _first(params, "search_field") or "all"
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = []
        if field in {"all", "preview"}:
            clauses.append({"masked_preview": pattern})
        if search.isdigit() and field in {"all", "reference_id"}:
            clauses.append({"id": int(search)})
        if search.isdigit() and field in {"all", "product_id"}:
            clauses.append({"offer_id": int(search)})
        if search.isdigit() and field in {"all", "order_id"}:
            clauses.extend(({"reserved_order_id": int(search)}, {"delivered_order_id": int(search)}))
        query["$or"] = clauses

    collection = db.get_conn().inventory
    total = collection.count_documents(query)
    projection = {"payload": 0, "fingerprint": 0}
    rows = collection.find(query, projection).sort("created_at", DESCENDING).skip((page - 1) * per_page).limit(per_page)
    items = []
    for row in rows:
        item = db._public(row)
        item["reference_id"] = item.get("id")
        items.append(item)
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


def list_customers(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return customer summaries with order and spending metrics."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    conn = db.get_conn()
    search = _first(params, "search")
    if search:
        field = _first(params, "search_field") or "all"
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = []
        if field in {"all", "username"}:
            clauses.append({"username": pattern})
        if field in {"all", "name"}:
            clauses.extend(({"first_name": pattern}, {"full_name": pattern}))
        if search.isdigit() and field in {"all", "telegram_id"}:
            clauses.append({"telegram_id": int(search)})
        query["$or"] = clauses
    status = _first(params, "status") or "all"
    if status == "active":
        query["banned"] = {"$ne": True}
    elif status == "banned":
        query["banned"] = True

    eligible_ids: set[int] | None = None
    all_user_ids = set(conn.users.distinct("telegram_id"))
    wallet_filter = _first(params, "wallet") or "all"
    if wallet_filter in {"funded", "empty"}:
        funded_ids = set(conn.wallets.distinct("user_id", {"balance_cents": {"$gt": 0}}))
        eligible_ids = funded_ids if wallet_filter == "funded" else all_user_ids - funded_ids

    orders_filter = _first(params, "orders") or "all"
    if orders_filter in {"with_orders", "without_orders"}:
        customer_ids = set(conn.orders.distinct("user_id"))
        order_ids = customer_ids if orders_filter == "with_orders" else all_user_ids - customer_ids
        eligible_ids = order_ids if eligible_ids is None else eligible_ids & order_ids
    if eligible_ids is not None:
        query["telegram_id"] = {"$in": list(eligible_ids)}

    collection = conn.users
    sort = _first(params, "sort") or "newest"
    if sort in {"balance", "spent", "orders"}:
        summaries = [_customer_summary(user) for user in collection.find(query)]
        sort_key = {
            "balance": "wallet_balance",
            "spent": "total_spent",
            "orders": "order_count",
        }[sort]
        summaries.sort(
            key=lambda item: (
                float(item.get(sort_key) or 0),
                int(item.get("telegram_id") or 0),
            ),
            reverse=True,
        )
        total = len(summaries)
        items = summaries[(page - 1) * per_page:page * per_page]
    else:
        total = collection.count_documents(query)
        direction = 1 if sort == "oldest" else DESCENDING
        users = collection.find(query).sort("created_at", direction).skip((page - 1) * per_page).limit(per_page)
        items = [_customer_summary(user) for user in users]
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


def customer_detail(user_id: int) -> dict[str, Any] | None:
    """Return one customer with their complete commercial and support history."""
    conn = db.get_conn()
    user = conn.users.find_one({"telegram_id": user_id})
    if not user:
        return None
    result = _customer_summary(user)

    orders = [
        _admin_order(row)
        for row in conn.orders.find({"user_id": user_id}).sort("created_at", DESCENDING)
    ]
    offer_ids = {int(row["offer_id"]) for row in orders if row.get("offer_id") is not None}
    offers = {
        int(row["id"]): row
        for row in conn.offers.find({"id": {"$in": list(offer_ids)}})
    } if offer_ids else {}
    for order in orders:
        offer = offers.get(int(order["offer_id"])) if order.get("offer_id") is not None else None
        description, source = _order_product_description(
            order,
            offer,
            str(user.get("lang") or order.get("product_description_language") or "en"),
        )
        order["product_description"] = description
        order["product_image_url"] = str((offer or {}).get("image_url") or "")
        order["product_description_source"] = source

    topups = []
    for row in conn.wallet_topups.find({"user_id": user_id}).sort("created_at", DESCENDING):
        item = db._public(row)
        item["amount"] = round(float(item.get("amount_cents") or 0) / 100, 2)
        item["status"] = item.get("status") or "confirmed"
        item["provider"] = item.get("provider") or item.get("network") or "unknown"
        topups.append(item)

    withdrawals = []
    for row in conn.withdrawals.find({"user_id": user_id}).sort("created_at", DESCENDING):
        item = db._public(row)
        item["amount"] = round(float(item.get("amount_cents") or 0) / 100, 2)
        withdrawals.append(item)

    tickets = [
        db._public(row)
        for row in conn.support_tickets.find({"user_id": user_id}).sort("updated_at", DESCENDING)
    ]
    warranties = [
        db._public(row)
        for row in conn.warranty_requests.find({"user_id": user_id}).sort("updated_at", DESCENDING)
    ]
    rewards = []
    for row in conn.affiliate_rewards.find({"referrer_id": user_id}).sort("created_at", DESCENDING):
        item = db._public(row)
        item["amount"] = round(float(item.get("amount_cents") or 0) / 100, 2)
        rewards.append(item)

    referrals = [
        db._public(row)
        for row in conn.referrals.find({"referrer_id": user_id}).sort("created_at", DESCENDING)
    ]
    referred_ids = [int(row["referred_id"]) for row in referrals if row.get("referred_id") is not None]
    referred_users = {
        int(row["telegram_id"]): db._public(row)
        for row in conn.users.find(
            {"telegram_id": {"$in": referred_ids}},
            {"telegram_id": 1, "username": 1, "first_name": 1, "full_name": 1},
        )
    } if referred_ids else {}
    for referral in referrals:
        referral["customer"] = referred_users.get(int(referral.get("referred_id") or 0), {})

    api_purchases = [
        db._public(row)
        for row in conn.buyer_api_purchases.find({"user_id": user_id}).sort("created_at", DESCENDING)
    ]
    wallet_adjustments = []
    for row in conn.audit_events.find({
        "action": "wallet.admin_adjustment",
        "details.user_id": user_id,
    }).sort("created_at", DESCENDING):
        item = db._public(row)
        details = dict(item.get("details") or {})
        details["amount"] = round(float(details.get("amount_cents") or 0) / 100, 2)
        details["balance"] = round(float(details.get("balance_cents") or 0) / 100, 2)
        item["details"] = details
        wallet_adjustments.append(item)

    interaction_total = conn.interaction_events.count_documents({"user_id": user_id})
    interactions = [
        db._public(row)
        for row in conn.interaction_events.find({"user_id": user_id})
        .sort("created_at", DESCENDING)
        .limit(100)
    ]

    timeline: list[dict[str, Any]] = []
    for order in orders:
        timeline.append({
            "type": "order", "id": order.get("id"), "created_at": order.get("created_at"),
            "title": order.get("offer_name") or order.get("service_name") or "Commande",
            "description": f"Commande #{order.get('id')}", "status": order.get("status"),
            "amount": order.get("charged_total"),
        })
    for topup in topups:
        timeline.append({
            "type": "topup", "id": topup.get("id"), "created_at": topup.get("created_at"),
            "title": "Dépôt portefeuille", "description": str(topup.get("provider") or ""),
            "status": topup.get("status"), "amount": topup.get("amount"),
        })
    for withdrawal in withdrawals:
        timeline.append({
            "type": "withdrawal", "id": withdrawal.get("id"), "created_at": withdrawal.get("created_at"),
            "title": "Retrait", "description": str(withdrawal.get("method") or ""),
            "status": withdrawal.get("status"), "amount": -float(withdrawal.get("amount") or 0),
        })
    for ticket in tickets:
        timeline.append({
            "type": "ticket", "id": ticket.get("id"),
            "created_at": ticket.get("updated_at") or ticket.get("created_at"),
            "title": f"Ticket #{ticket.get('id')}",
            "description": ticket.get("subject") or ticket.get("category") or ticket.get("message") or "Support",
            "status": ticket.get("status"),
        })
    for warranty in warranties:
        timeline.append({
            "type": "warranty", "id": warranty.get("id"),
            "created_at": warranty.get("updated_at") or warranty.get("created_at"),
            "title": f"Garantie commande #{warranty.get('order_id')}",
            "description": warranty.get("reason") or "Demande de garantie",
            "status": warranty.get("status"), "amount": warranty.get("refund_amount"),
        })
    for reward in rewards:
        timeline.append({
            "type": "reward", "id": reward.get("milestone"), "created_at": reward.get("created_at"),
            "title": "Récompense affiliation", "description": f"Palier {reward.get('milestone')}",
            "status": "confirmed", "amount": reward.get("amount"),
        })
    for adjustment in wallet_adjustments:
        details = adjustment.get("details") or {}
        timeline.append({
            "type": "adjustment", "id": adjustment.get("id"), "created_at": adjustment.get("created_at"),
            "title": "Ajustement administrateur", "description": details.get("reason") or "Sans motif",
            "status": "confirmed", "amount": details.get("amount"),
        })
    timeline.sort(key=lambda item: _event_timestamp(item.get("created_at")), reverse=True)

    result.update({
        "orders": orders,
        "topups": topups,
        "withdrawals": withdrawals,
        "tickets": tickets,
        "warranties": warranties,
        "referrals": referrals,
        "referral_count": len(referrals),
        "affiliate_rewards": rewards,
        "affiliate_earned": round(sum(float(row.get("amount") or 0) for row in rewards), 2),
        "loyalty": db._public(conn.loyalty.find_one({"user_id": user_id})) or {},
        "api_purchases": api_purchases,
        "wallet_adjustments": wallet_adjustments,
        "interactions": interactions,
        "interaction_total": interaction_total,
        "timeline": timeline,
        "deposit_total": round(sum(float(row.get("amount") or 0) for row in topups if row.get("status") == "confirmed"), 2),
        "withdrawal_total": round(sum(float(row.get("amount") or 0) for row in withdrawals if row.get("status") in {"approved", "paid", "completed"}), 2),
    })
    return result


def _event_timestamp(value: Any) -> float:
    """Normalize mixed MongoDB date formats for a stable CRM timeline."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).timestamp()
    if isinstance(value, str):
        with suppress(ValueError):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    return 0.0


def list_admin_notifications(limit: int = 100, complete: bool = False) -> dict[str, Any]:
    """Build a live, actionable notification feed from operational collections."""
    conn = db.get_conn()
    now = int(time.time())
    notifications: list[dict[str, Any]] = []
    user_cache: dict[int, str] = {}

    def customer_name(user_id: Any) -> str:
        try:
            parsed = int(user_id)
        except (TypeError, ValueError):
            return "Client inconnu"
        if parsed not in user_cache:
            user = conn.users.find_one(
                {"telegram_id": parsed},
                {"username": 1, "first_name": 1, "full_name": 1},
            ) or {}
            user_cache[parsed] = (
                f"@{user['username']}" if user.get("username")
                else str(user.get("full_name") or user.get("first_name") or f"Client {parsed}")
            )
        return user_cache[parsed]

    def add(
        notification_id: str,
        *,
        category: str,
        severity: str,
        title: str,
        message: str,
        page: str,
        created_at: Any,
        entity_id: Any = None,
        actionable: bool = True,
    ) -> None:
        notifications.append({
            "id": notification_id,
            "category": category,
            "severity": severity,
            "title": title,
            "message": message,
            "created_at": created_at,
            "actionable": actionable,
            "target": {"page": page, "entity_id": entity_id},
        })

    order_statuses = [
        "manual_review", "verification_failed", "paid", "payment_confirmed",
        "preparing_delivery", "stock_issue",
    ]
    for order in conn.orders.find({"status": {"$in": order_statuses}}).sort("created_at", DESCENDING).limit(0 if complete else 40):
        status = str(order.get("status") or "")
        order_id = order.get("id")
        age = max(0, now - int(_event_timestamp(order.get("paid_at") or order.get("created_at"))))
        delayed_delivery = status in {"paid", "payment_confirmed", "preparing_delivery"} and age >= 900
        severity = "error" if status in {"verification_failed", "stock_issue"} or delayed_delivery else "warning"
        title = "Livraison en retard" if delayed_delivery else (
            "Paiement à vérifier" if status in {"manual_review", "verification_failed"}
            else "Commande à finaliser"
        )
        add(
            f"order:{order_id}:{status}" + (":delayed" if delayed_delivery else ""),
            category="order", severity=severity, title=title,
            message=f"Commande #{order_id} · {customer_name(order.get('user_id'))} · {order.get('offer_name') or order.get('service_name') or 'Produit'}",
            page="orders", entity_id=order_id,
            created_at=order.get("updated_at") or order.get("paid_at") or order.get("created_at"),
        )

    for order in conn.orders.find({
        "status": "delivered",
        "created_at": {"$gte": now - 86400},
    }).sort("created_at", DESCENDING).limit(0 if complete else 12):
        order_id = order.get("id")
        add(
            f"order:{order_id}:delivered",
            category="sale", severity="success", title="Commande livrée",
            message=f"Commande #{order_id} · {customer_name(order.get('user_id'))} · {db.order_charge_total(order):.2f} USDT",
            page="orders", entity_id=order_id, created_at=order.get("created_at"), actionable=False,
        )

    for topup in conn.wallet_topups.find({"status": "manual_review"}).sort("created_at", DESCENDING).limit(0 if complete else 30):
        topup_id = topup.get("id")
        amount = float(topup.get("amount_cents") or 0) / 100
        add(
            f"topup:{topup_id}:manual_review",
            category="deposit", severity="warning", title="Dépôt à vérifier",
            message=f"{customer_name(topup.get('user_id'))} · {amount:.2f} {topup.get('currency') or 'USDT'} · {topup.get('network') or topup.get('provider') or 'paiement'}",
            page="deposits", entity_id=topup_id, created_at=topup.get("created_at"),
        )

    for topup in conn.wallet_topups.find({
        "$or": [{"status": "confirmed"}, {"status": {"$exists": False}}],
        "created_at": {"$gte": now - 86400},
    }).sort("created_at", DESCENDING).limit(0 if complete else 12):
        topup_id = topup.get("id") or topup.get("txid")
        amount = float(topup.get("amount_cents") or 0) / 100
        add(
            f"topup:{topup_id}:confirmed",
            category="deposit", severity="success", title="Dépôt confirmé",
            message=f"{customer_name(topup.get('user_id'))} · +{amount:.2f} {topup.get('currency') or 'USDT'}",
            page="deposits", entity_id=topup.get("id"), created_at=topup.get("created_at"), actionable=False,
        )

    for ticket in conn.support_tickets.find({"status": {"$in": ["open", "waiting_admin"]}}).sort("updated_at", DESCENDING).limit(0 if complete else 30):
        ticket_id = ticket.get("id")
        ticket_date = ticket.get("updated_at") or ticket.get("created_at")
        is_product_request = ticket.get("category") == "catalog_request"
        add(
            f"ticket:{ticket_id}:{ticket.get('status')}:{int(_event_timestamp(ticket_date))}",
            category="product_request" if is_product_request else "support",
            severity="warning",
            title="Nouveau produit demandé" if is_product_request else "Réponse client attendue",
            message=f"Ticket #{ticket_id} · {customer_name(ticket.get('user_id'))} · {ticket.get('subject') or ticket.get('category') or ticket.get('message') or 'Nouvelle demande'}",
            page="product-requests" if is_product_request else "support", entity_id=ticket_id,
            created_at=ticket_date,
        )

    for withdrawal in conn.withdrawals.find({"status": "pending"}).sort("created_at", DESCENDING).limit(0 if complete else 30):
        withdrawal_id = withdrawal.get("id")
        amount = float(withdrawal.get("amount_cents") or 0) / 100
        add(
            f"withdrawal:{withdrawal_id}:pending",
            category="withdrawal", severity="warning", title="Retrait en attente",
            message=f"{customer_name(withdrawal.get('user_id'))} · {amount:.2f} USDT · {withdrawal.get('method') or 'méthode non précisée'}",
            page="withdrawals", entity_id=withdrawal_id, created_at=withdrawal.get("created_at"),
        )

    pending_warranty_statuses = ["pending_admin_check", "pending", "waiting_admin"]
    for warranty in conn.warranty_requests.find({"status": {"$in": pending_warranty_statuses}}).sort("updated_at", DESCENDING).limit(0 if complete else 30):
        warranty_id = warranty.get("id")
        add(
            f"warranty:{warranty_id}:{warranty.get('status')}",
            category="warranty", severity="warning", title="Garantie à contrôler",
            message=f"Demande #{warranty_id} · commande #{warranty.get('order_id')} · {customer_name(warranty.get('user_id'))}",
            page="warranties", entity_id=warranty_id,
            created_at=warranty.get("updated_at") or warranty.get("created_at"),
        )

    from config import LOW_STOCK_THRESHOLD
    for offer in conn.offers.find({
        "active": 1,
        "stock": {"$lte": LOW_STOCK_THRESHOLD},
        "archived": {"$ne": 1},
    }).sort("stock", 1).limit(0 if complete else 30):
        offer_id = offer.get("id")
        stock = int(offer.get("stock") or 0)
        add(
            f"offer:{offer_id}:stock:{stock}",
            category="stock", severity="error" if stock <= 0 else "warning",
            title="Produit épuisé" if stock <= 0 else "Stock faible",
            message=f"{offer.get('name') or f'Produit #{offer_id}'} · {stock} unité(s) disponible(s)",
            page="inventory", entity_id=offer_id,
            created_at=offer.get("updated_at") or offer.get("created_at") or now,
        )

    for event in conn.audit_events.find({
        "action": {"$in": ["system.error", "webhook.error", "delivery.error"]},
        "created_at": {"$gte": datetime.fromtimestamp(max(0, now - 86400), UTC)},
    }).sort("created_at", DESCENDING).limit(0 if complete else 20):
        event_id = event.get("id")
        details = event.get("details") or {}
        add(
            f"error:{event_id}:{event.get('action')}",
            category="system", severity="error", title="Erreur système",
            message=str(details.get("message") or details.get("error") or event.get("action") or "Erreur à examiner"),
            page="activity", entity_id=event_id, created_at=event.get("created_at"),
        )

    priority = {"error": 0, "warning": 1, "success": 2, "info": 3}
    notifications.sort(key=lambda item: (
        priority.get(str(item.get("severity")), 4),
        -_event_timestamp(item.get("created_at")),
    ))
    if not complete:
        notifications = notifications[:max(1, min(int(limit), 200))]
    return {
        "items": notifications,
        "generated_at": now,
        "poll_after_seconds": 30,
        "summary": {
            "total": len(notifications),
            "critical": sum(1 for item in notifications if item["severity"] == "error"),
            "actionable": sum(1 for item in notifications if item["actionable"]),
            "information": sum(1 for item in notifications if not item["actionable"]),
        },
    }


def list_withdrawals(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return withdrawal requests with customer context and server-side filters."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    status = _first(params, "status")
    if status and status != "all":
        query["status"] = status
    search = _first(params, "search")
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = [
            {"method": pattern}, {"destination": pattern}, {"admin_note": pattern},
        ]
        if search.isdigit():
            clauses.extend(({"id": int(search)}, {"user_id": int(search)}))
        query["$or"] = clauses
    conn = db.get_conn()
    total = conn.withdrawals.count_documents(query)
    rows = conn.withdrawals.find(query).sort("created_at", DESCENDING).skip((page - 1) * per_page).limit(per_page)
    items = []
    for row in rows:
        item = db._public(row)
        user = conn.users.find_one({"telegram_id": int(item["user_id"])}) or {}
        item["amount"] = round(float(item.get("amount_cents") or 0) / 100, 2)
        item["username"] = user.get("username") or ""
        item["full_name"] = user.get("full_name") or user.get("first_name") or ""
        items.append(item)
    summary = {
        name: conn.withdrawals.count_documents({"status": name})
        for name in ("pending", "completed", "rejected")
    }
    summary["pending_amount"] = round(sum(
        float(row.get("amount_cents") or 0) / 100
        for row in conn.withdrawals.find({"status": "pending"}, {"amount_cents": 1})
    ), 2)
    return {"items": items, "page": page, "per_page": per_page, "total": total,
            "pages": max(1, (total + per_page - 1) // per_page), "summary": summary}


def list_warranties(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return warranty cases with their customer and order context."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    status = _first(params, "status")
    if status and status != "all":
        query["status"] = status
    search = _first(params, "search")
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        clauses: list[dict[str, Any]] = [{"reason": pattern}, {"admin_note": pattern}]
        if search.isdigit():
            clauses.extend(({"id": int(search)}, {"order_id": int(search)}, {"user_id": int(search)}))
        query["$or"] = clauses
    conn = db.get_conn()
    total = conn.warranty_requests.count_documents(query)
    rows = conn.warranty_requests.find(query).sort("updated_at", DESCENDING).skip((page - 1) * per_page).limit(per_page)
    items = []
    for row in rows:
        item = db._public(row)
        user = conn.users.find_one({"telegram_id": int(item["user_id"])}) or {}
        order = conn.orders.find_one({"id": int(item.get("order_id") or 0)}) or {}
        item["username"] = user.get("username") or ""
        item["full_name"] = user.get("full_name") or user.get("first_name") or ""
        item["product"] = order.get("offer_name") or order.get("service_name") or "Produit"
        item["order_status"] = order.get("status") or ""
        item["warranty"] = order.get("warranty") or order.get("warranty_days") or "NW"
        items.append(item)
    actionable = ["pending_admin_check", "accepted", "replacement_pending"]
    summary = {
        "actionable": conn.warranty_requests.count_documents({"status": {"$in": actionable}}),
        "pending": conn.warranty_requests.count_documents({"status": "pending_admin_check"}),
        "accepted": conn.warranty_requests.count_documents({"status": "accepted"}),
        "completed": conn.warranty_requests.count_documents({"status": {"$in": ["refunded", "replacement_delivered"]}}),
    }
    return {"items": items, "page": page, "per_page": per_page, "total": total,
            "pages": max(1, (total + per_page - 1) // per_page), "summary": summary}


def list_reseller_clients(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return safe reseller-API client profiles, keys, and purchase metrics."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    conn = db.get_conn()
    keys_by_user: dict[int, list[dict[str, Any]]] = {}
    for key in conn.buyer_api_keys.find({}).sort("created_at", DESCENDING):
        user_id = int(key["user_id"])
        keys_by_user.setdefault(user_id, []).append({
            "id": int(key["id"]),
            "prefix": str(key.get("prefix") or ""),
            "label": str(key.get("label") or "Buyer API"),
            "active": bool(key.get("active")),
            "created_at": key.get("created_at"),
            "last_used_at": key.get("last_used_at"),
            "revoked_at": key.get("revoked_at"),
        })

    cutoff = int(time.time()) - (30 * 24 * 60 * 60)
    summaries: list[dict[str, Any]] = []
    for user_id, keys in keys_by_user.items():
        user = conn.users.find_one({"telegram_id": user_id}) or {"telegram_id": user_id}
        wallet = conn.wallets.find_one({"user_id": user_id}) or {}
        purchases = list(
            conn.buyer_api_purchases.find({"user_id": user_id}).sort("created_at", DESCENDING)
        )
        successful = [row for row in purchases if (row.get("response") or {}).get("success") is True]
        failed = [row for row in purchases if (row.get("response") or {}).get("success") is False]
        pending = [row for row in purchases if not isinstance((row.get("response") or {}).get("success"), bool)]
        total_spent = sum(float((row.get("response") or {}).get("amount") or 0) for row in successful)
        spent_30d = sum(
            float((row.get("response") or {}).get("amount") or 0)
            for row in successful
            if int(row.get("created_at") or 0) >= cutoff
        )
        last_purchase_at = max((int(row.get("created_at") or 0) for row in purchases), default=0)
        last_key_use = max((int(key.get("last_used_at") or 0) for key in keys), default=0)
        recent_purchases = []
        for purchase in purchases[:10]:
            response = purchase.get("response") or {}
            recent_purchases.append({
                "order_id": purchase.get("order_id"),
                "idempotency_key": str(purchase.get("idempotency_key") or ""),
                "status": str(purchase.get("status") or response.get("status") or "unknown"),
                "success": response.get("success"),
                "product": str(response.get("productType") or ""),
                "quantity": int(response.get("quantity") or 0),
                "amount": round(float(response.get("amount") or 0), 2),
                "error_code": str(response.get("code") or ""),
                "created_at": purchase.get("created_at"),
            })
        summaries.append({
            "telegram_id": user_id,
            "username": str(user.get("username") or ""),
            "first_name": str(user.get("first_name") or ""),
            "full_name": str(user.get("full_name") or ""),
            "language": str(user.get("lang") or user.get("language") or ""),
            "joined_at": user.get("created_at"),
            "banned": bool(user.get("banned")),
            "wallet_balance": round(float(wallet.get("balance_cents") or 0) / 100, 2),
            "keys": keys,
            "key_count": len(keys),
            "active_key_count": sum(1 for key in keys if key["active"]),
            "api_order_count": len(successful),
            "failed_order_count": len(failed),
            "pending_order_count": len(pending),
            "total_spent": round(total_spent, 2),
            "spent_30d": round(spent_30d, 2),
            "last_activity_at": max(last_purchase_at, last_key_use) or None,
            "recent_purchases": recent_purchases,
        })

    global_summary = {
        "clients": len(summaries),
        "active_clients": sum(1 for item in summaries if item["active_key_count"]),
        "active_keys": sum(item["active_key_count"] for item in summaries),
        "api_orders": sum(item["api_order_count"] for item in summaries),
        "total_spent": round(sum(item["total_spent"] for item in summaries), 2),
        "spent_30d": round(sum(item["spent_30d"] for item in summaries), 2),
    }

    status = _first(params, "status") or "all"
    if status == "active":
        summaries = [item for item in summaries if item["active_key_count"] > 0]
    elif status == "revoked":
        summaries = [item for item in summaries if item["active_key_count"] == 0]
    search = _first(params, "search").lower()
    search_field = _first(params, "search_field") or "all"
    if search:
        def matches(item: dict[str, Any]) -> bool:
            values = {
                "name": f"{item['first_name']} {item['full_name']}",
                "username": item["username"],
                "telegram_id": str(item["telegram_id"]),
                "prefix": " ".join(key["prefix"] for key in item["keys"]),
            }
            haystack = " ".join(values.values()) if search_field == "all" else values.get(search_field, "")
            return search in haystack.lower()
        summaries = [item for item in summaries if matches(item)]

    sort = _first(params, "sort") or "activity"
    sort_key = {
        "spent": lambda item: (item["total_spent"], item["telegram_id"]),
        "orders": lambda item: (item["api_order_count"], item["telegram_id"]),
        "balance": lambda item: (item["wallet_balance"], item["telegram_id"]),
        "created": lambda item: (max((int(key.get("created_at") or 0) for key in item["keys"]), default=0), item["telegram_id"]),
        "activity": lambda item: (int(item["last_activity_at"] or 0), item["telegram_id"]),
    }.get(sort, lambda item: (int(item["last_activity_at"] or 0), item["telegram_id"]))
    summaries.sort(key=sort_key, reverse=True)
    total = len(summaries)
    return {
        "items": summaries[(page - 1) * per_page:page * per_page],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "summary": global_summary,
    }


def list_wallet_topups(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return the complete, filtered wallet-deposit history for every customer."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    status = _first(params, "status") or "all"
    provider = _first(params, "provider") or "all"
    query_parts: list[dict[str, Any]] = []
    if status == "confirmed":
        # Older Binance/Bybit deposits predate the explicit status field, but
        # they were only stored after successful verification and crediting.
        query_parts.append({"$or": [
            {"status": "confirmed"},
            {"status": {"$exists": False}},
        ]})
    elif status in {"manual_review", "rejected"}:
        query_parts.append({"status": status})
    if provider in {"binance", "bybit"}:
        query_parts.append({"provider": provider})
    elif provider in {"bsc", "polygon", "solana"}:
        query_parts.append({"network": provider})

    conn = db.get_conn()
    search = _first(params, "search")
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        search_field = _first(params, "search_field") or "all"
        clauses: list[dict[str, Any]] = []
        if search_field in {"all", "txid"}:
            clauses.append({"txid": pattern})
        if search_field in {"all", "provider"}:
            clauses.extend(({"network": pattern}, {"provider": pattern}))
        if search.isdigit() and search_field in {"all", "deposit_id"}:
            clauses.append({"id": int(search)})
        if search.isdigit() and search_field in {"all", "user_id"}:
            clauses.append({"user_id": int(search)})
        if search_field in {"all", "customer"}:
            user_ids = list(conn.users.distinct("telegram_id", {"$or": [
                {"username": pattern},
                {"first_name": pattern},
                {"full_name": pattern},
            ]}))
            if user_ids:
                clauses.append({"user_id": {"$in": user_ids}})
        if clauses:
            query_parts.append({"$or": clauses})

    query: dict[str, Any] = {"$and": query_parts} if query_parts else {}
    collection = conn.wallet_topups
    total = collection.count_documents(query)
    sort_field = "amount_cents" if _first(params, "sort") == "amount" else "created_at"
    direction = 1 if _first(params, "direction") == "asc" else DESCENDING
    rows = (
        collection.find(query)
        .sort([(sort_field, direction), ("_id", direction)])
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    items = []
    for row in rows:
        item = db._public(row)
        user = conn.users.find_one(
            {"telegram_id": int(item["user_id"])},
            {"username": 1, "first_name": 1},
        ) or {}
        item["username"] = user.get("username") or ""
        item["first_name"] = user.get("first_name") or ""
        item["full_name"] = user.get("full_name") or ""
        item["amount"] = round(float(item.get("amount_cents") or 0) / 100, 2)
        item["status"] = item.get("status") or "confirmed"
        item["provider"] = item.get("provider") or item.get("network") or "unknown"
        txid = str(item.get("txid") or "")
        explorer = {
            "bsc": "https://bscscan.com/tx/",
            "polygon": "https://polygonscan.com/tx/",
            "solana": "https://solscan.io/tx/",
        }.get(item.get("network"))
        item["explorer_url"] = f"{explorer}{txid}" if explorer and txid else ""
        items.append(item)

    summary = {"count": 0, "confirmed": 0, "manual_review": 0, "rejected": 0, "confirmed_amount": 0.0}
    for row in collection.find(query, {"status": 1, "amount_cents": 1}):
        row_status = str(row.get("status") or "confirmed")
        summary["count"] += 1
        if row_status in {"confirmed", "manual_review", "rejected"}:
            summary[row_status] += 1
        if row_status == "confirmed":
            summary["confirmed_amount"] += float(row.get("amount_cents") or 0) / 100
    summary["confirmed_amount"] = round(summary["confirmed_amount"], 2)
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "status": status,
        "summary": summary,
    }


def _customer_summary(user: dict[str, Any]) -> dict[str, Any]:
    conn = db.get_conn()
    user_id = user["telegram_id"]
    paid_filter = {"user_id": user_id, "status": {"$in": ["paid", "payment_confirmed", "delivered"]}}
    revenue = list(conn.orders.aggregate([
        {"$match": paid_filter},
        {"$group": {"_id": None, "total": {"$sum": db.order_charge_total_expression()}, "count": {"$sum": 1}}},
    ]))
    metrics = revenue[0] if revenue else {"total": 0, "count": 0}
    last_order = conn.orders.find_one({"user_id": user_id}, sort=[("created_at", DESCENDING)]) or {}
    deposits = list(conn.wallet_topups.aggregate([
        {"$match": {"user_id": user_id, "$or": [{"status": "confirmed"}, {"status": {"$exists": False}}]}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]))
    deposit_metrics = deposits[0] if deposits else {"total": 0, "count": 0}
    result = db._public(user)
    result.update({
        "order_count": conn.orders.count_documents({"user_id": user_id}),
        "paid_order_count": metrics["count"],
        "total_spent": round(float(metrics["total"]), 2),
        "referral_count": conn.referrals.count_documents({"referrer_id": user_id}),
        "ticket_count": conn.support_tickets.count_documents({"user_id": user_id}),
        "deposit_count": deposit_metrics["count"],
        "deposit_total": round(float(deposit_metrics["total"] or 0) / 100, 2),
        "last_order_at": last_order.get("created_at"),
        "last_order_name": last_order.get("offer_name") or last_order.get("service_name") or "",
        "wallet_balance": round(
            float((conn.wallets.find_one({"user_id": user_id}) or {}).get("balance_cents", 0)) / 100,
            2,
        ),
    })
    return result


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key, [])
    return values[0].strip() if values else ""
