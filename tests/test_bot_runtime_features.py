"""Guard caching, the file_id cache and the job handlers that talk to Telegram."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest, Forbidden
from telegram.ext import ApplicationHandlerStop

import database as db
from app.bot import media, middlewares
from app.jobs import handlers
from app.repositories import telegram_files


def test_ban_guard_does_not_trust_a_stale_not_banned_cache(monkeypatch, mock_mongodb):
    from app.core.cache import cache

    monkeypatch.setattr(middlewares, "GUARD_CACHE_SECONDS", 60)
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.users.insert_one({"telegram_id": 42})
    lookups = Mock(wraps=db.is_user_banned)
    monkeypatch.setattr("bot.db.is_user_banned", lookups)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        callback_query=None,
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )

    cache.set(middlewares.banned_cache_key(42), False, 60)
    asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    assert lookups.call_count == 2

    db.set_user_banned(42, True)
    cache.set(middlewares.banned_cache_key(42), False, 60)
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    update.effective_message.reply_text.assert_awaited()


def test_ban_guard_still_stops_when_the_notice_cannot_be_sent(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    db.upsert_user(42, "buyer", "Buyer")
    db.set_user_banned(42, True)
    query = SimpleNamespace(answer=AsyncMock(side_effect=BadRequest("query is too old")))
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        callback_query=query,
        effective_message=None,
    )

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))


def test_maintenance_guard_reads_settings_once_per_window(monkeypatch):
    monkeypatch.setattr(middlewares, "GUARD_CACHE_SECONDS", 60)
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    settings = Mock(return_value={"maintenance_enabled": False, "maintenance_message": ""})
    monkeypatch.setattr("bot.db.shop_settings", settings)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), callback_query=None, effective_message=None)

    for _ in range(3):
        asyncio.run(middlewares.block_maintenance_users(update, SimpleNamespace()))
    assert settings.call_count == 1


def test_click_report_does_not_block_the_button_handlers(monkeypatch):
    import bot
    import config

    token = "123456789:" + ("A" * 35)
    monkeypatch.setattr(config, "BOT_TOKEN", token)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    monkeypatch.setattr(config, "MONGODB_URI", "mongodb://127.0.0.1:27017/ci")
    monkeypatch.setattr(bot, "BOT_TOKEN", token)
    app = bot.build_app()
    report = next(h for h in app.handlers[-5] if h.callback is middlewares.notify_admin_interaction)
    assert report.block is False
    ban_group = min(
        group
        for group, registered in app.handlers.items()
        if any(handler.callback is middlewares.block_banned_users for handler in registered)
    )
    assert ban_group < -5


def _offer_click(user_id, update_id):
    from datetime import UTC, datetime

    from telegram import CallbackQuery, Chat, Message, Update, User

    user = User(
        id=user_id, is_bot=False, first_name="Stella", last_name="Martinez", username="stellamrtinze",
    )
    chat = Chat(id=user_id, type=Chat.PRIVATE)
    message = Message(
        message_id=18,
        date=datetime.now(UTC),
        chat=chat,
        text="Choose the Lovable plan you want to purchase:",
    )
    query = CallbackQuery(
        id=f"cq-{update_id}",
        from_user=user,
        chat_instance="shop",
        data="off:185",
        message=message,
    )
    return Update(update_id=update_id, callback_query=query)


def _catalog_command(user_id, update_id):
    from datetime import UTC, datetime

    from telegram import Chat, Message, Update, User

    user = User(id=user_id, is_bot=False, first_name="Stella", username="stellamrtinze")
    chat = Chat(id=user_id, type=Chat.PRIVATE)
    message = Message(
        message_id=19,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text="/catalog",
    )
    return Update(update_id=update_id, message=message)


def test_banned_telegram_id_cannot_complete_a_button_click(monkeypatch, mock_mongodb):
    """A client the admin marked Bloqué must not open an offer or be reported as clicking."""
    from telegram import User
    from telegram.ext import ExtBot

    import bot
    import config
    from app.core.cache import cache

    token = "123456789:" + ("A" * 35)
    monkeypatch.setattr(config, "BOT_TOKEN", token)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    monkeypatch.setattr(config, "MONGODB_URI", "mongodb://127.0.0.1:27017/ci")
    monkeypatch.setattr(bot, "BOT_TOKEN", token)
    monkeypatch.setattr(bot, "ADMIN_ID", 1)
    monkeypatch.setattr(middlewares, "GUARD_CACHE_SECONDS", 300)
    navigation = AsyncMock()
    catalog = AsyncMock()
    monkeypatch.setattr(bot, "cb_navigation", navigation)
    monkeypatch.setattr(bot, "cmd_catalog", catalog)
    monkeypatch.setattr(bot, "is_required_channel_member", AsyncMock(return_value=True))

    async def initialize(self):
        self._bot_initialized = True
        self._requests_initialized = True
        self._bot_user = User(id=123456789, is_bot=True, first_name="Shop")

    answered = []
    sent = []

    async def answer_callback_query(self, callback_query_id, text=None, show_alert=None, **kwargs):
        answered.append(text)
        return True

    async def send_message(self, chat_id, text=None, **kwargs):
        sent.append(text or "")
        return SimpleNamespace(message_id=1, chat_id=chat_id)

    monkeypatch.setattr(ExtBot, "initialize", initialize)
    monkeypatch.setattr(ExtBot, "answer_callback_query", answer_callback_query)
    monkeypatch.setattr(ExtBot, "send_message", send_message)

    banned_id = 8610043241
    db.upsert_user(banned_id, "stellamrtinze", "Stella")
    assert db.set_user_banned(banned_id, True) is True
    # The old guard cached "not banned" and kept serving that after Bloqué.
    cache.set(middlewares.banned_cache_key(banned_id), False, 300)
    app = bot.build_app()

    def attach_bot(update):
        update.set_bot(app.bot)
        for item in (update.callback_query, update.effective_message):
            if item is None:
                continue
            item.set_bot(app.bot)
            message = getattr(item, "message", None)
            if message is not None:
                message.set_bot(app.bot)

    async def deliver(update):
        await app.initialize()
        attach_bot(update)
        await app.process_update(update)
        pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        if pending:
            done = await asyncio.gather(*pending, return_exceptions=True)
            failures = [result for result in done if isinstance(result, Exception)]
            if failures:
                raise failures[0]

    asyncio.run(deliver(_offer_click(banned_id, 501)))

    navigation.assert_not_awaited()
    assert mock_mongodb.interaction_events.count_documents({"user_id": banned_id}) == 0
    assert answered == ["⛔ Accès suspendu."]
    assert not any("CUSTOMER CLICK" in text for text in sent)
    assert db.is_user_banned(banned_id) is True
    assert mock_mongodb.users.find_one({"telegram_id": banned_id})["username"] == "stellamrtinze"

    asyncio.run(deliver(_catalog_command(banned_id, 502)))
    catalog.assert_not_awaited()
    assert any("suspendu" in text for text in sent)

    db.set_user_banned(banned_id, False)
    cache.set(middlewares.banned_cache_key(banned_id), True, 300)
    answered.clear()
    asyncio.run(deliver(_offer_click(banned_id, 503)))
    navigation.assert_awaited()
    assert db.is_user_banned(banned_id) is False


def _photo_message(file_id):
    return SimpleNamespace(photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id=file_id)])


def test_photo_is_uploaded_by_url_once_then_by_file_id(mock_mongodb):
    url = "https://example.com/assets/benefits.png"
    send = AsyncMock(return_value=_photo_message("big-file-id"))

    asyncio.run(media.send_cached_photo(send, url, caption="x"))
    asyncio.run(media.send_cached_photo(send, url, caption="x"))

    assert send.await_args_list[0].kwargs == {"photo": url, "caption": "x"}
    assert send.await_args_list[1].kwargs == {"photo": "big-file-id", "caption": "x"}
    assert telegram_files.get_file_id(url) == "big-file-id"


def test_a_rejected_file_id_falls_back_to_the_url(mock_mongodb):
    url = "https://example.com/assets/benefits.png"
    telegram_files.remember_file_id(url, "expired")
    send = AsyncMock(side_effect=[BadRequest("Wrong file identifier"), _photo_message("fresh")])

    asyncio.run(media.send_cached_photo(send, url))

    assert send.await_args_list[1].kwargs == {"photo": url}
    assert telegram_files.get_file_id(url) == "fresh"


def _fake_bot_runtime(monkeypatch, send_message):
    from app.bot import runtime as bot_runtime

    monkeypatch.setattr(bot_runtime, "application", lambda: SimpleNamespace(bot=SimpleNamespace(send_message=send_message)))
    monkeypatch.setattr(bot_runtime, "run", asyncio.run)


def test_telegram_job_sends_and_drops_permanent_failures(monkeypatch):
    send = AsyncMock()
    _fake_bot_runtime(monkeypatch, send)
    handlers.send_telegram_message({"chat_id": 5, "text": "hi", "parse_mode": "HTML"})
    send.assert_awaited_once_with(5, "hi", parse_mode="HTML")

    _fake_bot_runtime(monkeypatch, AsyncMock(side_effect=Forbidden("bot was blocked by the user")))
    handlers.send_telegram_message({"chat_id": 5, "text": "hi"})


def test_telegram_job_raises_temporary_failures_for_retry(monkeypatch):
    from telegram.error import NetworkError

    _fake_bot_runtime(monkeypatch, AsyncMock(side_effect=NetworkError("timeout")))
    with pytest.raises(NetworkError):
        handlers.send_telegram_message({"chat_id": 5, "text": "hi"})


def test_ticket_reply_is_queued_when_the_runner_is_active(monkeypatch, mock_mongodb):
    from api import webhook
    from app.core import jobs

    monkeypatch.setattr(jobs, "runner_active", lambda: True)
    webhook._deliver_ticket_reply(42, 7, "<b>Bonjour</b>")

    job = mock_mongodb.jobs.find_one({"kind": "telegram.send_message"})
    assert job["payload"]["chat_id"] == 42
    assert "Ticket #7" in job["payload"]["text"]
    assert "&lt;b&gt;Bonjour&lt;/b&gt;" in job["payload"]["text"]
