"""Sold products and the clients who bought them, for the bot and the site.

A product stays in this list after it is deactivated, archived, or removed.
The sale itself is the record: the current catalog is only extra detail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from typing import Any

import database as db
from app.domain import order_conversation_service, warranty_service
from app.web.dashboard_api import _first, _telegram_description_plain_text

_SOLD_STATUSES = (
    "paid",
    "payment_confirmed",
    "preparing_delivery",
    "delivered",
    "refunded",
    "stock_issue",
)
_UNITS = {"days": "jours", "months": "mois", "years": "années"}
_ORDER_FIELDS = {
    "id": 1,
    "offer_id": 1,
    "offer_name": 1,
    "service_name": 1,
    "service_id": 1,
    "qty": 1,
    "quantity": 1,
    "status": 1,
    "created_at": 1,
    "paid_at": 1,
    "delivered_at": 1,
    "user_id": 1,
    "customer_id": 1,
    "customer_name": 1,
    "customer_email": 1,
    "customer_phone": 1,
    "customer_info": 1,
    "customer_note": 1,
    "site_remark": 1,
    "admin_note": 1,
    "total_price": 1,
    "wallet_amount": 1,
    "total_millimes": 1,
    "unit_price": 1,
    "unit_price_millimes": 1,
    "warranty": 1,
    "warranty_days": 1,
    "warranty_value": 1,
    "warranty_unit": 1,
    "period_days": 1,
    "period_value": 1,
    "period_unit": 1,
    "product_description_snapshot": 1,
    "cart_reference": 1,
    "sales_channel": 1,
}


def report(params: dict[str, list[str]]) -> dict[str, Any]:
    """List sold products, or one product with every client who bought it."""
    channel = "site" if _first(params, "channel") == "site" else "bot"
    selected = _first(params, "product")
    search = _first(params, "search").casefold()
    coverage = _first(params, "coverage")
    if coverage not in {"fw", "fw_active", "fw_finished"}:
        coverage = "all"
    try:
        start, end = _date_bounds(params)
    except ValueError:
        return {"ok": False, "error": "Période invalide : vérifiez les dates de début et de fin.", "products": []}
    conn = db.get_conn()
    summaries = _aggregate_summaries(conn.orders, channel, start, end, coverage)

    offer_ids = [
        int(key.removeprefix("offer:"))
        for key in summaries
        if key.startswith("offer:") and key.removeprefix("offer:").isdigit()
    ]
    offers = {
        int(row["id"]): row
        for row in conn.offers.find({"id": {"$in": offer_ids}})
    } if offer_ids else {}
    services = {
        int(row["id"]): row
        for row in conn.services.find({}, {"id": 1, "name": 1, "emoji": 1, "archived": 1, "active": 1})
        if row.get("id") is not None
    }

    products = []
    for key, summary in summaries.items():
        item = _aggregated_product_summary(key, summary, offers, services, channel)
        if search and search not in f"{item['name']} {item['service_name']}".casefold():
            continue
        products.append(item)
    products.sort(key=lambda item: (item["name"].casefold(), item["service_name"].casefold(), item["key"]))

    payload: dict[str, Any] = {
        "ok": True,
        "channel": channel,
        "currency": "TND" if channel == "site" else "USDT",
        "products": products,
    }
    if not selected:
        return payload
    summary = summaries.get(selected)
    if summary is None:
        if start is not None or end is not None or coverage != "all":
            payload["product"] = None
            return payload
        payload["ok"] = False
        payload["error"] = "Ce produit n’a aucune vente enregistrée."
        return payload
    rows = _selected_orders(conn.orders, channel, selected, start, end, coverage)
    if not rows:
        payload["product"] = None
        return payload
    product = _product_summary(selected, rows, offers, services, channel, detailed=True)
    product["buyers"] = _buyers(rows, channel, conn)
    payload["product"] = product
    return payload


def _summary_pipeline(
    channel: str,
    start: int | None,
    end: int | None,
    coverage: str,
    *,
    now: int | None = None,
) -> list[dict[str, Any]]:
    """Aggregate product totals without accumulating an unbounded order array."""
    current = int(datetime.now(UTC).timestamp()) if now is None else int(now)
    report_date = {
        "$cond": [
            {"$gt": [{"$ifNull": ["$paid_at", 0]}, 0]},
            "$paid_at",
            {"$ifNull": ["$created_at", 0]},
        ]
    }
    quantity = {
        "$cond": [
            {"$gt": [{"$ifNull": ["$qty", 0]}, 0]},
            "$qty",
            {"$cond": [{"$gt": [{"$ifNull": ["$quantity", 0]}, 0]}, "$quantity", 1]},
        ]
    }
    if channel == "site":
        buyer_key = {
            "$cond": [
                {"$ne": [{"$ifNull": ["$customer_id", None]}, None]},
                {"$concat": ["customer:", {"$toString": "$customer_id"}]},
                {"$cond": [
                    {"$ne": [{"$ifNull": ["$customer_email", ""]}, ""]},
                    {"$concat": ["email:", {"$toLower": {"$ifNull": ["$customer_email", ""]}}]},
                    {"$concat": ["name:", {"$toLower": {"$ifNull": ["$customer_name", ""]}}]},
                ]},
            ]
        }
        spent = {
            "$ifNull": [
                "$total_millimes",
                {"$multiply": [{"$ifNull": ["$total_price", 0]}, 1000]},
            ]
        }
    else:
        buyer_key = {
            "$cond": [
                {"$ne": [{"$ifNull": ["$user_id", None]}, None]},
                {"$concat": ["user:", {"$toString": "$user_id"}]},
                "user:unknown",
            ]
        }
        spent = db.order_charge_total_expression()
    is_fw = {
        "$or": [
            {"$eq": [{"$toUpper": {"$ifNull": ["$warranty", ""]}}, "FW"]},
            {"$and": [
                {"$gt": [{"$ifNull": ["$period_days", 0]}, 0]},
                {"$eq": [{"$ifNull": ["$period_days", 0]}, {"$ifNull": ["$warranty_days", 0]}]},
            ]},
        ]
    }
    started_at = {
        "$cond": [
            {"$gt": [{"$ifNull": ["$delivered_at", 0]}, 0]},
            "$delivered_at",
            report_date,
        ]
    }
    pipeline: list[dict[str, Any]] = [
        {"$match": _sold_query(channel, start, end)},
        {"$set": {
            "_report_date": report_date,
            "_quantity": quantity,
            "_buyer_key": buyer_key,
            "_spent": spent,
            "_is_fw": is_fw,
            "_fw_started_at": started_at,
        }},
        {"$set": {
            "_fw_expires_at": {
                "$cond": [
                    {"$and": ["$_is_fw", {"$gt": ["$_fw_started_at", 0]}, {"$gt": [{"$ifNull": ["$period_days", 0]}, 0]}]},
                    {"$add": ["$_fw_started_at", {"$multiply": ["$period_days", 86400]}]},
                    None,
                ]
            },
        }},
        {"$set": {
            "_fw_status": {
                "$cond": [
                    {"$not": ["$_is_fw"]},
                    "",
                    {"$cond": [
                        {"$and": [{"$ne": ["$_fw_expires_at", None]}, {"$lte": ["$_fw_expires_at", current]}]},
                        "finished",
                        "active",
                    ]},
                ]
            },
        }},
    ]
    if coverage == "fw":
        pipeline.append({"$match": {"_is_fw": True}})
    elif coverage == "fw_active":
        pipeline.append({"$match": {"_fw_status": "active"}})
    elif coverage == "fw_finished":
        pipeline.append({"$match": {"_fw_status": "finished"}})
    pipeline.extend([
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": {
                "offer_id": "$offer_id",
                "offer_name": "$offer_name",
                "service_name": "$service_name",
            },
            "sales_count": {"$sum": 1},
            "buyer_keys": {"$addToSet": "$_buyer_key"},
            "quantity": {"$sum": "$_quantity"},
            "spent": {"$sum": "$_spent"},
            "first_sale_at": {"$min": "$_report_date"},
            "last_sale_at": {"$max": "$_report_date"},
            "fw_total": {"$sum": {"$cond": ["$_is_fw", 1, 0]}},
            "fw_active": {"$sum": {"$cond": [{"$eq": ["$_fw_status", "active"]}, 1, 0]}},
            "fw_finished": {"$sum": {"$cond": [{"$eq": ["$_fw_status", "finished"]}, 1, 0]}},
            "latest": {"$first": {
                "offer_id": "$offer_id",
                "offer_name": "$offer_name",
                "service_name": "$service_name",
                "created_at": "$created_at",
                "warranty": "$warranty",
                "warranty_days": "$warranty_days",
                "warranty_value": "$warranty_value",
                "warranty_unit": "$warranty_unit",
                "period_days": "$period_days",
                "period_value": "$period_value",
                "period_unit": "$period_unit",
                "unit_price": "$unit_price",
                "unit_price_millimes": "$unit_price_millimes",
                "product_description_snapshot": "$product_description_snapshot",
            }},
        }},
    ])
    return pipeline


def _aggregate_summaries(
    collection: Any,
    channel: str,
    start: int | None,
    end: int | None,
    coverage: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw in collection.aggregate(_summary_pipeline(channel, start, end, coverage), allowDiskUse=True):
        latest = dict(raw.get("latest") or {})
        identity = raw.get("_id") or {}
        latest.setdefault("offer_id", identity.get("offer_id"))
        latest.setdefault("offer_name", identity.get("offer_name"))
        latest.setdefault("service_name", identity.get("service_name"))
        key = _product_key(latest)
        incoming = {
            "sales_count": int(raw.get("sales_count") or 0),
            "buyer_keys": set(raw.get("buyer_keys") or []),
            "quantity": int(raw.get("quantity") or 0),
            "spent": raw.get("spent") or 0,
            "first_sale_at": int(raw.get("first_sale_at") or 0),
            "last_sale_at": int(raw.get("last_sale_at") or 0),
            "fw_total": int(raw.get("fw_total") or 0),
            "fw_active": int(raw.get("fw_active") or 0),
            "fw_finished": int(raw.get("fw_finished") or 0),
            "latest": latest,
        }
        current = grouped.get(key)
        if current is None:
            grouped[key] = incoming
            continue
        current["sales_count"] += incoming["sales_count"]
        current["buyer_keys"].update(incoming["buyer_keys"])
        current["quantity"] += incoming["quantity"]
        current["spent"] += incoming["spent"]
        current["first_sale_at"] = min(current["first_sale_at"], incoming["first_sale_at"])
        current["last_sale_at"] = max(current["last_sale_at"], incoming["last_sale_at"])
        current["fw_total"] += incoming["fw_total"]
        current["fw_active"] += incoming["fw_active"]
        current["fw_finished"] += incoming["fw_finished"]
        if int(latest.get("created_at") or 0) > int(current["latest"].get("created_at") or 0):
            current["latest"] = latest
    return grouped


def _selected_orders(
    collection: Any,
    channel: str,
    selected: str,
    start: int | None,
    end: int | None,
    coverage: str,
) -> list[dict[str, Any]]:
    query = _sold_query(channel, start, end)
    if selected.startswith("offer:") and selected.removeprefix("offer:").isdigit():
        offer_id = int(selected.removeprefix("offer:"))
        selected_query = {"offer_id": {"$in": [offer_id, str(offer_id)]}}
    elif selected.startswith("snapshot:") and "|" in selected:
        service, name = selected.removeprefix("snapshot:").split("|", 1)
        import re
        selected_query = {
            "offer_id": {"$in": [None, ""]},
            "service_name": {"$regex": rf"^\s*{re.escape(service)}\s*$", "$options": "i"},
            "offer_name": {"$regex": rf"^\s*{re.escape(name)}\s*$", "$options": "i"},
        }
    else:
        return []
    rows = []
    for stored in collection.find({"$and": [query, selected_query]}, _ORDER_FIELDS):
        order = dict(stored)
        order["_fw_tracking"] = _fw_tracking(order)
        if _matches_coverage(order["_fw_tracking"], coverage):
            rows.append(order)
    return rows


def _date_bounds(params: dict[str, list[str]]) -> tuple[int | None, int | None]:
    """Unix seconds: inclusive start, exclusive end, supplied in the viewer's timezone."""
    bounds = []
    for key in ("from_ts", "to_ts"):
        raw = _first(params, key)
        value = int(raw) if raw else None
        if value is not None and not 0 <= value <= 253402300799:
            raise ValueError("Timestamp out of range")
        bounds.append(value)
    start, end = bounds
    if start is not None and end is not None and start >= end:
        raise ValueError("Empty or reversed range")
    return start, end


