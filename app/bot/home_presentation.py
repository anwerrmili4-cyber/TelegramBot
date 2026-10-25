"""Presentation for the bot home screen and sales ranking."""

from __future__ import annotations

import html

import database as db
from app.bot.customer_text import premium_customer_text
from app.bot.presentation import _is_single_emoji, render_stored_rich_text
from app.bot.text_previews import TERMS_OF_SERVICE_URL
from app.domain.offer_stock_control import keep_best_bot_price


def top_selling_products_text(lang: str) -> str:
    """Build the main-menu ranking from paid catalog orders."""
    titles = {
        "fr": "🔥 <b>TOP 5 DES PRODUITS LES PLUS VENDUS</b>",
        "en": "🔥 <b>TOP 5 BEST-SELLING PRODUCTS</b>",
        "ar": "🔥 <b>أفضل 5 منتجات مبيعاً</b>",
    }
    ranked = []
    for offer in keep_best_bot_price(db.list_catalog_offers()):
        sold = db.offer_sold_count(offer.get("id"))
        if sold > 0:
            ranked.append((sold, offer))
    ranked.sort(key=lambda item: (-item[0], int(item[1].get("id") or 0)))
    lines = []
    for position, (_sold, offer) in enumerate(ranked[:5], start=1):
        fallback = str(
            offer.get("emoji") or offer.get("service_emoji") or "📦",
        ).strip()
        if not _is_single_emoji(fallback):
            fallback = "📦"
        emoji_id = str(
            offer.get("custom_emoji_id")
            or offer.get("service_custom_emoji_id")
            or "",
        ).strip()
        icon = fallback
        if emoji_id and emoji_id.isascii():
            icon = f"[[TGEMOJI:{emoji_id}:{fallback.encode('utf-8').hex()}]]"
        name = html.escape(str(offer.get("name") or "Product"))
        lines.append(f"{position} - {icon} <b>{name}</b>")
    if not lines:
        empty = {
            "fr": "Aucune vente pour le moment.",
            "en": "No sales yet.",
            "ar": "لا توجد مبيعات بعد.",
        }
        lines.append(empty.get(lang, empty["en"]))
    return render_stored_rich_text(
        "[[HTML]]" + f"{titles.get(lang, titles['en'])}\n\n" + "\n".join(lines),
        parse_legacy_markdown=False,
    )


def welcome_home_text(user=None, lang="en") -> str:
    """Build the admin-editable welcome shown on every home visit."""
    first_name = str(getattr(user, "first_name", "") or "user").strip()
    return premium_customer_text(
        lang,
        "welcome",
        first_name=first_name,
        terms_url=TERMS_OF_SERVICE_URL,
    )


__all__ = ["top_selling_products_text", "welcome_home_text"]
