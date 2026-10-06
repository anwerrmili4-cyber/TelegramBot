"""Tunisian storefront settings the admin can change without a redeploy.

Values live in the MongoDB ``settings`` collection. The environment-driven
constants in ``config`` stay as defaults for a fresh database.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import database as db
from config import TN_MANUAL_PAYMENT_METHODS, TN_TND_PER_USDT, TN_WHATSAPP_NUMBER

PAYMENT_METHOD_LABELS = {
    "d17": "D17",
    "flouci": "Flouci",
    "izi": "IZI",
    "wafacash": "Wafa Cash",
    "virement_postal": "Virement postal",
}
POSTAL_METHOD = "virement_postal"
POSTAL_ACCOUNT_LABEL = "Carte e-dinar"
POSTAL_DESTINATION = "5359403634747440"
MAX_DETAILS_LENGTH = 300

_WHATSAPP_KEY = "tn_whatsapp_number"
_RATE_KEY = "tn_tnd_per_usdt"
_METHODS_KEY = "tn_payment_methods"
_DETAILS_KEY = "tn_payment_details"


class SiteSettingsError(ValueError):
    """Raised with a French message the admin UI shows as-is."""


def whatsapp_number() -> str:
    """Still used by the Telegram bot's manual D17/Flouci hand-off."""
    digits = re.sub(r"\D", "", str(db.get_setting(_WHATSAPP_KEY, "") or ""))
    return digits or TN_WHATSAPP_NUMBER


def tnd_per_usdt() -> float:
    try:
        rate = float(db.get_setting(_RATE_KEY, TN_TND_PER_USDT))
    except (TypeError, ValueError):
        return TN_TND_PER_USDT
    return rate if rate > 0 else TN_TND_PER_USDT


def _stored_details() -> dict[str, Any]:
    try:
        stored = json.loads(str(db.get_setting(_DETAILS_KEY, "") or "{}"))
    except ValueError:
        stored = {}
    return stored if isinstance(stored, dict) else {}


def payment_methods() -> list[str]:
    stored = db.get_setting(_METHODS_KEY)
    if stored is None:
        chosen = set(TN_MANUAL_PAYMENT_METHODS)
    else:
        chosen = {value.strip().lower() for value in str(stored).split(",") if value.strip()}
        # A shop that saved its methods before postal transfer existed keeps it
        # on until an administrator explicitly saves the new setting.
        if POSTAL_METHOD not in chosen and POSTAL_METHOD not in _stored_details():
            chosen.add(POSTAL_METHOD)
    return [key for key in PAYMENT_METHOD_LABELS if key in chosen]


def payment_details() -> dict[str, str]:
    """Where the customer sends the money, per method, as the admin wrote it."""
    stored = _stored_details()
    details = {}
    for key in PAYMENT_METHOD_LABELS:
        value = str(stored.get(key) or "")[:MAX_DETAILS_LENGTH]
        if not value and key == POSTAL_METHOD and key not in stored:
            value = POSTAL_DESTINATION
        details[key] = value
    return details


def public_payment_methods() -> list[dict[str, str]]:
    details = payment_details()
    methods = []
    for key in payment_methods():
        item = {"id": key, "label": PAYMENT_METHOD_LABELS[key], "details": details[key]}
        if key == POSTAL_METHOD:
            item["account_label"] = POSTAL_ACCOUNT_LABEL
        methods.append(item)
    return methods


def normalize_method(method: Any) -> str:
    value = str(method or "").strip().lower()
    enabled = payment_methods()
    if value not in enabled:
        labels = ", ".join(PAYMENT_METHOD_LABELS[key] for key in enabled)
        raise ValueError(f"Choisis un moyen de paiement disponible : {labels}.")
    return value


def get() -> dict[str, Any]:
    return {
        "tnd_per_usdt": tnd_per_usdt(),
        "payment_methods": payment_methods(),
        "payment_details": payment_details(),
        "available_payment_methods": [
            {"id": key, "label": label} for key, label in PAYMENT_METHOD_LABELS.items()
        ],
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def save(form: dict[str, Any]) -> dict[str, Any]:
    """Validate and store every storefront setting at once."""
    try:
        rate = Decimal(str(form.get("tnd_per_usdt") or "").replace(",", "."))
    except InvalidOperation as exc:
        raise SiteSettingsError("Le taux TND / USDT doit être un nombre.") from exc
    if not Decimal("0.5") <= rate <= Decimal("50"):
        raise SiteSettingsError("Le taux TND / USDT doit être compris entre 0,5 et 50.")

    methods = [key for key in PAYMENT_METHOD_LABELS if _truthy(form.get(f"payment_{key}"))]
    if not methods:
        raise SiteSettingsError("Active au moins un moyen de paiement.")

    details = payment_details()
    for key in PAYMENT_METHOD_LABELS:
        if f"details_{key}" in form:
            details[key] = str(form.get(f"details_{key}") or "").strip()[:MAX_DETAILS_LENGTH]
    # Persist the postal key even when this form leaves it off. That stops the
    # one-time auto-enable used for shops saved before the method existed.
    if POSTAL_METHOD not in _stored_details() and f"details_{POSTAL_METHOD}" not in form:
        details[POSTAL_METHOD] = details.get(POSTAL_METHOD) or POSTAL_DESTINATION
    missing = [PAYMENT_METHOD_LABELS[key] for key in methods if not details[key]]
    if missing:
        raise SiteSettingsError(
            f"Indique où les clients doivent envoyer l'argent pour : {', '.join(missing)}."
        )

    db.set_setting(_RATE_KEY, str(rate.normalize()))
    db.set_setting(_METHODS_KEY, ",".join(methods))
    db.set_setting(_DETAILS_KEY, json.dumps(details, ensure_ascii=False))
    db.audit_event(
        "site_settings.updated",
        details={"tnd_per_usdt": str(rate), "payment_methods": methods},
    )
    return get()