def _sold_query(channel: str, start: int | None = None, end: int | None = None) -> dict[str, Any]:
    sold = {
        "$or": [
            {"status": {"$in": list(_SOLD_STATUSES)}},
            {"paid_at": {"$gt": 0}},
        ],
    }
    query = {"sales_channel": "tn_site", **sold} if channel == "site" else db.customer_order_query(sold)
    if start is None and end is None:
        return query
    bounds = {}
    if start is not None:
        bounds["$gte"] = start
    if end is not None:
        bounds["$lt"] = end
    # Match the date used in the report: payment first, creation for legacy sales.
    return {"$and": [query, {"$or": [
        {"paid_at": {"$gt": 0, **bounds}},
        {"$and": [
            {"$or": [{"paid_at": None}, {"paid_at": 0}]},
            {"created_at": bounds},
        ]},
    ]}]}


def _fw_tracking(order: dict[str, Any], now: int | None = None) -> dict[str, Any]:
    """Describe Full Warranty usage from delivery until the product period ends."""
    is_full = warranty_service.has_full_warranty(order) or str(order.get("warranty") or "").strip().upper() == "FW"
    if not is_full:
        return {
            "is_full_warranty": False,
            "fw_status": "",
            "fw_started_at": None,
            "expires_at": None,
            "remaining_days": None,
        }
    current = int(datetime.now(UTC).timestamp()) if now is None else int(now)
    started_at = int(order.get("delivered_at") or order.get("paid_at") or order.get("created_at") or 0) or None
    period_days = max(0, int(order.get("period_days") or 0))
    expires_at = started_at + period_days * 86400 if started_at and period_days else None
    finished = expires_at is not None and current >= expires_at
    remaining_days = max(0, ceil((expires_at - current) / 86400)) if expires_at is not None else None
    return {
        "is_full_warranty": True,
        "fw_status": "finished" if finished else "active",
        "fw_started_at": started_at,
        "expires_at": expires_at,
        "remaining_days": remaining_days,
    }


