"""Presentation and delivery helpers for Telegram announcements."""

from __future__ import annotations

import logging
import re

from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from app.bot.presentation import _is_single_emoji

log = logging.getLogger("bot")


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


__all__ = [
    "announcement_plain",
    "announcement_service_emoji",
    "send_broadcast_message_safe",
    "track_broadcast_message",
]
