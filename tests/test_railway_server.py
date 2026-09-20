"""Tests for the all-in-one Railway process."""

from __future__ import annotations

import http.client
import threading
from contextlib import contextmanager
from http.server import HTTPServer

import config
import railway_server


@contextmanager
def running_surface(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_deployment_requires_a_generated_railway_domain(monkeypatch):
    monkeypatch.setattr(config, "configuration_issues", lambda **_kwargs: [])
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-id")
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    monkeypatch.delenv("HP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("HP_WEBHOOK_SECRET", "w" * 32)
    monkeypatch.setenv("CRON_SECRET", "a" * 32)

    assert "Railway public domain (generate one under Networking)" in (
        railway_server.deployment_issues()
    )


def test_deployment_accepts_railway_generated_domain(monkeypatch):
    monkeypatch.setattr(config, "configuration_issues", lambda **_kwargs: [])
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-id")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "blackmarket.up.railway.app")
    monkeypatch.delenv("HP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("HP_WEBHOOK_SECRET", "w" * 32)
    monkeypatch.setenv("CRON_SECRET", "a" * 32)

    assert railway_server.deployment_issues() == []


def test_webhook_registration_retries_transient_failure(monkeypatch):
    results = iter(
        [
            {"ok": False, "message": "temporary"},
            {"ok": True, "url": "https://blackmarket.up.railway.app/api/webhook"},
        ]
    )
    monkeypatch.setattr(
        railway_server.webhook,
        "repair_telegram_webhook",
        lambda: next(results),
    )

    result = railway_server.register_telegram_webhook(attempts=2, retry_seconds=0)

    assert result["ok"] is True


def test_public_port_blocks_admin_without_admin_domain(monkeypatch):
    monkeypatch.delenv("HP_ADMIN_BASE_URL", raising=False)
    with running_surface(railway_server.PublicHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/admin")
        response = connection.getresponse()
        body = response.read()
        connection.close()

    assert response.status == 404
    assert b"NOT_FOUND" in body


def test_public_port_never_discloses_isolated_admin_domain(monkeypatch):
    monkeypatch.setenv("HP_ADMIN_BASE_URL", "https://admin.trustmarket.tn/")
    with running_surface(railway_server.PublicHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/admin/orders")
        response = connection.getresponse()
        body = response.read()
        connection.close()

    assert response.status == 404
    assert response.headers.get("Location") is None
    assert b"admin.trustmarket.tn" not in body


def test_public_port_blocks_encoded_and_traversal_admin_paths():
    paths = (
        "/terms/../admin",
        "/terms/%2e%2e/admin",
        "/%61dmin/api/data",
        "/public%5c..%5cadmin-v2/orders",
        "/admin-legacy",
    )
    with running_surface(railway_server.PublicHandler) as port:
        for path in paths:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
            connection.close()

            assert response.status == 404
            assert b"NOT_FOUND" in body


def test_public_port_blocks_admin_for_post_and_options():
    requests = (
        ("POST", "/admin/api/login", "{}", {"Content-Type": "application/json"}),
        ("OPTIONS", "/admin/api/data", None, {}),
    )
    with running_surface(railway_server.PublicHandler) as port:
        for method, path, body, headers in requests:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            connection.close()

            assert response.status == 404
            assert response.headers.get("Location") is None
            assert response.headers["Cache-Control"] == "no-store"
            assert b"NOT_FOUND" in payload


def test_public_home_does_not_link_to_admin_panel():
    with running_surface(railway_server.PublicHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read()
        connection.close()

    assert response.status == 200
    assert b'href="/admin' not in body
    assert b"Dashboard commandes" not in body
    assert response.headers["X-Frame-Options"] == "DENY"


def test_public_port_serves_terms_page_from_railway():
    with running_surface(railway_server.PublicHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/terms")
        response = connection.getresponse()
        body = response.read()
        connection.close()

    assert response.status == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert b"Terms of Service" in body
    assert b"https://t.me/blackmarketBotChannel" in body
    assert b"https://t.me/Blackmarketgrp" in body
    assert b"https://t.me/b9hdc2" in body


def test_admin_port_root_redirects_to_dashboard():
    with running_surface(railway_server.AdminHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == 302
    assert response.headers["Location"] == "/admin"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