def _matches_coverage(tracking: dict[str, Any], coverage: str) -> bool:
    if coverage == "fw":
        return bool(tracking["is_full_warranty"])
    if coverage == "fw_active":
        return tracking["fw_status"] == "active"
    if coverage == "fw_finished":
        return tracking["fw_status"] == "finished"
    return True


def _product_key(order: dict[str, Any]) -> str:
    offer_id = order.get("offer_id")
    if offer_id is not None and str(offer_id).strip().isdigit():
        return f"offer:{int(offer_id)}"
    service = str(order.get("service_name") or "").strip().casefold()
    name = str(order.get("offer_name") or "").strip().casefold()
    return f"snapshot:{service}|{name}"


def _aggregated_product_summary(
    key: str,
    summary: dict[str, Any],
    offers: dict[int, dict[str, Any]],
    services: dict[int, dict[str, Any]],
    channel: str,
) -> dict[str, Any]:
    latest = summary["latest"]
    offer_id = int(key.removeprefix("offer:")) if key.startswith("offer:") else None
    offer = offers.get(offer_id) if offer_id is not None else None
    service = services.get(int(offer["service_id"])) if offer and offer.get("service_id") is not None else None
    state, state_label = _catalog_state(offer)
    spent = int(summary["spent"]) if channel == "site" else round(float(summary["spent"]), 2)
    return {
        "key": key,
        "offer_id": offer_id,
        "name": str((offer or {}).get("name") or latest.get("offer_name") or "Produit sans nom").strip() or "Produit sans nom",
        "service_name": str((service or {}).get("name") or latest.get("service_name") or "").strip(),
        "catalog_state": state,
        "catalog_label": state_label,
        "sales_count": int(summary["sales_count"]),
        "buyer_count": len(summary["buyer_keys"]),
        "quantity": int(summary["quantity"]),
        "spent": spent,
        "warranty": _warranty(offer, latest),
        "period": _period(offer, latest),
        "first_sale_at": summary["first_sale_at"] or None,
        "last_sale_at": summary["last_sale_at"] or None,
        "fw_total": int(summary["fw_total"]),
        "fw_active": int(summary["fw_active"]),
        "fw_finished": int(summary["fw_finished"]),
    }


