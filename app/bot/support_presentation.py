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


__all__ = ["ticket_conversation_text"]
