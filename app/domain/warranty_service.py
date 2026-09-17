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
            return format_duration(configured_value, unit, lang)

    if val is not None:
        if val <= 0:
            return "NW"
        if lang == "fr":
            return f"{val} j"
        if lang == "ar":
            return f"{val} يوم"
        return f"{val} day{'s' if val != 1 else ''}"

    note = str(legacy_note or "").strip()
    if not note or note.upper() in {"NW", "NO WARRANTY", "SANS GARANTIE", "0"}:
        return "NW"
    match = re.search(r"(\d{1,3})\s*(?:d|day|days|j|jour|jours)", note, re.I)
    if match:
        d = int(match.group(1))
        if lang == "fr":
            return f"{d} j"
        if lang == "ar":
            return f"{d} يوم"
        return f"{d} day{'s' if d != 1 else ''}"
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
    return format_duration(value or 30, unit, lang)
