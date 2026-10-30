"""Offer-card parsing and rendering for Telegram catalog messages."""

from __future__ import annotations

import html
import re

import database as db
from app.bot.methods_presentation import (
    is_bmc_vip_product,
    join_methods_description_title,
    strip_bmc_vip_term_suffix,
    without_method_detail_rows,
)
from app.bot.presentation import _is_single_emoji, render_stored_rich_text
from app.domain import warranty_service
from config import CURRENCY
from i18n import TRANSLATIONS

OFFER_CARD_TEMPLATE_VARIABLES = (
    "name", "catalog_name", "catalog_emoji", "product_name", "price",
    "currency", "stock", "sold", "warranty", "description", "period",
    "bulk_price", "bulk_quantity",
)


def offer_detail_fields(description: str, note: str) -> dict[str, str]:
    fields = {
        "note": note or "Full warranty",
        "duration": "30 Days",
        "mail": "Included",
        "access": "Ready-made account",
        "description": "",
    }
    remaining = []
    aliases = {
        "warranty": "note",
        "duration": "duration",
        "mail": "mail",
        "email": "mail",
        "access": "access",
        "type": "access",
    }
    for raw_line in (description or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            key, value = [part.strip() for part in line.split(":", 1)]
            normalized = key.lower().replace(" ", "_")
            target = aliases.get(normalized)
            if target and value:
                fields[target] = value
                continue
        remaining.append(line)
    fields["description"] = "\n".join(f"\u2022 {item}" for item in remaining)
    if not fields["description"]:
        fields["description"] = "\U0001f525 Premium benefits included"
    return fields


def parse_duration_input(
    value: str, *, allow_zero: bool = False,
) -> tuple[int, str, int]:
    """Parse durations such as ``30``, ``3 months`` or ``2 years``."""
    match = re.fullmatch(
        r"\s*(\d+)\s*([\w\u0600-\u06fféû]*)\s*", str(value or ""), re.I,
    )
    if not match:
        raise ValueError("invalid duration")
    amount = int(match.group(1))
    if amount < 0 or (not allow_zero and amount < 1):
        raise ValueError("invalid duration")
    raw_unit = match.group(2).lower()
    month_units = {
        "m", "mo", "month", "months", "mois", "شهر", "أشهر", "اشهر",
    }
    year_units = {
        "y", "yr", "year", "years", "an", "ans", "année", "années",
        "سنة", "سنوات",
    }
    unit = (
        "months" if raw_unit in month_units
        else "years" if raw_unit in year_units
        else "days"
    )
    return amount, unit, warranty_service.duration_to_days(amount, unit)


def decomposed_bulk_price_template(lang: str = "en") -> str:
    """Return the editable bulk-price row used by product card templates."""
    labels = {"fr": "PRIX EN GROS", "en": "BULK PRICE", "ar": "سعر الجملة"}
    return (
        f"📦 *{labels.get(lang, labels['en'])}:* "
        "{bulk_price} {currency} × {bulk_quantity}+"
    )


def decompose_legacy_bulk_line(template: str, lang: str = "en") -> str:
    """Upgrade the retired all-in-one bulk placeholder into editable fields."""
    return str(template).replace(
        "{bulk_price_line}", f"{decomposed_bulk_price_template(lang)}\n",
    )


def _bulk_tier_label(name: str, *, html_template: bool) -> str:
    cleaned = " ".join(str(name or "").split())[:40]
    if html_template:
        return html.escape(cleaned)
    return cleaned.replace("*", "").replace("_", "").replace("`", "")


def expand_bulk_tier_lines(template: str, tiers: list[dict]) -> str:
    """Turn the single wholesale row into one row per saved tier."""
    if len(tiers) <= 1:
        return template
    labels = ("BULK PRICE", "PRIX EN GROS", "سعر الجملة")
    html_template = str(template).lstrip().startswith(("[[HTML]]", "[HTML]"))
    output = []
    for line in str(template).splitlines():
        if "{bulk_price}" not in line and "{bulk_quantity}" not in line:
            output.append(line)
            continue
        for index, tier in enumerate(tiers):
            named = line
            label = _bulk_tier_label(tier.get("name"), html_template=html_template)
            if label and not any(marker in named for marker in labels):
                named = named.replace("{bulk_price}", f"{label}: {{bulk_price}}", 1)
            elif label:
                for marker in labels:
                    if marker in named:
                        named = named.replace(marker, label, 1)
                        break
            named = named.replace("{bulk_price}", f"{{bulk_price_{index}}}")
            named = named.replace("{bulk_quantity}", f"{{bulk_quantity_{index}}}")
            output.append(named)
    return "\n".join(output)


def offer_description_text(offer: dict, lang: str) -> str:
    """Render the stored product description for its dedicated screen."""
    if lang == "ar" and offer.get("description_ar"):
        description = offer.get("description_ar")
    elif lang == "fr" and offer.get("description_fr"):
        description = offer.get("description_fr")
    else:
        description = offer.get("description")
    rendered = render_stored_rich_text(
        (description or "").strip() or "—", parse_legacy_markdown=False,
    )
    rendered = re.sub(
        r"</?(?:code|pre)(?:\s[^>]*)?>", "", rendered, flags=re.I,
    )
    return re.sub(
        r"<blockquote\b[^>]*>", "<blockquote>", rendered, flags=re.I,
    )


def _product_title_emoji(offer: dict, service: dict | None) -> str:
    """Return the product emoji as Telegram HTML for the card title.

    A Premium emoji is stored as a custom emoji id with an empty Unicode
    fallback, so the title must render that icon instead of the plain box.
    """
    product_unicode = str(offer.get("emoji") or "").strip()
    product_custom = str(offer.get("custom_emoji_id") or "").strip()
    service_unicode = str(
        offer.get("service_emoji") or (service or {}).get("emoji") or ""
    ).strip()
    service_custom = str(
        offer.get("service_custom_emoji_id")
        or (service or {}).get("custom_emoji_id")
        or ""
    ).strip()
    if product_custom and product_custom.isascii():
        emoji_id = product_custom
        fallback = product_unicode or service_unicode or "📦"
    elif product_unicode:
        return html.escape(product_unicode)
    elif service_custom and service_custom.isascii():
        emoji_id = service_custom
        fallback = service_unicode or "📦"
    else:
        return html.escape(service_unicode or "📦")
    if not _is_single_emoji(fallback):
        fallback = "📦"
    return (
        f'<tg-emoji emoji-id="{html.escape(emoji_id, quote=True)}">'
        f"{html.escape(fallback)}</tg-emoji>"
    )


def offer_description_notice_text(lang: str) -> str:
    """Render the admin-editable warning shown on the compact product card."""
    notice = (
        db.get_text_override("offer_description_notice", lang)
        or TRANSLATIONS.get("offer_description_notice", {}).get(lang)
        or TRANSLATIONS["offer_description_notice"]["en"]
    )
    return render_stored_rich_text(notice)


def compact_offer_text(
    offer: dict, lang: str, *, show_stored_description: bool = False,
) -> str:
    """Build the compact public offer card used with or without an image.

    Customers see the shared warning in place of the description. The admin
    product screen passes ``show_stored_description`` so the saved text appears.
    """
    service = None
    if not offer.get("service_name") and offer.get("service_id") is not None:
        service = db.get_service(offer.get("service_id"))
    catalog_name = str(
        offer.get("service_name_ar")
        if lang == "ar" and offer.get("service_name_ar")
        else offer.get("service_name")
        or ((service or {}).get("name_ar") if lang == "ar" else "")
        or (service or {}).get("name")
        or ""
    ).strip()
    catalog_emoji = _product_title_emoji(offer, service)
    product_name = str(
        offer.get("name_ar")
        if lang == "ar" and offer.get("name_ar")
        else offer.get("name") or ""
    ).strip()
    display_name = product_name
    if catalog_name and not product_name.casefold().startswith(
        catalog_name.casefold(),
    ):
        display_name = f"{catalog_name} — {product_name}"
    title = html.escape(display_name)
    if catalog_emoji:
        title = f"{catalog_emoji} {title}".strip()
    rendered_notice = offer_description_notice_text(lang)
    description_html = (
        offer_description_text(offer, lang)
        if show_stored_description else rendered_notice
    )
    warranty = warranty_service.offer_warranty_label(offer, lang=lang)
    period = warranty_service.offer_period_label(offer, lang=lang)
    try:
        raw_price = offer.get("price")
        price = (
            "—" if raw_price is None or str(raw_price).strip() == ""
            else f"{float(raw_price):.2f}"
        )
    except (TypeError, ValueError):
        price = str(offer.get("price") or "—")
    sold = db.offer_sold_count(offer.get("id", 0))
    currency = str(offer.get("currency") or CURRENCY)
    stock_val = (
        "∞" if offer.get("unlimited_stock") else int(offer.get("stock") or 0)
    )
    tiers = db.list_bulk_tiers(offer)
    bulk_enabled = bool(tiers)
    bulk_quantity = tiers[0]["min_quantity"] if tiers else 0
    bulk_price = tiers[0]["unit_price"] if tiers else 0.0
    template = db.get_text_override("offer_card_template", lang)
    if not template:
        template = (
            TRANSLATIONS.get("offer_card_template", {}).get(lang)
            or TRANSLATIONS["offer_card_template"]["en"]
        )
    replacements = {
        "name": f"<b>{title}</b>",
        "catalog_name": html.escape(catalog_name),
        "catalog_emoji": catalog_emoji,
        "product_name": html.escape(product_name),
        "price": f"<b>{html.escape(str(price))}</b>",
        "currency": f"<b>{html.escape(currency)}</b>",
        "stock": f"<b>{html.escape(str(stock_val))}</b>",
        "sold": f"<b>{html.escape(str(sold))}</b>",
        "period": f"<b>{html.escape(str(period))}</b>",
        "warranty": f"<b>{html.escape(str(warranty)[:120])}</b>",
        "description": description_html,
        "bulk_price": f"<b>{bulk_price:.2f}</b>",
        "bulk_quantity": f"<b>{bulk_quantity}</b>",
    }
    for index, tier in enumerate(tiers):
        replacements[f"bulk_price_{index}"] = f"<b>{tier['unit_price']:.2f}</b>"
        replacements[f"bulk_quantity_{index}"] = f"<b>{tier['min_quantity']}</b>"
    tokens = {}
    protected_template = str(template)
    is_methods_catalog = catalog_name.casefold() == "methods"
    if offer.get("period_visible") is False:
        protected_template = "\n".join(
            line for line in protected_template.splitlines()
            if "{period}" not in line
        )
    if offer.get("warranty_visible") is False:
        protected_template = "\n".join(
            line for line in protected_template.splitlines()
            if "{warranty}" not in line
        )
    if (
        "{period}" not in protected_template
        and not is_methods_catalog
        and offer.get("period_visible") is not False
    ):
        period_label = {"fr": "PÉRIODE", "ar": "المدة"}.get(lang, "PERIOD")
        period_row = (
            f"📅 <b>{period_label}:</b> {{period}}"
            if protected_template.startswith(("[[HTML]]", "[HTML]"))
            else f"📅 *{period_label}:* {{period}}"
        )
        template_lines = protected_template.splitlines()
        price_index = next(
            (
                index for index, line in enumerate(template_lines)
                if "{price}" in line
            ),
            0,
        )
        template_lines.insert(price_index + 1, period_row)
        protected_template = "\n".join(template_lines)
    if bulk_enabled:
        protected_template = decompose_legacy_bulk_line(protected_template, lang)
    else:
        protected_template = protected_template.replace("{bulk_price_line}", "")
        protected_template = "\n".join(
            line for line in protected_template.splitlines()
            if "{bulk_price}" not in line and "{bulk_quantity}" not in line
        )
    if is_methods_catalog:
        protected_template = "\n".join(
            line for line in protected_template.splitlines()
            if "{stock}" not in line and "{sold}" not in line
            and not (
                "{warranty}" in line
                and not any(
                    token in line
                    for token in ("{name}", "{product_name}", "{catalog_name}")
                )
            )
        )
    for wrapped_name in (
        "<b>{name}</b>", "<strong>{name}</strong>", "<code>{name}</code>",
        "**{name}**", "*{name}*", "`{name}`",
    ):
        protected_template = protected_template.replace(wrapped_name, "{name}")
    value_placeholders = (
        "price|currency|stock|sold|warranty|bulk_price|bulk_quantity"
    )
    protected_template = re.sub(
        rf"<code>([^<]*(?:\{{(?:{value_placeholders})\}})[^<]*)</code>",
        r"\1", protected_template, flags=re.I,
    )
    protected_template = re.sub(
        rf"`([^`\n]*(?:\{{(?:{value_placeholders})\}})[^`\n]*)`",
        r"\1", protected_template,
    )
    if bulk_enabled:
        protected_template = expand_bulk_tier_lines(protected_template, tiers)
    for index, (key, value) in enumerate(replacements.items()):
        token = f"OFCARDTOKEN{index}X"
        protected_template = protected_template.replace(f"{{{key}}}", token)
        tokens[token] = value
    rendered = render_stored_rich_text(protected_template)
    for token, value in tokens.items():
        rendered = rendered.replace(token, value)
    if is_methods_catalog:
        rendered = without_method_detail_rows(rendered)
    rendered = re.sub(
        r"<blockquote\b[^>]*>", "<blockquote>", rendered, flags=re.I,
    )
    visible_card = html.unescape(re.sub(r"<[^>]+>", "", rendered))
    visible_notice = html.unescape(
        re.sub(r"<[^>]+>", "", rendered_notice),
    ).strip()
    if (
        not show_stored_description
        and visible_notice
        and visible_notice != "—"
        and visible_notice not in visible_card
    ):
        rendered = f"{rendered.rstrip()}\n{rendered_notice}"
    if show_stored_description and len(rendered) > 3500:
        rendered = rendered[:3500].rsplit("<", 1)[0] + "…"
    if is_methods_catalog:
        rendered = join_methods_description_title(rendered)
        if is_bmc_vip_product(offer):
            rendered = strip_bmc_vip_term_suffix(rendered)
    return rendered


__all__ = [
    "OFFER_CARD_TEMPLATE_VARIABLES",
    "compact_offer_text",
    "decompose_legacy_bulk_line",
    "decomposed_bulk_price_template",
    "offer_detail_fields",
    "offer_description_notice_text",
    "offer_description_text",
    "parse_duration_input",
]
