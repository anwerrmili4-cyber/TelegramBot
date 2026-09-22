"""Bridge support tickets between customers and the private Telegram channel."""

from __future__ import annotations

import html
import re
from typing import Any

from telegram.constants import ParseMode

import database as db
import keyboards as kb
from app.domain import support_service
from config import ADMIN_ID, SUPPORT_TICKET_CHANNEL_ID

_TICKET_REFERENCE_RE = re.compile(
    r"^(?:/reply\s+)?(?:TKT-)?(?P<ticket_id>\d+)\b",
    re.IGNORECASE,
)

TICKET_STYLE_DEFAULTS = {
    "title": "BLACKMARKET SUPPORT CENTER",
    "reply_hint": "Reply to this post or use /reply {ticket_id} your message.",
    "footer": "Fast • Secure • Human support",
}
TICKET_STYLE_SETTING_KEYS = {
    field: f"support_ticket_card_{field}" for field in TICKET_STYLE_DEFAULTS
}


def ticket_reference(ticket_id: int) -> str:
    return f"TKT-{int(ticket_id):06d}"


def media_label(message: Any) -> str:
    for attribute, label in (
        ("photo", "Photo"),
        ("document", "Document"),
        ("video", "Video"),
        ("animation", "Animation"),
        ("audio", "Audio"),
        ("voice", "Voice message"),
        ("video_note", "Video note"),
        ("sticker", "Sticker"),
    ):
        if getattr(message, attribute, None):
            return label
    return "Attachment"


def message_media(message: Any) -> dict | None:
    """Return safe Telegram file metadata that the dashboard can render."""
    value = None
    media_type = "document"
    photos = getattr(message, "photo", None) or []
    if photos:
        value = photos[-1]
        media_type = "image"
    else:
        for attribute, kind in (
            ("video", "video"),
            ("animation", "video"),
            ("video_note", "video"),
            ("document", "document"),
            ("sticker", "sticker"),
        ):
            candidate = getattr(message, attribute, None)
            if candidate:
                value = candidate
                media_type = kind
                break
    if not value or not getattr(value, "file_id", None):
        return None
    original = value
    if media_type == "sticker" and getattr(value, "thumbnail", None):
        value = value.thumbnail
    mime_type = str(getattr(value, "mime_type", None) or "")
    if media_type == "document" and mime_type.startswith("image/"):
        media_type = "image"
    elif media_type == "document" and mime_type.startswith("video/"):
        media_type = "video"
    return {
        "type": media_type,
        "file_id": value.file_id,
        "file_unique_id": getattr(value, "file_unique_id", None),
        "file_name": getattr(value, "file_name", None),
        "mime_type": mime_type or None,
        "width": getattr(value, "width", None),
        "height": getattr(value, "height", None),
        "duration": getattr(value, "duration", None),
        "file_size": getattr(value, "file_size", None),
        "custom_emoji_id": getattr(original, "custom_emoji_id", None),
    }


def _user_values(user: Any, user_id: int) -> tuple[str, str]:
    name = getattr(user, "full_name", None) or getattr(user, "first_name", None) or str(user_id)
    raw_username = getattr(user, "username", None) or ""
    return str(name), f"@{raw_username}" if raw_username else "Not provided"


def ticket_style() -> dict[str, str]:
    """Return the administrator-editable, plain-text ticket card style."""
    return {
        field: str(db.get_setting(TICKET_STYLE_SETTING_KEYS[field], default) or default).strip()
        or default
        for field, default in TICKET_STYLE_DEFAULTS.items()
    }


def save_ticket_style(field: str, value: str) -> str:
    if field not in TICKET_STYLE_DEFAULTS:
        raise ValueError("Unknown ticket style field.")
    limits = {"title": 80, "reply_hint": 240, "footer": 120}
    clean = " ".join(str(value or "").split())[:limits[field]]
    if not clean:
        raise ValueError("The value cannot be empty.")
    db.set_setting(TICKET_STYLE_SETTING_KEYS[field], clean)
    return clean


def reset_ticket_style() -> None:
    for field, default in TICKET_STYLE_DEFAULTS.items():
        db.set_setting(TICKET_STYLE_SETTING_KEYS[field], default)


def _styled_text(value: str, ticket: dict) -> str:
    return str(value).replace("{ticket_id}", str(int(ticket["id"]))).replace(
        "{ticket_ref}", ticket_reference(ticket["id"])
    )


def _event_style(event: str) -> tuple[str, str]:
    normalized = str(event or "").lower()
    if "closed" in normalized:
        return "✅", "CLOSED"
    if "attachment" in normalized:
        return "📎", "ATTACHMENT"
    if "reply" in normalized or "message" in normalized:
        return "💬", "CUSTOMER REPLY"
    if "catalog" in normalized:
        return "🛍️", "New catalog request"
    return "🆕", "NEW TICKET"


