"""Smoke tests for application startup and the public health endpoint."""

from __future__ import annotations

from datetime import datetime

import config
import database as db
from api import webhook
from api.webhook import handler, health_payload, public_site_html
from bot import build_app


def test_public_health_payload():
    payload = health_payload()

    assert payload["ok"] is True
    assert payload["service"] == "TelegramBot webhook"
    assert payload["version"]
    datetime.fromisoformat(payload["timestamp"])


def test_webhook_handler_is_importable():
    assert handler.__name__ == "handler"


def test_telegram_webhook_health_detects_stable_url(monkeypatch):
    expected = "https://blackmarket.up.railway.app/api/webhook"
    monkeypatch.setenv("HP_PUBLIC_BASE_URL", "https://blackmarket.up.railway.app")
    monkeypatch.setattr(
        webhook,
        "_telegram_api",
        lambda _method, _payload=None: {
            "ok": True,
            "result": {
                "url": expected,
                "pending_update_count": 2,
                "last_error_message": "",
            },
        },
    )

    result = webhook.telegram_webhook_health()

    assert result["ok"] is True
    assert result["healthy"] is True
    assert result["pending_update_count"] == 2


def test_repair_telegram_webhook_registers_secret(monkeypatch):
    captured = {}
    monkeypatch.setenv("HP_WEBHOOK_SECRET", "safe-secret")

    def fake_api(method, payload=None):
        captured.update({"method": method, "payload": payload})
        return {"ok": True, "result": True}

    monkeypatch.setattr(webhook, "_telegram_api", fake_api)

    result = webhook.repair_telegram_webhook()

    assert result["ok"] is True
    assert captured["method"] == "setWebhook"
    assert captured["payload"]["url"].endswith("/api/webhook")
    assert captured["payload"]["secret_token"] == "safe-secret"


def test_public_site_links_to_bot():
    page = public_site_html()

    assert "<!doctype html>" in page.lower()
    assert "https://t.me/blackmarketa_bot" in page
    assert "?start=catalog" in page
    assert "?start=orders" in page
    assert "?start=support" in page
    assert 'property="og:image"' in page
    assert "/assets/blackmarket-midnight-og.png" in page


def test_public_site_has_live_status_and_opt_in_notifications():
    page = public_site_html()

    assert 'fetch("/health"' in page
    assert "setInterval(checkHealth, 15000)" in page
    assert 'id="notify-button"' in page
    assert "Notification.requestPermission()" in page
    assert "prefers-reduced-motion:reduce" in page
    assert "admin/api/data" not in page


def test_bot_application_builds_with_mock_database(mock_mongodb, monkeypatch):
    import bot

    monkeypatch.setattr(db, "init_db", lambda: None)
    token = "123456789:" + ("A" * 35)
    monkeypatch.setattr(config, "BOT_TOKEN", token)
    monkeypatch.setattr(config, "ADMIN_ID", 1)
    monkeypatch.setattr(config, "MONGODB_URI", "mongodb://127.0.0.1:27017/ci")
    monkeypatch.setattr(bot, "BOT_TOKEN", token)

    application = build_app()

    assert application.bot.token

    command_names = {
        command
        for group in application.handlers.values()
        for registered in group
        for command in getattr(registered, "commands", ())
    }
    assert {
        "start",
        "catalog",
        "orders",
        "account",
        "support",
        "language",
        "affiliate",
        "terms",
        "privacy",
    } <= command_names
