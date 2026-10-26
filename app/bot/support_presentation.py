"""Customer-facing support ticket presentation."""

from __future__ import annotations

import html

from app import support_bridge


def ticket_conversation_text(ticket):
    category = str(ticket.get("category") or "other").replace("_", " ").title()
    reference = support_bridge.ticket_reference(ticket["id"])
    return (
        f"<b>Support Ticket {reference}</b>\n\n"
        f"<blockquote>Category: <b>{html.escape(category)}</b>\n"
        "Status: <b>Open</b></blockquote>\n\n"
        "Send any message or attachment here. It goes directly to our support team."
    )


def support_notifications_text(messages, lang="en"):
    copy = {
        "en": ("🔔 <b>Notifications</b>", "You have no unread support messages."),
        "fr": ("🔔 <b>Notifications</b>", "Vous n’avez aucun message de support non lu."),
        "ar": ("🔔 <b>الإشعارات</b>", "ليس لديك رسائل دعم غير مقروءة."),
    }
    title, empty = copy.get(lang, copy["en"])
    if not messages:
        return f"{title}\n\n{empty}"
    rows = [title, ""]
    for message in messages:
        reference = support_bridge.ticket_reference(message["ticket_id"])
        content = html.escape(str(message.get("content") or "")[:500])
        rows.append(f"🔴 <b>{reference}</b>\n{content}")
    return "\n\n".join(rows)


__all__ = ["support_notifications_text", "ticket_conversation_text"]
