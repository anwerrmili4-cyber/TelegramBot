"""Product warranty display helpers."""
from __future__ import annotations

import re
from typing import Any

VALID_DURATION_UNITS = {"days", "months", "years"}


def normalize_duration_unit(unit: Any) -> str:
    value = str(unit or "days").strip().lower()
    return value if value in VALID_DURATION_UNITS else "days"


def duration_to_days(value: Any, unit: Any = "days") -> int:
    """Convert a configured duration to days for expiry calculations."""
    amount = max(0, int(value or 0))
    multiplier = {"days": 1, "months": 30, "years": 365}[normalize_duration_unit(unit)]
    return amount * multiplier


def display_duration(value: Any, unit: Any = "days", lang: str = "en") -> str:
    """Show a customer duration in months, except short spans and long years.

    Less than 30 days stays in days. Exact 30-day groups, and exactly one
    year, are shown in months. More than one year keeps its original unit.
    A length that is not a whole month is left unchanged.
    """
    amount = max(0, int(value or 0))
    normalized = normalize_duration_unit(unit)
    if normalized == "years":
        if amount == 1:
            return format_duration(12, "months", lang)
        return format_duration(amount, "years", lang)
    if normalized == "months":
        return format_duration(amount, "months", lang)
    if amount == 365:
        return format_duration(12, "months", lang)
    if amount < 30 or amount % 30 or amount // 30 > 12:
        return format_duration(amount, "days", lang)
    return format_duration(amount // 30, "months", lang)


def format_duration(value: Any, unit: Any = "days", lang: str = "en") -> str:
    """Format a duration using its administrator-selected unit."""
    amount = max(0, int(value or 0))
    normalized = normalize_duration_unit(unit)
    labels = {
        "en": {
            "days": "day" if amount == 1 else "days",
            "months": "month" if amount == 1 else "months",
            "years": "year" if amount == 1 else "years",
        },
        "fr": {"days": "j", "months": "mois", "years": "an" if amount == 1 else "ans"},
        "ar": {"days": "يوم", "months": "شهر", "years": "سنة"},
    }
    return f"{amount} {labels.get(lang, labels['en'])[normalized]}"


def format_warranty(
    days: Any,
    legacy_note: str = "",
    lang: str = "en",
    *,
    value: Any = None,
    unit: Any = "days",
) -> str:
    """Format warranty label: 0 days -> NW, >0 -> X days/j/يوم."""
    try:
        val = int(days) if days is not None else None
    except (TypeError, ValueError):
        val = None

    if value is not None:
        try:
            configured_value = int(value)
        except (TypeError, ValueError):
            configured_value = None
        if configured_value is not None:
            if configured_value <= 0:
                return "NW"
            return display_duration(configured_value, unit, lang)

    if val is not None:
        if val <= 0:
            return "NW"
        return display_duration(val, "days", lang)

    note = str(legacy_note or "").strip()
    if not note or note.upper() in {"NW", "NO WARRANTY", "SANS GARANTIE", "0"}:
        return "NW"
    match = re.search(r"(\d{1,3})\s*(?:d|day|days|j|jour|jours)", note, re.I)
    if match:
        d = int(match.group(1))
        return display_duration(d, "days", lang)
    return note


def has_full_warranty(item: dict[str, Any] | None) -> bool:
    """Return whether warranty covers the product's complete configured period."""
    item = item or {}
    try:
        warranty_days = int(item.get("warranty_days") or 0)
        period_days = int(item.get("period_days") or 0)
    except (TypeError, ValueError):
        return False
    return period_days > 0 and warranty_days == period_days


def offer_warranty_label(offer: dict[str, Any] | None, lang: str = "en") -> str:
    """Return the warranty text stored on an offer (0 -> NW)."""
    offer = offer or {}
    if offer.get("warranty_visible") is False:
        return ""
    if has_full_warranty(offer):
        return "FW"
    return format_warranty(
        offer.get("warranty_days"), offer.get("note", ""), lang,
        value=offer.get("warranty_value"), unit=offer.get("warranty_unit", "days"),
    )


def order_warranty_label(order: dict[str, Any] | None, lang: str = "en") -> str:
    """Return the warranty text stored on an order (0 -> NW)."""
    order = order or {}
    if has_full_warranty(order):
        return "FW"
    return format_warranty(
        order.get("warranty_days"), order.get("warranty", ""), lang,
        value=order.get("warranty_value"), unit=order.get("warranty_unit", "days"),
    )


def offer_period_label(offer: dict[str, Any] | None, lang: str = "en") -> str:
    """Return the product period using months/years when configured."""
    offer = offer or {}
    if offer.get("period_visible") is False:
        return ""
    value = offer.get("period_value")
    unit = offer.get("period_unit", "days")
    if value is None:
        value = offer.get("period_days")
        unit = "days"
    try:
        if int(value or 0) <= 0:
            value = offer.get("warranty_value", offer.get("warranty_days", 30))
            unit = offer.get("warranty_unit", "days")
    except (TypeError, ValueError):
        value, unit = 30, "days"
    return display_duration(value or 30, unit, lang)
