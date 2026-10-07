"""Update guards that run before the feature handlers.

Registered in negative groups by ``bot.build_app``: interaction report (-5,
non-blocking so a button press never waits for the report channel),
maintenance (-4), bans (-3) and required-channel membership (-2). Shared
settings such as ``ADMIN_ID`` are read from the ``bot`` module at call time,
so the bot keeps a single place to configure (and patch) them.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.core.cache import CATALOG_PREFIX, cache

log = logging.getLogger("bot")

# Every update passes the ban and maintenance guards; a short cache saves two
# MongoDB round trips per update. Settings writes clear the maintenance entry
# through the catalog write listener and bans clear their user's entry.
GUARD_CACHE_SECONDS = 5.0
_MAINTENANCE_KEY = CATALOG_PREFIX + "bot-maintenance"


def _bot():
    import bot

    return bot


def banned_cache_key(user_id) -> str:
    return f"bot:banned:{int(user_id)}:"


def invalidate_banned(user_id) -> None:
    cache.invalidate(banned_cache_key(user_id))


def _is_banned(user_id) -> bool:
    return cache.get_or_set(
        banned_cache_key(user_id), GUARD_CACHE_SECONDS, lambda: bool(_bot().db.is_user_banned(user_id)),
    )


def _maintenance() -> tuple[bool, str]:
    def load():
        settings = _bot().db.shop_settings()
        return bool(settings["maintenance_enabled"]), str(settings["maintenance_message"] or "")

    return cache.get_or_set(_MAINTENANCE_KEY, GUARD_CACHE_SECONDS, load)


# Positive-only membership cache. Non-members are never cached, and the
# explicit Verify button always performs a live Telegram check.
_membership_cache: dict[tuple[int, str], float] = {}


def cache_required_channel_member(user_id: int) -> None:
    bot = _bot()
    channel = str(bot._normalize_required_chat(bot.REQUIRED_CHANNEL))
    if channel and bot.MEMBERSHIP_CACHE_SECONDS > 0:
        _membership_cache[(int(user_id), channel)] = (
            time.monotonic() + bot.MEMBERSHIP_CACHE_SECONDS
        )


async def is_required_channel_member_cached(telegram_bot, user_id: int) -> bool:
    """Avoid Telegram API round trips for recently verified members."""
    bot = _bot()
    channel = str(bot._normalize_required_chat(bot.REQUIRED_CHANNEL))
    key = (int(user_id), channel)
    now = time.monotonic()
    if _membership_cache.get(key, 0) > now:
        return True
    _membership_cache.pop(key, None)
    allowed = await bot.is_required_channel_member(telegram_bot, user_id)
    if allowed:
        cache_required_channel_member(user_id)
    if len(_membership_cache) > 10_000:
        expired = [cache_key for cache_key, expiry in _membership_cache.items() if expiry <= now]
        for cache_key in expired:
            _membership_cache.pop(cache_key, None)
    return allowed


async def block_non_channel_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prevent customers from bypassing the required channel via direct commands."""
    bot = _bot()
    user = update.effective_user
    if not user or user.id == bot.ADMIN_ID:
        return
    if update.callback_query and update.callback_query.data == "verify_channel_join":
        return
    message_text = getattr(update.effective_message, "text", "") or ""
    if message_text.startswith("/start"):
        return
    if await is_required_channel_member_cached(context.bot, user.id):
        return
    lang = bot.lang_of(user.id)
    if update.callback_query:
        await update.callback_query.answer()
    await update.effective_message.reply_text(
        bot.premium_customer_text(lang, "channel_join_required"),
        parse_mode=ParseMode.HTML,
        reply_markup=bot.kb.channel_join_keyboard(lang),
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
    bot = _bot()
    user = update.effective_user
    if not user or user.id == bot.ADMIN_ID or not update.callback_query:
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
        await asyncio.to_thread(
            bot.db.log_interaction,
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
            bot.CLICK_REPORT_CHAT_ID,
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
                    chat_id=bot.CLICK_REPORT_CHAT_ID,
                    from_chat_id=chat_id,
                    message_id=message_id,
                )
    except Exception:
        log.exception("Unable to notify admin about interaction from user %s", user.id)


async def block_banned_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = _bot()
    user = update.effective_user
    if user and user.id != bot.ADMIN_ID and _is_banned(user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Accès suspendu.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("⛔ Votre accès à cette boutique est suspendu.")
        raise ApplicationHandlerStop


async def block_maintenance_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lock the entire customer bot during maintenance while preserving admin access."""
    bot = _bot()
    user = update.effective_user
    if not user or user.id == bot.ADMIN_ID:
        return
    enabled, message = _maintenance()
    if not enabled:
        return

    message = message.strip() or (
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