def _channel_card(ticket: dict, user: Any, body: str, event: str) -> str:
    user_id = int(ticket["user_id"])
    name, username = _user_values(user, user_id)
    category = str(ticket.get("category") or "other").replace("_", " ").title()
    order_line = f"\n• <b>Order:</b> <code>#{int(ticket['order_id'])}</code>" if ticket.get("order_id") else ""
    priority = str(ticket.get("priority") or "normal").replace("_", " ").title()
    status = str(ticket.get("status") or "waiting_admin").replace("_", " ").title()
    style = ticket_style()
    event_icon, event_label = _event_style(event)
    reply_hint = _styled_text(style["reply_hint"], ticket)
    return (
        f"🛎️ <b>{html.escape(style['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<blockquote>{event_icon} <b>{event_label} · {ticket_reference(ticket['id'])}</b>\n"
        f"🟠 <b>Status:</b> {html.escape(status)}\n"
        f"🏷️ <b>Category:</b> {html.escape(category)}\n"
        f"⚡ <b>Priority:</b> {html.escape(priority)}</blockquote>\n\n"
        "👤 <b>CUSTOMER DETAILS</b>\n"
        f'• <b>Name:</b> <a href="tg://user?id={user_id}">{html.escape(name)}</a>\n'
        f"• <b>Username:</b> {html.escape(username)}\n"
        f"• <b>Telegram ID:</b> <code>{user_id}</code>"
        f"{order_line}\n\n"
        "💬 <b>CUSTOMER MESSAGE</b>\n"
        f"<blockquote>{html.escape(body[:2500])}</blockquote>\n\n"
        f"↩️ <b>REPLY</b>\n<i>{html.escape(reply_hint)}</i>\n\n"
        f"<i>— {html.escape(style['footer'])}</i>"
    )


def ticket_card_preview() -> str:
    """Render a safe example using the currently saved administrator style."""
    class PreviewUser:
        full_name = "Example Customer"
        first_name = "Example"
        username = "customer"

    return _channel_card(
        {
            "id": 62,
            "user_id": 123456789,
            "order_id": 412,
            "category": "delivery",
            "priority": "high",
            "status": "waiting_admin",
        },
        PreviewUser(),
        "Hello, I need help with my order.",
        "New support ticket",
    )


def _link_sent_message(ticket_id: int, sent: Any) -> None:
    message_id = getattr(sent, "message_id", None)
    if message_id:
        support_service.link_channel_message(ticket_id, int(message_id))


async def send_client_text(
    context,
    ticket: dict,
    user: Any,
    text: str,
    *,
    event: str = "New support ticket",
) -> None:
    sent = await context.bot.send_message(
        SUPPORT_TICKET_CHANNEL_ID,
        _channel_card(ticket, user, text, event),
        parse_mode=ParseMode.HTML,
    )
    _link_sent_message(ticket["id"], sent)


async def send_client_media(
    context,
    ticket: dict,
    user: Any,
    message: Any,
    *,
    event: str = "Customer attachment",
) -> None:
    caption = str(getattr(message, "caption", None) or "")
    summary = media_label(message)
    if caption:
        summary = f"{summary}: {caption}"
    header = await context.bot.send_message(
        SUPPORT_TICKET_CHANNEL_ID,
        _channel_card(ticket, user, summary, event),
        parse_mode=ParseMode.HTML,
    )
    _link_sent_message(ticket["id"], header)
    copied = await context.bot.copy_message(
        chat_id=SUPPORT_TICKET_CHANNEL_ID,
        from_chat_id=getattr(message, "chat_id", None) or message.chat.id,
        message_id=message.message_id,
    )
    _link_sent_message(ticket["id"], copied)


async def send_ticket_closed(context, ticket: dict, user: Any) -> None:
    sent = await context.bot.send_message(
        SUPPORT_TICKET_CHANNEL_ID,
        _channel_card(ticket, user, "Ticket closed by the customer.", "Ticket closed"),
        parse_mode=ParseMode.HTML,
    )
    _link_sent_message(ticket["id"], sent)


def _resolve_ticket(message: Any) -> tuple[dict | None, str]:
    reply = getattr(message, "reply_to_message", None)
    if reply and getattr(reply, "message_id", None):
        ticket = support_service.get_ticket_by_channel_message(reply.message_id)
        if ticket:
            return ticket, str(message.text or message.caption or "").strip()

    raw_text = str(message.text or message.caption or "").strip()
    match = _TICKET_REFERENCE_RE.match(raw_text)
    if not match:
        return None, raw_text
    ticket = support_service.get_ticket(int(match.group("ticket_id")))
    return ticket, raw_text[match.end() :].lstrip(" :-\n")


async def handle_admin_channel_post(update, context) -> bool:
    """Deliver a channel reply to the customer associated with that ticket post."""
    message = update.channel_post
    if not message or int(message.chat.id) != SUPPORT_TICKET_CHANNEL_ID:
        return False
    sender = getattr(message, "from_user", None)
    if sender and getattr(sender, "is_bot", False):
        return False

    ticket, content = _resolve_ticket(message)
    if not ticket or ticket.get("status") in {"closed", "resolved"}:
        return False

    has_media = any(
        getattr(message, attribute, None)
        for attribute in (
            "photo",
            "document",
            "video",
            "animation",
            "audio",
            "voice",
            "video_note",
            "sticker",
        )
    )
    if not content and not has_media:
        return False

    ticket_id = int(ticket["id"])
    user_id = int(ticket["user_id"])
    lang = db.get_user_lang(user_id) or "en"
    body = content or f"[{media_label(message)}]"
    await context.bot.send_message(
        user_id,
        (
            f"🛎️ <b>{html.escape(ticket_style()['title'])}</b>\n"
            f"<blockquote>💬 <b>REPLY · {ticket_reference(ticket_id)}</b></blockquote>\n\n"
            f"{html.escape(body[:2500])}\n\n"
            f"<i>— {html.escape(ticket_style()['footer'])}</i>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.ticket_conversation_keyboard(lang, ticket_id),
    )
    if has_media:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=SUPPORT_TICKET_CHANNEL_ID,
            message_id=message.message_id,
        )

    support_service.add_message(
        ticket_id,
        ADMIN_ID,
        body,
        sender_type="admin",
        media=message_media(message),
    )
    support_service.link_channel_message(ticket_id, message.message_id)
    return True
