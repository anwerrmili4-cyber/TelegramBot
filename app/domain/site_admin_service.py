"""Admin space for the Tunisian storefront: overview, catalog and customers.

Site fields (dinar price, visibility, badge…) are stored on the bot's own offer
and service documents but only the storefront reads them, so editing them here
never changes what the Telegram bot sells.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import database as db
from app.domain import (
    inventory_service,
    site_logo_service,
    site_orders_service,
    site_settings_service,
    storefront_service,
    storefront_wallet_service,
    warranty_service,
)
from app.domain.site_orders_service import SALES_CHANNEL, STATUS_FILTERS

# Tunisia stays on UTC+1 all year.
TUNIS_TZ = timezone(timedelta(hours=1))

_REVENUE_STATUSES = [*STATUS_FILTERS["confirmed"], *STATUS_FILTERS["delivered"]]
_MAX_SCANNED_LINES = 5000

CATALOG_FILTERS = ("all", "on_sale", "no_price", "hidden", "disabled")


class SiteAdminError(ValueError):
    """Raised with a French message the admin UI shows as-is."""


SITE_DESCRIPTION_LIMIT = 8000


def _site_description(value: Any) -> str:
    return str(value or "").strip()[:SITE_DESCRIPTION_LIMIT]


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
    conn = db.get_conn()
    return {
        "ok": True,
        "carts": counts,
        "deposits_pending": conn.storefront_deposits.count_documents(
            {"status": storefront_wallet_service.DEPOSIT_PENDING}
        ),
        "revenue_today_millimes": revenue_today,
        "revenue_month_millimes": revenue_month,
        "customers": conn.storefront_customers.count_documents({"email_verified": {"$ne": False}}),
        "top_products": top_products,
        "recent_carts": recent,
        "catalog": catalog_counts,
    }


def _catalog_row(service: dict[str, Any], offer: dict[str, Any], rate: float) -> dict[str, Any]:
    price = storefront_service._price_millimes(offer)
    unlimited = bool(offer.get("unlimited_stock"))
    configured_category = str(offer.get("site_category") or "").strip().lower()
    category = storefront_service._category(service, offer)
    active = bool(offer.get("active", 1))
    service_active = bool(service.get("active", 1))
    site_period_days = offer.get("site_period_days")
    period_days = int(site_period_days if site_period_days is not None else 0)
    site_warranty_days = offer.get("site_warranty_days")
    warranty_days = int(site_warranty_days if site_warranty_days is not None else 0)
    site_name = str(offer.get("site_name") or "").strip()
    return {
        "id": int(offer["id"]),
        "name": site_name or str(offer.get("name") or "Offre"),
        "bot_name": str(offer.get("name") or ""),
        "service_id": int(service["id"]),
        "service_name": str(service.get("name") or "Service"),
        "service_emoji": str(service.get("emoji") or ""),
        "service_logo_url": site_logo_service.logo_url(service),
        "service_visible": storefront_service._site_visible(service),
        "service_active": service_active,
        "active": active,
        "bot_price_usdt": float(offer.get("price") or 0),
        "stock": -1 if unlimited else max(0, int(offer.get("stock") or 0)),
        "unlimited_stock": unlimited,
        "manual_stock": bool(offer.get("manual_stock")),
        "supplier_provider": str(offer.get("supplier_provider") or ""),
        "auto_delivery": offer.get("auto_delivery") is not False,
        "delivery_delay": str(offer.get("site_delivery_delay") or ""),
        "period_value": int(offer.get("site_period_value") or period_days or 30),
        "period_unit": warranty_service.normalize_duration_unit(
            offer.get("site_period_unit") if offer.get("site_period_value") is not None else "days"
        ),
        "warranty_value": int(offer.get("site_warranty_value") or warranty_days or 0),
        "warranty_unit": warranty_service.normalize_duration_unit(
            offer.get("site_warranty_unit") if offer.get("site_warranty_value") is not None else "days"
        ),
        "tn_price_millimes": price or None,
        "suggested_price_millimes": storefront_service.suggested_price_millimes(offer, rate),
        "site_enabled": storefront_service.site_enabled(offer),
        "site_featured": bool(offer.get("site_featured")),
        "site_badge": str(offer.get("site_badge") or ""),
        "site_category": configured_category if configured_category in storefront_service.CATEGORY_LABELS else "",
        "site_category_name": str(offer.get("site_category_name") or ""),
        "product_categories": db.is_official_subscriptions_service(service),
        "effective_category": category,
        "category_label": storefront_service.CATEGORY_LABELS[category],
        "site_description_fr": str(offer.get("site_description_fr") or ""),
        "site_image_url": str(offer.get("site_image_url") or ""),
        "description": str(offer.get("description") or ""),
        "on_sale": (
            storefront_service._site_visible(service)
            and storefront_service._offer_on_sale(offer)
        ),
    }


def _public_category(row: dict[str, Any]) -> dict[str, Any]:
    """The category the storefront shows: the service, or the product name."""
    if row.get("product_categories"):
        label = str(row.get("site_category_name") or "").strip() or storefront_service._product_category_label(row)
        return {
            "id": f"category:{label.casefold()}",
            "label": label[:120],
            "kind": "product",
            "service_id": int(row["service_id"]),
        }
    label = str(row.get("service_name") or "Service")[:120]
    return {
        "id": f"service:{int(row['service_id'])}",
        "label": label,
        "kind": "service",
        "service_id": int(row["service_id"]),
    }


def _catalog_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the catalog the way the site does: one category per service name.

    Products that still live in the official-subscriptions folder are their own
    categories, named after the product, until an admin renames or moves them.
    """
    groups: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    for row in rows:
        category = _public_category(row)
        group = groups.get(category["id"])
        if group is None:
            group = {
                **category,
                "count": 0,
                "on_sale": 0,
                "offer_ids": [],
                "items": [],
            }
            groups[category["id"]] = group
            ordered.append(category["id"])
        group["count"] += 1
        group["on_sale"] += int(bool(row["on_sale"]))
        group["offer_ids"].append(int(row["id"]))
        group["items"].append(row)
    return [groups[key] for key in ordered]