def _product_summary(
    key: str,
    rows: list[dict[str, Any]],
    offers: dict[int, dict[str, Any]],
    services: dict[int, dict[str, Any]],
    channel: str,
    detailed: bool = False,
) -> dict[str, Any]:
    latest = max(rows, key=lambda row: int(row.get("created_at") or 0))
    offer_id = int(key.removeprefix("offer:")) if key.startswith("offer:") else None
    offer = offers.get(offer_id) if offer_id is not None else None
    service = services.get(int(offer["service_id"])) if offer and offer.get("service_id") is not None else None
    name = str((offer or {}).get("name") or latest.get("offer_name") or "Produit sans nom").strip()
    service_name = str((service or {}).get("name") or latest.get("service_name") or "").strip()
    state, state_label = _catalog_state(offer)
    quantity = sum(_quantity(row) for row in rows)
    spent = _sum_spent(rows, channel)
    first_sale = min(int(row.get("paid_at") or row.get("created_at") or 0) for row in rows)
    last_sale = max(int(row.get("paid_at") or row.get("created_at") or 0) for row in rows)
    tracked = [row.get("_fw_tracking") or _fw_tracking(row) for row in rows]
    item = {
        "key": key,
        "offer_id": offer_id,
        "name": name or "Produit sans nom",
        "service_name": service_name,
        "catalog_state": state,
        "catalog_label": state_label,
        "sales_count": len(rows),
        "buyer_count": len({_buyer_key(row, channel) for row in rows}),
        "quantity": quantity,
        "spent": spent,
        "warranty": _warranty(offer, latest),
        "period": _period(offer, latest),
        "first_sale_at": first_sale or None,
        "last_sale_at": last_sale or None,
        "fw_total": sum(1 for item in tracked if item["is_full_warranty"]),
        "fw_active": sum(1 for item in tracked if item["fw_status"] == "active"),
        "fw_finished": sum(1 for item in tracked if item["fw_status"] == "finished"),
    }
    if detailed:
        item["facts"] = _facts(item, offer, service, latest, channel)
    return item


