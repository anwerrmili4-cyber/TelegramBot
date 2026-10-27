"""Presentation and delivery helpers for Telegram announcements."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

import database as db
import keyboards as kb
from app.bot.customer_text import premium_customer_text
from app.bot.methods_presentation import method_announcement_text
from app.bot.presentation import _is_single_emoji
from app.domain import warranty_service
from config import CURRENCY, DEFAULT_LANG, SHOP_NAME

log = logging.getLogger("bot")

BROADCAST_BATCH_SIZE = max(
    1, min(20, int(os.environ.get("HP_BROADCAST_BATCH_SIZE", "15"))),
)
BROADCAST_BATCH_DELAY = max(
    0.25, float(os.environ.get("HP_BROADCAST_BATCH_DELAY", "0.55")),
)
def _default_admin_id():
    return 0


def _default_language(_user_id):
    return DEFAULT_LANG


_admin_id_provider = _default_admin_id
_language_provider = _default_language


def configure_admin_context(admin_id_provider, language_provider):
    """Inject bot-runtime lookups without creating an import cycle."""
    global _admin_id_provider, _language_provider
    _admin_id_provider = admin_id_provider
    _language_provider = language_provider


def announcement_service_emoji(service, fallback="📦"):
    """Render a service's Unicode or Premium emoji inside announcement text."""
    service = service or {}
    raw_emoji = str(service.get("emoji") or "").strip()
    emoji = raw_emoji if _is_single_emoji(raw_emoji) else fallback
    emoji_id = str(service.get("custom_emoji_id") or "").strip()
    if emoji_id and emoji_id.isascii():
        return f"[[TGEMOJI:{emoji_id}:{emoji.encode('utf-8').hex()}]]"
    return emoji


def announcement_plain(value):
    """Keep dynamic names from breaking the customizable Markdown template."""
    return str(value or "").replace("*", "").replace("_", " ").replace("`", "").strip()


def track_broadcast_message(context, sent_message, chat_id):
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
            # Delivery already succeeded, so a tracking error must not resend it.
            log.warning(
                "Could not track broadcast message %s/%s: %s",
                chat_id,
                message_id,
                exc,
            )
    return sent_message


async def send_broadcast_message_safe(context, chat_id, text, reply_markup=None):
    """Send an HTML announcement message with automatic plain-text fallback."""
    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        return track_broadcast_message(context, sent_message, chat_id)
    except BadRequest as exc:
        err_msg = str(exc).lower()
        if any(term in err_msg for term in ("entity", "parse", "html", "tag", "can't parse")):
            log.warning(
                "Broadcast HTML parse failure for user %s (%s). Falling back to plain text.",
                chat_id,
                exc,
            )
            plain_text = re.sub(r"<[^>]+>", "", text)
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                reply_markup=reply_markup,
            )
            return track_broadcast_message(context, sent_message, chat_id)
        raise


def is_blocked_broadcast_error(exc):
    message = str(exc).lower()
    return "blocked" in message or "chat not found" in message or "deactivated" in message


