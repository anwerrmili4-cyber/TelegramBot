"""Read-only JSON queries used by the administration dashboard."""

from __future__ import annotations

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
    if status:
        query["status"] = status
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
    analytics = _order_analytics(collection, analytics_query)
    return {
        "items": [_admin_order(row) for row in rows],
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
        {"_id": 0, "telegram_id": 1, "username": 1, "first_name": 1, "full_name": 1},
    ) or {}
    result["customer"] = db._public(user)
    result["delivery_content"] = _order_delivery_content(order)
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
    delivered = pending = 0

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
        "success_rate": round((delivered / total * 100) if total else 0, 1),
        "statuses": statuses,
        "daily": [
            {"date": key, "count": value["count"], "revenue": round(value["revenue"], 2)}
            for key, value in days.items()
        ],
    }


def list_tickets(params: dict[str, list[str]]) -> dict[str, Any]:
    """Return filtered, paginated support tickets."""
    page = _bounded_int(_first(params, "page"), 1, 1, 100_000)
    per_page = _bounded_int(_first(params, "per_page"), 25, 1, 100)
    query: dict[str, Any] = {}
    status = _first(params, "status")
    if status:
        query["status"] = status
    user_id = _first(params, "user_id")
    if user_id and user_id.isdigit():
        query["user_id"] = int(user_id)
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

    collection = db.get_conn().support_tickets
    total = collection.count_documents(query)
    rows = collection.find(query).sort("updated_at", DESCENDING).skip((page - 1) * per_page).limit(per_page)
    return {
        "items": [db._public(row) for row in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
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
    """Return one customer with their complete order history and CRM metrics."""
    conn = db.get_conn()
    user = conn.users.find_one({"telegram_id": user_id})
    if not user:
        return None
    result = _customer_summary(user)
    result["orders"] = [_admin_order(row) for row in conn.orders.find({"user_id": user_id}).sort("created_at", DESCENDING)]
    result["tickets"] = [db._public(row) for row in conn.support_tickets.find({"user_id": user_id}).sort("updated_at", DESCENDING).limit(25)]
    result["referrals"] = conn.referrals.count_documents({"referrer_id": user_id})
    return result


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
    result = db._public(user)
    result.update({
        "order_count": conn.orders.count_documents({"user_id": user_id}),
        "paid_order_count": metrics["count"],
        "total_spent": round(float(metrics["total"]), 2),
        "referral_count": conn.referrals.count_documents({"referrer_id": user_id}),
        "wallet_balance": round(
            float((conn.wallets.find_one({"user_id": user_id}) or {}).get("balance_cents", 0)) / 100,
            2,
        ),
    })
    return result


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key, [])
    return values[0].strip() if values else ""