def _catalog_status(row: dict[str, Any]) -> str:
    if not row["site_enabled"]:
        return "disabled"
    if not row["service_visible"]:
        return "hidden"
    if row["on_sale"]:
        return "on_sale"
    return "no_price"


def catalog(params: dict[str, list[str]]) -> dict[str, Any]:
    """Every non-archived bot offer with its storefront settings.

    Disabled offers and services are listed too so they can be re-enabled from
    the site space; they are simply never sold.
    """
    status = _first(params, "status") or "all"
    search = _first(params, "search").lower()[:80]
    service_filter = _first(params, "service_id")

    visible_services = db.sort_for_site([
        service for service in db.list_services(active_only=False)
        if service.get("archived") != 1
    ])
    offers_by_service = db.list_offers_for_services(
        visible_services, active_only=False, include_archived=False,
    )
    rate = site_settings_service.tnd_per_usdt()
    services = []
    rows = []
    for service in visible_services:
        offers = [
            _catalog_row(service, offer, rate)
            for offer in offers_by_service.get(int(service["id"]), [])
            if offer.get("archived") != 1
        ]
        services.append({
            "id": int(service["id"]),
            "name": str(service.get("site_name") or service.get("name") or "Service"),
            "bot_name": str(service.get("name") or ""),
            "name_ar": str(service.get("name_ar") or ""),
            "emoji": str(service.get("emoji") or ""),
            "logo_url": site_logo_service.logo_url(service),
            "active": bool(service.get("active", 1)),
            "site_enabled": storefront_service.site_enabled(service),
            "product_categories": db.is_official_subscriptions_service(service),
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
        "groups": _catalog_groups(rows),
        "counts": counts,
        "status": status,
        "services": services,
        "categories": [{"id": key, "label": label} for key, label in storefront_service.CATEGORY_LABELS.items()],
        "tnd_per_usdt": rate,
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
        "site_description_fr": _site_description(form.get("site_description_fr")),
    }
    update: dict[str, Any] = {"$set": changes}
    if price is None:
        update["$unset"] = {"tn_price_millimes": ""}
    else:
        changes["tn_price_millimes"] = price
    db.get_conn().offers.update_one({"id": offer_id}, update)
    db.audit_event("site_catalog.offer_updated", details={"offer_id": offer_id, "tn_price_millimes": price, **changes})
    return {"offer_id": offer_id, "name": offer.get("name", ""), "tn_price_millimes": price}


def reorder_services(form: dict[str, Any]) -> dict[str, Any]:
    """Save the storefront category order. The bot catalog order stays put."""
    ordered_ids = []
    for part in str(form.get("ordered_ids") or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ordered_ids.append(int(part))
        except ValueError as exc:
            raise SiteAdminError("Ordre du catalogue invalide.") from exc
    try:
        result = db.reorder_catalog("service", ordered_ids, order_field="site_sort_order")
    except ValueError as exc:
        raise SiteAdminError(str(exc)) from exc
    db.audit_event("site_catalog.reordered", details={**result, "reversible": False})
    return result


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


def _optional_id(value: Any, label: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise SiteAdminError(f"{label} invalide.") from exc


def set_offer_visibility(form: dict[str, Any]) -> dict[str, Any]:
    try:
        offer_id = int(form.get("offer_id"))
    except (TypeError, ValueError) as exc:
        raise SiteAdminError("Offre invalide.") from exc
    enabled = _truthy(form.get("site_enabled"))
    result = db.get_conn().offers.update_one({"id": offer_id}, {"$set": {"site_enabled": enabled}})
    if not result.matched_count:
        raise SiteAdminError("Offre introuvable.")
    offer = db.get_offer(offer_id) or {}
    db.audit_event("site_catalog.offer_visibility", details={"offer_id": offer_id, "site_enabled": enabled})
    return {"offer_id": offer_id, "name": offer.get("site_name") or offer.get("name", ""), "site_enabled": enabled}


def save_service(form: dict[str, Any]) -> dict[str, Any]:
    """Create a service, or change its storefront name and visibility.

    The bot keeps its own name, emoji and active flag. A service created here
    starts hidden on the bot (``active`` 0) until the bot workspace enables it.
    """
    service_id = _optional_id(form.get("service_id"), "Service")
    name = str(form.get("name") or "").strip()[:80]
    if not name:
        raise SiteAdminError("Le nom du service est obligatoire.")
    site_enabled = _truthy(form.get("site_enabled", "1"))
    logo = None
    if str(form.get("logo") or "").strip():
        try:
            logo = site_logo_service.decode(form.get("logo"))
        except site_logo_service.LogoError as exc:
            raise SiteAdminError(str(exc)) from exc

    if service_id is None:
        service_id = db.add_service(name, "📦", sales_channels=["bot"], site_enabled=site_enabled)
        db.get_conn().services.update_one(
            {"id": service_id},
            {"$set": {"site_name": name, "active": 0}},
        )
        created = True
    else:
        if not db.get_service(service_id):
            raise SiteAdminError("Service introuvable.")
        db.get_conn().services.update_one(
            {"id": service_id},
            {"$set": {"site_name": name, "site_enabled": site_enabled}},
        )
        created = False
    logo_change = None
    if logo:
        site_logo_service.save(service_id, *logo)
        logo_change = "updated"
    elif _truthy(form.get("remove_logo")):
        site_logo_service.remove(service_id)
        logo_change = "removed"
    db.audit_event(
        "site_catalog.service_created" if created else "site_catalog.service_updated",
        details={"service_id": service_id, "name": name, "site_enabled": site_enabled, "logo": logo_change},
    )
    return {"service_id": service_id, "name": name, "created": created}


def move_site_offer(form: dict[str, Any]) -> dict[str, Any]:
    """Move one product into another service, which becomes its site category."""
    try:
        offer_id = int(form.get("offer_id"))
        service_id = int(form.get("service_id"))
    except (TypeError, ValueError) as exc:
        raise SiteAdminError("Produit ou service invalide.") from exc
    offer = db.get_offer(offer_id)
    service = db.get_service(service_id)
    if not offer or offer.get("archived") == 1:
        raise SiteAdminError("Produit introuvable.")
    if not service or service.get("archived") == 1:
        raise SiteAdminError("Service introuvable.")
    name = str(offer.get("site_name") or offer.get("name") or "Produit")
    if int(offer.get("service_id") or 0) == service_id:
        return {"offer_id": offer_id, "name": name, "service_name": str(service.get("site_name") or service.get("name") or "")}
    try:
        db.move_offer(offer_id, service_id)
    except ValueError as exc:
        raise SiteAdminError(str(exc)) from exc
    # The destination service name is the category. A leftover product-category
    # label would keep the offer in the folder it just left.
    db.get_conn().offers.update_one({"id": offer_id}, {"$unset": {"site_category_name": ""}})
    service_name = str(service.get("site_name") or service.get("name") or "Service")
    db.audit_event("site_catalog.offer_moved", details={"offer_id": offer_id, "service_id": service_id})
    return {"offer_id": offer_id, "name": name, "service_name": service_name}


def move_catalog_offer(form: dict[str, Any]) -> dict[str, Any]:
    """Move one product into another service, which becomes its site category."""
    try:
        offer_id = int(form.get("offer_id"))
        service_id = int(form.get("service_id"))
    except (TypeError, ValueError) as exc:
        raise SiteAdminError("Produit ou service invalide.") from exc
    offer = db.get_offer(offer_id)
    service = db.get_service(service_id)
    if not offer or offer.get("archived") == 1:
        raise SiteAdminError("Offre introuvable.")
    if not service or service.get("archived") == 1:
        raise SiteAdminError("Service introuvable.")
    if int(offer.get("service_id") or 0) == service_id:
        raise SiteAdminError("Ce produit est déjà dans ce service.")
    try:
        db.move_offer(offer_id, service_id)
    except ValueError as exc:
        raise SiteAdminError(str(exc)) from exc
    if not db.is_official_subscriptions_service(service):
        db.get_conn().offers.update_one({"id": offer_id}, {"$unset": {"site_category_name": ""}})
    name = str(offer.get("site_name") or offer.get("name") or "Produit")
    service_name = str(service.get("site_name") or service.get("name") or "Service")
    db.audit_event("site_catalog.offer_moved", details={
        "offer_id": offer_id, "service_id": service_id, "name": name,
    })
    return {"offer_id": offer_id, "name": name, "service_name": service_name}


def rename_product_category(form: dict[str, Any]) -> dict[str, Any]:
    """Rename the site category of products that still share the official folder."""
    name = str(form.get("name") or "").strip()[:120]
    if not name:
        raise SiteAdminError("Le nom de la catégorie est obligatoire.")
    offer_ids = []
    for part in str(form.get("offer_ids") or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            offer_ids.append(int(part))
        except ValueError as exc:
            raise SiteAdminError("Produit invalide.") from exc
    if not offer_ids:
        raise SiteAdminError("Catégorie introuvable.")
    updated = 0
    for offer_id in offer_ids:
        offer = db.get_offer(offer_id)
        service = db.get_service(int(offer.get("service_id"))) if offer else None
        if not offer or offer.get("archived") == 1 or not service:
            continue
        if not db.is_official_subscriptions_service(service):
            continue
        db.get_conn().offers.update_one({"id": offer_id}, {"$set": {"site_category_name": name}})
        updated += 1
    if not updated:
        raise SiteAdminError("Catégorie introuvable.")
    db.audit_event("site_catalog.category_renamed", details={"name": name, "offer_ids": offer_ids})
    return {"name": name, "updated": updated}


def _duration(form: dict[str, Any], prefix: str, default: int, *, allow_zero: bool, label: str) -> tuple[int, str, int]:
    unit = warranty_service.normalize_duration_unit(form.get(f"{prefix}_unit"))
    raw = str(form.get(f"{prefix}_value") or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise SiteAdminError(f"{label} invalide.") from exc
    if value < (0 if allow_zero else 1) or value > 10_000:
        raise SiteAdminError(f"{label} invalide.")
    return value, unit, warranty_service.duration_to_days(value, unit)


def _image_url(value: Any) -> str:
    url = str(value or "").strip()[:1000]
    if url and not storefront_service._safe_image_url(url):
        raise SiteAdminError("L’image doit être une adresse https://…")
    return url


def save_offer(form: dict[str, Any]) -> dict[str, Any]:
    """Create or edit the storefront side of a shared offer.

    Name, description, warranty, period and visibility written here stay on
    ``site_*`` fields. The bot's description, price, note and ``active`` flag
    are left untouched. Stock mode is shared. A new product starts off on the bot.
    """
    offer_id = _optional_id(form.get("offer_id"), "Offre")
    previous = db.get_offer(offer_id) if offer_id is not None else None
    if offer_id is not None and not previous:
        raise SiteAdminError("Offre introuvable.")

    service_id = _optional_id(form.get("service_id"), "Service")
    if service_id is None:
        raise SiteAdminError("Choisissez un service.")
    service = db.get_service(service_id)
    if not service or service.get("archived") == 1:
        raise SiteAdminError("Service introuvable.")

    name = str(form.get("name") or "").strip()[:120]
    if not name:
        raise SiteAdminError("Le nom du produit est obligatoire.")
    category = str(form.get("site_category") or "").strip().lower()
    if category and category not in storefront_service.CATEGORY_LABELS:
        raise SiteAdminError("Catégorie inconnue.")

    tn_price = _dinar_millimes(form.get("tn_price"))
    period_value, period_unit, period_days = _duration(form, "period", 30, allow_zero=False, label="Durée")
    warranty_value, warranty_unit, warranty_days = _duration(form, "warranty", 0, allow_zero=True, label="Garantie")
    note = "NW" if warranty_days == 0 else warranty_service.format_duration(warranty_value, warranty_unit)
    description = _site_description(form.get("site_description_fr"))
    unlimited = str(form.get("stock_mode") or "inventory") == "unlimited"
    image = None
    if str(form.get("image") or "").strip():
        try:
            image = site_logo_service.decode_offer_image(form.get("image"))
        except site_logo_service.LogoError as exc:
            raise SiteAdminError(str(exc)) from exc
    fields: dict[str, Any] = {
        "site_name": name,
        "site_note": note,
        "site_delivery_delay": str(form.get("delivery_delay") or "").strip()[:120] or "Instantané après confirmation",
        "site_period_days": period_days,
        "site_period_value": period_value,
        "site_period_unit": period_unit,
        "site_warranty_days": warranty_days,
        "site_warranty_value": warranty_value,
        "site_warranty_unit": warranty_unit,
        "site_enabled": _truthy(form.get("site_enabled", "1")),
        "site_featured": _truthy(form.get("site_featured")),
        "site_badge": str(form.get("site_badge") or "").strip()[:48],
        "site_category": category,
        "site_description_fr": description,
        "site_image_url": _image_url(form.get("site_image_url")),
    }
    category_name = str(form.get("site_category_name") or "").strip()[:120]
    unset_category = not (db.is_official_subscriptions_service(service) and category_name)
    if not unset_category:
        fields["site_category_name"] = category_name

    conn = db.get_conn()
    if previous is None:
        initial_inventory = str(form.get("initial_inventory") or "").strip()
        items = inventory_service.parse_bulk_inventory(initial_inventory) if initial_inventory and not unlimited else []
        offer_id = db.add_offer(
            service_id,
            name,
            0,
            0,
            "",
            description="",
            active=False,
            unlimited_stock=unlimited,
            sales_channels=["bot"],
            tn_price_millimes=tn_price,
            site_enabled=fields["site_enabled"],
            site_name=name,
            site_note=note,
            site_delivery_delay=fields["site_delivery_delay"],
            site_description_fr=description,
            site_image_url=fields["site_image_url"],
            site_category=category,
            site_badge=fields["site_badge"],
            site_featured=fields["site_featured"],
            site_period_days=period_days,
            site_period_value=period_value,
            site_period_unit=period_unit,
            site_warranty_days=warranty_days,
            site_warranty_value=warranty_value,
            site_warranty_unit=warranty_unit,
        )
        if items:
            inventory_service.add_items(offer_id, items)
        if fields.get("site_category_name"):
            conn.offers.update_one(
                {"id": offer_id},
                {"$set": {"site_category_name": fields["site_category_name"]}},
            )
        created = True
    else:
        if int(previous.get("service_id") or 0) != service_id:
            try:
                db.move_offer(offer_id, service_id)
            except ValueError as exc:
                raise SiteAdminError(str(exc)) from exc
        externally_stocked = bool(previous.get("supplier_provider") or previous.get("manual_stock"))
        if not externally_stocked:
            fields["unlimited_stock"] = unlimited
        update: dict[str, Any] = {"$set": fields}
        unset: dict[str, str] = {}
        if tn_price is None:
            unset["tn_price_millimes"] = ""
        else:
            fields["tn_price_millimes"] = tn_price
        if unset_category:
            unset["site_category_name"] = ""
        if unset:
            update["$unset"] = unset
        conn.offers.update_one({"id": offer_id}, update)
        if not externally_stocked and previous.get("unlimited_stock") and not unlimited:
            inventory_service.sync_offer_stock(offer_id)
        created = False

    image_change = None
    if image:
        site_logo_service.save_offer_image(offer_id, *image)
        image_change = "uploaded"
    elif previous and site_logo_service.is_uploaded_offer_image(previous.get("site_image_url")) and (
        _truthy(form.get("remove_image")) or fields["site_image_url"] != previous.get("site_image_url")
    ):
        site_logo_service.remove_offer_image(offer_id)
        if fields["site_image_url"] and not site_logo_service.is_uploaded_offer_image(fields["site_image_url"]):
            conn.offers.update_one({"id": offer_id}, {"$set": {"site_image_url": fields["site_image_url"]}})
        image_change = "removed"

    db.audit_event(
        "site_catalog.offer_created" if created else "site_catalog.offer_updated",
        details={
            "offer_id": offer_id,
            "service_id": service_id,
            "name": name,
            "tn_price_millimes": tn_price,
            "image": image_change,
        },
    )
    return {"offer_id": offer_id, "name": name, "created": created, "tn_price_millimes": tn_price}


_SPENT_STATUSES = {"confirmed", "delivered", "partial"}


def customers(params: dict[str, list[str]]) -> dict[str, Any]:
    """Storefront accounts with their wallet, orders and spending, newest activity first."""
    search = _first(params, "search").lower()[:80]
    conn = db.get_conn()
    carts_by_customer: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for line in _site_lines({"cart_reference": {"$exists": True}, "customer_id": {"$ne": None}}):
        carts_by_customer.setdefault(int(line["customer_id"]), {}).setdefault(line["cart_reference"], []).append(line)
    balances = {
        int(row["customer_id"]): int(row.get("balance_millimes") or 0)
        for row in conn.storefront_wallets.find({}, {"customer_id": 1, "balance_millimes": 1})
    }

    rows = []
    for account in conn.storefront_customers.find({"email_verified": {"$ne": False}}, {"password_hash": 0}):
        customer_id = int(account["id"])
        summaries = sorted(
            (
                site_orders_service._cart_summary(reference, lines)
                for reference, lines in carts_by_customer.get(customer_id, {}).items()
            ),
            key=lambda cart: cart["created_at"],
            reverse=True,
        )
        rows.append({
            "id": customer_id,
            "name": account.get("name", ""),
            "email": account.get("email", ""),
            "phone": account.get("phone", ""),
            "balance_millimes": balances.get(customer_id, 0),
            "carts_count": len(summaries),
            "pending_count": sum(1 for cart in summaries if cart["status"] == "to_verify"),
            "total_spent_millimes": sum(
                cart["total_millimes"] - cart["refunded_millimes"]
                for cart in summaries
                if cart["status"] in _SPENT_STATUSES
            ),
            "created_at": account.get("created_at"),
            "last_order_at": summaries[0]["created_at"] if summaries else None,
            "carts": summaries[:20],
        })

    if search:
        rows = [
            row for row in rows
            if search in f"{row['name']} {row['email']} {row['phone']}".lower()
        ]
    rows.sort(key=lambda row: (row["last_order_at"] or 0, row["created_at"] or 0), reverse=True)
    return {"ok": True, **_paginate(rows, params)}
