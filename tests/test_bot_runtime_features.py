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


def test_ban_guard_is_cached_and_a_ban_clears_it(monkeypatch, mock_mongodb):
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

    asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    assert lookups.call_count == 1

    db.set_user_banned(42, True)
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(middlewares.block_banned_users(update, SimpleNamespace()))
    assert lookups.call_count == 2


def test_maintenance_guard_reads_settings_once_per_window(monkeypatch):
    monkeypatch.setattr(middlewares, "GUARD_CACHE_SECONDS", 60)
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    settings = Mock(return_value={"maintenance_enabled": False, "maintenance_message": ""})
    monkeypatch.setattr("bot.db.shop_settings", settings)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), callback_query=None, effective_message=None)

    for _ in range(3):
        asyncio.run(middlewares.block_maintenance_users(update, SimpleNamespace()))
    assert settings.call_count == 1


def test_click_report_does_not_block_the_button_handlers():
    import bot

    app = bot.build_app()
    report = next(h for h in app.handlers[-5] if h.callback is middlewares.notify_admin_interaction)
    assert report.block is False


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