def _catalog_state(offer: dict[str, Any] | None) -> tuple[str, str]:
    if not offer:
        return "deleted", "Supprimé"
    if offer.get("archived") == 1:
        return "archived", "Archivé"
    if not db.is_bot_visible(offer):
        return "inactive", "Désactivé"
    if not db.product_is_enabled(offer):
        return "product_off", "Produit off"
    if offer.get("unlimited_stock"):
        return "active", "Actif"
    if db.stock_is_enabled(offer) and int(offer.get("stock") or 0) <= 0:
        return "out_of_stock", "Hors stock"
    return "active", "Actif"


def _facts(
    summary: dict[str, Any],
    offer: dict[str, Any] | None,
    service: dict[str, Any] | None,
    latest: dict[str, Any],
    channel: str,
) -> list[dict[str, str]]:
    price = _catalog_price(offer, latest, channel)
    stock = "Illimité" if offer and offer.get("unlimited_stock") else (
        "Suivi désactivé" if offer and not db.stock_is_enabled(offer) else (
            str(int(offer.get("stock") or 0)) if offer else "Produit retiré du catalogue"
        )
    )
    description = _telegram_description_plain_text(
        (offer or {}).get("description") or latest.get("product_description_snapshot")
    )
    supplier = str((offer or {}).get("supplier_provider") or "").strip() or "Stock interne"
    channels = ", ".join(str(item) for item in ((offer or {}).get("sales_channels") or [])) or (
        "Site" if channel == "site" else "Bot"
    )
    facts = [
        {"label": "Nom", "value": summary["name"]},
        {"label": "Service", "value": summary["service_name"] or "—"},
        {"label": "Identifiant", "value": str(summary["offer_id"]) if summary["offer_id"] is not None else "Ancienne vente sans identifiant"},
        {"label": "État dans le catalogue", "value": summary["catalog_label"]},
        {"label": "Prix catalogue", "value": price},
        {"label": "Stock", "value": stock},
        {"label": "Produit", "value": "Activé" if offer and db.product_is_enabled(offer) else ("Désactivé" if offer else "Supprimé")},
        {"label": "Fournisseur", "value": supplier},
        {"label": "Garantie", "value": summary["warranty"] or "—"},
        {"label": "Durée", "value": summary["period"] or "—"},
        {"label": "Livraison", "value": str((offer or {}).get("delivery_delay") or "").strip() or "—"},
        {"label": "Canaux", "value": channels},
        {"label": "Ventes", "value": str(summary["sales_count"])},
        {"label": "Quantité vendue", "value": str(summary["quantity"])},
        {"label": "Clients", "value": str(summary["buyer_count"])},
    ]
    if service and service.get("emoji"):
        facts.insert(2, {"label": "Icône du service", "value": str(service["emoji"])})
    if description:
        facts.append({"label": "Description", "value": description})
    return facts


