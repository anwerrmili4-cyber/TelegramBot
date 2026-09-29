"""Admin space for the Tunisian storefront: overview, catalog and customers.

Site fields (dinar price, visibility, badge…) are stored on the bot's own offer
and service documents but only the storefront reads them, so editing them here
never changes what the Telegram bot sells.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import database as db
from app.domain import site_orders_service, storefront_service
from app.domain.site_orders_service import SALES_CHANNEL, STATUS_FILTERS

# Tunisia stays on UTC+1 all year.
TUNIS_TZ = timezone(timedelta(hours=1))

_REVENUE_STATUSES = [*STATUS_FILTERS["confirmed"], *STATUS_FILTERS["delivered"]]
_MAX_SCANNED_LINES = 5000

CATALOG_FILTERS = ("all", "on_sale", "no_price", "hidden")


class SiteAdminError(ValueError):
    """Raised with a French message the admin UI shows as-is."""


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return str(values[0] or "").strip()


def _bounded(value: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _paginate(items: list[Any], params: dict[str, list[str]], per_page_default: int = 25) -> dict[str, Any]:
    page = _bounded(_first(params, "page"), 1, 1, 10_000)
    per_page = _bounded(_first(params, "per_page"), per_page_default, 1, 100)
    start = (page - 1) * per_page
    return {
        "items": items[start : start + per_page],
        "page": page,
        "per_page": per_page,
        "total": len(items),
        "pages": max(1, -(-len(items) // per_page)),
    }


def _site_lines(query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list(
        db.get_conn()
        .orders.find({"sales_channel": SALES_CHANNEL, **(query or {})}, {"_id": 0})
        .sort("created_at", -1)
        .limit(_MAX_SCANNED_LINES)
    )


def _revenue_time(line: dict[str, Any]) -> int:
    return int(line.get("paid_at") or line.get("created_at") or 0)


def overview() -> dict[str, Any]:
    """Headline numbers for the storefront dashboard."""
    now = datetime.now(TUNIS_TZ)
    today = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    month = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())

    lines = _site_lines()
    sold = [line for line in lines if line.get("status") in _REVENUE_STATUSES]
    revenue_today = sum(int(line.get("total_millimes") or 0) for line in sold if _revenue_time(line) >= today)
    revenue_month = sum(int(line.get("total_millimes") or 0) for line in sold if _revenue_time(line) >= month)

    products: dict[str, dict[str, Any]] = {}
    for line in sold:
        name = str(line.get("offer_name") or "Offre")
        entry = products.setdefault(name, {
            "offer_name": name,
            "service_name": line.get("service_name", ""),
            "quantity": 0,
            "revenue_millimes": 0,
        })
        entry["quantity"] += int(line.get("qty") or 1)
        entry["revenue_millimes"] += int(line.get("total_millimes") or 0)
    top_products = sorted(products.values(), key=lambda item: item["revenue_millimes"], reverse=True)[:5]

    counts = site_orders_service.list_carts({"status": ["to_verify"], "per_page": ["1"]})["counts"]
    recent = site_orders_service.list_carts({"status": ["all"], "per_page": ["6"]})["items"]
    catalog_counts = catalog({"per_page": ["1"]})["counts"]
    return {
        "ok": True,
        "carts": counts,
        "revenue_today_millimes": revenue_today,
        "revenue_month_millimes": revenue_month,
        "customers": len({line.get("customer_phone") for line in lines if line.get("customer_phone")}),
        "top_products": top_products,
        "recent_carts": recent,
        "catalog": catalog_counts,
    }


def _catalog_row(service: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    price = storefront_service._price_millimes(offer)
    unlimited = bool(offer.get("unlimited_stock"))
    configured_category = str(offer.get("site_category") or "").strip().lower()
    return {
        "id": int(offer["id"]),
        "name": str(offer.get("name") or "Offre"),
        "service_id": int(service["id"]),
        "service_name": str(service.get("name") or "Service"),
        "service_emoji": str(service.get("emoji") or ""),
        "service_visible": storefront_service._site_visible(service),
        "bot_price_usdt": float(offer.get("price") or 0),
        "stock": -1 if unlimited else max(0, int(offer.get("stock") or 0)),
        "tn_price_millimes": price or None,
        "suggested_price_millimes": storefront_service.suggested_price_millimes(offer),
        "site_enabled": offer.get("site_enabled") is not False,
        "site_featured": bool(offer.get("site_featured")),
        "site_badge": str(offer.get("site_badge") or ""),
        "site_category": configured_category if configured_category in storefront_service.CATEGORY_LABELS else "",
        "effective_category": storefront_service._category(service, offer),
        "site_description_fr": str(offer.get("site_description_fr") or ""),
        "on_sale": storefront_service._site_visible(service) and storefront_service._offer_on_sale(offer),
    }


def _catalog_status(row: dict[str, Any]) -> str:
    if row["on_sale"]:
        return "on_sale"
    if not row["site_enabled"] or not row["service_visible"]:
        return "hidden"
    return "no_price"


def catalog(params: dict[str, list[str]]) -> dict[str, Any]:
    """Every active bot offer with its storefront settings."""
    status = _first(params, "status") or "all"
    search = _first(params, "search").lower()[:80]
    service_filter = _first(params, "service_id")

    services = []
    rows = []
    for service in db.list_services(active_only=True):
        offers = [
            _catalog_row(service, offer)
            for offer in db.list_offers(int(service["id"]), active_only=True)
            if offer.get("archived") != 1
        ]
        services.append({
            "id": int(service["id"]),
            "name": str(service.get("name") or "Service"),
            "emoji": str(service.get("emoji") or ""),
            "site_enabled": storefront_service._site_visible(service),
            "offers": len(offers),
            "on_sale": sum(1 for row in offers if row["on_sale"]),
        })
        rows.extend(offers)

    counts = {key: 0 for key in CATALOG_FILTERS}
    counts["all"] = len(rows)
    for row in rows:
        counts[_catalog_status(row)] += 1

    if status in CATALOG_FILTERS and status != "all":
        rows = [row for row in rows if _catalog_status(row) == status]
    if service_filter.isdigit():
        rows = [row for row in rows if row["service_id"] == int(service_filter)]
    if search:
        rows = [row for row in rows if search in f"{row['name']} {row['service_name']}".lower()]

    return {
        "ok": True,
        **_paginate(rows, params),
        "counts": counts,
        "status": status,
        "services": services,
        "categories": [{"id": key, "label": label} for key, label in storefront_service.CATEGORY_LABELS.items()],
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _dinar_millimes(value: Any) -> int | None:
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise SiteAdminError("Le prix en dinars doit être un nombre, par exemple 25,500.") from exc
    if amount <= 0 or amount > 100_000:
        raise SiteAdminError("Le prix en dinars doit être compris entre 0,001 et 100 000 DT.")
    return int((amount * 1000).to_integral_value())


def update_offer(form: dict[str, Any]) -> dict[str, Any]:
    """Save the storefront fields of one offer."""
    try:
        offer_id = int(form.get("offer_id"))
    except (TypeError, ValueError) as exc:
        raise SiteAdminError("Offre invalide.") from exc
    offer = db.get_conn().offers.find_one({"id": offer_id}, {"name": 1})
    if not offer:
        raise SiteAdminError("Offre introuvable.")

    category = str(form.get("site_category") or "").strip().lower()
    if category and category not in storefront_service.CATEGORY_LABELS:
        raise SiteAdminError("Catégorie inconnue.")
    price = _dinar_millimes(form.get("tn_price"))
    changes: dict[str, Any] = {
        "site_enabled": _truthy(form.get("site_enabled")),
        "site_featured": _truthy(form.get("site_featured")),
        "site_badge": str(form.get("site_badge") or "").strip()[:48],
        "site_category": category,
        "site_description_fr": str(form.get("site_description_fr") or "").strip()[:700],
    }
    update: dict[str, Any] = {"$set": changes}
    if price is None:
        update["$unset"] = {"tn_price_millimes": ""}
    else:
        changes["tn_price_millimes"] = price
    db.get_conn().offers.update_one({"id": offer_id}, update)
    db.audit_event("site_catalog.offer_updated", details={"offer_id": offer_id, "tn_price_millimes": price, **changes})
    return {"offer_id": offer_id, "name": offer.get("name", ""), "tn_price_millimes": price}


def set_service_visibility(form: dict[str, Any]) -> dict[str, Any]:
    try:
        service_id = int(form.get("service_id"))
    except (TypeError, ValueError) as exc:
        raise SiteAdminError("Service invalide.") from exc
    enabled = _truthy(form.get("site_enabled"))
    result = db.get_conn().services.update_one({"id": service_id}, {"$set": {"site_enabled": enabled}})
    if not result.matched_count:
        raise SiteAdminError("Service introuvable.")
    service = db.get_service(service_id) or {}
    db.audit_event("site_catalog.service_visibility", details={"service_id": service_id, "site_enabled": enabled})
    return {"service_id": service_id, "name": service.get("name", ""), "site_enabled": enabled}


def customers(params: dict[str, list[str]]) -> dict[str, Any]:
    """Storefront customers grouped by phone number, biggest spenders first."""
    search = _first(params, "search").lower()[:80]
    carts_by_phone: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for line in _site_lines({"cart_reference": {"$exists": True}}):
        phone = str(line.get("customer_phone") or "")
        if phone:
            carts_by_phone.setdefault(phone, {}).setdefault(line["cart_reference"], []).append(line)

    rows = []
    for phone, carts in carts_by_phone.items():
        summaries = sorted(
            (site_orders_service._cart_summary(reference, lines) for reference, lines in carts.items()),
            key=lambda cart: cart["created_at"],
            reverse=True,
        )
        spent = sum(cart["total_millimes"] for cart in summaries if cart["status"] in {"confirmed", "delivered"})
        rows.append({
            "phone": phone,
            "name": summaries[0]["customer_name"],
            "whatsapp_url": summaries[0]["whatsapp_url"],
            "carts_count": len(summaries),
            "pending_count": sum(1 for cart in summaries if cart["status"] == "to_verify"),
            "total_spent_millimes": spent,
            "first_order_at": summaries[-1]["created_at"],
            "last_order_at": summaries[0]["created_at"],
            "carts": summaries[:20],
        })

    if search:
        digits = "" if re.search(r"[^\d\s+().-]", search) else re.sub(r"\D", "", search)
        rows = [
            row for row in rows
            if search in row["name"].lower() or (digits and digits in re.sub(r"\D", "", row["phone"]))
        ]
    rows.sort(key=lambda row: (row["total_spent_millimes"], row["last_order_at"]), reverse=True)
    return {"ok": True, **_paginate(rows, params)}
