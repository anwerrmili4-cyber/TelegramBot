"""
HEAVENPREM — Bot Telegram de vente de services numériques.
Point d'entrée principal. Exécuté en long polling pour rester réactif 24/7.
"""
import asyncio
import contextlib
import html
import io
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

from pymongo import ReturnDocument
from telegram import Bot, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

import admin
import database as db
import keyboards as kb
from app import support_bridge
from app.domain import (
    affiliate_service,
    buyer_api_service,
    inventory_service,
    lovable_service,
    loyalty_service,
    order_service,
    payment_service,
    reseller_service,
    support_service,
    wallet_service,
    warranty_service,
)
from config import (
    ADMIN_ID,
    BINANCE_PAY_ID,
    BOT_TOKEN,
    BYBIT_UID,
    CLICK_REPORT_CHAT_ID,
    CURRENCY,
    DEFAULT_LANG,
    MEMBERSHIP_CACHE_SECONDS,
    REQUIRED_CHANNEL,
    SHOP_NAME,
    SOLANA_ALLOWED_USER_ID,
    SOLANA_DEPOSIT_ADDRESS,
    SOLANA_MIN_CONFIRMATIONS,
    SOLANA_MIN_DEPOSIT,
    SUPPORT_TICKET_CHANNEL_ID,
    USDT_EVM_ADDRESS,
    configuration_issues,
    public_base_url_from_environment,
)
from i18n import TRANSLATIONS, status_label, t

