"""Customer-facing delivery content and waiting-state presentation."""

from __future__ import annotations

import html

from app.domain import inventory_service


def numbered_delivery_content(items):
    """Number delivered accounts while preserving their exact content."""
    cleaned = []
    for item in items or []:
        value = inventory_service.clean_delivery_value(item)
        if value:
            cleaned.append(value)
    return "\n\n".join(
        f"{index}.\n{value}"
        for index, value in enumerate(cleaned, start=1)
    )


def manual_delivery_waiting_text(lang, order_id):
    messages = {
        "fr": (
            f"⏳ <b>Commande #{order_id} confirmée</b>\n\nVeuillez patienter : "
            "le bot vous prépare un nouveau compte. Votre produit sera "
            "disponible très bientôt."
        ),
        "en": (
            f"⏳ <b>Order #{order_id} confirmed</b>\n\nPlease wait — the bot is "
            "releasing a fresh account for you. Your product will be available "
            "very soon."
        ),
        "ar": (
            f"⏳ <b>تم تأكيد الطلب #{order_id}</b>\n\nيرجى الانتظار — يقوم "
            "البوت بتجهيز حساب جديد لك. سيكون منتجك متاحاً قريباً جداً."
        ),
    }
    return messages.get(lang, messages["en"])


def bmc_vip_channel_message(lang, link):
    """Tell the buyer their already-allocated private channel link."""
    safe_link = html.escape(str(link or ""), quote=True)
    texts = {
        "fr": (
            "✅ <b>BMC VIP est actif</b>\n\n"
            "Voici ton lien de canal privé. Rejoins-le pour récupérer toutes les "
            "méthodes, et les nouvelles chaque jour.\n\n"
            f'<a href="{safe_link}">{safe_link}</a>'
        ),
        "ar": (
            "✅ <b>BMC VIP مفعّل</b>\n\n"
            "هذا رابط قناتك الخاصة. انضم إليها لتحصل على كل الطرق، "
            "والطرق الجديدة كل يوم.\n\n"
            f'<a href="{safe_link}">{safe_link}</a>'
        ),
    }
    return texts.get(
        lang,
        (
            "✅ <b>BMC VIP is active</b>\n\n"
            "Here is your private channel link. Join it to claim every method, "
            "and the new ones every day.\n\n"
            f'<a href="{safe_link}">{safe_link}</a>'
        ),
    )


__all__ = [
    "bmc_vip_channel_message",
    "manual_delivery_waiting_text",
    "numbered_delivery_content",
]
