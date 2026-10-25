"""Admin-facing previews for editable Telegram text templates."""

from __future__ import annotations

import html
import os
import re

import database as db
from app.bot.offer_cards import (
    OFFER_CARD_TEMPLATE_VARIABLES,
    decompose_legacy_bulk_line,
)
from app.bot.presentation import render_stored_rich_text
from i18n import TRANSLATIONS

TERMS_OF_SERVICE_URL = os.environ.get(
    "HP_TERMS_OF_SERVICE_URL",
    "https://bot.ourblackmarket.com/terms",
).strip()


def preview_link_placeholders(value: str) -> str:
    """Replace variable URLs that Telegram would reject in a preview."""

    def real_url(match):
        url = (
            TERMS_OF_SERVICE_URL
            if match.group(2) == "terms_url"
            else "https://t.me"
        )
        return f"href={match.group(1)}{html.escape(url, quote=True)}{match.group(1)}"

    return re.sub(r"href=([\"'])\{(\w+)\}\1", real_url, str(value or ""))


def render_admin_text_preview(key: str, value: str, lang: str = "en") -> str:
    """Render editor previews without treating template underscores as Markdown."""
    value = preview_link_placeholders(value)
    if key != "offer_card_template":
        return render_stored_rich_text(value)
    protected = decompose_legacy_bulk_line(value, lang)
    for wrapped_name in (
        "<b>{name}</b>", "<strong>{name}</strong>", "<code>{name}</code>",
        "**{name}**", "*{name}*", "`{name}`",
    ):
        protected = protected.replace(wrapped_name, "{name}")
    value_placeholders = (
        "price|currency|stock|sold|warranty|bulk_price|bulk_quantity"
    )
    protected = re.sub(
        rf"<code>([^<]*(?:\{{(?:{value_placeholders})\}})[^<]*)</code>",
        r"\1", protected, flags=re.I,
    )
    protected = re.sub(
        rf"`([^`\n]*(?:\{{(?:{value_placeholders})\}})[^`\n]*)`",
        r"\1", protected,
    )
    tokens = {}
    for index, variable in enumerate(OFFER_CARD_TEMPLATE_VARIABLES):
        token = f"OFCARDPREVIEWTOKEN{index}X"
        protected = protected.replace(f"{{{variable}}}", token)
        if variable == "name":
            placeholder = "<b>{catalog_emoji} {catalog_name} — {product_name}</b>"
        elif variable in {
            "catalog_name", "catalog_emoji", "product_name", "price",
            "currency", "stock", "sold", "period", "warranty", "bulk_price",
            "bulk_quantity",
        }:
            placeholder = f"<b>{{{variable}}}</b>"
        elif variable == "description":
            placeholder = "{description}"
        else:
            placeholder = f"<code>{{{variable}}}</code>"
        tokens[token] = placeholder
    rendered = render_stored_rich_text(protected)
    for token, placeholder in tokens.items():
        rendered = rendered.replace(token, placeholder)
    return rendered


def admin_text_preview(key: str) -> str:
    """Build the bilingual preview shown to administrators."""
    en_current = (
        db.get_text_override(key, "en")
        or TRANSLATIONS.get(key, {}).get("en")
        or "—"
    )
    ar_current = (
        db.get_text_override(key, "ar")
        or TRANSLATIONS.get(key, {}).get("ar")
        or "—"
    )
    rendered_en = render_admin_text_preview(key, en_current, "en")
    rendered_ar = render_admin_text_preview(key, ar_current, "ar")
    return (
        f"✏️ <b>{html.escape(key)}</b>\n\n"
        f"🇬🇧 <b>English Preview :</b>\n{rendered_en}\n\n"
        f"🇸🇦 <b>Arabic Preview :</b>\n{rendered_ar}\n\n"
        "Choisissez la langue pour modifier ce texte :"
    )


__all__ = [
    "TERMS_OF_SERVICE_URL",
    "admin_text_preview",
    "preview_link_placeholders",
    "render_admin_text_preview",
]