_handlers = [logging.StreamHandler()]
if not os.environ.get("VERCEL") and not os.environ.get("RAILWAY_ENVIRONMENT_ID"):
    os.makedirs("logs", exist_ok=True)
    _handlers.insert(0, logging.FileHandler("logs/bot.log"))
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
    handlers=_handlers,
)
log = logging.getLogger("bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BROADCAST_BATCH_SIZE = max(1, min(20, int(os.environ.get("HP_BROADCAST_BATCH_SIZE", "15"))))
BROADCAST_BATCH_DELAY = max(0.25, float(os.environ.get("HP_BROADCAST_BATCH_DELAY", "0.55")))
_broadcast_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telegram-broadcast")
_submitted_broadcast_jobs: set[int] = set()
_broadcast_jobs_lock = threading.Lock()

# états utilisateurs en mémoire (clé = user_id)
# "await_txid": order_id  |  "adm_setprice": offer_id
#  "adm_deliver": order_id
class PendingStates:
    """Small mapping facade backed by MongoDB for serverless-safe conversations."""
    def __contains__(self, user_id):
        return db.get_pending_state(user_id) is not None

    def __setitem__(self, user_id, state):
        db.set_pending_state(user_id, state)

    def get(self, user_id, default=None):
        return db.get_pending_state(user_id) or default

    def pop(self, user_id, default=None):
        return db.pop_pending_state(user_id, default)


PENDING = PendingStates()

# Positive-only membership cache. Non-members are never cached, and the
# explicit Verify button always performs a live Telegram check.
_membership_cache: dict[tuple[int, str], float] = {}


def cache_required_channel_member(user_id: int) -> None:
    channel = str(_normalize_required_chat(REQUIRED_CHANNEL))
    if channel and MEMBERSHIP_CACHE_SECONDS > 0:
        _membership_cache[(int(user_id), channel)] = (
            time.monotonic() + MEMBERSHIP_CACHE_SECONDS
        )


async def is_required_channel_member_cached(bot, user_id: int) -> bool:
    """Avoid Telegram API round trips for recently verified members."""
    channel = str(_normalize_required_chat(REQUIRED_CHANNEL))
    key = (int(user_id), channel)
    now = time.monotonic()
    if _membership_cache.get(key, 0) > now:
        return True
    _membership_cache.pop(key, None)
    allowed = await is_required_channel_member(bot, user_id)
    if allowed:
        cache_required_channel_member(user_id)
    if len(_membership_cache) > 10_000:
        expired = [cache_key for cache_key, expiry in _membership_cache.items() if expiry <= now]
        for cache_key in expired:
            _membership_cache.pop(cache_key, None)
    return allowed

async def block_non_channel_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prevent customers from bypassing the required channel via direct commands."""
    user = update.effective_user
    if not user or user.id == ADMIN_ID:
        return
    if update.callback_query and update.callback_query.data == "verify_channel_join":
        return
    message_text = getattr(update.effective_message, "text", "") or ""
    if message_text.startswith("/start"):
        return
    if await is_required_channel_member_cached(context.bot, user.id):
        return
    lang = lang_of(user.id)
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        premium_customer_text(lang, "channel_join_required"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.channel_join_keyboard(lang),
    )
    raise ApplicationHandlerStop

def _interaction_button_name(query):
    """Return the exact visible label of a pressed inline button when available."""
    callback_data = str(getattr(query, "data", "") or "")
    markup = getattr(getattr(query, "message", None), "reply_markup", None)
    for row in getattr(markup, "inline_keyboard", None) or []:
        for button in row:
            if str(getattr(button, "callback_data", "") or "") == callback_data:
                label = " ".join(str(getattr(button, "text", "") or "").split())
                if label:
                    return label

    action, _, value = callback_data.partition(":")
    names = {
        "home": "Main menu", "catalog": "Catalog", "catalog_request": "Request a product",
        "lovable": "Lovable Unlimited Credit", "lovable_howto": "Lovable instructions",
        "lovable_buy": "Lovable plans", "lovable_trial": "Lovable free trial",
        "lovable_download": "Download Lovable extension",
        "orders": "My orders", "account": "My account", "affiliate": "Affiliate program",
        "affiliate_copy": "Copy referral link", "support": "Support", "language": "Language",
        "topup": "Top up balance",
        "topup_txid": "Verify Binance top-up", "topup_bybit": "Verify Bybit top-up",
        "topup_bsc": "Top up with BSC",
        "topup_polygon": "Top up with Polygon",
        "topup_sol": "Top up with Solana",
        "verify_channel_join": "Verify membership",
        "paid": "Verify payment with TXID",
        "paid_chain": "Submit blockchain TXID", "continue_pay": "Continue payment",
        "manual_reply": "Reply to administrator",
        "confirm_buy": "Create new order", "cancel_buy": "Cancel order",
        "pay_wallet": "Pay with wallet", "pay_binance": "Pay with Binance Pay",
        "pay_bybit": "Pay with Bybit Pay",
        "pay_bsc": "Pay with USDT BSC", "pay_polygon": "Pay with USDT Polygon",
        "orders_export": "Export orders", "rating": "Rate purchase",
        "support_cat": "Support category", "support_order": "Support order",
        "svc": "Open service", "off": "Open offer", "buy": "Buy now",
        "buyq": "Select quantity", "qty_page": "Change quantity page", "tour": "Onboarding",
    }
    name = names.get(action) or action.replace("_", " ").strip().title() or "Unknown button"
    return f"{name} ({value})" if value else name


async def notify_admin_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send customer button clicks to the private click-report channel."""
    user = update.effective_user
    if not user or user.id == ADMIN_ID or not update.callback_query:
        return

    raw_name = user.full_name or user.first_name or "Unknown user"
    display_name = html.escape(raw_name)
    raw_username = user.username or ""
    username = f"@{html.escape(raw_username)}" if raw_username else "Not provided"
    profile = f'<a href="tg://user?id={user.id}">{display_name}</a>'
    header = (
        "<b>CUSTOMER CLICK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Customer:</b> {profile}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>Telegram ID:</b> <code>{user.id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )

    media_message = None
    if update.callback_query:
        query = update.callback_query
        raw_callback = str(query.data or "")
        button_name = _interaction_button_name(query)
        source_text = (
            getattr(query.message, "text", None)
            or getattr(query.message, "caption", None)
            or ""
        )
        details = (
            "<b>Interaction:</b> Button click\n"
            f"<b>Button:</b> {html.escape(button_name[:200])}\n"
            f"<b>Action code:</b> <code>{html.escape(raw_callback[:500])}</code>"
        )
        if source_text:
            details += (
                "\n\n<b>Screen before the click:</b>\n"
                f"<blockquote>{html.escape(source_text[:1200])}</blockquote>"
            )
        interaction_type = "button"
        interaction_action = raw_callback
        interaction_content = button_name
        interaction_screen = source_text
    elif update.effective_message:
        message = update.effective_message
        content = message.text or message.caption or ""
        if content:
            interaction_type = "command" if str(content).startswith("/") else "message"
            type_name = "Command" if interaction_type == "command" else "Text message"
            interaction_action = str(content).split(maxsplit=1)[0] if interaction_type == "command" else ""
            interaction_content = content
            details = (
                f"<b>Interaction:</b> {type_name}\n"
                "<b>Customer sent:</b>\n"
                f"<blockquote>{html.escape(content[:2500])}</blockquote>"
            )
        elif getattr(message, "photo", None):
            details = "<b>Interaction:</b> Photo\n<b>Customer sent:</b> A photo (copied below)"
            interaction_type, interaction_action, interaction_content = "media", "photo", "Photo"
            media_message = message
        elif getattr(message, "document", None):
            document = message.document
            filename = html.escape(str(getattr(document, "file_name", "") or "Unnamed file"))
            details = f"<b>Interaction:</b> Document\n<b>Customer sent:</b> {filename} (copied below)"
            interaction_type, interaction_action, interaction_content = "media", "document", filename
            media_message = message
        elif getattr(message, "video", None):
            details = "<b>Interaction:</b> Video\n<b>Customer sent:</b> A video (copied below)"
            interaction_type, interaction_action, interaction_content = "media", "video", "Video"
            media_message = message
        elif getattr(message, "voice", None):
            details = "<b>Interaction:</b> Voice message\n<b>Customer sent:</b> A voice message (copied below)"
            interaction_type, interaction_action, interaction_content = "media", "voice", "Voice message"
            media_message = message
        else:
            details = "<b>Interaction:</b> Other message\n<b>Customer sent:</b> Unsupported Telegram content"
            interaction_type, interaction_action, interaction_content = "other", "unsupported", "Unsupported content"
        interaction_screen = ""
    else:
        return

    try:
        db.log_interaction(
            user.id,
            first_name=user.first_name or "",
            full_name=raw_name,
            username=raw_username,
            interaction_type=interaction_type,
            action=interaction_action,
            content=interaction_content,
            screen=interaction_screen,
        )
    except Exception:
        log.exception("Unable to persist interaction from user %s", user.id)

    try:
        await context.bot.send_message(
            CLICK_REPORT_CHAT_ID,
            f"{header}{details}",
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        if media_message and hasattr(context.bot, "copy_message"):
            chat = getattr(media_message, "chat", None)
            chat_id = getattr(chat, "id", None) or getattr(media_message, "chat_id", None)
            message_id = getattr(media_message, "message_id", None)
            if chat_id and message_id:
                await context.bot.copy_message(
                    chat_id=CLICK_REPORT_CHAT_ID,
                    from_chat_id=chat_id,
                    message_id=message_id,
                )
    except Exception:
        log.exception("Unable to notify admin about interaction from user %s", user.id)

async def block_banned_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id != ADMIN_ID and db.is_user_banned(user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Accès suspendu.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("⛔ Votre accès à cette boutique est suspendu.")
        raise ApplicationHandlerStop


async def block_maintenance_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lock the entire customer bot during maintenance while preserving admin access."""
    user = update.effective_user
    if not user or user.id == ADMIN_ID:
        return
    settings = db.shop_settings()
    if not settings["maintenance_enabled"]:
        return

    message = settings["maintenance_message"].strip() or (
        "The bot is temporarily under maintenance. Please try again later."
    )
    if update.callback_query:
        await update.callback_query.answer("Maintenance mode is active.", show_alert=True)
    if update.effective_message:
        await update.effective_message.reply_text(
            "🛠️ <b>BOT UNDER MAINTENANCE</b>\n\n"
            f"{html.escape(message)}\n\n"
            "Please try again later.",
            parse_mode=ParseMode.HTML,
        )
    raise ApplicationHandlerStop





def numbered_delivery_content(items):
    """Number delivered accounts while preserving their exact content."""
    cleaned = []
    for item in items or []:
        value = inventory_service.clean_delivery_value(item)
        if value:
            cleaned.append(value)
    return "\n\n".join(f"{index}.\n{value}" for index, value in enumerate(cleaned, start=1))

def lang_of(user_id):
    lang = db.get_user_lang(user_id) or DEFAULT_LANG
    return lang if lang in {"en", "ar"} else "en"


async def notify_successful_referral(context, referrer_id):
    """Notify the referrer after every valid referral and each reward milestone."""
    stats = affiliate_service.get_stats(referrer_id)
    lang = lang_of(referrer_id)
    target = affiliate_service.REFERRAL_TARGET
    if stats["referrals"] and stats["referrals"] % target == 0:
        key = "affiliate_ten_success"
        values = {"balance": f"{stats['balance_cents'] / 100:.2f}"}
    else:
        key = "affiliate_referral_success"
        values = {
            "progress": stats["progress"],
            "remaining": stats["remaining"],
        }
    await context.bot.send_message(
        referrer_id,
        premium_customer_text(lang, key, **values),
        parse_mode=ParseMode.HTML,
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


def parse_duration_input(value: str, *, allow_zero: bool = False) -> tuple[int, str, int]:
    """Parse durations such as ``30``, ``3 months`` or ``2 years``."""
    match = re.fullmatch(r"\s*(\d+)\s*([\w\u0600-\u06fféû]*)\s*", str(value or ""), re.I)
    if not match:
        raise ValueError("invalid duration")
    amount = int(match.group(1))
    if amount < 0 or (not allow_zero and amount < 1):
        raise ValueError("invalid duration")
    raw_unit = match.group(2).lower()
    month_units = {"m", "mo", "month", "months", "mois", "شهر", "أشهر", "اشهر"}
    year_units = {"y", "yr", "year", "years", "an", "ans", "année", "années", "سنة", "سنوات"}
    unit = "months" if raw_unit in month_units else "years" if raw_unit in year_units else "days"
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


def compact_offer_text(offer: dict, lang: str) -> str:
    """Build the compact public offer card used with or without an image."""
    service = None
    if not offer.get("service_name") and offer.get("service_id") is not None:
        service = db.get_service(offer.get("service_id"))
    catalog_name = str(
        offer.get("service_name_ar") if lang == "ar" and offer.get("service_name_ar")
        else offer.get("service_name")
        or ((service or {}).get("name_ar") if lang == "ar" else "")
        or (service or {}).get("name")
        or ""
    ).strip()
    catalog_emoji = str(
        offer.get("service_emoji")
        or (service or {}).get("emoji")
        or offer.get("emoji")
        or "📦"
    ).strip()
    product_name = str(
        offer.get("name_ar") if lang == "ar" and offer.get("name_ar")
        else offer.get("name") or ""
    ).strip()
    display_name = product_name
    if catalog_name and not product_name.casefold().startswith(catalog_name.casefold()):
        display_name = f"{catalog_name} — {product_name}"
    display_name = " ".join(part for part in (catalog_emoji, display_name) if part)
    description = (
        offer.get("description_ar") if lang == "ar" and offer.get("description_ar")
        else offer.get("description")
    )
    description = (description or "").strip() or "—"
    rendered_description = render_stored_rich_text(
        description, parse_legacy_markdown=False,
    )
    # Product descriptions are prose, not source code. Older saved content may
    # contain code/pre wrappers that Telegram renders in blue monospace.
    rendered_description = re.sub(
        r"</?(?:code|pre)(?:\s[^>]*)?>", "", rendered_description, flags=re.I,
    )
    warranty = warranty_service.offer_warranty_label(offer, lang=lang) or "NW"
    period = warranty_service.offer_period_label(offer, lang=lang)
    try:
        raw_price = offer.get("price")
        price = "—" if raw_price is None or str(raw_price).strip() == "" else f"{float(raw_price):.2f}"
    except (TypeError, ValueError):
        price = str(offer.get("price") or "—")
    sold = db.offer_sold_count(offer.get("id", 0))
    currency = str(offer.get("currency") or CURRENCY)
    stock_val = "∞" if offer.get("unlimited_stock") else int(offer.get("stock") or 0)
    bulk_enabled = False
    bulk_quantity = 0
    bulk_price = 0.0
    try:
        bulk_quantity = int(offer.get("bulk_quantity") or 0)
        bulk_price = float(offer.get("bulk_unit_price"))
        if bulk_quantity > 0 and 0 <= bulk_price < float(offer.get("price")):
            bulk_enabled = True
    except (TypeError, ValueError):
        pass
    template = db.get_text_override("offer_card_template", lang)
    if not template:
        template = (
            TRANSLATIONS.get("offer_card_template", {}).get(lang)
            or TRANSLATIONS["offer_card_template"]["en"]
        )
    replacements = {
        "name": f"<b>{html.escape(display_name)}</b>",
        "catalog_name": html.escape(catalog_name),
        "catalog_emoji": html.escape(catalog_emoji),
        "product_name": html.escape(product_name),
        "price": f"<b>{html.escape(str(price))}</b>",
        "currency": f"<b>{html.escape(currency)}</b>",
        "stock": f"<b>{html.escape(str(stock_val))}</b>",
        "sold": f"<b>{html.escape(str(sold))}</b>",
        "period": f"<b>{html.escape(str(period))}</b>",
        "warranty": f"<b>{html.escape(str(warranty)[:120])}</b>",
        "description": rendered_description,
        "bulk_price": f"<b>{bulk_price:.2f}</b>",
        "bulk_quantity": f"<b>{bulk_quantity}</b>",
    }
    # Protect placeholders while parsing Telegram/legacy formatting. Otherwise
    # underscores in names such as ``{bulk_price_line}`` look like italics.
    tokens = {}
    protected_template = str(template)
    is_methods_catalog = catalog_name.casefold() == "methods"
    if "{period}" not in protected_template and not is_methods_catalog:
        period_label = {"fr": "PÉRIODE", "ar": "المدة"}.get(lang, "PERIOD")
        period_row = (
            f"📅 <b>{period_label}:</b> {{period}}"
            if protected_template.startswith(("[[HTML]]", "[HTML]"))
            else f"📅 *{period_label}:* {{period}}"
        )
        template_lines = protected_template.splitlines()
        price_index = next(
            (index for index, line in enumerate(template_lines) if "{price}" in line),
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
            if not any(
                placeholder in line
                for placeholder in ("{stock}", "{sold}", "{warranty}")
            )
        )
    # The complete emoji/catalog/product title is always bold. Remove legacy
    # wrappers around {name} before injecting the canonical bold title.
    for wrapped_name in (
        "<b>{name}</b>", "<strong>{name}</strong>", "<code>{name}</code>",
        "**{name}**", "*{name}*", "`{name}`",
    ):
        protected_template = protected_template.replace(wrapped_name, "{name}")
    value_placeholders = "price|currency|stock|sold|warranty|bulk_price|bulk_quantity"
    # Old customized templates may wrap values in Telegram's monospace/code
    # style. Remove only code wrappers containing response-value variables so
    # the new regular bold typeface is applied consistently.
    protected_template = re.sub(
        rf"<code>([^<]*(?:\{{(?:{value_placeholders})\}})[^<]*)</code>",
        r"\1", protected_template, flags=re.I,
    )
    protected_template = re.sub(
        rf"`([^`\n]*(?:\{{(?:{value_placeholders})\}})[^`\n]*)`",
        r"\1", protected_template,
    )
    for index, (key, value) in enumerate(replacements.items()):
        token = f"OFCARDTOKEN{index}X"
        protected_template = protected_template.replace(f"{{{key}}}", token)
        tokens[token] = value
    rendered = render_stored_rich_text(protected_template)
    for token, value in tokens.items():
        rendered = rendered.replace(token, value)
    if is_methods_catalog:
        rendered = _without_method_detail_rows(rendered)
    return rendered


OFFER_CARD_TEMPLATE_VARIABLES = (
    "name", "catalog_name", "catalog_emoji", "product_name", "price", "currency", "stock", "sold", "warranty", "description",
    "period", "bulk_price", "bulk_quantity",
)


def render_admin_text_preview(key: str, value: str, lang: str = "en") -> str:
    """Render editor previews without treating template underscores as Markdown."""
    if key != "offer_card_template":
        return render_stored_rich_text(value)
    protected = decompose_legacy_bulk_line(value, lang)
    for wrapped_name in (
        "<b>{name}</b>", "<strong>{name}</strong>", "<code>{name}</code>",
        "**{name}**", "*{name}*", "`{name}`",
    ):
        protected = protected.replace(wrapped_name, "{name}")
    value_placeholders = "price|currency|stock|sold|warranty|bulk_price|bulk_quantity"
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
            "catalog_name", "catalog_emoji", "product_name", "price", "currency",
            "stock", "sold", "period", "warranty", "bulk_price", "bulk_quantity",
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
    en_current = db.get_text_override(key, "en") or TRANSLATIONS.get(key, {}).get("en") or "—"
    ar_current = db.get_text_override(key, "ar") or TRANSLATIONS.get(key, {}).get("ar") or "—"
    rendered_en = render_admin_text_preview(key, en_current, "en")
    rendered_ar = render_admin_text_preview(key, ar_current, "ar")
    return (
        f"✏️ <b>{html.escape(key)}</b>\n\n"
        f"🇬🇧 <b>English Preview :</b>\n{rendered_en}\n\n"
        f"🇸🇦 <b>Arabic Preview :</b>\n{rendered_ar}\n\n"
        "Choisissez la langue pour modifier ce texte :"
    )


def custom_emojis_from_message(message):
    """Extract every unique Premium custom emoji from entities or a sticker."""
    found = []
    entities = list(getattr(message, "entities", None) or [])
    entities.extend(getattr(message, "caption_entities", None) or [])
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        emoji_id = getattr(entity, "custom_emoji_id", None)
        if str(entity_type) == "custom_emoji" and emoji_id and emoji_id not in found:
            found.append(emoji_id)
    sticker = getattr(message, "sticker", None)
    sticker_emoji_id = getattr(sticker, "custom_emoji_id", None)
    if sticker_emoji_id and sticker_emoji_id not in found:
        found.append(sticker_emoji_id)
    return found


def custom_emoji_from_message(message):
    """Return the first Premium emoji, the only one Telegram allows as a button icon."""
    emojis = custom_emojis_from_message(message)
    return emojis[0] if emojis else ""


def text_without_custom_emojis(message):
    """Remove Premium emoji placeholders using Telegram's UTF-16 entity offsets."""
    value = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    entities = list(getattr(message, "entities", None) or [])
    entities.extend(getattr(message, "caption_entities", None) or [])
    encoded = bytearray(value.encode("utf-16-le"))
    ranges = []
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        if str(entity_type) == "custom_emoji":
            ranges.append((int(entity.offset) * 2, (int(entity.offset) + int(entity.length)) * 2))
    for start, end in sorted(ranges, reverse=True):
        del encoded[start:end]
    return encoded.decode("utf-16-le").strip()


def text_with_custom_emoji_tokens(message):
    """Preserve every Premium emoji ID and its exact UTF-16 text position."""
    value = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    entities = list(
        (getattr(message, "entities", None) if getattr(message, "text", None) else
         getattr(message, "caption_entities", None)) or []
    )
    encoded = bytearray(value.encode("utf-16-le"))
    replacements = []
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        emoji_id = getattr(entity, "custom_emoji_id", None)
        if str(entity_type) != "custom_emoji" or not emoji_id:
            continue
        start = int(entity.offset) * 2
        end = (int(entity.offset) + int(entity.length)) * 2
        fallback = bytes(encoded[start:end]).decode("utf-16-le")
        token = f"[[TGEMOJI:{emoji_id}:{fallback.encode('utf-8').hex()}]]"
        replacements.append((start, end, token.encode("utf-16-le")))
    for start, end, token in sorted(replacements, reverse=True):
        encoded[start:end] = token
    return encoded.decode("utf-16-le").strip()


def rich_text_from_message(message):
    """Capture Telegram's exact entity-aware HTML from an admin message."""
    html_value = (
        getattr(message, "text_html", None)
        or getattr(message, "caption_html", None)
    )
    if html_value:
        return f"[[HTML]]{html_value}"
    return text_with_custom_emoji_tokens(message)


def _is_single_emoji(value):
    """Check if a string contains an emoji character rather than text or digits."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    if any(c.isascii() and (c.isalnum() or c in "_-/:;=+,.<>?[]{}()!@#$%^&*`~|\\\"'") for c in s):
        return False
    return len(s) <= 8


def render_stored_rich_text(value, *, parse_legacy_markdown=True):
    """Render trusted admin HTML or legacy Markdown/token text as Telegram HTML."""
    raw_value = str(value or "")

    def close_unfinished_tags(rendered):
        """Close formatting tags left open when dashboard fields truncate HTML."""
        # Dashboard text fields can cut content in the middle of an HTML tag
        # (for example ``<tg-emoji emoji-id=\"496...``). Telegram rejects the
        # entire message in that case, so discard only the incomplete tail
        # before balancing the formatting tags that were fully opened.
        rendered = re.sub(r"<[^>]*\Z", "", rendered)
        supported = {
            "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
            "span", "tg-spoiler", "a", "code", "pre", "blockquote", "tg-emoji",
        }
        opened = []
        for match in re.finditer(r"<\s*(/?)\s*([a-zA-Z][\w-]*)(?:\s[^<>]*)?>", rendered):
            closing, tag = match.group(1), match.group(2).lower()
            if tag not in supported:
                continue
            if not closing:
                opened.append(tag)
            elif opened and opened[-1] == tag:
                opened.pop()
        return rendered + "".join(f"</{tag}>" for tag in reversed(opened))

    def render_custom_emoji(match):
        emoji_id, fallback_hex = match.groups()
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            fallback = bytes.fromhex(fallback_hex).decode("utf-8")
            if not _is_single_emoji(fallback):
                fallback = "📦"
            return f'<tg-emoji emoji-id="{emoji_id}">{html.escape(fallback)}</tg-emoji>'
        return ""

    def render_custom_emoji_tokens(rendered):
        return re.sub(
            r"\[\[TGEMOJI:([0-9A-Za-z_-]+):([0-9a-fA-F]+)\]\]",
            render_custom_emoji,
            rendered,
        )

    html_prefix = next(
        (prefix for prefix in ("[[HTML]]", "[HTML]") if raw_value.startswith(prefix)),
        None,
    )
    if html_prefix:
        rendered = raw_value.removeprefix(html_prefix)
        if parse_legacy_markdown:
            rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
            rendered = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", rendered)
            rendered = re.sub(r"_([^_]+)_", r"<i>\1</i>", rendered)
        return close_unfinished_tags(render_custom_emoji_tokens(rendered))
    rendered = html.escape(raw_value)
    if parse_legacy_markdown:
        rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
        rendered = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", rendered)
        rendered = re.sub(r"_([^_]+)_", r"<i>\1</i>", rendered)

    return render_custom_emoji_tokens(rendered)


# ---------------- /start ----------------
def _normalize_required_chat(chat):
    """Convert channel/group config into a Telegram get_chat_member target."""
    chat = str(chat or "").strip()
    if not chat:
        return ""
    if chat.startswith("https://t.me/"):
        chat = chat.removeprefix("https://t.me/").strip("/")
    elif chat.startswith("http://t.me/"):
        chat = chat.removeprefix("http://t.me/").strip("/")
    elif chat.startswith("t.me/"):
        chat = chat.removeprefix("t.me/").strip("/")
    if "/" in chat:
        chat = chat.split("/", 1)[0]
    if re.fullmatch(r"-?\d+", chat):
        return int(chat)
    if chat.startswith("@"):
        return chat
    return f"@{chat}"


async def is_required_channel_member(bot, user_id):
    """Return whether a customer belongs to the required official channel."""
    allowed, _details = await required_membership_status(bot, user_id)
    return allowed


async def required_membership_status(bot, user_id):
    """Return membership result plus per-chat diagnostics for admins/logs."""
    if user_id == ADMIN_ID:
        return True, []
    required_chats = [
        normalized
        for chat in (REQUIRED_CHANNEL,)
        if (normalized := _normalize_required_chat(chat))
    ]
    if not required_chats:
        return True, []
    details = []
    for chat in required_chats:
        resolved_chat = chat
        chat_title = str(chat)
        try:
            # Resolving public usernames first avoids unreliable username-based
            # getChatMember lookups and continues working if Telegram changes
            # the public username while the numeric chat ID stays the same.
            if hasattr(bot, "get_chat"):
                chat_info = await bot.get_chat(chat)
                resolved_chat = chat_info.id
                chat_title = (
                    getattr(chat_info, "title", None)
                    or getattr(chat_info, "full_name", None)
                    or str(chat)
                )

            member = None
            last_error = None
            for attempt in range(2):
                try:
                    member = await bot.get_chat_member(resolved_chat, user_id)
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        await asyncio.sleep(0.25)
            if member is None:
                raise last_error
        except Exception as exc:
            log.warning("Unable to verify membership in %s for %s: %s", chat, user_id, exc)
            detail = {"chat": chat, "ok": False, "error": str(exc)}
            if resolved_chat != chat:
                detail["chat_id"] = resolved_chat
            if chat_title != str(chat):
                detail["title"] = chat_title
            details.append(detail)
            continue
        status = getattr(getattr(member, "status", None), "value", getattr(member, "status", ""))
        status = str(status).lower()
        is_member = status in {"creator", "owner", "administrator", "member"} or (
            status == "restricted" and bool(getattr(member, "is_member", False))
        )
        detail = {"chat": chat, "ok": is_member, "status": status}
        if resolved_chat != chat:
            detail["chat_id"] = resolved_chat
        if chat_title != str(chat):
            detail["title"] = chat_title
        details.append(detail)
    return all(detail["ok"] for detail in details), details


def _format_membership_diagnostics(user_id, details):
    if not details:
        return f"Membership verification failed for <code>{user_id}</code>: no required chats configured."
    lines = [f"Membership verification failed for <code>{user_id}</code>:"]
    for detail in details:
        chat = html.escape(str(detail.get("chat", "")))
        title = html.escape(str(detail.get("title", "")))
        chat_id = html.escape(str(detail.get("chat_id", "")))
        identity = f"<code>{chat}</code>"
        if title and title != chat:
            identity += f" ({title})"
        if chat_id and chat_id != chat:
            identity += f" [<code>{chat_id}</code>]"
        if detail.get("error"):
            error = html.escape(str(detail["error"])[:500])
            lines.append(f"- {identity}: API error: {error}")
        else:
            status = html.escape(str(detail.get("status", "unknown")))
            result = "OK" if detail.get("ok") else "NOT JOINED"
            lines.append(f"- {identity}: {result}, status=<code>{status}</code>")
    return "\n".join(lines)


async def register_start_referral(context, referred_id, referrer_id):
    """Register a preserved start-link referral for later purchase qualification."""
    if not referrer_id:
        return
    affiliate_service.register_referral_link(referred_id, int(referrer_id))


async def send_channel_member_welcome(send, context, user_id, lang):
    """Show the post-verification marketing welcome and unlock the main menu."""
    username = context.bot.username or (await context.bot.get_me()).username
    referral_link = f"https://t.me/{username}?start=ref_{user_id}"
    await send(
        premium_customer_text(
            lang, "channel_member_welcome", shop=SHOP_NAME, link=referral_link,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.home_keyboard(lang, user_id),
    )


def _is_blocked_broadcast_error(exc):
    message = str(exc).lower()
    return "blocked" in message or "chat not found" in message or "deactivated" in message


async def _broadcast_in_batches(
    send_one, *, label, catalog_updates_only=False, catalog_offer_id=None,
):
    """Send concurrently in Telegram-safe chunks, with retries for rate limits."""
    users = [
        row for row in db.list_broadcast_users(
            catalog_updates_only=catalog_updates_only,
            catalog_offer_id=catalog_offer_id,
        )
        if row.get("telegram_id")
    ]

    async def deliver(user):
        user_id = int(user["telegram_id"])
        for attempt in range(3):
            try:
                await send_one(user)
                return 1
            except RetryAfter as exc:
                retry_after = exc.retry_after
                delay = retry_after.total_seconds() if hasattr(retry_after, "total_seconds") else float(retry_after)
                await asyncio.sleep(delay + 0.15)
            except (TimedOut, NetworkError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                log.warning("%s failed for user %s: %s", label, user_id, exc)
                return 0
            except Exception as exc:
                if _is_blocked_broadcast_error(exc):
                    db.mark_broadcast_blocked(user_id)
                else:
                    log.warning("%s failed for user %s: %s", label, user_id, exc)
                return 0
        return 0

    sent = 0
    for offset in range(0, len(users), BROADCAST_BATCH_SIZE):
        batch = users[offset:offset + BROADCAST_BATCH_SIZE]
        sent += sum(await asyncio.gather(*(deliver(user) for user in batch)))
        if offset + BROADCAST_BATCH_SIZE < len(users):
            await asyncio.sleep(BROADCAST_BATCH_DELAY)
    return sent


def _announcement_service_emoji(service, fallback="📦"):
    """Render a service's Unicode or Premium emoji inside announcement text."""
    service = service or {}
    raw_emoji = str(service.get("emoji") or "").strip()
    emoji = raw_emoji if _is_single_emoji(raw_emoji) else fallback
    emoji_id = str(service.get("custom_emoji_id") or "").strip()
    if emoji_id and emoji_id.isascii():
        return f"[[TGEMOJI:{emoji_id}:{emoji.encode('utf-8').hex()}]]"
    return emoji


def _announcement_plain(value):
    """Keep dynamic names from breaking the customizable Markdown template."""
    return str(value or "").replace("*", "").replace("_", " ").replace("`", "").strip()


_METHOD_HIDDEN_DETAIL_LABELS = (
    "duration", "period", "warranty", "stock",
    "durée", "duree", "période", "periode", "garantie",
    "المدة", "الفترة", "الضمان", "المخزون",
)


def _is_method_detail_row(line):
    """Recognize detail rows even when their icon is a Premium emoji tag."""
    visible = html.unescape(re.sub(r"<[^>]+>", "", str(line or ""))).strip()
    # Drop leading Unicode emoji/punctuation and inspect the visible label.
    visible = re.sub(r"^[^0-9A-Za-zÀ-ÖØ-öø-ÿ\u0600-\u06ff]+", "", visible).casefold()
    return any(
        visible == label or visible.startswith(f"{label}:") or visible.startswith(f"{label} :")
        for label in _METHOD_HIDDEN_DETAIL_LABELS
    )


def _without_method_detail_rows(text):
    """Remove duration, warranty and stock rows from a Methods message/card."""
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not _is_method_detail_row(line)
    ).strip()


def _method_announcement_description(value):
    """Render a method description without leaking HTML source into adverts.

    Descriptions captured from Telegram carry the ``[[HTML]]`` marker, which
    lets :func:`render_stored_rich_text` preserve formatting and Premium
    ``tg-emoji`` entities.  Older dashboard values may contain bare HTML;
    those tags are removed (rather than escaped into visible ``<...>`` text),
    while the normal custom-emoji token format remains supported.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("[[HTML]]", "[HTML]", "[[TGEMOJI:")):
        rendered = render_stored_rich_text(raw, parse_legacy_markdown=False)
    else:
        # Treat unmarked HTML as legacy source, not as trusted Telegram HTML.
        # Keep its readable text and let the token renderer restore Premium
        # emoji placeholders where present.
        cleaned = re.sub(r"</?[^>]+>", "", raw)
        rendered = render_stored_rich_text(cleaned, parse_legacy_markdown=False)
    # Product prose must never be shown in monospace just because an old
    # description was saved inside code/pre wrappers.
    return re.sub(r"</?(?:code|pre)(?:\s[^>]*)?>", "", rendered, flags=re.I).strip()


def _method_announcement_text(text, service, offer=None, lang="en"):
    """Replace period/warranty rows with the saved method description."""
    if str((service or {}).get("name") or "").strip().casefold() != "methods":
        return text
    raw_description = (
        (offer or {}).get("description_ar") if lang == "ar" and (offer or {}).get("description_ar")
        else (offer or {}).get("description")
    )
    description = _method_announcement_description(raw_description)
    label = {"fr": "Description", "ar": "الوصف"}.get(lang, "Description")
    description_row = f"💬 <b>{label}:</b> {description}" if description else ""
    rows = []
    inserted = False
    for line in str(text or "").splitlines():
        if _is_method_detail_row(line):
            if description_row and not inserted:
                rows.append(description_row)
                inserted = True
            continue
        rows.append(line)
    if description_row and not inserted:
        rows.append(description_row)
    return "\n".join(rows)


def _is_methods_offer(offer):
    """Return whether an offer belongs to the single-unit Methods service."""
    if not offer:
        return False
    service = db.get_service(offer.get("service_id")) or {}
    return str(service.get("name") or "").strip().casefold() == "methods"


def _is_single_unit_offer(offer):
    """Offers that must always be purchased as exactly one unit."""
    return _is_methods_offer(offer) or str((offer or {}).get("feature_key") or "") == "bot_like_mine"


def top_selling_products_text(lang: str) -> str:
    """Build the main-menu Top 5 from real paid catalogue orders."""
    titles = {
        "fr": "🔥 <b>TOP 5 DES PRODUITS LES PLUS VENDUS</b>",
        "en": "🔥 <b>TOP 5 BEST-SELLING PRODUCTS</b>",
        "ar": "🔥 <b>أفضل 5 منتجات مبيعاً</b>",
    }
    ranked = []
    for offer in db.list_catalog_offers():
        sold = db.offer_sold_count(offer.get("id"))
        if sold > 0:
            ranked.append((sold, offer))
    ranked.sort(key=lambda item: (-item[0], int(item[1].get("id") or 0)))
    lines = []
    for position, (_sold, offer) in enumerate(ranked[:5], start=1):
        fallback = str(offer.get("emoji") or offer.get("service_emoji") or "📦").strip()
        if not _is_single_emoji(fallback):
            fallback = "📦"
        emoji_id = str(offer.get("custom_emoji_id") or offer.get("service_custom_emoji_id") or "").strip()
        icon = fallback
        if emoji_id and emoji_id.isascii():
            icon = f"[[TGEMOJI:{emoji_id}:{fallback.encode('utf-8').hex()}]]"
        lines.append(f"{position} - {icon} <b>{html.escape(str(offer.get('name') or 'Product'))}</b>")
    if not lines:
        empty = {"fr": "Aucune vente pour le moment.", "en": "No sales yet.", "ar": "لا توجد مبيعات بعد."}
        lines.append(empty.get(lang, empty["en"]))
    return render_stored_rich_text(
        "[[HTML]]" + f"{titles.get(lang, titles['en'])}\n\n" + "\n".join(lines),
        parse_legacy_markdown=False,
    )


def _track_broadcast_message(context, sent_message, chat_id):
    """Persist an outgoing campaign message for later global deletion."""
    job_id = getattr(context, "broadcast_job_id", None)
    message_id = getattr(sent_message, "message_id", None)
    if job_id and message_id:
        try:
            db.record_broadcast_message(
                job_id,
                getattr(context, "broadcast_kind", "broadcast"),
                chat_id,
                message_id,
            )
        except Exception as exc:
            # The message is already delivered: never resend it just because
            # history tracking had a transient database failure.
            log.warning("Could not track broadcast message %s/%s: %s", chat_id, message_id, exc)
    return sent_message


async def _send_broadcast_message_safe(context, chat_id, text, reply_markup=None):
    """Send an HTML announcement message with automatic fallback to unformatted text."""
    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        return _track_broadcast_message(context, sent_message, chat_id)
    except BadRequest as exc:
        err_msg = str(exc).lower()
        if any(term in err_msg for term in ("entity", "parse", "html", "tag", "can't parse")):
            log.warning("Broadcast HTML parse failure for user %s (%s). Falling back to plain text.", chat_id, exc)
            plain_text = re.sub(r"<[^>]+>", "", text)
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                reply_markup=reply_markup,
            )
            return _track_broadcast_message(context, sent_message, chat_id)
        raise


async def announce_supplier_change_admin(context, event, change_type):
    """Send the normal bot-product design privately when a promo is unsuitable."""
    if not ADMIN_ID:
        return 0
    event = event or {}
    offer = db.get_offer(int(event.get("offer_id") or 0)) or {}
    if not offer:
        return 0
    lang = lang_of(ADMIN_ID)
    service = db.get_service(offer.get("service_id")) or {}
    values = {
        "emoji": _announcement_service_emoji(service),
        "service": _announcement_plain(service.get("name") or SHOP_NAME),
        "offer": _announcement_plain(offer.get("name") or f"Offer #{offer.get('id', 0)}"),
        "period": kb.offer_period_label(lang, offer),
        "warranty": warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
        "cur": CURRENCY,
    }
    if change_type == "stock":
        key = "channel_stock_announcement"
        values.update({
            "price": f"{float(offer.get('price') or 0):.2f}",
            "stock": max(0, int(event.get("stock") or 0)),
            "added": max(0, int(event.get("added") or 0)),
        })
    else:
        old_price = float(event.get("previous_price") or 0)
        new_price = float(event.get("price") or 0)
        if new_price < old_price:
            key = "flash_sale_announcement"
            values.update({
                "old_price": f"{old_price:.2f}",
                "price": f"{new_price:.2f}",
                "discount": round(((old_price - new_price) / old_price) * 100)
                if old_price else 0,
                "remaining": {
                    "fr": "Disponibilité limitée",
                    "ar": "متاح لفترة محدودة",
                }.get(lang, "Limited availability"),
            })
        else:
            key = "offer_stock_announcement"
            values.update({
                "price": f"{new_price:.2f}",
                "stock": (
                    "∞" if offer.get("unlimited_stock")
                    else max(0, int(offer.get("stock") or 0))
                ),
            })
    await _send_broadcast_message_safe(
        context,
        chat_id=ADMIN_ID,
        text=_method_announcement_text(
            premium_customer_text(lang, key, **values), service, offer, lang,
        ),
        reply_markup=kb.offer_detail_keyboard(lang, offer),
    )
    return 1


async def announce_channel_restock(
    context, offer_id, added, stock, supplier_event=None,
):
    """Broadcast a private new-stock advert to every active bot user."""
    offer = db.get_offer(int(offer_id))
    if not offer or not offer.get("active", 1):
        return await announce_supplier_change_admin(
            context,
            supplier_event or {
                "offer_id": offer_id, "added": added, "stock": stock,
            },
            "stock",
        ) if supplier_event else 0
    unlimited = bool(offer.get("unlimited_stock"))
    if not unlimited and int(stock or 0) <= 0:
        return 0
    if added is not None and int(added or 0) <= 0:
        return 0
    service = db.get_service(offer["service_id"]) or {}
    price = "—" if offer.get("price") is None else f"{float(offer['price']):.2f}"
    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        message_key = "channel_stock_announcement" if added is not None else "offer_stock_announcement"
        values = {
            "emoji": _announcement_service_emoji(service),
            "service": _announcement_plain(service.get("name") or SHOP_NAME),
            "offer": _announcement_plain(offer.get("name") or f"Offer #{offer_id}"),
            "period": kb.offer_period_label(lang, offer),
            "warranty": warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
            "price": price,
            "cur": CURRENCY,
            "stock": "∞" if unlimited else int(stock),
        }
        if added is not None:
            values["added"] = int(added)
        await _send_broadcast_message_safe(
            context,
            chat_id=user_id,
            text=_method_announcement_text(
                premium_customer_text(lang, message_key, **values), service, offer, lang,
            ),
            reply_markup=kb.offer_detail_keyboard(lang, offer),
        )
    return await _broadcast_in_batches(
        send_one,
        label="New-stock broadcast",
        catalog_updates_only=True,
        catalog_offer_id=offer_id,
    )


async def send_new_stock_broadcast(context, offer_id, added, stock):
    """Finish the broadcast before a serverless webhook request can terminate."""
    return await announce_channel_restock(context, offer_id, added, stock)


async def announce_flash_sale(context, offer_id):
    """Broadcast an active flash sale privately to every active bot user."""
    offer = db.get_offer(int(offer_id))
    if not offer or not offer.get("active", 1) or not offer.get("flash_sale_active"):
        return 0
    service = db.get_service(offer["service_id"]) or {}
    remaining_seconds = max(0, int(offer["flash_sale_ends_at"]) - int(time.time()))
    hours, remainder = divmod(remaining_seconds, 3600)
    minutes = max(1, remainder // 60)
    remaining = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    old_price = float(offer["flash_sale_original_price"])
    new_price = float(offer["price"])
    discount_percent = round(((old_price - new_price) / old_price) * 100) if old_price else 0
    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        await _send_broadcast_message_safe(
            context,
            chat_id=user_id,
            text=_method_announcement_text(
                premium_customer_text(
                    lang,
                    "flash_sale_announcement",
                    emoji=_announcement_service_emoji(service, "🎁"),
                    service=_announcement_plain(service.get("name") or SHOP_NAME),
                    offer=_announcement_plain(offer.get("name") or f"Offer #{offer_id}"),
                    period=kb.offer_period_label(lang, offer),
                    warranty=warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
                    old_price=f"{old_price:.2f}",
                    price=f"{new_price:.2f}",
                    cur=CURRENCY,
                    discount=discount_percent,
                    remaining=remaining,
                ), service, offer, lang,
            ),
            reply_markup=kb.offer_detail_keyboard(lang, offer),
        )
    return await _broadcast_in_batches(
        send_one,
        label="Flash-sale broadcast",
        catalog_updates_only=True,
        catalog_offer_id=offer_id,
    )


async def announce_api_flash_sale(context, event):
    """Broadcast a supplier-driven price drop without creating a temporary price."""
    offer = db.get_offer(int(event["offer_id"]))
    if not offer or not offer.get("active", 1) or not db.offer_has_stock(offer):
        return await announce_supplier_change_admin(context, event, "price")
    service = db.get_service(offer["service_id"]) or {}
    old_price = float(event["previous_price"])
    new_price = float(event["price"])
    discount_percent = round(((old_price - new_price) / old_price) * 100) if old_price else 0
    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        remaining = {
            "fr": "Disponibilité limitée",
            "ar": "متاح لفترة محدودة",
        }.get(lang, "Limited availability")
        await _send_broadcast_message_safe(
            context,
            chat_id=user_id,
            text=_method_announcement_text(
                premium_customer_text(
                    lang,
                    "flash_sale_announcement",
                    emoji=_announcement_service_emoji(service, "🔥"),
                    service=_announcement_plain(service.get("name") or SHOP_NAME),
                    offer=_announcement_plain(offer.get("name") or f"Offer #{offer['id']}"),
                    period=kb.offer_period_label(lang, offer),
                    warranty=warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
                    old_price=f"{old_price:.2f}",
                    price=f"{new_price:.2f}",
                    cur=CURRENCY,
                    discount=discount_percent,
                    remaining=remaining,
                ), service, offer, lang,
            ),
            reply_markup=kb.offer_detail_keyboard(lang, offer),
        )
    return await _broadcast_in_batches(
        send_one,
        label="Automatic flash-sale broadcast",
        catalog_updates_only=True,
        catalog_offer_id=offer["id"],
    )


async def announce_supplier_price_update(context, event):
    """Reuse the bot's manual new-drop design after a supplier price update."""
    offer = db.get_offer(int(event["offer_id"]))
    if not offer or not offer.get("active", 1) or not db.offer_has_stock(offer):
        return await announce_supplier_change_admin(context, event, "price")
    stock = "∞" if offer.get("unlimited_stock") else max(0, int(offer.get("stock") or 0))
    return await announce_channel_restock(
        context,
        int(offer["id"]),
        None,
        stock,
    )


async def broadcast_admin_message(context, source_chat_id, message_id):
    """Copy an admin-authored Telegram message to every active bot user."""
    async def send_one(user):
        sent_message = await context.bot.copy_message(
            chat_id=int(user["telegram_id"]),
            from_chat_id=source_chat_id,
            message_id=message_id,
        )
        _track_broadcast_message(context, sent_message, int(user["telegram_id"]))
    return await _broadcast_in_batches(send_one, label="Admin announcement")


async def announce_restock_digest(context, events):
    """Legacy compatibility: announce every restock as its own message."""
    sent = 0
    for event in list(events or [])[:12]:
        sent += await announce_channel_restock(
            context,
            int(event.get("offer_id") or 0),
            max(0, int(event.get("added") or 0)),
            max(0, int(event.get("stock") or 0)),
        )
    return sent


async def delete_broadcast_messages(context, target_job_id):
    """Delete one tracked campaign from every recipient Telegram still allows."""
    target_job_id = int(target_job_id)
    messages = db.list_broadcast_messages(target_job_id)
    db.set_broadcast_deletion_status(target_job_id, "deleting")

    async def delete_one(row):
        chat_id = int(row["chat_id"])
        message_id = int(row["message_id"])
        for attempt in range(3):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                db.mark_broadcast_message_deleted(target_job_id, chat_id, message_id)
                return 1
            except RetryAfter as exc:
                if attempt < 2:
                    delay = exc.retry_after
                    delay = delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)
                    await asyncio.sleep(delay + 0.15)
                    continue
                error = str(exc)
            except (TimedOut, NetworkError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                error = str(exc)
            except Exception as exc:
                error = str(exc)
                if "message to delete not found" in error.lower():
                    db.mark_broadcast_message_deleted(target_job_id, chat_id, message_id)
                    return 1
            db.mark_broadcast_message_deleted(
                target_job_id, chat_id, message_id, error=error,
            )
            return 0
        return 0

    deleted = 0
    for offset in range(0, len(messages), BROADCAST_BATCH_SIZE):
        batch = messages[offset:offset + BROADCAST_BATCH_SIZE]
        deleted += sum(await asyncio.gather(*(delete_one(row) for row in batch)))
        if offset + BROADCAST_BATCH_SIZE < len(messages):
            await asyncio.sleep(BROADCAST_BATCH_DELAY)
    failed = len(db.list_broadcast_messages(target_job_id))
    db.set_broadcast_deletion_status(
        target_job_id,
        "deleted" if failed == 0 else "partial",
        deleted_count=deleted,
        failed_count=failed,
    )
    return deleted


async def _execute_broadcast_job(job):
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(connect_timeout=20, read_timeout=30)
    bot_client = Bot(token=BOT_TOKEN, request=request)
    await bot_client.initialize()
    try:
        context = SimpleNamespace(
            bot=bot_client,
            broadcast_job_id=int(job["id"]),
            broadcast_kind=str(job.get("kind") or "broadcast"),
        )
        payload = job.get("payload") or {}
        kind = job.get("kind")
        sent = 0
        if kind == "stock":
            sent = await announce_channel_restock(
                context,
                payload["offer_id"],
                payload.get("added"),
                payload.get("stock"),
                payload.get("supplier_event"),
            )
        elif kind == "restock_digest":
            sent = await announce_restock_digest(context, payload.get("events") or [])
        elif kind == "flash_sale":
            sent = await announce_flash_sale(context, payload["offer_id"])
        elif kind == "api_flash_sale":
            sent = await announce_api_flash_sale(context, payload["event"])
        elif kind == "supplier_price_update":
            sent = await announce_supplier_price_update(context, payload["event"])
        elif kind == "admin_message":
            sent = await broadcast_admin_message(context, payload["source_chat_id"], payload["message_id"])
        elif kind == "delete_broadcast":
            sent = await delete_broadcast_messages(context, payload["target_job_id"])
        elif kind == "maintenance":
            sent = await broadcast_maintenance_notice(context, payload["message"])
        elif kind == "affiliate_update":
            sent = await broadcast_affiliate_program_update(context)
        else:
            raise ValueError(f"Unknown broadcast job: {kind}")

        return sent
    finally:
        await bot_client.shutdown()


def _run_broadcast_job(job_id):
    retry = False
    try:
        job = db.claim_broadcast_job(job_id)
        if not job:
            return
        sent = asyncio.run(_execute_broadcast_job(job))
        db.complete_broadcast_job(job_id, sent)
        log.info("Broadcast job %s completed: %s message(s)", job_id, sent)
    except Exception as exc:
        log.exception("Broadcast job %s failed", job_id)
        retry = db.fail_broadcast_job(job_id, exc) == "retry"
        if ADMIN_ID:
            def _notify_admin_fail():
                from telegram.request import HTTPXRequest
                req = HTTPXRequest(connect_timeout=10, read_timeout=10)
                b = Bot(token=BOT_TOKEN, request=req)
                async def _send():
                    async with b:
                        await b.send_message(
                            chat_id=ADMIN_ID,
                            text=f"⚠️ <b>Échec de la diffusion</b> (Job #{job_id})\n\nErreur : <code>{html.escape(str(exc)[:200])}</code>",
                            parse_mode=ParseMode.HTML,
                        )
                asyncio.run(_send())
            with contextlib.suppress(Exception):
                _notify_admin_fail()
    finally:
        with _broadcast_jobs_lock:
            _submitted_broadcast_jobs.discard(int(job_id))
        if retry:
            time.sleep(1.5)
            _submit_broadcast_job(job_id)


def _submit_broadcast_job(job_id):
    job_id = int(job_id)
    with _broadcast_jobs_lock:
        if job_id in _submitted_broadcast_jobs:
            return False
        _submitted_broadcast_jobs.add(job_id)
    _broadcast_executor.submit(_run_broadcast_job, job_id)
    return True


def queue_broadcast(kind, *, dedupe_key="", **payload):
    """Queue a reliable broadcast and return immediately to the admin/cron."""
    job, created = db.create_broadcast_job(kind, payload, dedupe_key=dedupe_key)
    if job and job.get("status") in {"queued", "retry"}:
        _submit_broadcast_job(job["id"])
    return {
        "job_id": job.get("id") if job else None,
        "queued": bool(created),
        "recipient_count": int((job or {}).get("recipient_count") or 0),
    }


def resume_pending_broadcasts():
    for job in db.pending_broadcast_jobs():
        _submit_broadcast_job(job["id"])


async def broadcast_maintenance_notice(context, message):
    """Notify every active bot user when maintenance mode is enabled."""
    async def send_one(user):
        user_id = int(user["telegram_id"])
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=f"🛠️ Maintenance\n\n{message}",
        )
        _track_broadcast_message(context, sent_message, user_id)
    return await _broadcast_in_batches(send_one, label="Maintenance notice")


async def broadcast_affiliate_program_update(context):
    """Notify every active bot user about the affiliate qualification rule."""
    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=premium_customer_text(lang, "affiliate_program_update"),
            parse_mode=ParseMode.HTML,
        )
        _track_broadcast_message(context, sent_message, user_id)
    return await _broadcast_in_batches(send_one, label="Affiliate program update")


async def announce_channel_purchase(context, order_id):
    """Compatibility no-op: purchase results stay in the private bot chat."""
    return False


async def safely_announce_channel_purchase(context, order_id):
    return False

async def show_deep_link_offer(update, lang, offer_id):
    """Open one channel-advertised offer safely in the customer's private chat."""
    offer = db.get_offer(int(offer_id))
    if not offer or not db.offer_has_stock(offer):
        await update.message.reply_text(
            premium_customer_text(lang, "out_of_stock"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.out_of_stock_keyboard(lang),
        )
        return
    detail_text = compact_offer_text(offer, lang)
    markup = kb.offer_detail_keyboard(lang, offer)
    if offer.get("photo_file_id"):
        if len(detail_text) <= 900:
            await update.message.reply_photo(
                photo=offer["photo_file_id"], caption=detail_text,
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
        else:
            await update.message.reply_photo(photo=offer["photo_file_id"])
            await update.message.reply_text(
                detail_text, parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True), reply_markup=markup,
            )
        return
    await update.message.reply_text(
        detail_text, parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True), reply_markup=markup,
    )


async def show_service_offers(update, context, lang, service_id):
    """Open a service, skipping its catalogue screen when it has one offer."""
    service = db.get_service(int(service_id))
    if not service:
        await show_catalog(update, context, lang)
        return

    offers = db.list_offers(int(service_id))
    if len(offers) == 1:
        await show_deep_link_offer(update, lang, offers[0]["id"])
        return

    await update.message.reply_text(
        t(
            lang,
            "service_title",
            emoji=service.get("emoji", "📦"),
            name=service.get("name", ""),
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.offers_keyboard(lang, int(service_id)),
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    is_new = db.upsert_user(u.id, u.username or "", u.first_name or "")
    lang = DEFAULT_LANG
    if db.get_user_lang(u.id) != DEFAULT_LANG:
        db.set_user_lang(u.id, DEFAULT_LANG)

    pending = PENDING.get(u.id)
    referrer_id = pending[1] if pending and pending[0] == "await_channel_join" else 0
    if context.args and context.args[0].startswith("ref_"):
        with contextlib.suppress(ValueError, TypeError):
            referrer_id = int(context.args[0][4:])

    if u.id != ADMIN_ID and not await is_required_channel_member_cached(context.bot, u.id):
        PENDING[u.id] = ("await_channel_join", referrer_id)
        await update.message.reply_text(
            premium_customer_text(lang, "channel_join_required"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.channel_join_keyboard(lang),
        )
        return

    if pending and pending[0] == "await_channel_join":
        PENDING.pop(u.id, None)
    await register_start_referral(context, u.id, referrer_id)

    if is_new and not context.args:
        await send_channel_member_welcome(update.message.reply_text, context, u.id, lang)
    elif context.args and (context.args[0].startswith("offer_") or context.args[0].startswith("off_")):
        try:
            offer_id = int(context.args[0].split("_", 1)[1])
        except (ValueError, IndexError):
            await show_catalog(update, context, lang)
        else:
            await show_deep_link_offer(update, lang, offer_id)
    elif context.args and context.args[0].startswith("svc_"):
        try:
            service_id = int(context.args[0].split("_", 1)[1])
        except (ValueError, IndexError):
            await show_catalog(update, context, lang)
        else:
            await show_service_offers(update, context, lang, service_id)
    elif context.args and context.args[0] == "catalog":
        await show_catalog(update, context, lang)
    elif context.args and context.args[0] == "orders":
        await show_my_orders(update, context, lang)
    elif context.args and context.args[0] == "support":
        await cmd_support(update, context)
    else:
        await send_main_menu(update, context, lang)


async def send_main_menu(update, context, lang, chat_id=None):
    uid = update.effective_user.id if update.effective_user else chat_id
    text = top_selling_products_text(lang)
    target = update.message or (update.callback_query.message if update.callback_query else None)
    markup = kb.home_keyboard(lang, uid)
    public_base_url = public_base_url_from_environment()
    banner_source = (
        os.environ.get("HP_WELCOME_PHOTO_FILE_ID", "").strip()
        or f"{public_base_url}/assets/blackmarket-welcome-v2.png"
    )
    if target:
        try:
            await target.reply_photo(
                photo=banner_source,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            log.exception("Welcome image could not be sent; falling back to text")
            await target.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        try:
            await context.bot.send_photo(
                chat_id,
                photo=banner_source,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            log.exception("Welcome image could not be sent; falling back to text")
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Accès refusé.")
        return
    await update.message.reply_text(
        "🛠️ *Panneau Admin*", parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin.admin_panel_keyboard(),
    )


def ticket_conversation_text(ticket):
    category = str(ticket.get("category") or "other").replace("_", " ").title()
    return (
        f"<b>Support Ticket {support_bridge.ticket_reference(ticket['id'])}</b>\n\n"
        f"<blockquote>Category: <b>{html.escape(category)}</b>\n"
        "Status: <b>Open</b></blockquote>\n\n"
        "Send any message or attachment here. It goes directly to our support team."
    )


async def send_ticket_conversation(message, lang, ticket):
    await message.reply_text(
        ticket_conversation_text(ticket),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.ticket_conversation_keyboard(lang, ticket["id"]),
    )


async def delete_customer_support_message(message):
    """Remove a customer's original message after it reaches support."""
    with contextlib.suppress(Exception):
        await message.delete()


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(update.effective_user.id)
    await update.effective_message.reply_text(
        t(lang, "support_choose_category"),
        reply_markup=kb.support_category_keyboard(lang),
    )


async def cmd_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_catalog(update, context, lang_of(update.effective_user.id))


async def show_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = lang_of(uid)
    await update.effective_message.reply_text(
        premium_customer_text(
            lang, "topup_message", binance_id=BINANCE_PAY_ID, bybit_uid=BYBIT_UID,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.topup_keyboard(lang, uid),
    )


def topup_provider_screen(lang, provider):
    is_bybit = provider == "bybit"
    provider_name = "Bybit Transfer (UID)" if is_bybit else "Binance Pay (ID)"
    pay_label = "Pay UID" if is_bybit else "Pay ID"
    pay_id = BYBIT_UID if is_bybit else BINANCE_PAY_ID
    txid_note = (
        "⚠️ <b>Bybit:</b> the Transaction ID is the code with dashes — not the long order/receipt number."
        if is_bybit else
        "⚠️ <b>Binance:</b> send the blockchain/payment Transaction ID (TXID), not the order number."
    )
    return (
        f"<b>{provider_name}</b>\n\n"
        f"<b>{pay_label}</b>\n<code>{html.escape(str(pay_id))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to deposit</b>\n"
        "<blockquote>1️⃣ Copy the ID above\n"
        "2️⃣ Send any USDT amount from your wallet/exchange\n"
        "3️⃣ Copy the Transaction ID (TXID)\n"
        "4️⃣ Paste the TXID here in this chat\n"
        "5️⃣ Auto-verify and instant credit ⚡</blockquote>\n\n"
        f"<blockquote>{txid_note}</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this screen for auto-credit.</blockquote>"
    )


def topup_onchain_screen(lang, network, amount):
    """Render BSC/Polygon top-ups in the same compact card style as Binance Pay."""
    is_bsc = str(network).lower() == "bsc"
    network_label = "BSC (BEP20)" if is_bsc else "Polygon"
    contract_suffix = "97955" if is_bsc else "58e8f"
    return (
        f"<b>USDT TOP UP — {network_label}</b>\n\n"
        f"<b>Wallet Address</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to deposit</b>\n"
        "<blockquote>1️⃣ Copy the wallet address above\n"
        f"2️⃣ Send exactly <b>{float(amount):.2f} USDT</b>\n"
        f"3️⃣ Select only the <b>{network_label}</b> network\n"
        "4️⃣ Copy the Transaction ID (TXID/hash)\n"
        "5️⃣ Paste the TXID here in this chat\n"
        "6️⃣ Auto-verify and instant credit ⚡</blockquote>\n\n"
        f"<blockquote>⚠️ <b>{network_label} only:</b> verify that the USDT contract "
        f"address ends in <b>{contract_suffix}</b>.</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this screen "
        "for auto-credit.</blockquote>"
    )


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_my_orders(update, context, lang_of(update.effective_user.id))


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(update.effective_user.id)
    await update.effective_message.reply_text(t(lang, "choose_lang"), reply_markup=kb.lang_keyboard())


async def cmd_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(update.effective_user.id)
    text = db.shop_settings().get("terms_message", "").strip() or t(lang, "terms_text")
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(update.effective_user.id)
    text = db.shop_settings().get("privacy_message", "").strip() or t(lang, "privacy_text")
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_replacement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume sending content for a warranty replacement awaiting delivery."""
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    if not context.args or not str(context.args[0]).isdigit():
        await update.effective_message.reply_text(
            "Usage: /replacement <warranty request ID>\nExample: /replacement 3"
        )
        return
    request_id = int(context.args[0])
    request = db.get_conn().warranty_requests.find_one({
        "id": request_id,
        "status": "replacement_pending",
    })
    if not request:
        await update.effective_message.reply_text(
            "⚠️ This warranty request is not awaiting replacement delivery."
        )
        return
    PENDING[uid] = ("adm_warranty_replacement", request_id)
    await update.effective_message.reply_text(
        f"🔁 Send the replacement content for warranty request #{request_id} now.\n\n"
        "Your next text message will be delivered to the customer."
    )


async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = lang_of(uid)
    account = db.user_account_summary(uid)
    stats = affiliate_service.get_stats(uid)
    loyalty = loyalty_service.active_benefit(uid)
    wallet = stats["balance_cents"] / 100
    name = html.escape(str(account.get("first_name") or update.effective_user.full_name or "—"))
    username = html.escape("@" + account["username"] if account.get("username") else "—")
    level = loyalty["level"] or "—"
    expires = datetime.fromtimestamp(loyalty["expires_at"], UTC).strftime("%d/%m/%Y") if loyalty["expires_at"] else "—"
    text = t(
        lang, "profile_card", name=name, username=username, telegram_id=uid,
        wallet=f"{wallet:.2f}", invites=stats["referrals"],
        orders=account["order_count"], delivered=account["delivered_count"],
        referral_code=f"ref_{uid}",
        qualified=stats["valid_referrals"], total_buy=f"{account['total_paid']:.2f}",
        level=level.title(), discount=loyalty["discount_percent"], expires=expires,
    )
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb.profile_keyboard(lang),
    )


async def show_affiliate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = lang_of(user_id)
    me = context.bot.username or (await context.bot.get_me()).username
    link = f"https://t.me/{me}?start=ref_{user_id}"
    stats = affiliate_service.get_stats(user_id)
    balance = stats["balance_cents"] / 100
    earned = stats["earned_cents"] / 100
    message = t(
        lang, "affiliate_title", earned=f"{earned:.2f}", balance=f"{balance:.2f}",
        referrals=stats["referrals"], progress=stats["progress"],
        link=link,
    )
    share_text = {
        "fr": f"🎁 Rejoins {SHOP_NAME} avec mon lien : {link}",
        "en": f"🎁 Join {SHOP_NAME} with my link: {link}",
        "ar": f"🎁 انضم إلى {SHOP_NAME} عبر رابطي: {link}",
    }.get(lang, f"Join {SHOP_NAME}: {link}")
    await update.effective_message.reply_text(
        message, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.affiliate_keyboard(lang, link, share_text),
    )


def reseller_api_dashboard_text(user_id, *, revealed_key=None):
    summary = buyer_api_service.dashboard(user_id)
    endpoint = f"{public_base_url_from_environment()}/api/v2/telegram-buyer"
    key = summary.get("key") or {}
    if revealed_key:
        credential = html.escape(revealed_key)
        key_note = "🔓 <i>Copy this key now. It will never be shown again.</i>"
    elif key:
        credential = html.escape(f"{key.get('prefix', '')}{'•' * 20}")
        key_note = "🔒 <i>The full key was shown once. Regenerate it to get a new one.</i>"
    else:
        credential = "Not created yet"
        key_note = "Create a key to start using the reseller API."
    status = "🟢 Active" if summary["active"] else "⚪ Inactive"
    return (
        "🔗 <b>Reseller API Dashboard</b>\n\n"
        "<blockquote>"
        f"Status: <b>{status}</b>\n"
        f"Balance: <b>{summary['balance']:.2f} {html.escape(summary['currency'])}</b>\n"
        f"Total API Orders: <b>{summary['total_orders']}</b>\n"
        f"Spend (30d): <b>{summary['spend_30d']:.2f} {html.escape(summary['currency'])}</b>"
        "</blockquote>\n\n"
        f"<b>Endpoint</b>\n<code>{html.escape(endpoint)}</code>\n\n"
        f"<b>Your API Key</b>\n<code>{credential}</code>\n"
        f"{key_note}\n\n"
        "<i>Treat this key like a password. Use the documentation for request examples.</i>"
    )


async def show_reseller_api(update: Update, context: ContextTypes.DEFAULT_TYPE, *, revealed_key=None):
    uid = update.effective_user.id
    lang = lang_of(uid)
    chat = getattr(update, "effective_chat", None)
    if chat is not None and getattr(chat, "type", "private") != "private":
        await update.effective_message.reply_text(
            "🔒 Open a private chat with the bot to manage your Reseller API key."
        )
        return
    summary = buyer_api_service.dashboard(uid)
    markup = kb.reseller_api_keyboard(
        lang,
        has_key=summary["active"],
        docs_url=f"{public_base_url_from_environment()}/api/swagger",
    )
    await update.effective_message.reply_text(
        reseller_api_dashboard_text(uid, revealed_key=revealed_key),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------- Sélection langue ----------------
async def cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    lang = q.data.split(":")[1]
    active_languages = {
        code.strip()
        for code in str(db.shop_settings().get("active_languages") or "en,ar").split(",")
    }
    if lang not in {"en", "ar"} or lang not in active_languages:
        await q.answer("Only English and Arabic are available.", show_alert=True)
        return
    db.set_user_lang(q.from_user.id, lang)
    await q.answer()
    await q.edit_message_text(
        top_selling_products_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.home_keyboard(lang, q.from_user.id),
    )


# ---------------- Boutons du menu reply ----------------
async def on_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = lang_of(uid)
    text = update.message.text.strip()
    pending = PENDING.get(uid)

    def clear_support_pending():
        if pending and pending[0].startswith(("support", "ticket_")):
            PENDING.pop(uid, None)

    blocking_states = {
        "await_txid",
        "await_onchain_txid",
        "await_topup_txid",
        "await_onchain_topup_amount",
        "await_onchain_topup_txid",
        "await_solana_topup_check",
        "await_withdraw_amount",
        "await_withdraw_method",
        "await_withdraw_destination",
        "warranty_reason",
        "adm_warranty_refuse_reason",
        "adm_warranty_replacement",
        "adm_method_media",
        "adm_bot_package_doc",
        "adm_bot_package_link",
        "manual_order_reply",
        "await_quantity",
        "await_preorder_quantity",
        "catalog_request",
        "adm_setprice",
        "adm_flash_start",
        "adm_svcname",
        "adm_svcemoji",
        "adm_offname",
        "adm_offemoji",
        "adm_offnote",
        "adm_offdesc",
        "adm_offdelay",
        "adm_addsvc",
        "adm_addoff",
        "adm_addoff_image",
        "adm_addoff_name",
        "adm_addoff_warranty",
        "adm_addoff_description",
        "adm_addoff_price",
        "adm_offimage",
        "adm_text_override",
        "adm_ticket_style",
        "adm_btn_add",
        "adm_inventory",
        "adm_manual_stock",
        "adm_broadcast_message",
        "adm_client_message",
        "adm_deliver",
        "adm_codex_number",
        "adm_codex_otp",
        "adm_lovable_zip",
        "adm_lovable_trial",
    }

    if pending and pending[0] in blocking_states:
        await handle_pending_input(update, context, lang)
        return
    if text == t(lang, "menu_catalog"):
        clear_support_pending()
        await show_catalog(update, context, lang)
    elif text == t(lang, "menu_methods"):
        clear_support_pending()
        await show_methods(update, context, lang)
    elif text == t(lang, "menu_bot_like_mine"):
        clear_support_pending()
        offer_id = db.ensure_bot_like_mine_feature()
        offer = db.get_offer(offer_id)
        await update.message.reply_text(
            compact_offer_text(offer, lang),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=kb.offer_detail_keyboard(lang, offer),
        )
    elif text == t(lang, "menu_lovable"):
        clear_support_pending()
        await show_catalog(update, context, lang)
    elif text == t(lang, "menu_orders"):
        clear_support_pending()
        await show_my_orders(update, context, lang)
    elif text == t(lang, "menu_topup"):
        clear_support_pending()
        await show_topup(update, context)
    elif text == t(lang, "menu_account"):
        clear_support_pending()
        await show_account(update, context)
    elif text == t(lang, "menu_lang"):
        clear_support_pending()
        await update.message.reply_text(t(lang, "choose_lang"), reply_markup=kb.lang_keyboard())
    elif text == t(lang, "menu_affiliate"):
        clear_support_pending()
        await show_affiliate(update, context)
    elif text == t(lang, "menu_support"):
        await cmd_support(update, context)
    elif text == t(lang, "menu_admin") and uid == ADMIN_ID:
        clear_support_pending()
        await update.message.reply_text("\U0001f6e0\ufe0f *Panneau Admin*", parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=admin.admin_panel_keyboard())
    elif pending and pending[0].startswith(("support", "ticket_")):
        await handle_pending_input(update, context, lang)
    else:
        await send_main_menu(update, context, lang)


# ---------------- Catalogue (client) ----------------
async def show_catalog(update, context, lang):
    text = t(lang, "catalog_flat_title", shop=SHOP_NAME)
    msg = update.message or update.callback_query.message
    notifications_enabled = db.catalog_notifications_enabled(update.effective_user.id)
    await msg.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.catalog_offers_keyboard(lang, notifications_enabled),
    )


async def show_methods(update, context, lang):
    service_id = db.ensure_methods_service()
    offers = db.list_offers(service_id)
    message = update.message or update.callback_query.message
    if not offers:
        await message.reply_text(
            "🧠 <b>Methods</b>\n\nNo methods are available yet.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.home_keyboard(lang, update.effective_user.id),
        )
        return
    await message.reply_text(
        "🧠 <b>Methods</b>\n\nChoose a method to view its description and price:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.offers_keyboard(lang, service_id),
    )


async def show_lovable(update, context, lang):
    """Open the dedicated Lovable Unlimited Credit storefront."""
    msg = update.message or update.callback_query.message
    await msg.reply_text(
        t(lang, "lovable_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.lovable_home_keyboard(
            lang, is_admin=int(update.effective_user.id) == int(ADMIN_ID),
        ),
    )


def lovable_expiry_text(timestamp):
    return datetime.fromtimestamp(int(timestamp), tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


async def send_lovable_extension(bot, user_id, lang):
    extension = lovable_service.extension_file()
    if not extension:
        await bot.send_message(int(user_id), t(lang, "lovable_download_unavailable"))
        return False
    try:
        await bot.send_document(
            chat_id=int(user_id),
            document=extension["file_id"],
            caption="💗 Lovable Unlimited Credit — Browser Extension\n\n"
            "Extract this ZIP file, load the folder in Developer mode, then enter your license.",
        )
        return True
    except Exception as exc:
        log.warning("Lovable extension download failed for user %s: %s", user_id, exc)
        await bot.send_message(int(user_id), t(lang, "lovable_download_unavailable"))
        return False


async def show_callback_screen(
    query,
    text,
    *,
    reply_markup,
    parse_mode=ParseMode.MARKDOWN,
    link_preview_options=None,
):
    """Render a callback screen from either a text message or a photo caption."""
    options = {}
    if link_preview_options is not None:
        options["link_preview_options"] = link_preview_options
    try:
        if getattr(query.message, "text", None):
            await query.edit_message_text(
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                **options,
            )
            return
        await query.message.reply_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **options,
        )
        with contextlib.suppress(Exception):
            await query.edit_message_reply_markup(reply_markup=None)
    except Exception as exc:
        log.warning("show_callback_screen error with parse_mode=%s: %s. Retrying with plain text fallback.", parse_mode, exc)
        clean_text = re.sub(r"<[^>]+>", "", str(text or ""))
        try:
            if getattr(query.message, "text", None):
                await query.edit_message_text(
                    clean_text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                    **options,
                )
                return
            await query.message.reply_text(
                clean_text,
                parse_mode=None,
                reply_markup=reply_markup,
                **options,
            )
        except Exception:
            with contextlib.suppress(Exception):
                await query.message.reply_text(
                    clean_text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                    **options,
                )


def order_delivery_timestamp(order):
    delivered_at = order.get("delivered_at") or order.get("created_at") or time.time()
    if isinstance(delivered_at, datetime):
        return delivered_at.timestamp()
    try:
        return float(delivered_at)
    except (TypeError, ValueError, OverflowError):
        return time.time()


def warranty_days_used(order):
    return max(0, int((time.time() - order_delivery_timestamp(order)) // 86400))


def product_warranty_days(order):
    """Resolve the warranty duration from the product, with order snapshot fallback."""
    offer_id = order.get("offer_id")
    if offer_id:
        offer = db.get_offer(int(offer_id))
        if offer and offer.get("warranty_days") is not None:
            return max(0, int(offer.get("warranty_days") or 0))
    return max(0, int(order.get("warranty_days") or 0))


def product_period_days(order):
    offer_id = order.get("offer_id")
    if offer_id:
        offer = db.get_offer(int(offer_id))
        if offer and offer.get("period_days") is not None:
            return max(0, int(offer.get("period_days") or 0))
    return max(0, int(order.get("period_days") or 0))


async def cb_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    lang = lang_of(uid)
    data = q.data
    with contextlib.suppress(Exception):
        await q.answer()

    if data.startswith("codex_number_agree:"):
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if (
            not is_otp_order(order)
            or int(order.get("user_id") or 0) != uid
            or order.get("status") not in {"paid", "payment_confirmed"}
        ):
            await q.message.reply_text(t(lang, "otp_order_unavailable"))
            return
        workflow = str(order.get("otp_workflow_status") or "")
        now = int(time.time())
        deadline = int(order.get("codex_agree_deadline") or 0)
        if workflow == "number_sent" and deadline and deadline <= now:
            expired = db.expire_codex_number_acceptance(order_id, now)
            if expired:
                await notify_codex_acceptance_expired(context.bot, expired)
            await q.edit_message_text(
                t(lang, "codex_acceptance_expired", oid=order_id),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.home_keyboard(lang, uid),
            )
            return
        if workflow == "number_sent":
            changed = db.get_conn().orders.update_one(
                {
                    "id": order_id,
                    "user_id": uid,
                    "status": {"$in": ["paid", "payment_confirmed"]},
                    "otp_workflow_status": "number_sent",
                },
                {"$set": {
                    "otp_workflow_status": "customer_agreed",
                    "codex_agreed_at": now,
                    "updated_at": now,
                }},
            )
            if not changed.modified_count:
                await q.message.reply_text(t(lang, "otp_order_unavailable"))
                return
            order = db.get_order(order_id)
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    "<b>Customer accepted the Codex number</b>\n\n"
                    f"Order: <b>#{order_id}</b>\n"
                    f"Client ID: <code>{uid}</code>\n"
                    f"Number: <code>{html.escape(str(order.get('codex_number') or '—'))}</code>\n\n"
                    "Send the OTP code to complete the order.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin.codex_otp_request_keyboard(order_id),
                )
            except Exception as exc:
                log.warning("Codex order #%s agreement notification failed: %s", order_id, exc)
        elif workflow != "customer_agreed":
            await q.message.reply_text(t(lang, "otp_order_unavailable"))
            return
        await q.edit_message_text(
            t(lang, "codex_number_agreed"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.home_keyboard(lang, uid),
        )
        return

    if data == "verify_channel_join":
        allowed, details = await required_membership_status(context.bot, uid)
        if not allowed:
            log.info("%s", _format_membership_diagnostics(uid, details))
            await q.edit_message_text(
                premium_customer_text(lang, "channel_join_not_verified"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.channel_join_keyboard(lang),
            )
            return
        cache_required_channel_member(uid)
        pending = PENDING.pop(uid, None)
        referrer_id = pending[1] if pending and pending[0] == "await_channel_join" else 0
        db.set_user_lang(uid, DEFAULT_LANG)
        await register_start_referral(context, uid, referrer_id)
        await send_channel_member_welcome(q.edit_message_text, context, uid, DEFAULT_LANG)
        return
    if data.startswith("tour:"):
        await q.edit_message_text(
            top_selling_products_text(lang),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.home_keyboard(lang, uid),
        )
        return
    if data == "home":
        await send_main_menu(update, context, lang)
        return
    if data == "catalog":
        await show_callback_screen(
            q,
            t(lang, "catalog_flat_title", shop=SHOP_NAME),
            reply_markup=kb.catalog_offers_keyboard(
                lang, db.catalog_notifications_enabled(uid),
            ),
        )
        return
    if data == "catalog_notifications_toggle":
        enabled = not db.catalog_notifications_enabled(uid)
        db.set_catalog_notifications_enabled(uid, enabled)
        await q.edit_message_reply_markup(
            reply_markup=kb.catalog_offers_keyboard(lang, enabled),
        )
        return
    if data == "profile_notifications":
        enabled = db.catalog_notifications_enabled(uid)
        await show_callback_screen(
            q,
            t(lang, "profile_notifications_title"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.profile_notifications_keyboard(lang, uid, enabled),
        )
        return
    if data == "profile_catalog_notifications_toggle":
        enabled = not db.catalog_notifications_enabled(uid)
        db.set_catalog_notifications_enabled(uid, enabled)
        await q.edit_message_reply_markup(
            reply_markup=kb.profile_notifications_keyboard(lang, uid, enabled),
        )
        return
    if data.startswith("profile_notifications_page:"):
        page = int(data.rsplit(":", 1)[1])
        await q.edit_message_reply_markup(
            reply_markup=kb.profile_notifications_keyboard(
                lang, uid, db.catalog_notifications_enabled(uid), page,
            ),
        )
        return
    if data.startswith("profile_product_notification:"):
        _prefix, offer_id, page = data.split(":")
        offer_id = int(offer_id)
        offer = db.get_offer(offer_id)
        if not offer or not offer.get("active", 1):
            await q.edit_message_reply_markup(
                reply_markup=kb.profile_notifications_keyboard(
                    lang, uid, db.catalog_notifications_enabled(uid), int(page),
                ),
            )
            return
        product_enabled = not db.product_notifications_enabled(uid, offer_id)
        db.set_product_notifications_enabled(uid, offer_id, product_enabled)
        await q.edit_message_reply_markup(
            reply_markup=kb.profile_notifications_keyboard(
                lang, uid, db.catalog_notifications_enabled(uid), int(page),
            ),
        )
        return
    if data == "profile_withdraw":
        balance = wallet_service.balance_cents(uid) / 100
        await show_callback_screen(
            q,
            f"💸 <b>Withdraw</b>\n\nAvailable wallet balance: <b>{balance:.2f} {CURRENCY}</b>\nMinimum withdrawal: <b>10.00 {CURRENCY}</b>\nProcessing time: <b>1 to 24 hours</b>\n\nHow much would you like to withdraw?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.profile_back_keyboard(lang),
        )
        if balance >= 10:
            PENDING[uid] = ("await_withdraw_amount", None)
        return
    if data == "warranty":
        # A warranty flow starts a fresh callback route; discard any stale
        # text-entry state left by another customer action.
        PENDING.pop(uid, None)
        orders = [
            o for o in db.list_user_orders(uid, limit=100)
            if o.get("status") == "delivered"
            and product_period_days(o) > 0
            and warranty_days_used(o) < product_period_days(o)
        ]
        if not orders:
            await show_callback_screen(
                q,
                "🛡️ No delivered product currently has an active product period.",
                reply_markup=kb.home_keyboard(lang, uid),
            )
            return
        await show_callback_screen(q, "Select the delivered product with a problem:", reply_markup=kb.warranty_orders_keyboard(lang, orders))
        return
    if data.startswith("warranty_order:"):
        PENDING.pop(uid, None)
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if (
            not order
            or int(order.get("user_id") or 0) != uid
            or order.get("status") != "delivered"
        ):
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        days_used = warranty_days_used(order)
        period = max(1, product_period_days(order))
        warranty_days = product_warranty_days(order)
        if days_used >= period:
            await q.message.reply_text(
                "⚠️ This product period has already expired.",
                reply_markup=kb.home_keyboard(lang, uid),
            )
            return
        if warranty_days <= 0 or days_used >= warranty_days:
            delivered_timestamp = order_delivery_timestamp(order)
            delivered_text = datetime.fromtimestamp(delivered_timestamp, UTC).strftime("%Y-%m-%d %H:%M UTC")
            product_expires = datetime.fromtimestamp(delivered_timestamp + period * 86400, UTC).strftime("%Y-%m-%d %H:%M UTC")
            product_name = html.escape(str(order.get("offer_name") or order.get("service_name") or "Product"))
            await q.message.reply_text(
                "🛡️ <b>Product out of warranty</b>\n\n"
                f"Product: <b>{product_name}</b>\n"
                f"Order: <code>#{order_id}</code>\n"
                f"Delivered: <b>{delivered_text}</b>\n"
                f"Product period: <b>{period} days</b>\n"
                f"Product expires: <b>{product_expires}</b>\n"
                f"Warranty period: <b>{max(0, warranty_days)} days</b>\n"
                f"Days used: <b>{days_used}</b>\n\n"
                "The product period is still active, but warranty support has expired.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang, uid),
            )
            return
        original = float(order.get("unit_price") or order.get("total_price") or 0)
        refund = round(max(0, original - (original / period) * days_used), 2)
        existing_request = db.get_conn().warranty_requests.find_one(
            {"user_id": uid, "order_id": order_id},
            {"_id": 1},
        )
        if existing_request:
            await q.message.reply_text("⚠️ A warranty request for this order has already been submitted.")
            return
        PENDING[uid] = ("warranty_reason", {
            "order_id": order_id,
            "days_used": days_used,
            "refund": refund,
        })
        await q.message.reply_text(
            "Please describe the problem with this product, then send your message."
        )
        return
    if data.startswith("withdraw_method:"):
        method = data.split(":", 1)[1]
        if method == "bybit":
            await q.message.reply_text(t(lang, "bybit_disabled"))
            return
        if method not in {"binance", "bep20"}:
            return
        pending_withdraw = PENDING.get(uid)
        amount = pending_withdraw[1] if pending_withdraw and pending_withdraw[0] == "await_withdraw_method" else 0
        PENDING[uid] = ("await_withdraw_destination", {"method": method, "amount": amount})
        await q.message.reply_text("Send your Binance ID or USDT BEP20 address:")
        return
    if data in {"lovable", "lovable_howto", "lovable_buy", "lovable_trial", "lovable_download"}:
        await q.answer("Ce catalogue n'est plus disponible.", show_alert=True)
        return
    if data == "reseller_api":
        await show_reseller_api(update, context)
        return
    if data == "reseller_api_create":
        chat = getattr(update, "effective_chat", None)
        if chat is not None and getattr(chat, "type", "private") != "private":
            await q.message.reply_text(
                "🔒 Open a private chat with the bot to create your API key."
            )
            return
        try:
            issued = await asyncio.to_thread(buyer_api_service.issue_user_key, uid)
        except buyer_api_service.BuyerApiError as exc:
            await q.message.reply_text(html.escape(exc.message), parse_mode=ParseMode.HTML)
            return
        await show_reseller_api(update, context, revealed_key=issued["key"])
        return
    if data == "reseller_api_regen":
        await q.message.reply_text(
            "⚠️ <b>Regenerate your API key?</b>\n\n"
            "Your current key will stop working immediately. This cannot be undone.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.reseller_api_regenerate_keyboard(lang),
        )
        return
    if data == "reseller_api_regen_confirm":
        chat = getattr(update, "effective_chat", None)
        if chat is not None and getattr(chat, "type", "private") != "private":
            await q.message.reply_text(
                "🔒 Open a private chat with the bot to regenerate your API key."
            )
            return
        issued = await asyncio.to_thread(
            buyer_api_service.issue_user_key, uid, regenerate=True,
        )
        await show_reseller_api(update, context, revealed_key=issued["key"])
        return
    if data == "preorder_catalog":
        await show_callback_screen(
            q,
            t(lang, "preorder_catalog_title"),
            reply_markup=kb.preorder_services_keyboard(lang),
        )
        return
    if data.startswith("preorder_svc:"):
        sid = int(data.split(":", 1)[1])
        service = db.get_service(sid)
        if not service:
            await show_callback_screen(
                q,
                t(lang, "preorder_catalog_title"),
                reply_markup=kb.preorder_services_keyboard(lang),
            )
            return
        await show_callback_screen(
            q,
            t(
                lang,
                "preorder_service_title",
                emoji=service.get("emoji") or "📦",
                name=service.get("name") or f"Service #{sid}",
            ),
            reply_markup=kb.preorder_offers_keyboard(lang, sid),
        )
        return
    if data == "catalog_request":
        PENDING[uid] = ("catalog_request", 0)
        await q.message.reply_text(
            premium_customer_text(lang, "catalog_request_prompt"),
            parse_mode=ParseMode.HTML,
        )
        return
    if data == "orders":
        await show_my_orders(update, context, lang)
        return
    if data == "topup":
        await show_topup(update, context)
        return
    if data == "methods":
        await show_methods(update, context, lang)
        return
    if data == "bot_like_mine":
        data = f"off:{db.ensure_bot_like_mine_feature()}"
    if data.startswith("bot_package_preview:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if not offer or offer.get("feature_key") != "bot_like_mine":
            await q.answer(t(lang, "bot_package_preview_unavailable"), show_alert=True)
            return
        document_file_id = str(offer.get("benefits_document_file_id") or "").strip()
        if not document_file_id:
            await q.message.reply_text(t(lang, "bot_package_preview_unavailable"))
            return
        await q.message.reply_document(
            document=document_file_id,
            caption=t(lang, "bot_package_preview_caption"),
            reply_markup=kb.offer_detail_keyboard(lang, offer),
        )
        return
    if data == "topup_onchain":
        await show_callback_screen(
            q,
            "⛓️ <b>Onchain USDT deposit</b>\n\nChoose the network you will use:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.topup_onchain_keyboard(lang),
        )
        return
    if data == "topup_sol":
        if uid != ADMIN_ID and (SOLANA_ALLOWED_USER_ID <= 0 or uid != SOLANA_ALLOWED_USER_ID):
            await q.answer("This deposit method is not available for your account.", show_alert=True)
            return
        PENDING[uid] = ("await_solana_topup_check", {"created_at": int(time.time())})
        await show_callback_screen(
            q,
            t(lang, "topup_sol_instructions", address=SOLANA_DEPOSIT_ADDRESS, minimum=f"{SOLANA_MIN_DEPOSIT:.9f}".rstrip("0").rstrip("."), confirmations=SOLANA_MIN_CONFIRMATIONS),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.topup_provider_keyboard(lang, "solana", SOLANA_DEPOSIT_ADDRESS),
        )
        return
    if data == "solana_check_payment":
        if uid != ADMIN_ID and (SOLANA_ALLOWED_USER_ID <= 0 or uid != SOLANA_ALLOWED_USER_ID):
            await q.answer("This deposit method is not available for your account.", show_alert=True)
            return
        pending = PENDING.get(uid)
        since = int((pending[1] if pending else {}).get("created_at") or time.time())
        for progress in (0, 20, 40, 60, 80, 100):
            bar = "🟩" * (progress // 20) + "⬜" * (5 - progress // 20)
            await q.edit_message_text(t(lang, "topup_sol_checking", progress=progress, bar=bar), parse_mode=ParseMode.HTML)
            if progress < 100:
                await asyncio.sleep(2)
            result = await asyncio.to_thread(wallet_service.submit_solana_scan, uid, since)
            if result["status"] == "confirmed":
                PENDING.pop(uid, None)
                await q.edit_message_text(t(lang, "topup_sol_approved", sol_amount=f"{result['sol_amount']:.9f}".rstrip("0").rstrip("."), rate=f"{result['rate']:.4f}".rstrip("0").rstrip("."), source=result.get("quote_source", "Binance SOL/USDT"), amount=f"{result['amount']:.2f}", balance=f"{result['balance']:.2f}"), parse_mode=ParseMode.HTML, reply_markup=kb.home_keyboard(lang, uid))
                return
            if result.get("code") == "already_used":
                PENDING.pop(uid, None)
                await q.edit_message_text(result.get("message") or "This payment has already been credited.", reply_markup=kb.home_keyboard(lang, uid))
                return
        PENDING.pop(uid, None)
        await q.edit_message_text(t(lang, "topup_sol_not_found"), reply_markup=kb.topup_keyboard(lang, uid))
        return
    if data in {"topup_bsc", "topup_polygon"}:
        network = "bsc" if data == "topup_bsc" else "polygon"
        network_label = "BSC (BEP20)" if network == "bsc" else "Polygon"
        PENDING[uid] = ("await_onchain_topup_amount", network)
        await q.message.reply_text(
            t(lang, "topup_onchain_amount", network=network_label),
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data == "topup_bybit":
        PENDING.pop(uid, None)
        await q.message.reply_text(
            t(lang, "bybit_disabled"), reply_markup=kb.topup_keyboard(lang, uid),
        )
        return
    if data in {"topup_txid", "topup_claim"}:
        # Older messages used topup_claim for the removed automatic scan.
        # Keep them useful by routing directly to TXID entry.
        provider = "binance"
        PENDING[uid] = ("await_topup_txid", provider)
        pay_id = BYBIT_UID if provider == "bybit" else BINANCE_PAY_ID
        await show_callback_screen(
            q,
            topup_provider_screen(lang, provider),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.topup_provider_keyboard(lang, provider, pay_id),
        )
        return
    if data.startswith("manual_reply:"):
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if not order or int(order.get("user_id") or 0) != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        if order.get("status") not in {"paid", "payment_confirmed"}:
            await q.answer(
                t(lang, "manual_order_conversation_closed"),
                show_alert=True,
            )
            return
        PENDING[uid] = ("manual_order_reply", order_id)
        await q.message.reply_text(
            t(lang, "manual_order_reply_prompt", oid=order_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("orders_group:") or data == "orders_export:all":
        orders = db.list_user_orders(uid, limit=500)
        if not orders:
            await q.message.reply_text(t(lang, "no_orders"), reply_markup=kb.orders_keyboard(lang))
            return
        if data == "orders_export:all":
            await send_orders_export(q, lang, orders, t(lang, "orders_all_title"))
            return
        groups = order_service_groups(orders)
        index = int(data.split(":", 1)[1])
        if index < 0 or index >= len(groups):
            await q.answer(t(lang, "orders_group_unavailable"), show_alert=True)
            return
        group = groups[index]
        await send_orders_export(q, lang, group["orders"], group["name"])
        return
    if data == "account":
        await show_account(update, context)
        return
    if data == "affiliate":
        await show_affiliate(update, context)
        return
    if data == "affiliate_copy":
        me = context.bot.username or (await context.bot.get_me()).username
        link = f"https://t.me/{me}?start=ref_{uid}"
        await q.message.reply_text(t(lang, "affiliate_copy_message", link=link), parse_mode=ParseMode.MARKDOWN)
        return
    if data == "support":
        await cmd_support(update, context)
        return
    if data == "language":
        await q.message.reply_text(t(lang, "choose_lang"), reply_markup=kb.lang_keyboard())
        return
    if data.startswith("order_view:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        warranty = (
            "FW" if warranty_service.has_full_warranty(order)
            else str(order.get("warranty") or "").strip()
            or warranty_service.order_warranty_label(order, lang=lang)
            or "—"
        )
        await q.message.reply_text(
            t(lang, "order_card", oid=oid, offer=order["offer_name"], qty=order["qty"],
              total=f"{order['total_price']:.2f}", cur=CURRENCY,
              status=status_label(lang, order["status"]))
            + f"\n🛡 Warranty: {escape_markdown(warranty, version=1)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.orders_keyboard(lang),
        )
        return
    if data.startswith("svc:"):
        sid = int(data.split(":")[1])
        service = db.get_service(sid)
        if not service:
            await show_callback_screen(
                q,
                t(lang, "catalog_flat_title", shop=SHOP_NAME),
                reply_markup=kb.catalog_offers_keyboard(
                    lang, db.catalog_notifications_enabled(uid),
                ),
            )
            return
        offers = db.list_offers(sid)
        if len(offers) == 1:
            # Continue through the regular offer-detail branch below so old
            # service buttons and links also skip the redundant catalogue.
            data = f"off:{offers[0]['id']}"
        else:
            emoji = service.get("emoji", "📦")
            name = service.get("name", "")
            await show_callback_screen(
                q,
                t(lang, "service_title", emoji=emoji, name=name),
                reply_markup=kb.offers_keyboard(lang, sid),
            )
            return


    if data.startswith("off:"):
        raw_oid = data.split(":")[1]
        try:
            oid = int(raw_oid)
        except (ValueError, TypeError):
            oid = raw_oid
        off = db.get_offer(oid) or db.get_offer(str(raw_oid))
        if not off or not db.offer_has_stock(off):
            await q.message.reply_text(
                premium_customer_text(lang, "out_of_stock"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.out_of_stock_keyboard(lang),
            )
            return
        try:
            detail_text = compact_offer_text(off, lang)
        except Exception as exc:
            log.warning("compact_offer_text failed: %s", exc)
            detail_text = (
                f"🏷 <b>{html.escape(str(off.get('name') or 'Offre'))}</b>\n\n"
                f"💎 <b>Prix :</b> {off.get('price')} {html.escape(str(off.get('currency', CURRENCY)))}\n"
                f"📦 <b>Stock :</b> {off.get('stock') or 0}"
            )

        photo_file_id = off.get("photo_file_id")
        if photo_file_id:
            try:
                if len(detail_text) <= 900:
                    await q.message.reply_photo(
                        photo=photo_file_id,
                        caption=detail_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb.offer_detail_keyboard(lang, off),
                    )
                else:
                    await q.message.reply_photo(photo=photo_file_id)
                    await q.message.reply_text(
                        detail_text,
                        parse_mode=ParseMode.HTML,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                        reply_markup=kb.offer_detail_keyboard(lang, off),
                    )
                with contextlib.suppress(Exception):
                    await q.message.delete()
                return
            except Exception as e:
                log.warning("Failed to reply with offer photo %s: %s", photo_file_id, e)

        off_name = str(off.get("name") or "").lower()
        is_chatgpt_offer = "chat" in off_name and "gpt" in off_name
        if is_chatgpt_offer:
            try:
                base_url = public_base_url_from_environment()
                await q.message.reply_photo(
                    photo=f"{base_url}/assets/chatgpt-plus-benefits.png",
                    caption="\U0001f525 *ChatGPT Plus Benefits*",
                    parse_mode=ParseMode.MARKDOWN,
                )
                await q.message.reply_text(
                    detail_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                    reply_markup=kb.offer_detail_keyboard(lang, off),
                )
                with contextlib.suppress(Exception):
                    await q.message.delete()
                return
            except Exception as e:
                log.warning("Failed to send ChatGPT photo: %s", e)

        await show_callback_screen(
            q,
            detail_text,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=kb.offer_detail_keyboard(lang, off),
        )
        return
    if data.startswith("buy:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if _is_single_unit_offer(offer):
            send_confirmation = (
                q.message.reply_text if q.message and q.message.photo else q.edit_message_text
            )
            if not await send_buy_confirmation(
                send_confirmation, uid, offer_id, 1, lang,
            ):
                await q.answer(t(lang, "out_of_stock"), show_alert=True)
        else:
            await handle_quantity_selection(update, context, lang)
        return
    if data.startswith("preorder:"):
        await show_callback_screen(
            q,
            t(lang, "preorder_catalog_title"),
            reply_markup=kb.preorder_services_keyboard(lang),
        )
        return
    if data.startswith(("preorder_start:", "preorder_page:")):
        await handle_preorder_quantity_selection(update, context, lang)
        return
    if data.startswith("qty_page:"):
        await handle_quantity_selection(update, context, lang)
        return
    if data.startswith("buyq:"):
        await handle_buy_confirmation(update, context, lang)
        return
    if data.startswith("preorderq:"):
        await handle_buy_confirmation(update, context, lang, preorder=True)
        return
    if data.startswith((
        "confirm_buy:", "pay_wallet:", "pay_binance:", "pay_bybit:", "pay_bsc:", "pay_polygon:",
    )):
        if data.startswith("pay_bybit:"):
            await q.message.reply_text(t(lang, "bybit_disabled"))
            return
        payment_method = (
            "wallet" if data.startswith("pay_wallet:")
            else "usdt_bsc" if data.startswith("pay_bsc:")
            else "usdt_polygon" if data.startswith("pay_polygon:")
            else "bybit" if data.startswith("pay_bybit:")
            else "binance"
        )
        await handle_buy_confirmed(update, context, lang, payment_method=payment_method)
        return
    if data.startswith("cancel_buy:"):
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if order and order.get("user_id") == uid:
            order_service.cancel_order(order_id, reason="Cancelled by customer")
        await q.edit_message_text(
            premium_customer_text(lang, "cancelled_msg"),
            parse_mode=ParseMode.HTML,
        )
        return
    if data.startswith("copy_binance_id:"):
        oid = int(data.split(":")[1])
        order = db.get_order(oid)
        if order and order["user_id"] == uid:
            await q.message.reply_text(
                t(lang, "copy_binance_id_msg", binance_id=BINANCE_PAY_ID),
                parse_mode=ParseMode.MARKDOWN,
            )
        return
    if data.startswith("copy_amount:"):
        oid = int(data.split(":")[1])
        order = db.get_order(oid)
        if order and order["user_id"] == uid:
            await q.message.reply_text(
                t(lang, "copy_amount_msg", total=f"{order['total_price']:.2f}", cur=CURRENCY),
                parse_mode=ParseMode.MARKDOWN,
            )
        return
    if data.startswith(("paid:", "verify_auto:")):
        # Older order messages may still contain verify_auto. Automatic
        # matching is gone; route that legacy button to TXID entry instead.
        oid = int(data.split(":")[1])
        PENDING[uid] = ("await_txid", oid)
        order = db.get_order(oid)
        prompt_key = (
            "ask_bybit_txid"
            if order and order.get("payment_method") == "bybit"
            else "ask_txid"
        )
        await q.message.reply_text(t(lang, prompt_key, oid=oid),
                                   parse_mode=ParseMode.MARKDOWN)
        return
    if data.startswith("paid_chain:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        network = (
            "BSC (BEP20)"
            if order.get("payment_method") == "usdt_bsc"
            else "Polygon"
        )
        PENDING[uid] = ("await_onchain_txid", {"order_id": oid, "network": network})
        await q.message.reply_text(
            t(lang, "ask_onchain_txid", oid=oid, network=network),
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("continue_pay:"):
        oid = int(data.split(":")[1])
        order = db.get_order(oid)
        if order and order["user_id"] == uid:
            onchain = order.get("payment_method") in {"usdt_bsc", "usdt_polygon"}
            payment_key = (
                "bybit_order_created"
                if order.get("payment_method") == "bybit"
                else "order_created"
            )
            text = (
                onchain_payment_screen(lang, order)
                if onchain
                else premium_customer_text(
                    lang, payment_key, oid=oid, service=order["service_name"],
                    offer=order["offer_name"], qty=order["qty"],
                    total=f"{order['total_price']:.2f}", cur=CURRENCY,
                    binance_id=BINANCE_PAY_ID,
                    bybit_uid=BYBIT_UID,
                )
            )
            await q.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=(
                    kb.onchain_payment_keyboard(lang, oid, USDT_EVM_ADDRESS)
                    if onchain
                    else kb.paid_keyboard(
                        lang, oid, BINANCE_PAY_ID,
                        f"{order['total_price']:.2f}", CURRENCY,
                    )
                ),
            )
        return
    if data.startswith("change_payment:"):
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if not order or int(order.get("user_id") or 0) != uid:
            await q.message.reply_text(t(lang, "not_for_you"))
            return
        if order.get("status") != "pending_payment":
            await q.message.reply_text(t(lang, "payment_order_unavailable"))
            return
        order_service.cancel_order(order_id, reason="Customer changed payment method")
        await send_buy_confirmation(
            q.edit_message_text,
            uid,
            int(order["offer_id"]),
            int(order.get("qty") or 1),
            lang,
            preorder=bool(order.get("is_preorder")),
        )
        return
    if data.startswith("delivery_ok:"):
        order_id = int(data.split(":")[1])
        order = db.get_order(order_id)
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        db.audit_event("order.delivery_confirmed", actor_id=uid, details={"order_id": order_id})
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(t(lang, "delivery_confirmed"))
        return
    if data.startswith("delivery_problem:"):
        order_id = int(data.split(":")[1])
        order = db.get_order(order_id)
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        PENDING[uid] = ("support_order", order_id)
        await q.message.reply_text(t(lang, "support_order_prompt", oid=order_id))
        return
    if data.startswith("rate:"):
        order_id = int(data.split(":", 1)[1])
        order = db.get_order(order_id)
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        await q.message.reply_text(t(lang, "rating_prompt"), reply_markup=kb.rating_keyboard(order_id))
        return
    if data.startswith("rating:"):
        _, order_id, score = data.split(":")
        order = db.get_order(int(order_id))
        if not order or order.get("user_id") != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        db.audit_event("order.rated", actor_id=uid, details={"order_id": int(order_id), "score": int(score)})
        await q.edit_message_text(t(lang, "rating_thanks", score=score))
        return
    if data.startswith("ticket_close:"):
        ticket_id = int(data.split(":", 1)[1])
        ticket = support_service.get_ticket(ticket_id)
        if not ticket or int(ticket.get("user_id") or 0) != uid:
            await q.answer(t(lang, "not_for_you"), show_alert=True)
            return
        support_service.close_ticket(ticket_id)
        pending = PENDING.get(uid)
        if pending and pending[0] == "ticket_message" and int(pending[1]) == ticket_id:
            PENDING.pop(uid, None)
        await q.edit_message_text(
            f"<b>Support Ticket {support_bridge.ticket_reference(ticket_id)}</b>\n\n"
            "Status: <b>Closed</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.home_keyboard(lang, uid),
        )
        await support_bridge.send_ticket_closed(context, ticket, q.from_user)
        return

    if data.startswith("support_cat:"):
        category = data.split(":", 1)[1]
        PENDING[uid] = ("support_category", category)
        if category in {"payment", "delivery", "invalid_content", "order"}:
            orders = db.list_user_orders(uid, limit=8)
            await q.message.reply_text(t(lang, "support_choose_order"), reply_markup=kb.support_order_keyboard(lang, orders))
        else:
            PENDING[uid] = ("support", category)
            await q.message.reply_text(t(lang, "support_prompt"))
        return
    if data.startswith("support_order:"):
        order_id = int(data.split(":", 1)[1])
        pending = PENDING.get(uid)
        category = pending[1] if pending and pending[0] == "support_category" else "other"
        PENDING[uid] = ("support_guided", f"{category}|{order_id}")
        await q.message.reply_text(t(lang, "support_prompt"))
        return


# ---------------- Confirmation avant achat ----------------
async def handle_quantity_selection(update, context, lang):
    """Demande au client combien de comptes/produits il veut acheter."""
    q = update.callback_query
    parts = q.data.split(":")
    offer_id = int(parts[1])
    offer = db.get_offer(offer_id)

    if not offer or offer.get("price") is None or not db.offer_has_stock(offer):
        await q.answer(t(lang, "out_of_stock"), show_alert=True)
        return

    PENDING[q.from_user.id] = ("await_quantity", offer_id)
    send_quantity_prompt = q.message.reply_text if (q.message and q.message.photo) else q.edit_message_text
    stock_display = "∞" if offer.get("unlimited_stock") else offer["stock"]
    bulk_line = ""
    try:
        bulk_quantity = int(offer.get("bulk_quantity") or 0)
        bulk_price = float(offer.get("bulk_unit_price"))
        if bulk_quantity > 0 and 0 <= bulk_price < float(offer["price"]):
            bulk_line = t(
                lang, "bulk_price_line", quantity=bulk_quantity,
                price=f"{bulk_price:.2f}", cur=CURRENCY,
            )
    except (TypeError, ValueError):
        pass
    quantity_text = t(
            lang,
            "choose_quantity",
            offer=offer["name"],
            stock=stock_display,
            price=f"{offer['price']:.2f}",
            cur=CURRENCY,
        )
    if bulk_line:
        quantity_text += f"\n{bulk_line}"
    await send_quantity_prompt(
        quantity_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.quantity_keyboard(lang, offer, page=0),
    )


async def handle_preorder_quantity_selection(update, context, lang):
    """Select a quantity for an empty offer at the pre-order price."""
    q = update.callback_query
    parts = q.data.split(":")
    offer_id = int(parts[1])
    page = int(parts[2]) if q.data.startswith("preorder_page:") and len(parts) > 2 else 0
    offer = db.get_offer(offer_id)

    if not offer or offer.get("price") is None:
        await q.answer(t(lang, "out_of_stock"), show_alert=True)
        return
    if db.offer_has_stock(offer):
        await q.answer(t(lang, "btn_buy"), show_alert=True)
        return

    max_qty = 100
    PENDING[q.from_user.id] = ("await_preorder_quantity", offer_id)
    send_quantity_prompt = q.message.reply_text if (q.message and q.message.photo) else q.edit_message_text
    await send_quantity_prompt(
        t(
            lang,
            "choose_preorder_quantity",
            offer=offer["name"],
            price=f"{order_service.preorder_unit_price(offer['price']):.2f}",
            cur=CURRENCY,
            max_qty=max_qty,
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.preorder_quantity_keyboard(lang, offer_id, page=page, max_qty=max_qty),
    )


async def send_buy_confirmation(send, uid, offer_id, qty, lang, preorder=False):
    """Validate a quantity and display the purchase summary."""
    offer = db.get_offer(offer_id)
    if not offer or offer.get("price") is None:
        return False
    if _is_single_unit_offer(offer):
        qty = 1
        preorder = False
    if preorder:
        if db.offer_has_stock(offer) or qty < 1 or qty > 100:
            return False
    elif not db.offer_has_stock(offer, qty):
        return False
    svc = db.get_service(offer["service_id"])
    unit_price = order_service.unit_price_for_quantity(offer, qty, preorder=preorder)
    gross_total = round(unit_price * qty, 2)
    referral_discount = loyalty_service.discount_for_order(uid, gross_total)
    discount_line = ""
    if referral_discount["amount"] > 0:
        discount_line = t(
            lang, "loyalty_discount_line",
            level=(referral_discount["level"] or "").title(),
            percent=referral_discount["discount_percent"],
            amount=f"{referral_discount['amount']:.2f}", cur=CURRENCY,
        )

    await send(
        t(lang, "confirm_purchase",
          emoji=svc["emoji"] if svc else "📦", service=svc["name"] if svc else "",
          offer=offer["name"],
          price=f"{unit_price:.2f}", cur=CURRENCY, qty=qty,
          total=f"{gross_total - referral_discount['amount']:.2f}",
          discount_line=t(lang, "preorder_line") + discount_line if preorder else discount_line),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.confirm_buy_keyboard(lang, offer_id, qty, preorder=preorder),
    )
    return True


async def handle_buy_confirmation(update, context, lang, preorder=False):
    """Affiche un résumé avant de créer la commande."""
    q = update.callback_query
    uid = q.from_user.id
    parts = q.data.split(":")
    offer_id = int(parts[1])
    qty = int(parts[2]) if len(parts) > 2 else 1
    offer = db.get_offer(offer_id)
    if _is_single_unit_offer(offer):
        qty = 1
    send_confirmation = (
        q.message.reply_text if q.message and q.message.photo else q.edit_message_text
    )
    if not await send_buy_confirmation(
        send_confirmation, uid, offer_id, qty, lang, preorder=preorder,
    ):
        await q.message.reply_text(t(lang, "out_of_stock"))


def onchain_payment_screen(lang, order):
    method = order.get("payment_method")
    network = "BSC (BEP20)" if method == "usdt_bsc" else "Polygon"
    contract_suffix = "97955" if method == "usdt_bsc" else "58e8f"
    return (
        f"<b>USDT PAYMENT — {network}</b>\n\n"
        f"<b>Product</b>\n{html.escape(str(order.get('offer_name') or '—'))}\n"
        f"<b>Order</b>\n#{int(order['id'])}\n\n"
        f"<b>Wallet Address</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to pay</b>\n"
        "<blockquote>1️⃣ Copy the wallet address above\n"
        f"2️⃣ Send exactly <b>{float(order['total_price']):.2f} USDT</b>\n"
        f"3️⃣ Select only the <b>{network}</b> network\n"
        "4️⃣ Copy the Transaction ID (TXID/hash)\n"
        "5️⃣ Tap Submit TXID and paste it in this chat\n"
        "6️⃣ Auto-verify and begin delivery ⚡</blockquote>\n\n"
        f"<blockquote>⚠️ <b>{network} only:</b> verify that the USDT contract "
        f"address ends in <b>{contract_suffix}</b>.</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this screen "
        "for automatic verification.</blockquote>"
    )


async def handle_buy_confirmed(update, context, lang, payment_method="binance"):
    """Cr?e la commande apr?s confirmation de l'utilisateur."""
    q = update.callback_query
    uid = q.from_user.id
    if payment_method == "bybit":
        await q.message.reply_text(t(lang, "bybit_disabled"))
        return
    parts = q.data.split(":")
    offer_id = int(parts[1])
    qty = int(parts[2]) if len(parts) > 2 else 1
    preorder = len(parts) > 3 and parts[3] == "preorder"
    offer = db.get_offer(offer_id)
    if _is_single_unit_offer(offer):
        qty = 1
        preorder = False

    if not offer or offer["price"] is None or (
        not preorder and not db.offer_has_stock(offer, qty)
    ) or (preorder and (db.offer_has_stock(offer) or qty < 1 or qty > 100)):
        await q.message.reply_text(t(lang, "out_of_stock"))
        return

    try:
        order = order_service.create_order(
            uid, offer, qty=qty, payment_method=payment_method, preorder=preorder,
        )
        order_service.cancel_incomplete_orders(uid, exclude_order_id=order["id"])
    except ValueError as exc:
        # cb_navigation already acknowledged this callback. Telegram rejects a
        # second q.answer(), which previously left wallet errors invisible.
        await q.message.reply_text(str(exc))
        return

    if order["total_price"] == 0:
        await q.edit_message_text(t(lang, "wallet_payment_processing"), parse_mode=ParseMode.MARKDOWN)
        result = await asyncio.to_thread(payment_service.confirm_wallet_order, order["id"], uid)
        await send_payment_result(q.message, context, lang, order["id"], result, uid)
        return

    if payment_method in {"usdt_bsc", "usdt_polygon"}:
        await q.edit_message_text(
            onchain_payment_screen(lang, order),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.onchain_payment_keyboard(
                lang, order["id"], USDT_EVM_ADDRESS,
            ),
        )
        return

    payment_key = "bybit_order_created" if payment_method == "bybit" else "order_created"
    text = premium_customer_text(
        lang, payment_key, oid=order["id"], service=order["service_name"],
        offer=order["offer_name"], qty=order["qty"],
        total=f"{order['total_price']:.2f}", cur=CURRENCY,
        binance_id=BINANCE_PAY_ID,
        bybit_uid=BYBIT_UID,
    )
    await q.edit_message_text(text, parse_mode=ParseMode.HTML,
                              reply_markup=kb.paid_keyboard(
                                  lang, order["id"], BINANCE_PAY_ID,
                                  f"{order['total_price']:.2f}", CURRENCY,
                              ))


# ---------------- Saisie en attente (txid / admin) ----------------
async def handle_pending_input(update, context, lang):
    uid = update.effective_user.id
    kind, ref = PENDING.get(uid)
    text = update.message.text.strip()

    if kind == "adm_lovable_trial" and uid == ADMIN_ID:
        customer_id = int(ref)
        try:
            await context.bot.send_message(
                customer_id,
                "🎁 <b>LOVABLE FREE TRIAL</b>\n\n"
                "Your one-hour trial license is ready.\n\n"
                f"🔑 <b>License</b>\n<code>{html.escape(text)}</code>\n\n"
                "Open the extension and enter this license.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb.lovable_back_keyboard(lang_of(customer_id)),
            )
            license_row = await asyncio.to_thread(
                lovable_service.complete_trial, customer_id, text,
            )
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Échec d’envoi de la licence : {exc}")
            return
        PENDING.pop(uid, None)
        await send_lovable_extension(context.bot, customer_id, lang_of(customer_id))
        await update.message.reply_text(
            f"✅ Licence d’essai envoyée manuellement au client {customer_id}.\n"
            f"Expiration : {lovable_expiry_text(license_row['expires_at'])}"
        )
        return

    if kind == "adm_lovable_zip" and uid == ADMIN_ID:
        await update.message.reply_text(
            "📎 Envoyez le fichier de l’extension comme document ZIP, pas comme texte."
        )
        return

    if kind == "await_quantity":
        ref_id = ref
        offer = db.get_offer(int(ref_id))
        try:
            qty = int(text)
        except ValueError:
            qty = 0
        stock = "∞" if (offer or {}).get("unlimited_stock") else int((offer or {}).get("stock") or 0)
        if not offer or not db.offer_has_stock(offer, qty) or qty < 1 or qty > 500:
            await update.message.reply_text(
                t(lang, "quantity_invalid", stock=stock),
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        PENDING.pop(uid, None)
        await send_buy_confirmation(update.message.reply_text, uid, int(ref_id), qty, lang)
        return

    if kind == "await_preorder_quantity":
        offer = db.get_offer(int(ref))
        try:
            qty = int(text)
        except ValueError:
            qty = 0
        if not offer or db.offer_has_stock(offer) or qty < 1 or qty > 100:
            await update.message.reply_text(
                t(lang, "preorder_quantity_invalid", max_qty=100),
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        PENDING.pop(uid, None)
        await send_buy_confirmation(
            update.message.reply_text, uid, int(ref), qty, lang, preorder=True,
        )
        return

    if kind == "catalog_request":
        request_text = rich_text_from_message(update.message).strip()
        if not request_text:
            await update.message.reply_text(
                premium_customer_text(lang, "catalog_request_prompt"),
                parse_mode=ParseMode.HTML,
            )
            return
        ticket = support_service.create_ticket(uid, request_text, category="catalog_request")
        PENDING.pop(uid, None)
        await support_bridge.send_client_text(
            context,
            ticket,
            update.effective_user,
            request_text,
            event="New catalog request",
        )
        await update.message.reply_text(
            premium_customer_text(lang, "catalog_request_sent"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.home_keyboard(lang, uid),
        )
        await delete_customer_support_message(update.message)
        log.info("Catalog request ticket %s created by user %s", ticket["id"], uid)
        return

    if kind == "adm_flash_start" and uid == ADMIN_ID:
        try:
            parts = text.replace(",", ".").split()
            if len(parts) != 2:
                raise ValueError("Format attendu : prix puis durée.")
            sale_price = float(parts[0])
            duration_minutes = int(parts[1])
            offer = db.start_flash_sale(ref, sale_price, duration_minutes)
        except (TypeError, ValueError) as exc:
            await update.message.reply_text(
                f"⚠️ Valeurs invalides. Envoyez : `prix durée_en_minutes`\n"
                f"Exemple : `3 480`\n\n{exc}",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        PENDING.pop(uid, None)
        queued = queue_broadcast("flash_sale", offer_id=ref)
        await update.message.reply_text(
            f"⚡ Vente flash lancée pour *{offer['name']}*.\n"
            f"Prix : *{offer['flash_sale_original_price']:.2f} → {offer['price']:.2f} {CURRENCY}*\n"
            f"📣 Envoi lancé en arrière-plan pour *{queued['recipient_count']} utilisateur(s)*.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.offer_admin_keyboard(ref),
        )
        return

    if kind == "adm_broadcast_message" and uid == ADMIN_ID:
        PENDING.pop(uid, None)
        queued = queue_broadcast(
            "admin_message",
            source_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        await update.message.reply_text(
            f"✅ Annonce mise en file pour {queued['recipient_count']} utilisateur(s).\n"
            "L’envoi continue en arrière-plan.",
            reply_markup=admin.admin_panel_keyboard(),
        )
        return
    if kind == "adm_ticket_style" and uid == ADMIN_ID:
        try:
            saved = support_bridge.save_ticket_style(str(ref), text)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            return
        PENDING.pop(uid, None)
        await update.message.reply_text(
            f"✅ Design enregistré : {saved}",
            reply_markup=admin.ticket_style_keyboard(),
        )
        return
    if kind == "adm_text_override" and uid == ADMIN_ID:
        saved_key = ""
        override_icon = custom_emoji_from_message(update.message)
        override_text = (
            text_without_custom_emojis(update.message)
            if kb.is_button_text_key(ref.rsplit("|", 1)[0] if isinstance(ref, str) and "|" in ref else "")
            else rich_text_from_message(update.message)
        )
        if isinstance(ref, str) and "|" in ref:
            key, selected_lang = ref.rsplit("|", 1)
            if key not in TRANSLATIONS or selected_lang not in {"en", "ar"}:
                await update.message.reply_text("⚠️ Sélection de texte invalide.")
                return
            db.set_text_override(key, selected_lang, override_text, override_icon)
            saved_key = key
        else:
            parts = [part.strip() for part in text.split("|", 2)]
            if len(parts) != 3 or parts[1] not in {"en", "ar"} or not parts[0] or not parts[2]:
                await update.message.reply_text("⚠️ Format : `key | en/ar | new text`", parse_mode=ParseMode.MARKDOWN)
                return
            db.set_text_override(parts[0], parts[1], parts[2])
            saved_key = parts[0]
        PENDING.pop(uid, None)
        keys = sorted(TRANSLATIONS)
        if saved_key in keys:
            category = admin.text_category_for_key(saved_key)
            await update.message.reply_text(
                "✅ Texte enregistré immédiatement. Choisissez un autre texte à modifier :",
                reply_markup=admin.texts_category_keyboard(category),
            )
        else:
            await update.message.reply_text("✅ Texte enregistré immédiatement.", reply_markup=admin.customize_keyboard())
        return

    if kind == "adm_btn_add" and uid == ADMIN_ID:
        parts = [part.strip() for part in text.split("|", 2)]
        if len(parts) != 3 or not re.fullmatch(r"https?://\S+", parts[2]):
            await update.message.reply_text(
                "⚠️ Format : `English | العربية | https://exemple.com`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        db.add_custom_button(*parts)
        PENDING.pop(uid, None)
        await update.message.reply_text("✅ Bouton ajouté au menu principal.", reply_markup=admin.buttons_editor_keyboard())
        return
    if kind == "adm_addoff_image" and uid == ADMIN_ID:
        if text.casefold() in {"skip", "pass", "none", "no image"}:
            service_id = int(ref)
            service = db.get_service(service_id) or {}
            is_method = str(service.get("name") or "").strip().lower() == "methods"
            PENDING[uid] = ("adm_addoff_name", {
                "service_id": service_id,
                "photo_file_id": "",
            })
            await update.message.reply_text(
                f"✏️ *New {'method' if is_method else 'offer'} — step 2/{5 if is_method else 6}*\n\n"
                f"Send the {'method' if is_method else 'offer'} name:",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await update.message.reply_text(
            "🖼 Send an image, or type `skip` to continue without one.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if kind == "adm_offimage" and uid == ADMIN_ID:
        await update.message.reply_text("🖼 Envoyez la nouvelle image comme photo Telegram.")
        return

    if kind == "adm_addoff_name" and uid == ADMIN_ID:
        clean_name = kb.clean_button_name(text)[:120]
        if not clean_name:
            await update.message.reply_text("⚠️ Le nom de l’offre ne peut pas être vide.")
            return
        data = dict(ref)
        data["name"] = clean_name
        service = db.get_service(int(data["service_id"])) or {}
        if str(service.get("name") or "").strip().lower() == "methods":
            data.update({"period_days": 0, "period_value": 0, "period_unit": "days", "warranty_days": 0, "warranty_value": 0, "warranty_unit": "days"})
            PENDING[uid] = ("adm_addoff_description", data)
            await update.message.reply_text(
                "📝 *New method — step 2/4*\n\nSend the public sales description:",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            PENDING[uid] = ("adm_addoff_period", data)
            await update.message.reply_text(
                "📅 *Étape 3/5* — envoyez la période (ex: `30 days`, `3 months` ou `1 year`) :",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    if kind == "adm_addoff_period" and uid == ADMIN_ID:
        try:
            period_value, period_unit, period_days = parse_duration_input(text)
        except (TypeError, ValueError):
            await update.message.reply_text("⚠️ Durée invalide. Exemple : 30 days, 3 months ou 1 year.")
            return
        data = dict(ref)
        data["period_days"] = period_days
        data["period_value"] = period_value
        data["period_unit"] = period_unit
        PENDING[uid] = ("adm_addoff_warranty", data)
        await update.message.reply_text(
            "🛡️ *Étape 4/6* — envoyez la garantie (`0` = aucune, ou ex: `6 months`, `1 year`) :",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if kind == "adm_addoff_warranty" and uid == ADMIN_ID:
        try:
            warranty_value, warranty_unit, warranty_days = parse_duration_input(text, allow_zero=True)
        except (TypeError, ValueError):
            await update.message.reply_text("⚠️ Durée invalide. Exemple : 0, 30 days, 6 months ou 1 year.")
            return
        data = dict(ref)
        data["warranty_days"] = warranty_days
        data["warranty_value"] = warranty_value
        data["warranty_unit"] = warranty_unit
        PENDING[uid] = ("adm_addoff_description", data)
        await update.message.reply_text(
            "📝 *Étape 5/6* — envoyez la description de l’offre :",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if kind == "adm_addoff_description" and uid == ADMIN_ID:
        description = rich_text_from_message(update.message)
        if not description:
            await update.message.reply_text("⚠️ La description ne peut pas être vide.")
            return
        data = dict(ref)
        data["description"] = description
        PENDING[uid] = ("adm_addoff_price", data)
        service = db.get_service(int(data["service_id"])) or {}
        is_method = str(service.get("name") or "").strip().lower() == "methods"
        await update.message.reply_text(
            (
                "💵 *New method — step 3/4*\n\nSend the selling price in USDT (example: `4.99`):"
                if is_method else
                "💵 *Étape 6/6* — envoyez le prix unitaire en USDT (exemple : 4.99) :"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if kind == "adm_addoff_price" and uid == ADMIN_ID:
        try:
            price = float(text.replace(",", "."))
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Prix invalide. Envoyez un nombre, par exemple : 4.99")
            return
        data = dict(ref)
        service = db.get_service(int(data["service_id"])) or {}
        is_method_offer = str(service.get("name") or "").strip().lower() == "methods"
        offer_id = db.add_offer(
            data["service_id"], data["name"], price, 0,
            warranty_days=data["warranty_days"],
            period_days=data["period_days"],
            warranty_value=data["warranty_value"],
            warranty_unit=data["warranty_unit"],
            period_value=data["period_value"],
            period_unit=data["period_unit"],
            description=data["description"],
            instructions="",
            photo_file_id=data["photo_file_id"],
            unlimited_stock=False if is_method_offer else False,
            auto_delivery=True,
            active=not is_method_offer,
        )
        if is_method_offer:
            PENDING[uid] = ("adm_method_media", offer_id)
            confirmation = (
                "🎬 *New method — step 4/4*\n\n"
                "Send everything the customer must receive after payment. You can send:\n"
                "• text instructions or links\n"
                "• photos\n"
                "• videos\n"
                "• documents\n\n"
                "Send multiple items in the required delivery order, then type `done`.\n"
                "The method remains hidden and cannot be purchased until content is saved."
            )
        else:
            PENDING.pop(uid, None)
            confirmation = (
                "✅ Offre créée.\n\n📦 Le stock sera calculé automatiquement à partir des comptes ajoutés.\n"
                "🛒 Les ventes seront calculées automatiquement à partir des commandes confirmées.\n\n"
                "Ajoutez maintenant les comptes pour alimenter le stock."
            )
        await update.message.reply_text(
            confirmation,
            parse_mode=ParseMode.MARKDOWN if is_method_offer else None,
            reply_markup=admin.offer_admin_keyboard(offer_id),
        )
        return

    if kind == "await_withdraw_amount":
        try:
            amount = round(float(text.replace(",", ".")), 2)
            balance = wallet_service.balance_cents(uid) / 100
            if amount < 10 or amount > balance:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                f"⚠️ Enter an amount between 10.00 and {wallet_service.balance_cents(uid) / 100:.2f} {CURRENCY}."
            )
            return
        PENDING[uid] = ("await_withdraw_method", amount)
        await update.message.reply_text("Choose your withdrawal method:", reply_markup=kb.withdrawal_methods_keyboard(lang))
        return

    if kind == "adm_warranty_refuse_reason" and uid == ADMIN_ID:
        reason = rich_text_from_message(update.message).strip()
        if not reason:
            await update.message.reply_text("Please provide a reason for refusing this warranty request.")
            return
        request = db.refuse_warranty_request(int(ref), reason)
        if not request:
            PENDING.pop(uid, None)
            await update.message.reply_text("⚠️ This warranty request has already been processed.")
            return
        PENDING.pop(uid, None)
        customer_id = int(request["user_id"])
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                customer_id,
                "❌ <b>Warranty request refused</b>\n\n"
                f"Request <b>#{int(ref)}</b> was refused.\n"
                f"Reason: {html.escape(reason)}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang_of(customer_id), customer_id),
            )
        await update.message.reply_text(f"✅ Warranty request #{int(ref)} refused and customer notified.")
        return

    if kind == "adm_warranty_replacement" and uid == ADMIN_ID:
        replacement = update.message.text.strip()
        if not replacement:
            await update.message.reply_text("Please send the replacement content.")
            return
        request_id = int(ref)
        request = db.get_conn().warranty_requests.find_one({
            "id": request_id,
            "status": "replacement_pending",
        })
        if not request:
            PENDING.pop(uid, None)
            await update.message.reply_text(
                "⚠️ This warranty request is no longer awaiting replacement delivery."
            )
            return
        customer_id = int(request["user_id"])
        order_id = int(request["order_id"])
        delivery_text = (
            "🔁 <b>Your warranty replacement is ready</b>\n\n"
            f"Order: <code>#{order_id}</code>\n"
            f"Warranty request: <code>#{request_id}</code>\n\n"
            f"<blockquote>{html.escape(replacement)}</blockquote>"
        )
        try:
            await _send_manual_delivery(
                context.bot,
                customer_id=customer_id,
                delivery_text=delivery_text,
                raw_content=replacement,
                reply_markup=kb.home_keyboard(lang_of(customer_id), customer_id),
            )
        except Exception as exc:
            await update.message.reply_text(
                f"⚠️ Failed to send the replacement: {exc}\n"
                "The request is still pending; send the message again to retry."
            )
            return
        completed = db.complete_warranty_replacement(request_id)
        PENDING.pop(uid, None)
        if not completed:
            await update.message.reply_text(
                "⚠️ The replacement was sent, but the warranty status changed before it could be completed."
            )
            return
        await update.message.reply_text(
            f"✅ Replacement sent to the customer. Warranty request #{request_id} is complete."
        )
        return

    if kind == "adm_method_media" and uid == ADMIN_ID:
        offer = db.get_offer(int(ref))
        media = list((offer or {}).get("method_media") or [])
        if text.casefold() in {"done", "finish", "finished"}:
            if not media:
                await update.message.reply_text(
                    "⚠️ Add at least one text, photo, video, or document before finishing the method."
                )
                return
            db.update_offer(
                int(ref), active=1, unlimited_stock=True, auto_delivery=True,
            )
            PENDING.pop(uid, None)
            await update.message.reply_text(
                f"✅ Method content saved ({len(media)} item(s)). The method is now active and ready for sale.",
                reply_markup=admin.offer_admin_keyboard(int(ref)),
            )
        elif text.casefold() in {"clear", "clear all", "delete all"}:
            db.update_offer(int(ref), method_media=[], active=0, unlimited_stock=False)
            await update.message.reply_text(
                "🧹 Method content cleared. The method is hidden until you add content and send `done`."
            )
        else:
            if not offer:
                PENDING.pop(uid, None)
                await update.message.reply_text("⚠️ Method offer not found.")
                return
            media.append({"type": "text", "text": text[:4000], "caption": ""})
            db.update_offer(int(ref), method_media=media, unlimited_stock=False, active=0)
            await update.message.reply_text(
                f"✅ Text content item {len(media)} saved. Send more content or `done`.",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    if kind == "adm_bot_package_doc" and uid == ADMIN_ID:
        await update.message.reply_text("📄 Envoyez le document client comme fichier Telegram.")
        return

    if kind == "adm_bot_package_link" and uid == ADMIN_ID:
        delivery_url = text.strip()
        if not re.fullmatch(r"https://github\.com/[^\s/]+/[^\s/]+/?", delivery_url, flags=re.IGNORECASE):
            await update.message.reply_text(
                "⚠️ Envoyez un lien de dépôt GitHub valide, par exemple :\n"
                "https://github.com/organisation/project"
            )
            return
        db.update_offer(int(ref), delivery_url=delivery_url.rstrip("/"))
        PENDING.pop(uid, None)
        await update.message.reply_text(
            "✅ Lien GitHub de livraison enregistré. Il sera envoyé uniquement après paiement confirmé.",
            reply_markup=admin.offer_admin_keyboard(int(ref)),
        )
        return

    if kind == "warranty_reason":
        reason = rich_text_from_message(update.message).strip()
        if not reason:
            await update.message.reply_text("Please describe the problem before sending the request.")
            return
        if len(reason) > 2000:
            await update.message.reply_text("Please keep the description under 2000 characters.")
            return
        order_id = int(ref["order_id"])
        request = db.create_warranty_request(
            uid, order_id, int(ref["days_used"]), float(ref["refund"]), reason,
        )
        PENDING.pop(uid, None)
        await update.message.reply_text(
            "✅ Warranty request sent. The admin will test the account and then offer replacement or refund.",
            reply_markup=kb.home_keyboard(lang, uid),
        )
        with contextlib.suppress(Exception):
            report = admin.warranty_request_report(request)
            await context.bot.send_message(
                ADMIN_ID,
                admin.warranty_request_text(request),
                parse_mode=ParseMode.HTML,
                reply_markup=admin.warranty_request_keyboard(request),
            )
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=InputFile(
                    io.BytesIO(report.encode("utf-8")),
                    filename=f"warranty-{int(request['id'])}-order-{order_id}.txt",
                ),
                caption=(
                    f"Full warranty report #{int(request['id'])}: supplier, payment, "
                    "inventory, customer message and real delivered content."
                ),
            )
        return

    if kind == "await_withdraw_destination":
        destination = text.strip()
        method = str(ref.get("method") if isinstance(ref, dict) else ref)
        if not destination or len(destination) > 180:
            await update.message.reply_text("⚠️ Please send a valid destination.")
            return
        amount = float(ref.get("amount") if isinstance(ref, dict) else 0)
        customer = update.effective_user
        customer_name = html.escape(str(getattr(customer, "full_name", "") or "—"))
        customer_username = str(getattr(customer, "username", "") or "").strip()
        customer_username = html.escape(f"@{customer_username}" if customer_username else "—")
        requested_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        try:
            request = await asyncio.to_thread(db.create_withdrawal, uid, amount, method, destination)
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            PENDING.pop(uid, None)
            return
        PENDING.pop(uid, None)
        await update.message.reply_text(
            f"✅ Withdrawal request #{request['id']} submitted for <b>{amount:.2f} {CURRENCY}</b>.\n\nProcessing time: 1 to 24 hours.",
            parse_mode=ParseMode.HTML, reply_markup=kb.home_keyboard(lang, uid),
        )
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(f"💸 <b>New withdrawal request #{request['id']}</b>\n\n"
                      f"Name: <b>{customer_name}</b>\nUsername: <b>{customer_username}</b>\n"
                      f"User ID: <code>{uid}</code>\nAmount: <b>{amount:.2f} {CURRENCY}</b>\n"
                      f"Method: <b>{html.escape(method)}</b>\nDestination: <code>{html.escape(destination)}</code>\n"
                      f"Requested: <b>{requested_at}</b>"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.withdrawal_admin_keyboard(request["id"]),
            )
        return

    if kind == "await_withdraw_method":
        return

    if kind == "await_txid":
        await process_txid(update, context, lang, ref, text)
        PENDING.pop(uid, None)
        return

    if kind == "await_onchain_txid":
        order_id = int(ref["order_id"])
        await update.message.reply_text(
            premium_customer_text(lang, "verifying"),
            parse_mode=ParseMode.HTML,
        )
        result = await asyncio.to_thread(
            payment_service.submit_onchain_payment, order_id, text, uid,
        )
        if result["status"] in {"confirmed", "confirmed_no_delivery", "delivered"}:
            PENDING.pop(uid, None)
            await send_payment_result(
                update.message, context, lang, order_id, result, uid,
            )
            return
        if result["status"] == "pending":
            await update.message.reply_text(
                t(lang, "onchain_payment_pending", oid=order_id),
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await update.message.reply_text(
            result.get("error_message") or "Invalid transaction ID.",
        )
        return

    if kind == "await_topup_txid":
        provider = "bybit" if ref == "bybit" else "binance"
        result = await asyncio.to_thread(
            wallet_service.claim_transfer, uid, text, provider,
        )
        if result["status"] == "confirmed":
            PENDING.pop(uid, None)
            await update.message.reply_text(
                premium_customer_text(lang, "topup_success", amount=f"{result['amount']:.2f}", balance=f"{result['balance']:.2f}"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang, uid),
            )
        elif result.get("code") == "already_used":
            PENDING.pop(uid, None)
            await update.message.reply_text(
                premium_customer_text(lang, "topup_already_confirmed"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang, uid),
            )
        else:
            await update.message.reply_text(
                premium_customer_text(lang, "topup_failed"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.topup_keyboard(lang, uid),
            )
        return

    if kind == "await_onchain_topup_amount":
        try:
            amount = round(float(text.replace(",", ".")), 2)
            if amount < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Enter a valid amount of at least 1 USDT.")
            return
        network = str(ref)
        PENDING[uid] = (
            "await_onchain_topup_txid",
            {"network": network, "amount": amount, "created_at": int(time.time())},
        )
        await update.message.reply_text(
            topup_onchain_screen(lang, network, amount),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.topup_provider_keyboard(
                lang, network, USDT_EVM_ADDRESS,
            ),
        )
        return

    if kind == "await_solana_topup_signature":
        await update.message.reply_text(premium_customer_text(lang, "verifying"), parse_mode=ParseMode.HTML)
        result = await asyncio.to_thread(wallet_service.submit_solana_topup, uid, text)
        if result["status"] == "pending":
            await update.message.reply_text(t(lang, "topup_sol_pending"))
            return
        if result.get("code") == "already_used":
            PENDING.pop(uid, None)
            await update.message.reply_text(premium_customer_text(lang, "topup_already_confirmed"), parse_mode=ParseMode.HTML, reply_markup=kb.home_keyboard(lang, uid))
            return
        if result["status"] != "confirmed":
            await update.message.reply_text(result.get("message") or "Invalid Solana transaction signature.")
            return
        PENDING.pop(uid, None)
        await update.message.reply_text(t(lang, "topup_sol_approved", sol_amount=f"{result['sol_amount']:.9f}".rstrip("0").rstrip("."), rate=f"{result['rate']:.4f}".rstrip("0").rstrip("."), amount=f"{result['amount']:.2f}", balance=f"{result['balance']:.2f}"), parse_mode=ParseMode.HTML, reply_markup=kb.home_keyboard(lang, uid))
        return

    if kind == "await_onchain_topup_txid":
        await update.message.reply_text(
            premium_customer_text(lang, "verifying"),
            parse_mode=ParseMode.HTML,
        )
        result = await asyncio.to_thread(
            wallet_service.submit_onchain_topup,
            uid, text, float(ref["amount"]), str(ref["network"]),
            int(ref["created_at"]),
        )
        if result["status"] == "pending":
            await update.message.reply_text(t(lang, "topup_onchain_pending"))
            return
        if result["status"] != "confirmed":
            await update.message.reply_text(result.get("message") or "Invalid transaction ID.")
            return
        PENDING.pop(uid, None)
        await update.message.reply_text(
            premium_customer_text(
                lang,
                "topup_onchain_approved",
                amount=f"{result['amount']:.2f}",
                balance=f"{result['balance']:.2f}",
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.home_keyboard(lang, uid),
        )
        return

    # --- Admin : prix ---
    if kind == "adm_setprice" and uid == ADMIN_ID:
        try:
            price = float(text.replace(",", "."))
            if price < 0:
                raise ValueError
            db.update_offer(ref, price=price)
            await update.message.reply_text(f"✅ Prix mis à jour : {price:.2f} {CURRENCY}")
        except ValueError:
            await update.message.reply_text("⚠️ Valeur invalide. Envoyez un nombre, ex : 1.99")
            return
        PENDING.pop(uid, None)
        await update.message.reply_text("🛠️ *Panneau Admin*", parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=admin.admin_panel_keyboard())
        return

    if uid == ADMIN_ID and kind in {
        "adm_svcname", "adm_svcemoji", "adm_svcsuffix", "adm_offname", "adm_offemoji", "adm_offnote",
        "adm_offdesc", "adm_offdelay",
    }:
        custom_emoji_id = custom_emoji_from_message(update.message)
        if kind not in {"adm_offnote", "adm_offdesc", "adm_svcemoji", "adm_svcsuffix", "adm_offemoji"} and not text and not custom_emoji_id:
            await update.message.reply_text("⚠️ La valeur ne peut pas être vide.")
            return
        if kind == "adm_svcname":
            service = db.get_service(ref)
            clean_name = kb.clean_button_name(text)
            db.update_service(
                ref,
                name=(clean_name[:80] or service["name"]),
                custom_emoji_id=custom_emoji_id,
            )
            PENDING.pop(uid, None)
            await update.message.reply_text(
                f"✅ Nom du service mis à jour : {clean_name}",
                reply_markup=admin.service_admin_keyboard(ref),
            )
            return
        elif kind == "adm_svcemoji":
            # A Premium emoji is sent as both text and an entity. Keep only the
            # entity-backed icon; otherwise Telegram displays two icons.
            raw_emoji = "" if custom_emoji_id else (text.strip() if text else "")
            db.update_service(
                ref,
                emoji=raw_emoji[:12],
                custom_emoji_id=custom_emoji_id,
            )
            PENDING.pop(uid, None)
            display_emoji = raw_emoji or "✅"
            await update.message.reply_text(
                f"✅ Emoji du service mis à jour : {display_emoji}",
                reply_markup=admin.service_admin_keyboard(ref),
            )
            return
        elif kind == "adm_svcsuffix":
            if custom_emoji_id and not text.strip():
                await update.message.reply_text(
                    "⚠️ Telegram ne permet pas une icône Premium native à droite. "
                    "Envoyez un emoji Unicode, par exemple : ✅"
                )
                return
            suffix_emoji = text.strip()[:12]
            db.update_service(ref, suffix_emoji=suffix_emoji)
            PENDING.pop(uid, None)
            await update.message.reply_text(
                f"✅ Emoji droit mis à jour : {suffix_emoji or 'aucun'}",
                reply_markup=admin.service_admin_keyboard(ref),
            )
            return
        elif kind == "adm_offname":
            offer = db.get_offer(ref)
            clean_name = kb.clean_button_name(text)
            db.update_offer(
                ref,
                name=(clean_name[:120] or offer["name"]),
                custom_emoji_id=custom_emoji_id,
            )
            PENDING.pop(uid, None)
            await update.message.reply_text(
                f"✅ Nom de l'offre mis à jour : {clean_name}",
                reply_markup=admin.offer_admin_keyboard(ref),
            )
            return
        elif kind == "adm_offemoji":
            raw_emoji = "" if custom_emoji_id else (text.strip() if text else "")
            db.update_offer(
                ref,
                emoji=raw_emoji[:12],
                custom_emoji_id=custom_emoji_id,
            )
            PENDING.pop(uid, None)
            await update.message.reply_text(
                "✅ Emoji de l'offre mis à jour.",
                reply_markup=admin.offer_admin_keyboard(ref),
            )
            return
        elif kind == "adm_offnote":
            try:
                raw_text = text.strip().upper()
                if raw_text == "NW":
                    warranty_value, warranty_unit, wdays = 0, "days", 0
                else:
                    warranty_value, warranty_unit, wdays = parse_duration_input(text, allow_zero=True)
            except (TypeError, ValueError):
                await update.message.reply_text("⚠️ Envoyez 0/NW, 30 days, 6 months ou 1 year.")
                return
            db.update_offer(
                ref,
                warranty_days=wdays,
                warranty_value=warranty_value,
                warranty_unit=warranty_unit,
                note="NW" if wdays == 0 else warranty_service.format_duration(warranty_value, warranty_unit),
            )
        elif kind == "adm_offperiod":
            try:
                period_value, period_unit, period_days = parse_duration_input(text)
            except (TypeError, ValueError):
                await update.message.reply_text("⚠️ Envoyez 30 days, 3 months ou 1 year.")
                return
            db.update_offer(
                ref, period_days=period_days,
                period_value=period_value, period_unit=period_unit,
            )
        elif kind == "adm_offdesc":
            db.update_offer(ref, description=rich_text_from_message(update.message))
        else:
            db.update_offer(ref, delivery_delay=text[:120])
        PENDING.pop(uid, None)
        await update.message.reply_text("✅ Modification enregistrée.",
                                        reply_markup=admin.admin_panel_keyboard())
        return

    if kind == "adm_addsvc" and uid == ADMIN_ID:
        parts = [p.strip() for p in text.split("|", 1)]
        name, emoji = parts[0], parts[1] if len(parts) > 1 else "📦"
        if not name:
            await update.message.reply_text("⚠️ Format : Nom du service | emoji")
            return
        db.add_service(
            kb.clean_button_name(name)[:80],
            "" if custom_emoji_from_message(update.message) else emoji[:12],
            custom_emoji_id=custom_emoji_from_message(update.message),
        )
        PENDING.pop(uid, None)
        await update.message.reply_text("✅ Service ajouté.", reply_markup=admin.admin_panel_keyboard())
        return

    if kind == "adm_addoff" and uid == ADMIN_ID:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            await update.message.reply_text("⚠️ Format : Nom | prix | note optionnelle")
            return
        try:
            price = float(parts[1].replace(",", "."))
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Prix invalide.")
            return
        note = parts[2][:250] if len(parts) > 2 else ""
        db.add_offer(
            ref,
            kb.clean_button_name(parts[0])[:120],
            price,
            0,
            note,
            custom_emoji_id=custom_emoji_from_message(update.message),
        )
        PENDING.pop(uid, None)
        await update.message.reply_text("✅ Offre ajoutée.", reply_markup=admin.admin_panel_keyboard())
        return

    if kind == "adm_inventory" and uid == ADMIN_ID:
        if text.strip().upper() == inventory_service.MANUAL_STOCK_KEYWORD:
            PENDING[uid] = ("adm_manual_stock", ref)
            await update.message.reply_text(
                "📦 *Stock manuel*\n\n"
                "Envoyez le nombre de comptes à afficher publiquement.\n"
                "Après chaque achat, ce stock diminuera automatiquement.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        try:
            items = inventory_service.parse_bulk_inventory(text)
            added = inventory_service.add_items(ref, items)
        except (RuntimeError, ValueError) as exc:
            await update.message.reply_text(f"⚠️ {exc}")
            return
        PENDING.pop(uid, None)
        stock = inventory_service.sync_offer_stock(ref)
        queued = None
        if added:
            queued = queue_broadcast("stock", offer_id=ref, added=added, stock=stock)
        await update.message.reply_text(
            f"✅ {added} compte(s) ajouté(s) et chiffré(s).\n"
            f"📦 Stock affiché synchronisé dans le bot : {stock}\n"
            f"📣 Alerte mise en file pour {(queued or {}).get('recipient_count', 0)} utilisateur(s).",
            reply_markup=admin.offer_admin_keyboard(ref),
        )
        return

    if kind == "adm_manual_stock" and uid == ADMIN_ID:
        try:
            stock = int(text.strip())
            if stock < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Envoyez un nombre entier valide supérieur ou égal à 0."
            )
            return
        db.update_offer(
            ref,
            stock=stock,
            manual_stock=True,
            unlimited_stock=False,
        )
        PENDING.pop(uid, None)
        queued = None
        if stock > 0:
            queued = queue_broadcast("stock", offer_id=ref, added=stock, stock=stock)
        await update.message.reply_text(
            f"✅ Stock manuel activé : {stock}\n"
            "📦 Ce nombre est maintenant visible publiquement.\n"
            f"📣 Alerte mise en file pour {(queued or {}).get('recipient_count', 0)} utilisateur(s).\n"
            "🤖 Après paiement, le bot vous demandera de répondre directement au client.",
            reply_markup=admin.offer_admin_keyboard(ref),
        )
        return

    if kind == "support":
        ticket = support_service.create_ticket(uid, text, category=str(ref or "other"))
        PENDING[uid] = ("ticket_message", ticket["id"])
        await send_ticket_conversation(update.message, lang, ticket)
        await support_bridge.send_client_text(
            context, ticket, update.effective_user, text,
        )
        await delete_customer_support_message(update.message)
        return

    if kind == "support_guided":
        category, order_id_text = str(ref).split("|", 1)
        order_id = int(order_id_text) or None
        if order_id:
            order = db.get_order(order_id)
            if not order or order.get("user_id") != uid:
                await update.message.reply_text(t(lang, "not_for_you"))
                return
        ticket = support_service.create_ticket(
            uid, text, category=category, order_id=order_id,
        )
        PENDING[uid] = ("ticket_message", ticket["id"])
        await send_ticket_conversation(update.message, lang, ticket)
        await support_bridge.send_client_text(
            context, ticket, update.effective_user, text,
        )
        await delete_customer_support_message(update.message)
        return

    if kind == "support_order":
        ticket = support_service.create_ticket(
            uid,
            text,
            category="delivery",
            order_id=int(ref),
            priority="high",
        )
        PENDING[uid] = ("ticket_message", ticket["id"])
        await send_ticket_conversation(update.message, lang, ticket)
        await support_bridge.send_client_text(
            context, ticket, update.effective_user, text,
        )
        await delete_customer_support_message(update.message)
        return

    if kind == "ticket_message":
        ticket = support_service.get_ticket(int(ref))
        if not ticket or ticket.get("user_id") != uid or ticket.get("status") == "closed":
            PENDING.pop(uid, None)
            await update.message.reply_text(t(lang, "ticket_unavailable"))
            return
        support_service.add_message(int(ref), uid, text, sender_type="client")
        await update.message.reply_text(
            f"Message sent to {support_bridge.ticket_reference(ref)}.",
            reply_markup=kb.ticket_conversation_keyboard(lang, ref),
        )
        await support_bridge.send_client_text(
            context,
            ticket,
            update.effective_user,
            text,
            event="Customer reply",
        )
        await delete_customer_support_message(update.message)
        return

    if kind == "manual_order_reply":
        order_id = int(ref)
        order = db.get_order(order_id)
        if (
            not order
            or int(order.get("user_id") or 0) != uid
            or order.get("status") not in {"paid", "payment_confirmed"}
        ):
            PENDING.pop(uid, None)
            await update.message.reply_text(
                t(lang, "manual_order_conversation_closed")
            )
            return
        await context.bot.send_message(
            ADMIN_ID,
            "💬 <b>Customer reply — manual order</b>\n\n"
            f"Order: <b>#{order_id}</b>\n"
            f"Customer: <code>{uid}</code>\n"
            f"Product: <b>{html.escape(str(order.get('service_name') or ''))} — "
            f"{html.escape(str(order.get('offer_name') or ''))}</b>\n\n"
            f"Message:\n{html.escape(text)}",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.manual_delivery_request_keyboard(order_id),
        )
        PENDING.pop(uid, None)
        await update.message.reply_text(
            t(lang, "manual_order_reply_sent", oid=order_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # --- Admin : livraison ---
    if kind == "adm_client_message" and uid == ADMIN_ID:
        await send_admin_message_to_client(update, context, ref, text)
        PENDING.pop(uid, None)
        return

    if kind == "adm_deliver" and uid == ADMIN_ID:
        if await deliver_order(update, context, ref, text):
            PENDING.pop(uid, None)
        return

    if kind == "adm_codex_number" and uid == ADMIN_ID:
        order_id = int(ref)
        order = db.get_order(order_id)
        number = " ".join(text.split())[:240]
        if (
            not is_otp_order(order)
            or order.get("status") not in {"paid", "payment_confirmed"}
            or str(order.get("otp_workflow_status") or "") != "awaiting_admin_number"
        ):
            PENDING.pop(uid, None)
            await update.message.reply_text("⚠️ This Codex number order is no longer awaiting a number.")
            return
        if not number:
            await update.message.reply_text("📱 Send the Codex number as text.")
            return
        customer_id = int(order["user_id"])
        customer_lang = lang_of(customer_id)
        try:
            await context.bot.send_message(
                customer_id,
                t(
                    customer_lang,
                    "codex_number_received",
                    oid=order_id,
                    number=escape_markdown(number),
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.codex_number_agree_keyboard(customer_lang, order_id),
            )
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Could not send the number to the customer: {exc}")
            return
        now = int(time.time())
        changed = db.get_conn().orders.update_one(
            {
                "id": order_id,
                "status": {"$in": ["paid", "payment_confirmed"]},
                "otp_workflow_status": "awaiting_admin_number",
            },
            {"$set": {
                "codex_number": number,
                "otp_workflow_status": "number_sent",
                "codex_number_sent_at": now,
                "codex_agree_deadline": now + db.CODEX_ACCEPTANCE_SECONDS,
                "updated_at": now,
            }},
        )
        PENDING.pop(uid, None)
        if changed.modified_count:
            await update.message.reply_text(
                f"✅ Number sent for order #{order_id}. Waiting for the customer to tap I agree."
            )
        else:
            await update.message.reply_text(
                f"⚠️ The number was sent, but order #{order_id} changed before it could be saved."
            )
        return

    if kind == "adm_codex_otp" and uid == ADMIN_ID:
        order_id = int(ref)
        order = db.get_order(order_id)
        code = " ".join(text.split())[:240]
        if (
            not is_otp_order(order)
            or order.get("status") not in {"paid", "payment_confirmed"}
            or str(order.get("otp_workflow_status") or "") != "customer_agreed"
        ):
            PENDING.pop(uid, None)
            await update.message.reply_text("⚠️ This order is not ready for its OTP code.")
            return
        if not code:
            await update.message.reply_text("🔐 Send the OTP code as text.")
            return
        customer_id = int(order["user_id"])
        customer_lang = lang_of(customer_id)
        try:
            await context.bot.send_message(
                customer_id,
                t(
                    customer_lang,
                    "codex_otp_received",
                    oid=order_id,
                    code=escape_markdown(code),
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.post_delivery_keyboard(customer_lang, order_id),
            )
            delivered = order_service.manual_deliver_order(
                order_id,
                f"Codex number: {order.get('codex_number') or ''}\nOTP: {code}",
            )
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Could not send the OTP code: {exc}")
            return
        PENDING.pop(uid, None)
        if not delivered:
            await update.message.reply_text(
                f"⚠️ The OTP was sent, but order #{order_id} was no longer awaiting delivery."
            )
            return
        now = int(time.time())
        db.get_conn().orders.update_one(
            {"id": order_id, "status": "delivered"},
            {"$set": {
                "otp_workflow_status": "completed",
                "codex_otp_sent_at": now,
                "updated_at": now,
            }},
        )
        await update.message.reply_text(f"✅ OTP sent. Order #{order_id} is complete.")
        return


def is_otp_order(order):
    return bool(order and db.is_otp_service_name(order.get("service_name")))


async def notify_codex_acceptance_expired(bot, order):
    """Notify both parties after the five-minute Codex acceptance window."""
    order_id = int(order["id"])
    customer_id = int(order["user_id"])
    customer_lang = lang_of(customer_id)
    with contextlib.suppress(Exception):
        await bot.send_message(
            customer_id,
            t(customer_lang, "codex_acceptance_expired", oid=order_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.home_keyboard(customer_lang, customer_id),
        )
    with contextlib.suppress(Exception):
        await bot.send_message(
            ADMIN_ID,
            "⌛ <b>Codex number order expired</b>\n\n"
            f"Order: <b>#{order_id}</b>\n"
            f"Client ID: <code>{customer_id}</code>\n"
            "Reason: the customer did not tap I agree within 5 minutes.",
            parse_mode=ParseMode.HTML,
        )


async def monitor_codex_number_deadlines(bot, now=None):
    """Expire and announce all overdue Codex-number acceptance windows."""
    expired_orders = []
    for order_id in db.due_codex_number_acceptances(now):
        expired = db.expire_codex_number_acceptance(order_id, now)
        if not expired:
            continue
        expired_orders.append(expired)
        await notify_codex_acceptance_expired(bot, expired)
    return expired_orders


async def begin_otp_order_questions(message, context, lang, order_id, uid):
    """Start or recover the staged Codex number delivery workflow."""
    order = db.get_order(order_id)
    if not is_otp_order(order):
        return False
    workflow = str(order.get("otp_workflow_status") or "")
    if workflow in {"number_sent", "customer_agreed", "completed"}:
        return True
    PENDING.pop(uid, None)
    now = int(time.time())
    db.get_conn().orders.update_one(
        {"id": order_id},
        {"$set": {
            "otp_workflow_status": "awaiting_admin_number",
            "updated_at": now,
        }},
    )
    if not order.get("codex_admin_notified_at"):
        try:
            await context.bot.send_message(
                ADMIN_ID,
                "<b>New paid Codex number order</b>\n\n"
                f"Order: <b>#{order_id}</b>\n"
                f"Client ID: <code>{uid}</code>\n"
                f"Quantity: <b>{int(order.get('qty') or 1)}</b>\n"
                f"Total paid: <b>{float(order.get('wallet_amount') or order.get('total_price') or 0):.2f} {CURRENCY}</b>\n"
                f"Payment: <b>{html.escape(str(order.get('verify_method') or order.get('payment_method') or 'confirmed'))}</b>\n\n"
                "Send the number to the customer.",
                parse_mode=ParseMode.HTML,
                reply_markup=admin.codex_number_request_keyboard(order_id),
            )
            db.get_conn().orders.update_one(
                {"id": order_id},
                {"$set": {"codex_admin_notified_at": now}},
            )
        except Exception as exc:
            log.warning("Codex order #%s admin notification failed: %s", order_id, exc)
    await message.reply_text(
        t(lang, "codex_payment_confirmed_waiting_number", oid=order_id),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.home_keyboard(lang, uid),
    )
    return True

# ---------------- Traitement de paiement ----------------
class _DirectChatMessage:
    """Minimal Message adapter that sends replies directly to one customer."""

    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = int(chat_id)

    async def reply_text(self, text, **kwargs):
        return await self.bot.send_message(self.chat_id, text, **kwargs)


def supplier_delivery_problem_text(order_id, result):
    """Build a complete, credential-safe supplier delivery incident report."""
    order = db.get_order(int(order_id)) or {}
    offer = db.get_offer(order.get("offer_id")) if order.get("offer_id") else {}
    provider = str((offer or {}).get("supplier_provider") or "").strip().lower()
    provider_name = reseller_service.provider_display_name(provider)
    provider_bot = reseller_service.provider_bot_username(provider)
    buyer = db.get_conn().users.find_one(
        {"telegram_id": int(order.get("user_id") or 0)},
        {"_id": 0, "username": 1, "first_name": 1, "full_name": 1, "lang": 1},
    ) or {}
    fulfillment = db.get_conn().reseller_fulfillments.find_one(
        {"provider": provider, "external_order_id": f"BM-{int(order_id)}"},
        {"_id": 0, "encrypted_items": 0},
    ) or {}

    def safe(value, fallback="—"):
        normalized = str(value if value not in (None, "") else fallback).strip()
        return html.escape(normalized or fallback)

    username = str(buyer.get("username") or "").strip().lstrip("@")
    buyer_username = f"@{safe(username)}" if username else "Non renseigné"
    buyer_name = buyer.get("full_name") or buyer.get("first_name") or "Non renseigné"
    supplier_bot = (
        f'<a href="https://t.me/{safe(provider_bot)}">@{safe(provider_bot)}</a>'
        if provider_bot
        else "Non renseigné par le fournisseur"
    )
    supplier_order_id = fulfillment.get("supplier_order_id") or "Non retourné"
    payment_reference = order.get("txid") or "Wallet / aucune référence TXID"
    error_code = result.get("error_code") or "supplier_delivery_error"
    error_message = result.get("error_message") or "Contenu de livraison non retourné"
    incident_warning = (
        "La commande fournisseur peut déjà avoir été débitée. Vérifiez son statut "
        "avant toute nouvelle tentative afin d’éviter une double livraison."
        if error_code == "supplier_delivery_pending"
        else "Le fournisseur indique que la commande n’a pas été créée. Vérifiez tout "
        "de même son bot avant une livraison ou une nouvelle tentative."
    )
    return (
        "🚨 <b>ÉCHEC DE LIVRAISON API</b>\n\n"
        "🏪 <b>Fournisseur</b>\n"
        f"• Nom : <b>{safe(provider_name)}</b>\n"
        f"• Bot Telegram : {supplier_bot}\n"
        f"• Code fournisseur : <code>{safe(provider)}</code>\n"
        f"• Statut API : <code>{safe(fulfillment.get('status'))}</code>\n\n"
        "📦 <b>Commande</b>\n"
        f"• ID local : <b>#{int(order_id)}</b>\n"
        f"• Référence envoyée : <code>BM-{int(order_id)}</code>\n"
        f"• ID fournisseur : <code>{safe(supplier_order_id)}</code>\n"
        f"• ID produit fournisseur : <code>{safe((offer or {}).get('supplier_product_id'))}</code>\n"
        f"• Produit : <b>{safe(order.get('service_name'))} — {safe(order.get('offer_name'))}</b>\n"
        f"• Quantité : <b>{safe(order.get('qty'), '1')}</b>\n"
        f"• Prix unitaire : <b>{safe(order.get('unit_price'), '0')} {html.escape(CURRENCY)}</b>\n"
        f"• Total : <b>{safe(order.get('total_price'), '0')} {html.escape(CURRENCY)}</b>\n"
        f"• Statut local : <code>{safe(order.get('status'))}</code>\n\n"
        "👤 <b>Acheteur</b>\n"
        f"• Telegram ID : <code>{safe(order.get('user_id'))}</code>\n"
        f"• Nom : <b>{safe(buyer_name)}</b>\n"
        f"• Username : <b>{buyer_username}</b>\n"
        f"• Langue : <code>{safe(buyer.get('lang'))}</code>\n\n"
        "💳 <b>Paiement</b>\n"
        f"• Méthode : <code>{safe(order.get('verify_method') or order.get('payment_method'))}</code>\n"
        f"• TXID / référence : <code>{safe(payment_reference)}</code>\n\n"
        "❌ <b>Erreur</b>\n"
        f"• Code : <code>{safe(error_code)}</code>\n"
        f"• Détail : {safe(error_message)}\n\n"
        f"⚠️ {html.escape(incident_warning)}\n\n"
        "Utilisez les boutons ci-dessous pour informer l’acheteur ou effectuer "
        "une livraison manuelle."
    )


_DELIVERY_WATCHERS = set()


def manual_delivery_waiting_text(lang, order_id):
    messages = {
        "fr": f"⏳ <b>Commande #{order_id} confirmée</b>\n\nVeuillez patienter : le bot vous prépare un nouveau compte. Votre produit sera disponible très bientôt.",
        "en": f"⏳ <b>Order #{order_id} confirmed</b>\n\nPlease wait — the bot is releasing a fresh account for you. Your product will be available very soon.",
        "ar": f"⏳ <b>تم تأكيد الطلب #{order_id}</b>\n\nيرجى الانتظار — يقوم البوت بتجهيز حساب جديد لك. سيكون منتجك متاحاً قريباً جداً.",
    }
    return messages.get(lang, messages["en"])


async def watch_manual_delivery(bot, chat_id, order_id, message_id, lang, timeout=3600):
    """Keep the customer informed while an API-failed order is delivered manually."""
    key = (int(chat_id), int(order_id))
    _DELIVERY_WATCHERS.add(key)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            order = db.get_order(order_id) or {}
            if order.get("status") == "delivered":
                with contextlib.suppress(Exception):
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text="✅ <b>Your product has been released.</b> Check the message above for your account.",
                        parse_mode=ParseMode.HTML,
                    )
                return
            if order.get("status") not in {"paid", "payment_confirmed"}:
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Manual delivery watcher failed for order #%s", order_id)
    finally:
        _DELIVERY_WATCHERS.discard(key)


async def send_method_media(bot, customer_id, media):
    for item in media or []:
        kind = str(item.get("type") or "document")
        file_id = item.get("file_id")
        if kind == "text":
            content = str(item.get("text") or item.get("caption") or "").strip()
            if content:
                await bot.send_message(customer_id, text=content)
            continue
        if not file_id:
            continue
        caption = str(item.get("caption") or "")[:900] or None
        if kind == "photo":
            await bot.send_photo(customer_id, photo=file_id, caption=caption)
        elif kind == "video":
            await bot.send_video(customer_id, video=file_id, caption=caption)
        else:
            await bot.send_document(customer_id, document=file_id, caption=caption)


async def send_payment_result(message, context, lang, order_id, result, uid):
    if result["status"] in ("delivered", "confirmed", "confirmed_no_delivery"):
        affiliate = result.get("affiliate")
        if affiliate:
            referrer_id = affiliate["referrer_id"]
            ref_lang = lang_of(referrer_id)
            if affiliate["rewarded"]:
                await context.bot.send_message(
                    referrer_id,
                    premium_customer_text(
                        ref_lang,
                        "affiliate_rewarded",
                        count=affiliate["daily_count"],
                        reward=f"{affiliate['reward_amount']:.2f}",
                    ),
                    parse_mode=ParseMode.HTML,
                )
            else:
                await context.bot.send_message(
                    referrer_id,
                    premium_customer_text(
                        ref_lang,
                        "affiliate_payment_progress",
                        count=affiliate["valid_referrals"],
                        target=affiliate_service.REFERRAL_TARGET,
                    ),
                    parse_mode=ParseMode.HTML,
                )
        loyalty = result.get("loyalty")
        if loyalty and loyalty.get("activated"):
            await message.reply_text(
                premium_customer_text(
                    lang,
                    "loyalty_activated",
                    level=loyalty["level"].title(),
                    discount=loyalty["discount_percent"],
                ),
                parse_mode=ParseMode.HTML,
            )
        paid_order = db.get_order(order_id)
        if is_otp_order(paid_order) and await begin_otp_order_questions(
            message, context, lang, order_id, uid,
        ):
            return
        if result["delivered_content"]:
            paid_order = db.get_order(order_id)
            offer = db.get_offer(paid_order.get("offer_id")) if paid_order else None
            if offer and result["delivered_content"] == ["__method_media__"]:
                await message.reply_text(
                    f"✅ <b>Payment confirmed</b>\n\nYour method <b>{html.escape(str(paid_order.get('offer_name') or ''))}</b> is ready. The content is attached below.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.post_delivery_keyboard(lang, order_id),
                )
                await send_method_media(context.bot, uid, offer.get("method_media") or [])
            else:
                content = numbered_delivery_content(result["delivered_content"])
                await message.reply_text(
                    premium_customer_text(lang, "delivery_received", oid=order_id,
                      service=paid_order["service_name"], offer=paid_order["offer_name"],
                      content=content),
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.post_delivery_keyboard(lang, order_id),
                )
        else:
            if str(result.get("error_code") or "").startswith("supplier_"):
                waiting_message = await message.reply_text(
                    manual_delivery_waiting_text(lang, order_id),
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.post_delivery_keyboard(lang, order_id),
                )
                watcher_key = (int(uid), int(order_id))
                if watcher_key not in _DELIVERY_WATCHERS and getattr(waiting_message, "message_id", None):
                    asyncio.create_task(
                        watch_manual_delivery(
                            context.bot, uid, order_id,
                            waiting_message.message_id, lang,
                        )
                    )
            else:
                await message.reply_text(
                    premium_customer_text(lang, "verify_ok", oid=order_id),
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.post_delivery_keyboard(lang, order_id),
                )
        with contextlib.suppress(Exception):
            if result["status"] == "confirmed_no_delivery":
                # Manual fulfillment is safe for native/manual products and
                # when the supplier explicitly rejected the purchase before
                # creating an order (for example, insufficient API balance).
                # If an API order may already exist, never risk a duplicate
                # account or a second supplier charge.
                if not str(result.get("error_code") or "").startswith("supplier_"):
                    await admin.notify_manual_delivery_request(context, paid_order)
                else:
                    await context.bot.send_message(
                        ADMIN_ID,
                        supplier_delivery_problem_text(order_id, result),
                        parse_mode=ParseMode.HTML,
                        reply_markup=admin.manual_delivery_request_keyboard(order_id),
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            else:
                await admin.notify_new_order(context, paid_order)
    elif result["status"] == "already_paid":
        await message.reply_text(premium_customer_text(lang, "already_paid", oid=order_id),
                                 parse_mode=ParseMode.HTML)
    else:
        error_code = result.get("error_code", "unknown")
        if error_code == "too_short":
            await message.reply_text(
                premium_customer_text(lang, "txid_too_short"),
                parse_mode=ParseMode.HTML,
            )
            PENDING[uid] = ("await_txid", order_id)
            return
        error_key = {
            "wrong_amount": "payment_wrong_amount",
            "wrong_currency": "payment_wrong_currency",
            "not_found": "payment_not_found",
            "already_used": "payment_txid_used",
        }.get(error_code, "verify_failed")
        await message.reply_text(premium_customer_text(lang, error_key, oid=order_id),
                                 parse_mode=ParseMode.HTML)
        PENDING[uid] = ("await_txid", order_id)


def premium_customer_text(lang: str, key: str, **kwargs) -> str:
    """Render selected customer texts as HTML with their Premium emoji."""
    protected_values = {}
    if key == "delivery_received" and "content" in kwargs:
        # Delivery data is opaque customer content, not bot markup. Protect it
        # while rendering the customizable template, then insert escaped text.
        token = "DELIVERYCONTENTPLACEHOLDER9F4A"
        protected_values[token] = html.escape(str(kwargs["content"]))
        kwargs = dict(kwargs)
        kwargs["content"] = token
    raw_override = db.get_text_override(key, lang)
    if raw_override is not None and str(raw_override).strip():
        raw_value = str(raw_override)
        if kwargs:
            format_kwargs = kwargs
            is_stored_html = raw_value.startswith(("[[HTML]]", "[HTML]"))
            if is_stored_html:
                format_kwargs = {name: html.escape(str(value)) for name, value in kwargs.items()}
                if key == "order_created":
                    for name in ("total", "binance_id"):
                        if name in format_kwargs:
                            format_kwargs[name] = f"<code>{format_kwargs[name]}</code>"
            with contextlib.suppress(KeyError, IndexError, ValueError):
                raw_value = raw_value.format(**format_kwargs)
    else:
        raw_value = t(lang, key, **kwargs)
    if key == "order_created" and not raw_value.startswith(("[[HTML]]", "[HTML]")):
        # Keep the payment values individually copyable in Telegram,
        # even when the admin's customized template uses plain placeholders.
        copyable_values = {
            name: str(kwargs[name])
            for name in ("total", "binance_id")
            if name in kwargs
        }
        if copyable_values:
            raw_template = str(raw_override) if raw_override is not None else ""
            for name, plain_value in copyable_values.items():
                if f"`{{{name}}}`" not in raw_template:
                    raw_value = raw_value.replace(plain_value, f"`{plain_value}`", 1)
    value = render_stored_rich_text(raw_value)
    for token, protected_value in protected_values.items():
        value = value.replace(token, protected_value)
    inline_emojis = "<tg-emoji " in value
    emoji_id = db.get_text_override_icon(key, lang)
    if emoji_id and not inline_emojis:
        value = f'<tg-emoji emoji-id="{html.escape(emoji_id)}">⭐</tg-emoji> {value}'
    return value


async def process_txid(update, context, lang, order_id, txid):
    uid = update.effective_user.id
    await update.message.reply_text(
        premium_customer_text(lang, "verifying"),
        parse_mode=ParseMode.HTML,
    )
    result = await asyncio.to_thread(
        payment_service.submit_payment, order_id, txid, uid
    )
    await send_payment_result(update.message, context, lang, order_id, result, uid)

# ---------------- Mes commandes ----------------
async def show_my_orders(update, context, lang):
    uid = update.effective_user.id
    orders = db.list_user_orders(uid, limit=500)
    if not orders:
        await update.effective_message.reply_text(t(lang, "no_orders"), reply_markup=kb.orders_keyboard(lang))
        return
    groups = order_service_groups(orders)
    await update.effective_message.reply_text(
        t(lang, "orders_choose_service"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.orders_services_keyboard(lang, groups, len(orders)),
    )


async def handle_ticket_attachment(update, context):
    """Create or continue a support ticket with a customer attachment."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return False
    pending = PENDING.get(user.id)
    if not pending or pending[0] not in {
        "support", "support_guided", "support_order", "ticket_message",
    }:
        return False

    label = support_bridge.media_label(message)
    caption = str(getattr(message, "caption", None) or "").strip()
    content = f"[{label}]" + (f" {caption}" if caption else "")
    kind, ref = pending
    is_new = kind != "ticket_message"

    if kind == "support":
        ticket = support_service.create_ticket(
            user.id, content, category=str(ref or "other"),
        )
    elif kind == "support_guided":
        category, order_id_text = str(ref).split("|", 1)
        order_id = int(order_id_text) or None
        if order_id:
            order = db.get_order(order_id)
            if not order or order.get("user_id") != user.id:
                await message.reply_text(t(lang_of(user.id), "not_for_you"))
                return True
        ticket = support_service.create_ticket(
            user.id, content, category=category, order_id=order_id,
        )
    elif kind == "support_order":
        ticket = support_service.create_ticket(
            user.id,
            content,
            category="delivery",
            order_id=int(ref),
            priority="high",
        )
    else:
        ticket = support_service.get_ticket(int(ref))
        if (
            not ticket
            or ticket.get("user_id") != user.id
            or ticket.get("status") == "closed"
        ):
            PENDING.pop(user.id, None)
            await message.reply_text(t(lang_of(user.id), "ticket_unavailable"))
            return True
        support_service.add_message(
            int(ref), user.id, content, sender_type="client",
        )

    ticket_id = int(ticket["id"])
    PENDING[user.id] = ("ticket_message", ticket_id)
    lang = lang_of(user.id)
    if is_new:
        await send_ticket_conversation(message, lang, ticket)
    else:
        await message.reply_text(
            f"Attachment sent to {support_bridge.ticket_reference(ticket_id)}.",
            reply_markup=kb.ticket_conversation_keyboard(lang, ticket_id),
        )
    await support_bridge.send_client_media(
        context,
        ticket,
        user,
        message,
        event="New support ticket" if is_new else "Customer attachment",
    )
    await delete_customer_support_message(message)
    return True


async def handle_pending_attachment(update, context):
    if await handle_ticket_attachment(update, context):
        return
    uid = update.effective_user.id
    pending = PENDING.get(uid)
    message = update.effective_message
    if uid == ADMIN_ID and pending and pending[0] == "adm_bot_package_doc":
        document = getattr(message, "document", None)
        if not document:
            await message.reply_text("⚠️ Envoyez le document comme fichier Telegram.")
            return
        file_name = str(getattr(document, "file_name", "") or "BOT-LIKE-MINE-benefits")[:240]
        db.update_offer(
            int(pending[1]),
            benefits_document_file_id=document.file_id,
            benefits_document_name=file_name,
        )
        PENDING.pop(uid, None)
        await message.reply_text(
            f"✅ Document client enregistré : <code>{html.escape(file_name)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.offer_admin_keyboard(int(pending[1])),
        )
        return
    if uid == ADMIN_ID and pending and pending[0] == "adm_method_media":
        media_type = None
        media_obj = getattr(message, "video", None)
        if media_obj:
            media_type = "video"
        else:
            media_obj = getattr(message, "document", None)
            if media_obj:
                media_type = "document"
        if not media_obj:
            await message.reply_text("⚠️ Send a video or document, or send `done` when finished.", parse_mode=ParseMode.MARKDOWN)
            return
        offer = db.get_offer(int(pending[1]))
        media = list((offer or {}).get("method_media") or [])
        media.append({
            "type": media_type,
            "file_id": media_obj.file_id,
            "caption": str(getattr(message, "caption", "") or "")[:900],
        })
        db.update_offer(int(pending[1]), method_media=media, unlimited_stock=True)
        await message.reply_text(f"✅ Content item {len(media)} saved. Send more or `done`.", parse_mode=ParseMode.MARKDOWN)
        return
    if uid == ADMIN_ID and pending and pending[0] == "adm_lovable_zip":
        document = getattr(message, "document", None)
        file_name = str(getattr(document, "file_name", "") or "")
        if not document or not file_name.lower().endswith(".zip"):
            await message.reply_text(
                "⚠️ Fichier refusé. Envoyez l’extension comme document avec l’extension .zip."
            )
            return
        lovable_service.set_extension_file(document.file_id, file_name)
        PENDING.pop(uid, None)
        await message.reply_text(
            f"✅ Extension enregistrée : <code>{html.escape(file_name)}</code>\n\n"
            "Le bouton Download est maintenant actif pour les clients.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.admin_panel_keyboard(),
        )
        return
    if uid == ADMIN_ID and pending and pending[0] == "adm_deliver":
        if lovable_service.is_lovable_order(db.get_order(int(pending[1]))):
            await message.reply_text(
                "⚠️ Pour Lovable, envoyez la licence uniquement comme message texte."
            )
            return
        document = getattr(message, "document", None)
        if document and str(getattr(document, "mime_type", "")).startswith("image/"):
            caption = str(getattr(message, "caption", None) or "").strip()
            if await deliver_order(
                update,
                context,
                int(pending[1]),
                caption or "🖼️ Image de livraison",
                document_file_id=document.file_id,
            ):
                PENDING.pop(uid, None)
            return
        await message.reply_text(
            "⚠️ Pour livrer un média, envoyez une photo ou un fichier image."
        )
        return
    if uid != ADMIN_ID or not pending or pending[0] not in {
        "adm_svcemoji", "adm_svcsuffix", "adm_offemoji",
    }:
        return
    kind, object_id = pending
    if kind == "adm_svcsuffix":
        sticker = getattr(message, "sticker", None)
        fallback_emoji = str(
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or getattr(sticker, "emoji", None)
            or ""
        ).strip()
        if not fallback_emoji:
            await message.reply_text(
                "⚠️ Cet emoji Premium n’a pas d’équivalent Unicode utilisable à droite. "
                "Envoyez l’emoji depuis le clavier, par exemple : ✅"
            )
            return
        suffix_emoji = fallback_emoji[:12]
        db.update_service(int(object_id), suffix_emoji=suffix_emoji)
        PENDING.pop(uid, None)
        await message.reply_text(
            f"✅ Emoji droit mis à jour : {suffix_emoji}",
            reply_markup=admin.service_admin_keyboard(int(object_id)),
        )
        return
    custom_emoji_id = custom_emoji_from_message(update.effective_message)
    if not custom_emoji_id:
        await update.effective_message.reply_text(
            "⚠️ Envoyez un emoji Telegram Premium, pas un sticker ordinaire."
        )
        return
    if kind == "adm_svcemoji":
        db.update_service(int(object_id), emoji="", custom_emoji_id=custom_emoji_id)
        markup = admin.service_admin_keyboard(int(object_id))
        confirmation = "✅ Emoji du service mis à jour."
    else:
        db.update_offer(int(object_id), emoji="", custom_emoji_id=custom_emoji_id)
        markup = admin.offer_admin_keyboard(int(object_id))
        confirmation = "✅ Emoji de l'offre mis à jour."
    PENDING.pop(uid, None)
    await update.effective_message.reply_text(confirmation, reply_markup=markup)


async def handle_pending_photo(update, context):
    """Handle pending admin advertising and order-delivery photos."""
    if await handle_ticket_attachment(update, context):
        return
    uid = update.effective_user.id
    pending = PENDING.get(uid)
    if uid == ADMIN_ID and pending and pending[0] == "adm_method_media":
        offer = db.get_offer(int(pending[1]))
        media = list((offer or {}).get("method_media") or [])
        media.append({
            "type": "photo",
            "file_id": update.message.photo[-1].file_id,
            "caption": str(update.message.caption or "")[:900],
        })
        db.update_offer(int(pending[1]), method_media=media, unlimited_stock=True)
        await update.message.reply_text(f"✅ Content item {len(media)} saved. Send more or `done`.", parse_mode=ParseMode.MARKDOWN)
        return
    if uid == ADMIN_ID and pending and pending[0] == "adm_deliver":
        if lovable_service.is_lovable_order(db.get_order(int(pending[1]))):
            await update.message.reply_text(
                "⚠️ Pour Lovable, envoyez la licence uniquement comme message texte."
            )
            return
        caption = str(update.message.caption or "").strip()
        if await deliver_order(
            update,
            context,
            int(pending[1]),
            caption or "🖼️ Image de livraison",
            photo_file_id=update.message.photo[-1].file_id,
        ):
            PENDING.pop(uid, None)
        return
    if uid != ADMIN_ID or not pending or pending[0] not in {"adm_addoff_image", "adm_offimage"}:
        return
    if pending[0] == "adm_offimage":
        offer_id = int(pending[1])
        db.update_offer(offer_id, photo_file_id=update.message.photo[-1].file_id)
        PENDING.pop(uid, None)
        await update.message.reply_text(
            "✅ Image publicitaire mise à jour. Elle sera affichée lorsque le client ouvrira l’offre.",
            reply_markup=admin.offer_admin_keyboard(offer_id),
        )
        return
    service_id = pending[1]
    photo_file_id = update.message.photo[-1].file_id
    service = db.get_service(int(service_id)) or {}
    is_method = str(service.get("name") or "").strip().lower() == "methods"
    PENDING[uid] = ("adm_addoff_name", {
        "service_id": service_id,
        "photo_file_id": photo_file_id,
    })
    await update.message.reply_text(
        f"✏️ *New {'method' if is_method else 'offer'} — step 2/{5 if is_method else 6}*\n\n"
        f"Send the {'method' if is_method else 'offer'} name:",
        parse_mode=ParseMode.MARKDOWN,
    )

def order_service_groups(orders):
    service_emojis = {service["name"]: service.get("emoji", "📦") for service in db.list_services()}
    grouped = {}
    for order in orders:
        name = str(order.get("service_name") or "Other")
        grouped.setdefault(name, {
            "name": name,
            "emoji": service_emojis.get(name, "📦"),
            "orders": [],
        })["orders"].append(order)
    groups = sorted(grouped.values(), key=lambda group: (-len(group["orders"]), group["name"].lower()))
    for group in groups:
        group["count"] = len(group["orders"])
    return groups


def orders_text_export(lang, orders, title):
    lines = [
        f"PURCHASE HISTORY — {title}",
        "=" * max(32, len(title) + 19),
        "",
    ]
    for order in orders:
        created_at = order.get("created_at")
        delivered_at = order.get("delivered_at")
        purchase_date = (
            datetime.fromtimestamp(created_at, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if created_at else "—"
        )
        delivery_date = (
            datetime.fromtimestamp(delivered_at, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if delivered_at else "—"
        )
        qty = max(1, int(order.get("qty") or 1))
        unit_price = float(order.get("unit_price") or 0)
        wallet_amount = float(order.get("wallet_amount") or 0)
        external_amount = float(order.get("total_price") or 0)
        paid_total = round(wallet_amount + external_amount, 2)
        gross_total = float(
            order.get("gross_total")
            if order.get("gross_total") is not None
            else unit_price * qty if unit_price else paid_total
        )
        offer = db.get_offer(order.get("offer_id")) if order.get("offer_id") else None
        warranty = (
            "FW" if warranty_service.has_full_warranty(order)
            else str(order.get("warranty") or "").strip()
        )
        if not warranty and offer:
            warranty = (
                "FW" if warranty_service.has_full_warranty(offer)
                else str(offer.get("note") or "").strip()
                or warranty_service.offer_warranty_label(offer, lang=lang)
            )
        warranty = warranty or "No warranty information recorded"
        delivered_content = order_service.delivery_content_for_order(order)
        payment_method = str(
            order.get("verify_method") or order.get("payment_method") or "—"
        )
        txid = str(order.get("txid") or "—")
        lines.extend([
            f"ORDER #{order['id']}",
            "-" * 32,
            f"Service: {order.get('service_name') or '—'}",
            f"Offer: {order.get('offer_name') or '—'}",
            f"Quantity: {qty}",
            f"Unit price: {unit_price:.2f} {order.get('currency', CURRENCY)}",
            f"Catalog total: {gross_total:.2f} {order.get('currency', CURRENCY)}",
            f"Total paid: {paid_total:.2f} {order.get('currency', CURRENCY)}",
            f"Status: {status_label(lang, order.get('status', ''))}",
            f"Purchase date: {purchase_date}",
            f"Delivery date: {delivery_date}",
            f"Payment method: {payment_method}",
            f"Transaction ID: {txid}",
            f"Warranty: {warranty}",
            "",
            "PURCHASE CONTENT",
            "-" * 32,
            delivered_content or "Content not delivered or no longer available.",
            "",
            "=" * 48,
            "",
        ])
    return "\n".join(lines)


async def send_orders_export(query, lang, orders, title):
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", title).strip("-").lower() or "orders"
    content = orders_text_export(lang, orders, title).encode("utf-8")
    await query.message.reply_document(
        document=InputFile(io.BytesIO(content), filename=f"{safe_name}.txt"),
        caption=t(lang, "orders_file_caption", service=title, count=len(orders)),
        reply_markup=kb.orders_keyboard(lang),
    )


# ================= ADMIN CALLBACKS =================
async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        await q.answer("⛔", show_alert=True)
        return
    data = q.data
    await q.answer()

    if data == "adm_panel":
        await show_callback_screen(
            q,
            "🛠️ *Panneau Admin*",
            reply_markup=admin.admin_panel_keyboard(),
        )
        return

    if data.startswith("adm_stock_products:"):
        page = int(data.split(":", 1)[1])
        text, markup = admin.available_products_screen(page)
        await show_callback_screen(
            q,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return

    if data == "adm_withdrawals":
        withdrawals = db.list_withdrawals(status="pending", limit=50)
        await show_callback_screen(
            q,
            "💸 <b>Pending withdrawals</b>\n\nSelect a request after sending the funds to the customer:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.withdrawals_keyboard(withdrawals),
        )
        return

    if data.startswith("adm_warranties:"):
        page = int(data.split(":", 1)[1])
        markup, requests, total = admin.warranty_requests_keyboard(page)
        active = sum(
            1 for request in requests
            if request.get("status") in {"pending_admin_check", "accepted", "replacement_pending"}
        )
        await show_callback_screen(
            q,
            "🛡 <b>Warranty updates</b>\n\n"
            f"Total requests: <b>{total}</b>\n"
            f"Actionable on this page: <b>{active}</b>\n\n"
            "Select a request to view its latest status and available actions.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return

    if data.startswith("adm_warranty_view:"):
        request_id = int(data.split(":", 1)[1])
        request = db.get_conn().warranty_requests.find_one({"id": request_id})
        await show_callback_screen(
            q,
            admin.warranty_request_text(request),
            parse_mode=ParseMode.HTML,
            reply_markup=admin.warranty_request_keyboard(request),
        )
        return

    if data.startswith("adm_warranty_report:"):
        request_id = int(data.split(":", 1)[1])
        request = db.get_conn().warranty_requests.find_one({"id": request_id})
        if not request:
            await q.message.reply_text("⚠️ Warranty request not found.")
            return
        report = admin.warranty_request_report(request)
        await q.message.reply_document(
            document=InputFile(
                io.BytesIO(report.encode("utf-8")),
                filename=f"warranty-{request_id}-order-{int(request.get('order_id') or 0)}.txt",
            ),
            caption="Full warranty report with supplier details and real delivered content.",
        )
        return

    if data.startswith("adm_warranty_send:"):
        request_id = int(data.split(":", 1)[1])
        request = db.get_conn().warranty_requests.find_one({
            "id": request_id,
            "status": "replacement_pending",
        })
        if not request:
            await q.message.reply_text("⚠️ This request is not awaiting replacement delivery.")
            return
        PENDING[uid] = ("adm_warranty_replacement", request_id)
        await q.message.reply_text(
            f"📨 Send the replacement account or message for warranty request #{request_id}.\n\n"
            "Your next text message will be delivered directly to the customer."
        )
        return

    if data.startswith("adm_payments:"):
        page = int(data.split(":", 1)[1])
        markup, orders, total = admin.confirmed_payments_keyboard(page)
        awaiting_delivery = sum(
            1 for order in orders
            if order.get("status") in {"paid", "payment_confirmed"}
        )
        await show_callback_screen(
            q,
            "✅ <b>Payment Confirmed</b>\n\n"
            f"Confirmed orders: <b>{total}</b>\n"
            f"Awaiting delivery on this page: <b>{awaiting_delivery}</b>\n\n"
            "Select an order to view payment and delivery details.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return

    if data.startswith("adm_api_pending_view:"):
        order_id = int(data.split(":", 1)[1])
        fulfillment = db.get_pending_api_delivery(order_id)
        await show_callback_screen(
            q,
            admin.pending_api_delivery_text(fulfillment),
            parse_mode=ParseMode.HTML,
            reply_markup=admin.pending_api_delivery_keyboard(order_id),
        )
        return

    if data.startswith("adm_api_pending_report:"):
        order_id = int(data.split(":", 1)[1])
        fulfillment = db.get_pending_api_delivery(order_id)
        if not fulfillment:
            await q.message.reply_text("⚠️ Pending API delivery not found.")
            return
        report = admin.pending_api_delivery_report(fulfillment)
        await q.message.reply_document(
            document=InputFile(
                io.BytesIO(report.encode("utf-8")),
                filename=f"api-delivery-order-{order_id}.txt",
            ),
            caption="Full API delivery table with order, payment, supplier and content details.",
        )
        return

    if data.startswith("adm_api_pending:"):
        page = int(data.split(":", 1)[1])
        markup, _fulfillments, total = admin.pending_api_deliveries_keyboard(page)
        await show_callback_screen(
            q,
            "⏳ <b>Livraison API en attente</b>\n\n"
            f"Orders requiring attention: <b>{total}</b>\n\n"
            "This list includes supplier purchases still processing, delivery pending, "
            "failed/review-required purchases, and paid API orders missing fulfillment.",
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return

    if data.startswith("adm_warranty_accept:"):
        request_id = int(data.split(":", 1)[1])
        changed = db.get_conn().warranty_requests.find_one_and_update(
            {"id": request_id, "status": "pending_admin_check"},
            {"$set": {"status": "accepted", "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        if not changed:
            await q.message.reply_text("⚠️ This warranty request has already been processed.")
            return
        await q.edit_message_reply_markup(reply_markup=admin.warranty_request_keyboard(changed))
        await q.message.reply_text("✅ Accepted. Choose replacement or refund:")
        return

    if data.startswith("adm_warranty_refuse:"):
        request_id = int(data.split(":", 1)[1])
        request = db.get_conn().warranty_requests.find_one({"id": request_id, "status": "pending_admin_check"})
        if not request:
            await q.message.reply_text("⚠️ This warranty request has already been processed.")
            return
        PENDING[uid] = ("adm_warranty_refuse_reason", request_id)
        await q.message.reply_text("Send the reason for refusing this warranty request:")
        return

    if data.startswith("adm_warranty_resolve:"):
        _, resolution, raw_id = data.split(":", 2)
        request_id = int(raw_id)
        request = db.resolve_warranty_request(request_id, resolution)
        if resolution == "replacement" and not request:
            request = db.get_conn().warranty_requests.find_one({
                "id": request_id,
                "status": "replacement_pending",
            })
        if not request:
            await q.message.reply_text("⚠️ This warranty request has already been processed.")
            return
        customer_id = int(request["user_id"])
        refund = float(request.get("refund_amount") or 0)
        if resolution == "refund":
            customer_text = f"💰 <b>Refund approved</b>\n\n<b>{refund:.2f} {CURRENCY}</b> was added to your wallet for warranty request <b>#{request_id}</b>."
        else:
            customer_text = f"🔁 <b>Replacement approved</b>\n\nYour replacement for warranty request <b>#{request_id}</b> will be prepared by the admin."
        with contextlib.suppress(Exception):
            await context.bot.send_message(customer_id, customer_text, parse_mode=ParseMode.HTML, reply_markup=kb.home_keyboard(lang_of(customer_id), customer_id))
        await q.edit_message_reply_markup(reply_markup=None)
        if resolution == "replacement":
            PENDING[uid] = ("adm_warranty_replacement", request_id)
            await q.message.reply_text(
                f"🔁 Replacement approved for request #{request_id}.\n\n"
                "Send the replacement account or message now. Your next text message "
                "will be delivered directly to the customer.\n\n"
                f"To resume later, use /replacement {request_id}."
            )
        else:
            await q.message.reply_text(f"✅ Warranty request #{request_id} resolved: refund.")
        return

    if data.startswith("adm_method_media:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if not offer:
            await q.message.reply_text("⚠️ Method offer not found.")
            return
        PENDING[uid] = ("adm_method_media", offer_id)
        await q.message.reply_text(
            "🎬 Send method content as photos, videos, or documents.\n"
            "Send `done` when all content has been uploaded.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data.startswith("adm_bot_package_doc:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if not offer or offer.get("feature_key") != "bot_like_mine":
            await q.message.reply_text("⚠️ Offre BOT LIKE MINE introuvable.")
            return
        PENDING[uid] = ("adm_bot_package_doc", offer_id)
        await q.message.reply_text(
            "📄 Envoyez le document affiché par le bouton « What you'll get? » comme fichier Telegram."
        )
        return

    if data.startswith("adm_bot_package_link:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if not offer or offer.get("feature_key") != "bot_like_mine":
            await q.message.reply_text("⚠️ Offre BOT LIKE MINE introuvable.")
            return
        PENDING[uid] = ("adm_bot_package_link", offer_id)
        await q.message.reply_text(
            "🔗 Envoyez le lien privé GitHub livré au client après confirmation du paiement."
        )
        return

    if data.startswith("adm_withdraw_done:"):
        withdrawal_id = int(data.split(":", 1)[1])
        withdrawal = db.update_withdrawal(withdrawal_id, "completed")
        if not withdrawal:
            await q.message.reply_text("⚠️ This withdrawal is already processed.")
            return
        customer_id = int(withdrawal["user_id"])
        amount = int(withdrawal.get("amount_cents") or 0) / 100
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                customer_id,
                f"✅ <b>Withdrawal completed</b>\n\nYour withdrawal request <b>#{withdrawal_id}</b> "
                f"for <b>{amount:.2f} {CURRENCY}</b> has been processed successfully.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang_of(customer_id), customer_id),
            )
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"✅ Withdrawal #{withdrawal_id} marked as completed.")
        return

    if data == "adm_lovable":
        db.ensure_lovable_unlimited_feature()
        extension = lovable_service.extension_file()
        status = (
            f"✅ ZIP configuré : <code>{html.escape(extension['file_name'])}</code>"
            if extension else "⚠️ Aucun fichier ZIP configuré"
        )
        await q.edit_message_text(
            "💗 <b>LOVABLE EXTENSION</b>\n\n"
            f"{status}\n\n"
            "Forfaits actifs : <b>1 jour ($1), 7 jours ($4), 30 jours ($8)</b>\n"
            "Essai gratuit : <b>1 heure par utilisateur</b>\n"
            "Livraison : <b>licence saisie et envoyée manuellement par l’admin</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📤 Importer/remplacer le ZIP",
                    callback_data="adm_lovable_upload",
                    style="primary",
                )],
                [InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel")],
            ]),
        )
        return

    if data == "adm_lovable_upload":
        PENDING[uid] = ("adm_lovable_zip", 0)
        await q.message.reply_text(
            "📤 <b>Envoyez maintenant le fichier ZIP de l’extension.</b>\n\n"
            "Le nouveau fichier remplacera automatiquement l’ancienne version.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("adm_lovable_trial:"):
        customer_id = int(data.split(":", 1)[1])
        request = db.get_conn().lovable_trial_requests.find_one({
            "user_id": customer_id,
        })
        if not request or request.get("status") != "pending":
            await q.message.reply_text("⚠️ Cette demande d’essai a déjà été traitée.")
            return
        PENDING[uid] = ("adm_lovable_trial", customer_id)
        await q.message.reply_text(
            f"🔑 Envoyez la licence manuelle pour le client {customer_id}.\n\n"
            "Elle sera activée pendant une heure à partir de son envoi."
        )
        return

    if data == "adm_broadcast_history":
        history = db.list_broadcast_history(limit=20)
        await q.edit_message_text(
            "🧹 <b>ANNONCES ENVOYÉES</b>\n\n"
            "Sélectionnez une campagne pour supprimer son message chez tous les clients. "
            "Telegram peut refuser les messages trop anciens.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.broadcast_history_keyboard(history),
        )
        return

    if data.startswith("adm_broadcast_view:"):
        job_id = int(data.split(":", 1)[1])
        job = db.get_broadcast_job(job_id)
        if not job:
            await q.edit_message_text(
                "⚠️ Annonce introuvable.",
                reply_markup=admin.broadcast_history_keyboard(db.list_broadcast_history()),
            )
            return
        all_messages = db.list_broadcast_messages(job_id, active_only=False)
        active_messages = db.list_broadcast_messages(job_id)
        job["tracked_count"] = len(all_messages)
        job["active_message_count"] = len(active_messages)
        payload = job.get("payload") or {}
        offer_id = payload.get("offer_id") or (payload.get("event") or {}).get("offer_id")
        offer = db.get_offer(int(offer_id)) if offer_id else None
        product = html.escape(str((offer or {}).get("name") or "Annonce générale"))
        deletion_status = html.escape(str(job.get("deletion_status") or "active"))
        await q.edit_message_text(
            f"{admin.broadcast_kind_label(job.get('kind'))}\n\n"
            f"Produit : <b>{product}</b>\n"
            f"Messages encore visibles : <b>{len(active_messages)}</b> / {len(all_messages)}\n"
            f"Suppression : <b>{deletion_status}</b>\n\n"
            "La suppression sera appliquée à tous les clients ayant reçu cette campagne.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.broadcast_delete_keyboard(job),
        )
        return

    if data.startswith("adm_broadcast_confirm:"):
        job_id = int(data.split(":", 1)[1])
        active = len(db.list_broadcast_messages(job_id))
        await q.edit_message_text(
            "⚠️ <b>CONFIRMER LA SUPPRESSION</b>\n\n"
            f"Cette action tentera de supprimer l’annonce chez <b>{active}</b> client(s).\n"
            "Les messages trop anciens peuvent être refusés par Telegram.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.broadcast_delete_confirmation_keyboard(job_id),
        )
        return

    if data.startswith("adm_broadcast_delete:"):
        job_id = int(data.split(":", 1)[1])
        job = db.get_broadcast_job(job_id)
        active = len(db.list_broadcast_messages(job_id))
        if not job or active == 0:
            await q.edit_message_text(
                "✅ Cette annonce n’est plus visible chez les clients.",
                reply_markup=admin.broadcast_history_keyboard(db.list_broadcast_history()),
            )
            return
        if job.get("deletion_status") not in {"queued", "deleting"}:
            db.set_broadcast_deletion_status(job_id, "queued")
            queue_broadcast("delete_broadcast", target_job_id=job_id)
        await q.edit_message_text(
            "🧹 <b>Suppression lancée</b>\n\n"
            f"Le bot supprime cette annonce chez {active} client(s) en arrière-plan. "
            "Actualisez l’historique dans quelques instants.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.broadcast_history_keyboard(db.list_broadcast_history()),
        )
        return

    if data.startswith("adm_onchain_approve:"):
        order_id = int(data.split(":", 1)[1])
        result = await asyncio.to_thread(
            payment_service.review_onchain_payment,
            order_id,
            uid,
            approved=True,
        )
        if result["status"] in {"not_found", "already_processed"}:
            await q.edit_message_text(
                "⚠️ Cette demande a déjà été traitée ou n’existe plus.",
            )
            return
        if result["status"] == "failed":
            await q.edit_message_text(
                "⚠️ Le paiement n’a pas pu être accepté. Vérifiez le stock et réessayez.",
                reply_markup=admin.onchain_payment_review_keyboard(order_id),
            )
            return
        order = result["order"]
        network = "BSC (BEP20)" if order["payment_method"] == "usdt_bsc" else "Polygon"
        await q.edit_message_text(
            "✅ <b>On-chain payment accepted</b>\n"
            f"Order: <b>#{order_id}</b>\n"
            f"Network: <b>{network}</b>\n"
            f"Amount: <b>{float(order.get('total_price') or 0):.2f} USDT</b>\n"
            f"TXID: <code>{html.escape(str(order.get('txid') or ''))}</code>",
            parse_mode=ParseMode.HTML,
        )
        customer_id = int(order["user_id"])
        await send_payment_result(
            _DirectChatMessage(context.bot, customer_id),
            context,
            lang_of(customer_id),
            order_id,
            result,
            customer_id,
        )
        return

    if data.startswith("adm_onchain_reject:"):
        order_id = int(data.split(":", 1)[1])
        result = await asyncio.to_thread(
            payment_service.review_onchain_payment,
            order_id,
            uid,
            approved=False,
        )
        if result["status"] in {"not_found", "already_processed"}:
            await q.edit_message_text(
                "⚠️ Cette demande a déjà été traitée ou n’existe plus.",
            )
            return
        order = result["order"]
        network = "BSC (BEP20)" if order["payment_method"] == "usdt_bsc" else "Polygon"
        await q.edit_message_text(
            "❌ <b>On-chain payment rejected</b>\n"
            f"Order: <b>#{order_id}</b>\n"
            f"Network: <b>{network}</b>\n"
            f"TXID: <code>{html.escape(str(order.get('txid') or ''))}</code>",
            parse_mode=ParseMode.HTML,
        )
        customer_id = int(order["user_id"])
        customer_lang = lang_of(customer_id)
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                customer_id,
                t(
                    customer_lang,
                    "onchain_payment_rejected",
                    oid=order_id,
                    network=network,
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.txid_verify_keyboard(customer_lang, order_id),
            )
        return

    if data.startswith("adm_topup_approve:"):
        topup_id = int(data.split(":", 1)[1])
        approved = wallet_service.approve_onchain_topup(topup_id, uid)
        if not approved:
            await q.edit_message_text("⚠️ This top-up was already processed or no longer exists.")
            return
        amount = int(approved["amount_cents"]) / 100
        customer_id = int(approved["user_id"])
        await q.edit_message_text(
            "✅ <b>Wallet top-up approved</b>\n"
            f"Request: <b>#{topup_id}</b>\n"
            f"User: <code>{customer_id}</code>\n"
            f"Credited: <b>{amount:.2f} USDT</b>",
            parse_mode=ParseMode.HTML,
        )
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                customer_id,
                premium_customer_text(
                    lang_of(customer_id),
                    "topup_onchain_approved",
                    amount=f"{amount:.2f}",
                    balance=f"{float(approved['balance']):.2f}",
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.home_keyboard(lang_of(customer_id), customer_id),
            )
        return

    if data.startswith("adm_topup_reject:"):
        topup_id = int(data.split(":", 1)[1])
        rejected = wallet_service.reject_onchain_topup(topup_id, uid)
        if not rejected:
            await q.edit_message_text("⚠️ This top-up was already processed or no longer exists.")
            return
        customer_id = int(rejected["user_id"])
        await q.edit_message_text(
            "❌ <b>Wallet top-up rejected</b>\n"
            f"Request: <b>#{topup_id}</b>\n"
            f"User: <code>{customer_id}</code>",
            parse_mode=ParseMode.HTML,
        )
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                customer_id,
                premium_customer_text(
                    lang_of(customer_id), "topup_onchain_rejected",
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.support_keyboard(lang_of(customer_id)),
            )
        return

    if data == "adm_user_activity":
        activity = db.user_activity_summary()
        await show_callback_screen(
            q,
            "👥 *Activité utilisateurs*\n\n"
            f"🟢 En ligne récemment : *{activity['online_now']}*\n"
            f"📅 Actifs aujourd’hui : *{activity['active_today']}*\n"
            f"👤 Total utilisateurs : *{activity['total_users']}*\n\n"
            "_« En ligne récemment » signifie actif sur le bot durant les 5 dernières minutes._",
            reply_markup=admin.user_activity_keyboard(),
        )
        return

    if data == "adm_maintenance_toggle":
        enabled = not db.shop_settings()["maintenance_enabled"]
        db.set_setting("maintenance_enabled", enabled)
        status = "ACTIVÉE 🔴" if enabled else "DÉSACTIVÉE 🟢"
        if enabled:
            settings = db.shop_settings()
            queued = queue_broadcast(
                "maintenance", message=settings["maintenance_message"],
            )
            detail = (
                "Tous les clients sont maintenant bloqués. Seul l'admin peut utiliser le bot.\n"
                f"📢 Notification mise en file pour {queued['recipient_count']} utilisateur(s)."
            )
        else:
            detail = "Le bot est de nouveau accessible à tous les clients."
        await show_callback_screen(
            q,
            "🛠️ *Panneau Admin*\n\n"
            f"Maintenance : *{status}*\n"
            f"{detail}",
            reply_markup=admin.admin_panel_keyboard(),
        )
        return

    if data == "adm_customize":
        await q.edit_message_text(
            "🎛 *Personnalisation du bot*\n\nModifiez les textes, la visibilité des boutons et les liens personnalisés.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.customize_keyboard(),
        )
        return
    if data == "adm_texts":
        await q.edit_message_text(
            "🗂 *Textes du bot par catégorie*\n\nChoisissez la partie du bot que vous souhaitez modifier :",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.text_categories_keyboard(),
        )
        return

    if data == "adm_broadcast_message":
        PENDING[uid] = ("adm_broadcast_message", 0)
        await q.message.reply_text(
            "📢 *Créer une annonce*\n\n"
            "Envoyez maintenant le message à publier à tous les utilisateurs.\n"
            "La mise en forme Telegram sera conservée.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("adm_text_cat:"):
        category, page = data.removeprefix("adm_text_cat:").rsplit(":", 1)
        labels = dict(admin.TEXT_CATEGORIES)
        await q.edit_message_text(
            f"{labels.get(category, '📝 Textes')}\n\nChoisissez un texte à modifier :",
            reply_markup=admin.texts_category_keyboard(category, int(page)),
        )
        return
    if data.startswith("adm_text_page:"):
        page = int(data.split(":", 1)[1])
        await q.edit_message_text(
            t(lang_of(uid), "admin_text_editor_title"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.texts_editor_keyboard(page),
        )
        return
    if data == "adm_text_noop":
        return
    if data.startswith("adm_text_key:"):
        key = data.split(":", 1)[1]
        await q.edit_message_text(
            admin_text_preview(key),
            parse_mode=ParseMode.HTML,
            reply_markup=admin.text_languages_keyboard(key),
        )
        return
    if data.startswith("adm_text_lang:"):
        key, selected_lang = data.removeprefix("adm_text_lang:").rsplit(":", 1)
        if selected_lang not in {"en", "ar"}:
            await q.answer("Langue non supportée.", show_alert=True)
            return
        current = db.get_text_override(key, selected_lang)
        if current is None:
            current = TRANSLATIONS.get(key, {}).get(selected_lang, "—")
        PENDING[uid] = ("adm_text_override", f"{key}|{selected_lang}")
        if key == "offer_card_template" and "{bulk_price_line}" in current:
            current = decompose_legacy_bulk_line(current, selected_lang)
            db.set_text_override(
                key, selected_lang, current,
                db.get_text_override_icon(key, selected_lang),
            )
        rendered_current = render_admin_text_preview(key, current, selected_lang)
        template_help = (
            "\n\n<b>Variables disponibles :</b>\n"
            "<code>{name}</code> <code>{catalog_emoji}</code> "
            "<code>{catalog_name}</code> <code>{product_name}</code> "
            "<code>{price}</code> <code>{currency}</code> "
            "<code>{stock}</code> <code>{sold}</code> <code>{warranty}</code> "
            "<code>{description}</code> <code>{bulk_price}</code> "
            "<code>{bulk_quantity}</code>"
            "\n<i>{name} inclut automatiquement l’emoji, le catalogue et le produit en gras.</i>"
            if key == "offer_card_template" else ""
        )
        prompt = (
            f"✏️ <b>Modifier {html.escape(key)}</b> "
            f"(<code>{html.escape(selected_lang)}</code>)\n\n"
            f"<b>Aperçu actuel :</b>\n\n{rendered_current}\n\n"
            "Envoyez maintenant le nouveau texte. La mise en forme et les emojis Telegram Premium seront conservés."
            f"{template_help}"
        )
        await q.message.reply_text(
            prompt[:4000],
            parse_mode=ParseMode.HTML,
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Envoyez le nouveau texte…",
            ),
        )
        return
    if data == "adm_buttons":
        await q.edit_message_text(
            "🔘 *Gestion des boutons*\n\nCliquez sur un bouton standard pour le masquer/réactiver. Les boutons personnalisés marqués 🗑 peuvent être supprimés.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.buttons_editor_keyboard(),
        )
        return
    if data.startswith("adm_btn_toggle:"):
        action = data.split(":", 1)[1]
        allowed = {"catalog", "lovable", "topup", "orders", "account", "affiliate", "support", "language"}
        if action in allowed:
            hidden = set(filter(None, (db.get_setting("hidden_home_actions", "") or "").split(",")))
            hidden.remove(action) if action in hidden else hidden.add(action)
            db.set_setting("hidden_home_actions", ",".join(sorted(hidden)))
        await q.edit_message_reply_markup(reply_markup=admin.buttons_editor_keyboard())
        return
    if data == "adm_btn_add":
        PENDING[uid] = ("adm_btn_add", 0)
        await q.message.reply_text(
            "➕ Envoyez : `English | العربية | https://exemple.com`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("adm_btn_del:"):
        db.delete_custom_button(int(data.split(":", 1)[1]))
        await q.edit_message_reply_markup(reply_markup=admin.buttons_editor_keyboard())
        return

    if data.startswith("adm_list:"):
        status = data.split(":")[1]
        keyboard, orders = admin.orders_list_keyboard(status)
        await q.edit_message_text(f"📋 Commandes — *{status}* ({len(orders)})",
                                  parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return

    if data.startswith("adm_order_report:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if not order:
            await q.message.reply_text("⚠️ Commande introuvable.")
            return
        report = admin.order_report(order)
        await q.message.reply_document(
            document=InputFile(
                io.BytesIO(report.encode("utf-8")),
                filename=f"order-{oid}-full-report.txt",
            ),
            caption="Full copyable order report with the real delivered content.",
        )
        return

    if data.startswith("adm_order:"):
        oid = int(data.split(":")[1])
        o = db.get_order(oid)
        await q.edit_message_text(admin.order_detail_text(o), parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=admin.order_detail_keyboard(o))
        return

    if data.startswith("adm_deliver:"):
        oid = int(data.split(":")[1])
        order = db.get_order(oid)
        if not order:
            await q.message.reply_text("⚠️ Commande introuvable.")
            return
        if order.get("status") not in {"paid", "payment_confirmed"}:
            await q.message.reply_text(
                f"⚠️ La commande #{oid} n’est plus en attente de livraison "
                f"(statut : {order.get('status') or 'inconnu'})."
            )
            return
        PENDING[uid] = ("adm_deliver", oid)
        prompt = (
            f"🔑 Envoyez uniquement la licence Lovable pour la commande #{oid}.\n\n"
            "La licence sera enregistrée avec la durée du forfait puis transmise au client."
            if lovable_service.is_lovable_order(order)
            else (
                f"🎁 Envoyez le contenu à livrer pour la commande #{oid} "
                f"(texte, URL, compte, code, instructions ou image). "
                "Tous les caractères seront transmis sans modification."
            )
        )
        await q.message.reply_text(prompt)
        return

    if data.startswith("adm_codex_number:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if (
            not is_otp_order(order)
            or order.get("status") not in {"paid", "payment_confirmed"}
            or str(order.get("otp_workflow_status") or "") not in {
                "", "awaiting_service", "awaiting_country", "sent_to_admin",
                "awaiting_admin_number",
            }
        ):
            await q.message.reply_text("⚠️ This order is not awaiting a Codex number.")
            return
        if str(order.get("otp_workflow_status") or "") != "awaiting_admin_number":
            db.get_conn().orders.update_one(
                {"id": oid},
                {"$set": {
                    "otp_workflow_status": "awaiting_admin_number",
                    "updated_at": int(time.time()),
                }},
            )
        PENDING[uid] = ("adm_codex_number", oid)
        await q.message.reply_text(
            f"📱 Send the Codex number for order #{oid}.\n\n"
            "The customer will receive an I agree button."
        )
        return
    if data == "adm_alert_design":
        await q.edit_message_text(
            "✨ *Design des alertes*\n\n"
            "Modifiez les annonces de nouveaux stocks et de ventes flash. "
            "La mise en forme et les emojis Premium Telegram sont conservés.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.alert_design_keyboard(),
        )
        return
    if data == "adm_ticket_style":
        style = support_bridge.ticket_style()
        await q.edit_message_text(
            "🎨 <b>DESIGN DES TICKETS</b>\n\n"
            "Personnalisez les cartes envoyées dans le canal support. "
            "Les informations sensibles restent protégées.\n\n"
            f"<b>Titre</b>\n<code>{html.escape(style['title'])}</code>\n\n"
            f"<b>Instruction de réponse</b>\n<code>{html.escape(style['reply_hint'])}</code>\n\n"
            f"<b>Signature</b>\n<code>{html.escape(style['footer'])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.ticket_style_keyboard(),
        )
        return
    if data == "adm_ticket_style_preview":
        await q.edit_message_text(
            support_bridge.ticket_card_preview(),
            parse_mode=ParseMode.HTML,
            reply_markup=admin.ticket_style_keyboard(),
        )
        return
    if data == "adm_ticket_style_reset":
        support_bridge.reset_ticket_style()
        await q.edit_message_text(
            "✅ <b>Design restauré</b>\n\nLes valeurs professionnelles par défaut sont de nouveau actives.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin.ticket_style_keyboard(),
        )
        return
    if data.startswith("adm_ticket_style_edit:"):
        field = data.split(":", 1)[1]
        labels = {
            "title": "le nouveau titre",
            "reply_hint": "la nouvelle instruction de réponse",
            "footer": "la nouvelle signature",
        }
        if field not in labels:
            return
        PENDING[uid] = ("adm_ticket_style", field)
        placeholder_note = (
            "\n\nVariables disponibles : `{ticket_id}` et `{ticket_ref}`."
            if field == "reply_hint" else ""
        )
        await q.message.reply_text(
            f"✏️ Envoyez {labels[field]}.{placeholder_note}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data.startswith("adm_codex_otp:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if (
            not is_otp_order(order)
            or order.get("status") not in {"paid", "payment_confirmed"}
            or str(order.get("otp_workflow_status") or "") != "customer_agreed"
        ):
            await q.message.reply_text("⚠️ The customer has not accepted this number yet.")
            return
        PENDING[uid] = ("adm_codex_otp", oid)
        await q.message.reply_text(
            f"🔐 Send the OTP code for order #{oid}.\n\n"
            "Sending it will complete the order."
        )
        return

    if data.startswith("adm_client_message:"):
        oid = int(data.split(":", 1)[1])
        order = db.get_order(oid)
        if not order:
            await q.message.reply_text("⚠️ Commande introuvable.")
            return
        PENDING[uid] = ("adm_client_message", oid)
        await q.message.reply_text(
            f"💬 Envoyez le message destiné au client pour la commande #{oid}.\n\n"
            "Ce message ne livrera pas et ne confirmera pas la commande."
        )
        return

    # ---- gestion catalogue ----
    if data == "adm_catalog":
        db.ensure_methods_service()
        await q.edit_message_text("📦 *Gestion catalogue* — choisissez un service :",
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=admin.catalog_admin_keyboard())
        return
    if data == "adm_tickets":
        markup, tickets = admin.tickets_keyboard()
        await q.edit_message_text(f"🎫 Tickets ouverts ({len(tickets)})", reply_markup=markup)
        return
    if data.startswith("adm_ticket:"):
        ticket = db.get_ticket(int(data.split(":")[1]))
        if ticket:
            await q.edit_message_text(
                f"🎫 Ticket #{ticket['id']}\nUtilisateur: `{ticket['user_id']}`\n"
                f"Statut: `{ticket['status']}`\n\n{ticket['message']}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin.admin_panel_keyboard(),
            )
        return
    if data == "adm_addsvc":
        PENDING[uid] = ("adm_addsvc", 0)
        await q.message.reply_text("➕ Envoyez : `Nom du service | emoji`\nExemple : `Netflix | 🎬`",
                                   parse_mode=ParseMode.MARKDOWN)
        return
    if data.startswith("adm_addoff:"):
        sid = int(data.split(":")[1])
        service = db.get_service(sid) or {}
        is_method = str(service.get("name") or "").strip().lower() == "methods"
        if is_method:
            PENDING[uid] = ("adm_addoff_name", {
                "service_id": sid,
                "photo_file_id": "",
            })
            await q.message.reply_text(
                "✏️ *New method — step 1/4*\n\nSend the method name:",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        PENDING[uid] = ("adm_addoff_image", sid)
        await q.message.reply_text(
            f"🖼 *New offer — step 1/6*\n\n"
            "Send the advertising image, or type `skip` to continue without one.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("adm_inventory:"):
        oid = int(data.split(":")[1])
        PENDING[uid] = ("adm_inventory", oid)
        stats = db.inventory_stats(oid)
        await q.message.reply_text(
            "🔐 *Import massif sécurisé*\n\n"
            f"Pour une livraison manuelle, envoyez uniquement `{inventory_service.MANUAL_STOCK_KEYWORD}` : le bot vous demandera le stock public.\n\n"
            f"Placez `{inventory_service.ACCOUNT_DELIMITER}` seul sur une ligne avant chaque nouveau compte.\n"
            "Le caractère `#` est maintenant un caractère normal et sera conservé dans les comptes, mots de passe et URL.\n"
            f"Toutes les lignes suivantes appartiennent à ce compte jusqu'au prochain `{inventory_service.ACCOUNT_DELIMITER}`.\n\n"
            "Exemple :\n"
            f"`{inventory_service.ACCOUNT_DELIMITER}`\n"
            "`Email: client1@example.com`\n"
            "`Password: secret1`\n"
            "`Instructions: profil A`\n\n"
            f"`{inventory_service.ACCOUNT_DELIMITER}`\n"
            "`Email: client2@example.com`\n"
            "`Password: secret2`\n\n"
            f"Actuellement disponibles : {stats['available']}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith(("adm_svcname:", "adm_svcemoji:", "adm_svcsuffix:")):
        action, sid = data.split(":")
        kind = action
        PENDING[uid] = (kind, int(sid))
        prompt = "➡️ Envoyez l’emoji Unicode à afficher à droite du nom :" if kind == "adm_svcsuffix" else "✏️ Envoyez la nouvelle valeur :"
        await q.message.reply_text(prompt)
        return
    if data.startswith("adm_svctoggle:"):
        sid = int(data.split(":")[1])
        svc = db.get_service(sid)
        db.update_service(sid, active=0 if svc["active"] else 1)
        await q.edit_message_text("✅ Statut du service modifié.",
                                  reply_markup=admin.catalog_admin_keyboard())
        return
    if data.startswith("adm_svcdel:"):
        sid = int(data.split(":")[1])
        return
    if data.startswith("adm_svctoggle:"):
        sid = int(data.split(":")[1])
        svc = db.get_service(sid)
        db.update_service(sid, active=0 if svc["active"] else 1)
        await q.edit_message_text("✅ Statut du service modifié.",
                                  reply_markup=admin.catalog_admin_keyboard())
        return
    if data.startswith("adm_svcdel:"):
        sid = int(data.split(":")[1])
        db.archive_service(sid)
        await q.edit_message_text("🗑 Service archivé avec ses offres.",
                                  reply_markup=admin.catalog_admin_keyboard())
        return
    if data.startswith("adm_svc:"):
        sid = int(data.split(":")[1])
        svc = db.get_service(sid)
        await q.edit_message_text(f"📦 *{svc['name']}* — offres :",
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=admin.service_admin_keyboard(sid))
        return
    if data.startswith("adm_offmove_to:"):
        _, offer_id_text, service_id_text = data.split(":", 2)
        result = db.move_offer(int(offer_id_text), int(service_id_text))
        destination = db.get_service(result["service_id"]) or {}
        await q.edit_message_text(
            f"✅ Offre déplacée vers « {destination.get('name') or result['service_id']} ».",
            reply_markup=admin.offer_admin_keyboard(result["offer_id"]),
        )
        return
    if data.startswith("adm_offmove:"):
        oid = int(data.split(":", 1)[1])
        offer = db.get_offer(oid)
        if not offer:
            await q.answer("Offre introuvable.", show_alert=True)
            return
        await q.edit_message_text(
            f"📂 Déplacer « {offer['name']} »\n\nChoisissez le service de destination :",
            reply_markup=admin.move_offer_keyboard(oid),
        )
        return
    if data.startswith("adm_off:") or data.startswith("adm_off_back:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        if not off:
            await q.answer("Offre introuvable.", show_alert=True)
            return

        # Keep the admin preview identical to the public product card.  Reusing
        # the customer formatter also makes future display changes visible here
        # automatically instead of letting the two screens drift apart.
        preview_text = compact_offer_text(off, lang_of(uid))
        await q.edit_message_text(
            preview_text,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=admin.offer_admin_keyboard(oid))
        return
    if data.startswith(("adm_offname:", "adm_offemoji:", "adm_offnote:", "adm_offperiod:", "adm_offdesc:", "adm_offdelay:")):
        action, oid = data.split(":")
        PENDING[uid] = (action, int(oid))
        prompts = {
            "adm_offname": "✏️ Envoyez le nouveau nom :",
            "adm_offemoji": "🎨 Envoyez un emoji Telegram Premium animé :",
            "adm_offnote": "🛡 Envoyez 0/NW, 30 days, 6 months ou 1 year :",
            "adm_offperiod": "📅 Envoyez 30 days, 3 months ou 1 year :",
            "adm_offdesc": "📄 Envoyez la description complète :",
            "adm_offdelay": "🚚 Envoyez le délai de livraison affiché :",
        }
        await q.message.reply_text(prompts[action])
        return
    if data.startswith("adm_offtoggle:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        db.update_offer(oid, active=0 if off["active"] else 1)
        await q.edit_message_text("✅ Statut de l'offre modifié.",
                                  reply_markup=admin.service_admin_keyboard(off["service_id"]))
        return
    if data.startswith("adm_unlimited:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        enabled = not bool(off.get("unlimited_stock"))
        db.update_offer(oid, unlimited_stock=enabled, manual_stock=False)
        await q.edit_message_text(
            "✅ Stock illimité activé." if enabled else "✅ Stock illimité désactivé.",
            reply_markup=admin.offer_admin_keyboard(oid),
        )
        return
    if data.startswith("adm_flash_start:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        if not off or not off.get("active", 1) or off.get("price") is None:
            await q.answer("Offre indisponible.", show_alert=True)
            return
        PENDING[uid] = ("adm_flash_start", oid)
        await q.message.reply_text(
            f"⚡ *Lancer une vente flash — {off['name']}*\n\n"
            f"Prix actuel : *{float(off['price']):.2f} {CURRENCY}*\n"
            "Envoyez le nouveau prix et la durée en minutes.\n\n"
            "Exemple : `3 480` = 3 USDT pendant 8 heures.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if data.startswith("adm_flash_stop:"):
        oid = int(data.split(":")[1])
        off = db.stop_flash_sale(oid)
        await q.message.reply_text(
            f"⏹ Vente flash arrêtée.\n"
            f"Prix restauré : *{float(off.get('price') or 0):.2f} {CURRENCY}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin.offer_admin_keyboard(oid),
        )
        return
    if data.startswith("adm_broadcast_offer:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        if not off:
            await q.answer("Offre introuvable.", show_alert=True)
            return
        if off.get("archived") == 1:
            db.unarchive_offer(oid)
            off["archived"] = 0
            off["active"] = 1
        elif not off.get("active", 1):
            db.update_offer(oid, active=1)
            off["active"] = 1
        stock = int(off.get("stock") or 0)
        if stock <= 0 and not off.get("unlimited_stock"):
            await q.answer("Aucun stock disponible à annoncer.", show_alert=True)
            return
        queued = queue_broadcast("stock", offer_id=oid, added=None, stock=stock)
        await q.message.reply_text(
            f"✅ Annonce mise en file pour {queued['recipient_count']} utilisateur(s).\n"
            "L’envoi continue en arrière-plan.\n"
            f"💵 Prix actuel : {float(off.get('price') or 0):.2f} {CURRENCY}\n"
            f"📦 Stock annoncé : {'∞' if off.get('unlimited_stock') else stock}"
        )
        return
    if data.startswith("adm_offdel:"):
        oid = int(data.split(":")[1])
        off = db.get_offer(oid)
        db.archive_offer(oid)
        await q.edit_message_text("🗑 Offre archivée.",
                                  reply_markup=admin.service_admin_keyboard(off["service_id"]))
        return
    if data.startswith("adm_setprice:"):
        oid = int(data.split(":")[1])
        PENDING[uid] = ("adm_setprice", oid)
        await q.message.reply_text("💵 Envoyez le nouveau prix (ex : 1.99) :")
        return
    if data.startswith("adm_offimage:"):
        oid = int(data.split(":")[1])
        PENDING[uid] = ("adm_offimage", oid)
        await q.message.reply_text(
            "🖼 *Envoyez la nouvelle image publicitaire*\n\n"
            "Utilisez le bouton 📎 de Telegram, puis choisissez *Photo ou vidéo*.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
async def _send_manual_delivery(
    bot,
    *,
    customer_id,
    delivery_text,
    raw_content,
    reply_markup,
    photo_file_id=None,
    document_file_id=None,
):
    """Send one complete delivery without Telegram markup or length corruption."""
    media_kwargs = {"chat_id": customer_id}
    if photo_file_id or document_file_id:
        if len(delivery_text) <= 900:
            media_kwargs.update({
                "caption": delivery_text,
                "parse_mode": ParseMode.HTML,
                "reply_markup": reply_markup,
            })
            if photo_file_id:
                await bot.send_photo(photo=photo_file_id, **media_kwargs)
            else:
                await bot.send_document(document=document_file_id, **media_kwargs)
            return
        if photo_file_id:
            await bot.send_photo(photo=photo_file_id, **media_kwargs)
        else:
            await bot.send_document(document=document_file_id, **media_kwargs)

    if len(delivery_text) <= 4000:
        await bot.send_message(
            chat_id=customer_id,
            text=delivery_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        return

    # Telegram text messages are capped at 4096 characters. Send a short
    # receipt first, then the opaque delivery data in plain-text chunks.
    header = delivery_text.replace(html.escape(str(raw_content)), "⬇️")
    await bot.send_message(
        chat_id=customer_id,
        text=header,
        parse_mode=ParseMode.HTML,
    )
    chunks = [str(raw_content)[start:start + 4000] for start in range(0, len(str(raw_content)), 4000)]
    for index, chunk in enumerate(chunks):
        await bot.send_message(
            chat_id=customer_id,
            text=chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


async def deliver_order(
    update,
    context,
    order_id,
    content,
    *,
    photo_file_id=None,
    document_file_id=None,
):
    o = db.get_order(order_id)
    if not o:
        await update.message.reply_text("Commande introuvable.")
        return False
    if o.get("status") not in {"paid", "payment_confirmed"}:
        await update.message.reply_text(
            f"⚠️ La commande #{order_id} n’est plus en attente de livraison "
            f"(statut : {o.get('status') or 'inconnu'}). Aucun contenu n’a été envoyé."
        )
        return False
    if is_otp_order(o):
        await update.message.reply_text(
            "⚠️ Codex number orders must use Send number, customer I agree, "
            "then Send OTP code. Generic delivery is disabled for this service."
        )
        return False
    cl = lang_of(o["user_id"])
    try:
        delivery_text = premium_customer_text(
            cl,
            "delivery_received",
            oid=order_id,
            service=o["service_name"],
            offer=o["offer_name"],
            content=content,
        )
        await _send_manual_delivery(
            context.bot,
            customer_id=o["user_id"],
            delivery_text=delivery_text,
            raw_content=content,
            reply_markup=kb.post_delivery_keyboard(cl, order_id),
            photo_file_id=photo_file_id,
            document_file_id=document_file_id,
        )
        if lovable_service.is_lovable_order(o):
            await asyncio.to_thread(
                lovable_service.register_paid_license, order_id, content,
            )
        delivered = order_service.manual_deliver_order(order_id, content)
        if not delivered:
            await update.message.reply_text(
                f"⚠️ Le contenu a été envoyé, mais la commande #{order_id} "
                "n’était plus en attente de livraison."
            )
            return False
        await update.message.reply_text(f"✅ Commande #{order_id} livrée au client.")
        return True
    except Exception as e:
        await update.message.reply_text(f"⚠️ Échec d'envoi au client : {e}")
        return False


async def send_admin_message_to_client(update, context, order_id, content):
    """Send an informational message without changing the order status."""
    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("Commande introuvable.")
        return
    try:
        await context.bot.send_message(
            int(order["user_id"]),
            "💬 <b>Message concernant votre commande "
            f"#{int(order_id)}</b>\n\n{html.escape(str(content))}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.manual_order_reply_keyboard(
                lang_of(int(order["user_id"])), order_id,
            ),
        )
        await update.message.reply_text(
            f"✅ Message envoyé au client. La commande #{order_id} reste en attente de livraison."
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Échec d'envoi au client : {exc}")


async def notify_client(context, user_id, key, **kwargs):
    cl = lang_of(user_id)
    with contextlib.suppress(Exception):
        await context.bot.send_message(user_id, t(cl, key, **kwargs),
                                       parse_mode=ParseMode.MARKDOWN)


# ---------------- Erreurs ----------------
async def on_error(update, context):
    log.error("Update error: %s", context.error)


def build_app():
    issues = configuration_issues()
    if issues:
        raise RuntimeError(f"Configuration incomplète : {', '.join(issues)}")
    db.init_db()
    resume_pending_broadcasts()
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    # Report customer button clicks without consuming them, then apply global gates.
    app.add_handler(CallbackQueryHandler(notify_admin_interaction), group=-5)
    app.add_handler(MessageHandler(filters.ALL, block_maintenance_users), group=-4)
    app.add_handler(CallbackQueryHandler(block_maintenance_users), group=-4)
    app.add_handler(MessageHandler(filters.ALL, block_banned_users), group=-3)
    app.add_handler(CallbackQueryHandler(block_banned_users), group=-3)
    app.add_handler(MessageHandler(filters.ALL, block_non_channel_members), group=-2)
    app.add_handler(CallbackQueryHandler(block_non_channel_members), group=-2)
    app.add_handler(MessageHandler(
        filters.UpdateType.CHANNEL_POST
        & filters.Chat(SUPPORT_TICKET_CHANNEL_ID),
        support_bridge.handle_admin_channel_post,
    ))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", lambda u, c: send_main_menu(u, c, lang_of(u.effective_user.id))))
    app.add_handler(CommandHandler("catalog", cmd_catalog))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("support", cmd_support))
    app.add_handler(CommandHandler("account", show_account))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("affiliate", show_affiliate))
    app.add_handler(CommandHandler("reseller", show_reseller_api))
    app.add_handler(CommandHandler("resellerapi", show_reseller_api))
    app.add_handler(CommandHandler("terms", cmd_terms))
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CommandHandler("replacement", cmd_replacement))
    app.add_handler(CallbackQueryHandler(cb_lang, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(cb_admin, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(cb_navigation))  # reste
    app.add_handler(MessageHandler(filters.PHOTO, handle_pending_photo))
    app.add_handler(MessageHandler(filters.ATTACHMENT, handle_pending_attachment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_menu))
    app.add_error_handler(on_error)
    return app


def main():
    app = build_app()
    log.info("HEAVENPREM bot démarré (long polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
