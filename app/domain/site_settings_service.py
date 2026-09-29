"""Tunisian storefront settings the admin can change without a redeploy.

Values live in the MongoDB ``settings`` collection. The environment-driven
constants in ``config`` stay as defaults for a fresh database.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import database as db
from config import TN_MANUAL_PAYMENT_METHODS, TN_TND_PER_USDT, TN_WHATSAPP_NUMBER

PAYMENT_METHOD_LABELS = {"d17": "D17", "flouci": "Flouci"}

_WHATSAPP_KEY = "tn_whatsapp_number"
_RATE_KEY = "tn_tnd_per_usdt"
_METHODS_KEY = "tn_payment_methods"


class SiteSettingsError(ValueError):
    """Raised with a French message the admin UI shows as-is."""


def whatsapp_number() -> str:
    digits = re.sub(r"\D", "", str(db.get_setting(_WHATSAPP_KEY, "") or ""))
    return digits or TN_WHATSAPP_NUMBER


def tnd_per_usdt() -> float:
    try:
        rate = float(db.get_setting(_RATE_KEY, TN_TND_PER_USDT))
    except (TypeError, ValueError):
        return TN_TND_PER_USDT
    return rate if rate > 0 else TN_TND_PER_USDT


def payment_methods() -> list[str]:
    stored = db.get_setting(_METHODS_KEY)
    if stored is None:
        return sorted(TN_MANUAL_PAYMENT_METHODS)
    chosen = {value.strip().lower() for value in str(stored).split(",")}
    return sorted(chosen & set(PAYMENT_METHOD_LABELS))


def get() -> dict[str, Any]:
    return {
        "whatsapp_number": whatsapp_number(),
        "tnd_per_usdt": tnd_per_usdt(),
        "payment_methods": payment_methods(),
        "available_payment_methods": [
            {"id": key, "label": label} for key, label in PAYMENT_METHOD_LABELS.items()
        ],
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def save(form: dict[str, Any]) -> dict[str, Any]:
    """Validate and store every storefront setting at once."""
    digits = re.sub(r"\D", "", str(form.get("whatsapp_number") or ""))
    if len(digits) == 8:
        digits = f"216{digits}"
    if not re.fullmatch(r"\d{10,15}", digits):
        raise SiteSettingsError("Numéro WhatsApp invalide : indique l'indicatif, par exemple 216 21 994 132.")

    try:
        rate = Decimal(str(form.get("tnd_per_usdt") or "").replace(",", "."))
    except InvalidOperation as exc:
        raise SiteSettingsError("Le taux TND / USDT doit être un nombre.") from exc
    if not Decimal("0.5") <= rate <= Decimal("50"):
        raise SiteSettingsError("Le taux TND / USDT doit être compris entre 0,5 et 50.")

    methods = [key for key in PAYMENT_METHOD_LABELS if _truthy(form.get(f"payment_{key}"))]
    if not methods:
        raise SiteSettingsError("Active au moins un moyen de paiement.")

    db.set_setting(_WHATSAPP_KEY, digits)
    db.set_setting(_RATE_KEY, str(rate.normalize()))
    db.set_setting(_METHODS_KEY, ",".join(methods))
    db.audit_event("site_settings.updated", details={"whatsapp_number": digits, "tnd_per_usdt": str(rate), "payment_methods": methods})
    return get()
