"""Job kinds executed by :class:`app.core.jobs.JobRunner`.

Importing this module registers them; the server does so at startup.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core import jobs

log = logging.getLogger(__name__)


@jobs.handler("email.send")
def send_email(payload: dict[str, Any]) -> None:
    from app.domain import email_service

    email_service.deliver(payload["message"])


@jobs.handler("telegram.send_message")
def send_telegram_message(payload: dict[str, Any]) -> None:
    """Send a customer message; blocked chats and bad requests are not retried."""
    from telegram.error import BadRequest, Forbidden

    from app.bot import runtime as bot_runtime

    bot = bot_runtime.application().bot
    try:
        bot_runtime.run(bot.send_message(
            payload["chat_id"],
            payload["text"],
            parse_mode=payload.get("parse_mode"),
        ))
    except (Forbidden, BadRequest) as exc:
        log.warning("telegram_message_dropped chat_id=%s reason=%s", payload["chat_id"], exc)


def queue_telegram_message(chat_id: int, text: str, *, parse_mode: str | None = None) -> None:
    payload = {"chat_id": int(chat_id), "text": text, "parse_mode": parse_mode}
    jobs.dispatch(
        "telegram.send_message",
        payload,
        fallback=lambda: send_telegram_message(payload),
    )
