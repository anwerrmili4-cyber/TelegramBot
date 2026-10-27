"""Presentation and delivery helpers for Telegram announcements."""

from __future__ import annotations

import asyncio
import logging
import os
import re

from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

import database as db
from app.bot.presentation import _is_single_emoji

log = logging.getLogger("bot")

BROADCAST_BATCH_SIZE = max(
    1, min(20, int(os.environ.get("HP_BROADCAST_BATCH_SIZE", "15"))),
)
BROADCAST_BATCH_DELAY = max(
    0.25, float(os.environ.get("HP_BROADCAST_BATCH_DELAY", "0.55")),
)


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


__all__ = [
    "announcement_plain",
    "announcement_service_emoji",
    "broadcast_in_batches",
    "is_blocked_broadcast_error",
    "send_broadcast_message_safe",
    "track_broadcast_message",
]