async def broadcast_in_batches(
    send_one, *, label, catalog_updates_only=False, catalog_offer_id=None,
):
    """Send concurrently in Telegram-safe chunks, with rate-limit retries."""
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
                delay = (
                    retry_after.total_seconds()
                    if hasattr(retry_after, "total_seconds")
                    else float(retry_after)
                )
                await asyncio.sleep(delay + 0.15)
            except (TimedOut, NetworkError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                log.warning("%s failed for user %s: %s", label, user_id, exc)
                return 0
            except Exception as exc:
                if is_blocked_broadcast_error(exc):
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


def offer_reaches_customers(offer):
    from app.domain.offer_stock_control import offer_reaches_bot_customers

    return offer_reaches_bot_customers(offer)


async def announce_channel_restock(
    context, offer_id, added, stock, supplier_event=None,
):
    """Broadcast a private new-stock advert to every active bot user."""
    offer = db.get_offer(int(offer_id))
    if not offer_reaches_customers(offer):
        return 0
    unlimited = bool(offer.get("unlimited_stock"))
    if not unlimited:
        try:
            stock = max(0, int(offer.get("stock") or 0))
        except (TypeError, ValueError):
            stock = max(0, int(stock or 0))
        if stock <= 0:
            return 0
    if added is not None and int(added or 0) <= 0:
        return 0
    service = db.get_service(offer["service_id"]) or {}
    price = "—" if offer.get("price") is None else f"{float(offer['price']):.2f}"

    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        message_key = (
            "channel_stock_announcement"
            if added is not None
            else "offer_stock_announcement"
        )
        values = {
            "emoji": announcement_service_emoji(service),
            "service": announcement_plain(service.get("name") or SHOP_NAME),
            "offer": announcement_plain(offer.get("name") or f"Offer #{offer_id}"),
            "period": kb.offer_period_label(lang, offer),
            "warranty": warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
            "price": price,
            "cur": CURRENCY,
            "stock": "∞" if unlimited else int(stock),
        }
        if added is not None:
            values["added"] = int(added)
        await send_broadcast_message_safe(
            context,
            chat_id=user_id,
            text=method_announcement_text(
                premium_customer_text(lang, message_key, **values),
                service,
                offer,
                lang,
            ),
            reply_markup=kb.announcement_offer_keyboard(lang, offer),
        )

    return await broadcast_in_batches(
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
    if not offer_reaches_customers(offer) or not offer.get("flash_sale_active"):
        return 0
    service = db.get_service(offer["service_id"]) or {}
    remaining_seconds = max(0, int(offer["flash_sale_ends_at"]) - int(time.time()))
    hours, remainder = divmod(remaining_seconds, 3600)
    minutes = max(1, remainder // 60)
    remaining = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    old_price = float(offer["flash_sale_original_price"])
    new_price = float(offer["price"])
    discount_percent = (
        round(((old_price - new_price) / old_price) * 100) if old_price else 0
    )

    async def send_one(user):
        user_id = int(user["telegram_id"])
        lang = user.get("lang") or DEFAULT_LANG
        await send_broadcast_message_safe(
            context,
            chat_id=user_id,
            text=method_announcement_text(
                premium_customer_text(
                    lang,
                    "flash_sale_announcement",
                    emoji=announcement_service_emoji(service, "🎁"),
                    service=announcement_plain(service.get("name") or SHOP_NAME),
                    offer=announcement_plain(offer.get("name") or f"Offer #{offer_id}"),
                    period=kb.offer_period_label(lang, offer),
                    warranty=warranty_service.offer_warranty_label(offer, lang=lang) or "NW",
                    old_price=f"{old_price:.2f}",
                    price=f"{new_price:.2f}",
                    cur=CURRENCY,
                    discount=discount_percent,
                    remaining=remaining,
                ),
                service,
                offer,
                lang,
            ),
            reply_markup=kb.announcement_offer_keyboard(lang, offer),
        )

    return await broadcast_in_batches(
        send_one,
        label="Flash-sale broadcast",
        catalog_updates_only=True,
        catalog_offer_id=offer_id,
    )


async def announce_supplier_change_admin(context, event, change_type):
    """Send the normal product design privately when a promo is unsuitable."""
    admin_id = int(_admin_id_provider() or 0)
    if not admin_id:
        return 0
    event = event or {}
    offer = db.get_offer(int(event.get("offer_id") or 0)) or {}
    if not offer:
        return 0
    lang = _language_provider(admin_id)
    service = db.get_service(offer.get("service_id")) or {}
    values = {
        "emoji": announcement_service_emoji(service),
        "service": announcement_plain(service.get("name") or SHOP_NAME),
        "offer": announcement_plain(
            offer.get("name") or f"Offer #{offer.get('id', 0)}",
        ),
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
                "discount": (
                    round(((old_price - new_price) / old_price) * 100)
                    if old_price else 0
                ),
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
    await send_broadcast_message_safe(
        context,
        chat_id=admin_id,
        text=method_announcement_text(
            premium_customer_text(lang, key, **values),
            service,
            offer,
            lang,
        ),
        reply_markup=kb.offer_detail_keyboard(lang, offer),
    )
    return 1


__all__ = [
    "announcement_plain",
    "announcement_service_emoji",
    "announce_channel_restock",
    "announce_flash_sale",
    "announce_supplier_change_admin",
    "broadcast_in_batches",
    "configure_admin_context",
    "is_blocked_broadcast_error",
    "send_broadcast_message_safe",
    "send_new_stock_broadcast",
    "track_broadcast_message",
]