def _catalog_price(offer: dict[str, Any] | None, latest: dict[str, Any], channel: str) -> str:
    if channel == "site":
        millimes = (offer or {}).get("tn_price_millimes") or latest.get("unit_price_millimes")
        if millimes:
            return f"{int(millimes) / 1000:.3f} DT"
    if offer and offer.get("price") is not None:
        return f"{float(offer['price']):.2f} USDT"
    if latest.get("unit_price") is not None:
        return f"{float(latest['unit_price']):.2f} USDT"
    return "—"


def _buyers(rows: list[dict[str, Any]], channel: str, conn: Any) -> list[dict[str, Any]]:
    messages = order_conversation_service.messages_by_order(
        row.get("id") for row in rows if row.get("id") is not None
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for stored in rows:
        row = dict(stored)
        row["_order_messages"] = messages.get(int(row["id"]), []) if row.get("id") is not None else []
        grouped.setdefault(_buyer_key(row, channel), []).append(row)
    if channel == "site":
        buyers = [_site_buyer(key, purchases, conn) for key, purchases in grouped.items()]
    else:
        buyers = [_bot_buyer(key, purchases, conn) for key, purchases in grouped.items()]
    buyers.sort(key=lambda item: (item["last_purchase_at"] or 0, item["name"].casefold()), reverse=True)
    return buyers


def _buyer_key(order: dict[str, Any], channel: str) -> str:
    if channel == "site":
        customer_id = order.get("customer_id")
        if customer_id is not None and str(customer_id).strip().isdigit():
            return f"customer:{int(customer_id)}"
        email = str(order.get("customer_email") or "").strip().casefold()
        if email:
            return f"email:{email}"
        return f"name:{str(order.get('customer_name') or '').strip().casefold()}"
    user_id = order.get("user_id")
    if user_id is not None and str(user_id).strip().lstrip("-").isdigit():
        return f"user:{int(user_id)}"
    return "user:unknown"


def _bot_buyer(key: str, purchases: list[dict[str, Any]], conn: Any) -> dict[str, Any]:
    user_id = int(key.removeprefix("user:")) if key.removeprefix("user:").lstrip("-").isdigit() else None
    user = conn.users.find_one({"telegram_id": user_id}) if user_id is not None else None
    user = user or {}
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    full_name = str(user.get("full_name") or " ".join(part for part in (first_name, last_name) if part)).strip()
    username = str(user.get("username") or "").strip()
    name = full_name or (f"@{username}" if username else f"Client {user_id if user_id is not None else 'inconnu'}")
    wallet = conn.wallets.find_one({"user_id": user_id}) if user_id is not None else None
    balance = round(float((wallet or {}).get("balance_cents") or 0) / 100, 2)
    details = [
        {"label": "Identifiant Telegram", "value": str(user_id) if user_id is not None else "—"},
        {"label": "Nom d’utilisateur", "value": f"@{username}" if username else "—"},
        {"label": "Nom", "value": full_name or "—"},
        {"label": "Langue", "value": str(user.get("lang") or "—").upper()},
        {"label": "Compte", "value": "Bloqué" if user.get("banned") else ("Actif" if user else "Compte introuvable")},
        {"label": "Client depuis", "value": _stamp(user.get("created_at"))},
        {"label": "Portefeuille", "value": f"{balance:.2f} USDT"},
    ]
    return _buyer_payload(key, name, user_id, "customers", purchases, "bot", details)


def _site_buyer(key: str, purchases: list[dict[str, Any]], conn: Any) -> dict[str, Any]:
    latest = max(purchases, key=lambda row: int(row.get("created_at") or 0))
    customer_id = int(key.removeprefix("customer:")) if key.startswith("customer:") else None
    account = conn.storefront_customers.find_one(
        {"id": customer_id},
        {"password_hash": 0, "reset_token_hash": 0, "verification_code_hash": 0},
    ) if customer_id is not None else None
    account = account or {}
    name = str(account.get("name") or latest.get("customer_name") or "Client").strip() or "Client"
    email = str(account.get("email") or latest.get("customer_email") or "").strip()
    phone = str(account.get("phone") or latest.get("customer_phone") or "").strip()
    wallet = conn.storefront_wallets.find_one({"customer_id": customer_id}) if customer_id is not None else None
    balance = int((wallet or {}).get("balance_millimes") or 0)
    verified = account.get("email_verified")
    details = [
        {"label": "Identifiant", "value": str(customer_id) if customer_id is not None else "—"},
        {"label": "Email", "value": email or "—"},
        {"label": "Téléphone", "value": phone or "—"},
        {"label": "Compte", "value": "Vérifié" if verified is not False and account else ("Non vérifié" if account else "Compte introuvable")},
        {"label": "Client depuis", "value": _stamp(account.get("created_at"))},
        {"label": "Portefeuille", "value": f"{balance / 1000:.3f} DT"},
    ]
    return _buyer_payload(key, name, customer_id, "site-customers", purchases, "site", details, email)


def _buyer_payload(
    key: str,
    name: str,
    entity_id: int | None,
    page: str,
    purchases: list[dict[str, Any]],
    channel: str,
    details: list[dict[str, str]],
    email: str = "",
) -> dict[str, Any]:
    ordered = sorted(purchases, key=lambda row: int(row.get("created_at") or 0), reverse=True)
    tracked = [row.get("_fw_tracking") or _fw_tracking(row) for row in ordered]
    return {
        "key": key,
        "name": name,
        "entity_id": entity_id,
        "page": page,
        "email": email,
        "orders_count": len(ordered),
        "quantity": sum(_quantity(row) for row in ordered),
        "spent": _sum_spent(ordered, channel),
        "first_purchase_at": min(int(row.get("paid_at") or row.get("created_at") or 0) for row in ordered) or None,
        "last_purchase_at": max(int(row.get("paid_at") or row.get("created_at") or 0) for row in ordered) or None,
        "fw_total": sum(1 for item in tracked if item["is_full_warranty"]),
        "fw_active": sum(1 for item in tracked if item["fw_status"] == "active"),
        "fw_finished": sum(1 for item in tracked if item["fw_status"] == "finished"),
        "details": details,
        "orders": [_purchase(row, channel) for row in ordered],
    }


def _purchase(order: dict[str, Any], channel: str) -> dict[str, Any]:
    tracking = order.get("_fw_tracking") or _fw_tracking(order)
    messages = [
        {
            "id": message.get("id"),
            "sender_type": str(message.get("sender_type") or ""),
            "content": str(message.get("content") or ""),
            "kind": str(message.get("kind") or "message"),
            "source": str(message.get("source") or "order"),
            "ticket_id": message.get("ticket_id"),
            "created_at": message.get("created_at"),
        }
        for message in order.get("_order_messages") or []
        if message.get("sender_type") in {"admin", "client"} and str(message.get("content") or "").strip()
    ]
    context = {
        "prompt": str(order.get("site_remark") or "").strip(),
        "customer_info": str(order.get("customer_info") or "").strip(),
        "customer_note": str(order.get("customer_note") or "").strip(),
        "admin_note": str(order.get("admin_note") or "").strip(),
        "messages": messages,
    }
    purchase = {
        "order_id": order.get("id"),
        "cart_reference": str(order.get("cart_reference") or ""),
        "status": str(order.get("status") or ""),
        "quantity": _quantity(order),
        "spent": _spent(order, channel),
        "created_at": order.get("created_at"),
        "paid_at": order.get("paid_at"),
        "delivered_at": order.get("delivered_at"),
        "warranty": _warranty(None, order),
        "period": _period(None, order),
        **tracking,
    }
    if any((context["customer_info"], context["customer_note"], context["admin_note"], context["messages"])):
        purchase["pre_confirmation"] = context
    return purchase


def _quantity(order: dict[str, Any]) -> int:
    for key in ("qty", "quantity"):
        value = order.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return 1


def _spent(order: dict[str, Any], channel: str) -> int | float:
    if channel == "site":
        if order.get("total_millimes") is not None:
            return int(order.get("total_millimes") or 0)
        return int(round(float(order.get("total_price") or 0) * 1000))
    return db.order_charge_total(order)


def _sum_spent(rows: list[dict[str, Any]], channel: str) -> int | float:
    total = sum(_spent(row, channel) for row in rows)
    return int(total) if channel == "site" else round(float(total), 2)


def _warranty(offer: dict[str, Any] | None, order: dict[str, Any]) -> str:
    if offer:
        label = _span(offer.get("warranty_value"), offer.get("warranty_unit"), zero_label="NW")
        if label:
            return label
        note = str(offer.get("note") or "").strip()
        if note:
            return note
    stored = str(order.get("warranty") or "").strip()
    if stored:
        return stored
    return _span(order.get("warranty_value") or order.get("warranty_days"), order.get("warranty_unit"), zero_label="NW")


def _period(offer: dict[str, Any] | None, order: dict[str, Any]) -> str:
    source = offer or order
    return _span(
        source.get("period_value") if source.get("period_value") is not None else source.get("period_days"),
        source.get("period_unit"),
    )


def _span(value: Any, unit: Any, zero_label: str = "") -> str:
    if value is None or value == "":
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    if number <= 0:
        return zero_label
    label = _UNITS.get(str(unit or "days"), str(unit or "jours"))
    return f"{number} {label}"


def _stamp(value: Any) -> str:
    if not value:
        return "—"
    try:
        stamp = int(value)
    except (TypeError, ValueError):
        return str(value)
    if stamp <= 0:
        return "—"
    return datetime.fromtimestamp(stamp, UTC).strftime("%d/%m/%Y")
