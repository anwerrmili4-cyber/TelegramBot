"""Site flash sales: a lower dinar price for a limited time, then the old price returns.

The Telegram bot keeps its USDT price. Only ``tn_price_millimes`` moves, and
only for a product the storefront is already selling. Starting a sale also
emails every verified customer in the same shop notification design.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

import database as db
from app.domain import storefront_notification_service, storefront_service

_MIN_MINUTES = 15
_MAX_MINUTES = 7 * 24 * 60
_UNSET = {
    "site_flash_original_millimes": "",
    "site_flash_price_millimes": "",
    "site_flash_ends_at": "",
    "site_flash_started_at": "",
    "site_flash_label": "",
}


class FlashError(ValueError):
    """French message safe to show in the admin panel."""


def expire_due() -> int:
    """Put the regular dinar price back on every sale whose time is over."""
    now = int(time.time())
    due = list(db.get_conn().offers.find(
        {"site_flash_active": True, "site_flash_ends_at": {"$lte": now}},
        {"id": 1},
    ))
    restored = 0
    for row in due:
        if _restore(int(row["id"])):
            restored += 1
    return restored


def price_edit_block(offer: dict[str, Any] | None, new_millimes: int | None) -> str:
    """Why a catalog save must leave the dinar price alone, or an empty string."""
    if not offer or not offer.get("site_flash_active"):
        return ""
    if int(offer.get("site_flash_ends_at") or 0) <= int(time.time()):
        return ""
    current = int(offer.get("tn_price_millimes") or 0)
    if new_millimes == current:
        return ""
    return "Une vente flash est en cours sur ce produit. Arrêtez-la avant de changer le prix."


def admin_list() -> dict[str, Any]:
    expire_due()
    products = []
    for service in storefront_service.catalog()["services"]:
        for offer in service["offers"]:
            products.append(_row(offer))
    products.sort(key=lambda row: (row["service_name"].casefold(), row["name"].casefold(), row["id"]))
    active = [row for row in products if row["flash_active"]]
    active.sort(key=lambda row: (row["flash_ends_at"], row["id"]))
    return {"ok": True, "products": products, "active": active}


def start(form: dict[str, Any]) -> dict[str, Any]:
    """Lower one site price, then email the verified customers."""
    expire_due()
    offer_id = _offer_id(form.get("offer_id"))
    offer = db.get_offer(offer_id)
    if not offer:
        raise FlashError("Ce produit est introuvable.")
    if not storefront_service._offer_is_listed(offer_id):
        raise FlashError("Ce produit n'est pas en vente sur le site.")
    now = int(time.time())
    if offer.get("site_flash_active") and int(offer.get("site_flash_ends_at") or 0) > now:
        raise FlashError("Une vente flash est déjà en cours sur ce produit.")

    current = int(offer.get("tn_price_millimes") or 0)
    if current <= 0:
        raise FlashError("Ce produit n'a pas de prix en dinars.")
    sale = _millimes(form.get("flash_price"))
    if sale >= current:
        raise FlashError("Le prix flash doit être inférieur au prix actuel.")
    minutes = _minutes(form.get("duration_minutes"))
    label = _label(form.get("label"))
    name = _product_name(offer)
    title = _optional(form.get("title"), 3, 120, "Le titre") or f"{name} en vente flash"
    body = _optional(form.get("body"), 8, 2000, "Le message") or _default_body(name, current, sale, minutes)
    title = title[:120]
    if len(title) < 3:
        raise FlashError("Le titre doit faire entre 3 et 120 caractères.")

    people = storefront_notification_service._verified_people(db.get_conn())
    audience = len(people)
    if audience < 1:
        raise FlashError("Aucun client vérifié pour le moment.")
    if audience > storefront_notification_service._MAX_AUDIENCE:
        raise FlashError(f"{storefront_notification_service._MAX_AUDIENCE} clients maximum par annonce.")

    ends_at = now + minutes * 60
    result = db.get_conn().offers.update_one(
        {"id": offer_id, "site_flash_active": {"$ne": True}},
        {"$set": {
            "tn_price_millimes": sale,
            "site_flash_active": True,
            "site_flash_original_millimes": current,
            "site_flash_price_millimes": sale,
            "site_flash_ends_at": ends_at,
            "site_flash_started_at": now,
            "site_flash_label": label,
        }},
    )
    if result.modified_count != 1:
        raise FlashError("Une vente flash est déjà en cours sur ce produit.")

    try:
        storefront_notification_service.publish(
            {"kind": "flash", "title": title, "body": body, "offer_id": offer_id},
            allow_flash=True,
        )
    except storefront_notification_service.NotificationError:
        _restore(offer_id)
        raise

    db.audit_event("site_flash.started", details={
        "offer_id": offer_id,
        "from_millimes": current,
        "to_millimes": sale,
        "minutes": minutes,
        "ends_at": ends_at,
        "audience": audience,
    })
    noun = "client" if audience == 1 else "clients"
    return {
        "ok": True,
        "offer_id": offer_id,
        "message": (
            f"Vente flash lancée : {name} passe de {_money(current)} à {_money(sale)} "
            f"pendant {_duration_label(minutes)}. Annonce envoyée à {audience} {noun}."
        ),
    }


def stop(form: dict[str, Any]) -> dict[str, Any]:
    """Restore the dinar price before the sale reaches its end."""
    expire_due()
    offer_id = _offer_id(form.get("offer_id"))
    offer = db.get_conn().offers.find_one({"id": offer_id, "site_flash_active": True})
    if not offer:
        raise FlashError("Cette vente flash est déjà terminée.")
    original = int(offer.get("site_flash_original_millimes") or 0)
    name = _product_name(offer)
    if not _restore(offer_id):
        raise FlashError("Cette vente flash est déjà terminée.")
    db.audit_event("site_flash.stopped", details={"offer_id": offer_id, "restored_millimes": original})
    return {
        "ok": True,
        "offer_id": offer_id,
        "message": f"Vente flash arrêtée. {name} revient à {_money(original)}.",
    }


def _restore(offer_id: int) -> bool:
    conn = db.get_conn()
    offer = conn.offers.find_one({"id": int(offer_id), "site_flash_active": True})
    if not offer:
        return False
    original = offer.get("site_flash_original_millimes")
    update: dict[str, Any] = {"$set": {"site_flash_active": False}, "$unset": dict(_UNSET)}
    if original is not None:
        update["$set"]["tn_price_millimes"] = int(original)
    result = conn.offers.update_one({"id": int(offer_id), "site_flash_active": True}, update)
    return result.modified_count == 1


def _row(offer: dict[str, Any]) -> dict[str, Any]:
    price = int(offer.get("price_millimes") or 0)
    compare = int(offer.get("compare_millimes") or 0)
    ends_at = int(offer.get("flash_ends_at") or 0)
    active = compare > price and ends_at > int(time.time())
    return {
        "id": int(offer["id"]),
        "name": str(offer.get("name") or ""),
        "service_name": str(offer.get("service_name") or ""),
        "price_millimes": price,
        "regular_millimes": compare if active else price,
        "flash_price_millimes": price if active else 0,
        "flash_active": active,
        "flash_ends_at": ends_at if active else 0,
        "flash_label": str(offer.get("flash_label") or "") if active else "",
        "available": bool(offer.get("available")),
    }


def _offer_id(value: Any) -> int:
    try:
        offer_id = int(value)
    except (TypeError, ValueError) as exc:
        raise FlashError("Choisis un produit du site.") from exc
    if offer_id <= 0:
        raise FlashError("Choisis un produit du site.")
    return offer_id


def _millimes(value: Any) -> int:
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not text:
        raise FlashError("Indique le prix flash.")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise FlashError("Le prix flash doit être un nombre, par exemple 19,500.") from exc
    if amount <= 0 or amount > 100_000:
        raise FlashError("Le prix flash doit être compris entre 0,001 et 100 000 DT.")
    return int((amount * 1000).to_integral_value())


def _minutes(value: Any) -> int:
    try:
        minutes = int(str(value or "").strip())
    except (TypeError, ValueError) as exc:
        raise FlashError("Choisis une durée.") from exc
    if minutes < _MIN_MINUTES or minutes > _MAX_MINUTES:
        raise FlashError("La durée doit être comprise entre 15 minutes et 7 jours.")
    return minutes


def _label(value: Any) -> str:
    label = str(value or "").strip()
    if not label:
        return "Vente flash"
    if not 2 <= len(label) <= 24:
        raise FlashError("Le libellé doit faire entre 2 et 24 caractères.")
    return label


def _optional(value: Any, minimum: int, maximum: int, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not minimum <= len(text) <= maximum:
        raise FlashError(f"{label} doit faire entre {minimum} et {maximum} caractères.")
    return text


def _product_name(offer: dict[str, Any]) -> str:
    return str(offer.get("site_name") or offer.get("name") or "Ce produit").strip()[:120] or "Ce produit"


def _money(millimes: int) -> str:
    return f"{int(millimes) / 1000:.3f}".replace(".", ",") + " DT"


def _percent(current: int, sale: int) -> int:
    if current <= 0 or sale >= current:
        return 0
    return max(1, (current - sale) * 100 // current)


def _duration_label(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "1 jour" if days == 1 else f"{days} jours"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 heure" if hours == 1 else f"{hours} heures"
    hours, rest = divmod(minutes, 60)
    if hours <= 0:
        return f"{rest} minutes"
    return f"{hours} h {rest:02d}"


def _default_body(name: str, current: int, sale: int, minutes: int) -> str:
    return (
        f"{name} passe de {_money(current)} à {_money(sale)} "
        f"(-{_percent(current, sale)} %). La vente dure {_duration_label(minutes)}."
    )
