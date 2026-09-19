import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import PENDING, cb_navigation, handle_pending_input


def test_ai_agent_button_starts_private_conversation(monkeypatch):
    monkeypatch.setattr("bot.customer_ai_service.is_configured", lambda: True)
    monkeypatch.setattr("bot.customer_ai_service.clear_history", lambda user_id: None)
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="ai_agent",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert PENDING.get(42) == ("ai_agent", "other")
    assert message.reply_text.await_count == 1


def test_ai_agent_message_updates_handoff_category(monkeypatch):
    PENDING[42] = ("ai_agent", "other")
    monkeypatch.setattr(
        "bot.customer_ai_service.chat",
        lambda user_id, text, lang: {
            "reply": "A human should check that delivery.",
            "needs_human": True,
            "category": "delivery",
        },
    )
    message = SimpleNamespace(text="My delivery is missing", reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )

    asyncio.run(handle_pending_input(update, SimpleNamespace(), "en"))

    assert PENDING.get(42) == ("ai_agent", "delivery")
    assert message.reply_text.await_args.args[0] == "A human should check that delivery."
