"""Tests for the all-in-one Railway process."""

from __future__ import annotations

import http.client
import threading
from contextlib import contextmanager
from http.server import HTTPServer

import pytest

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


def _get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


def test_storefront_port_serves_the_built_customer_site():
    with running_surface(railway_server.StorefrontHandler) as port:
        response, body = _get(port, "/")

    assert response.status == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert b"BlackMarket Tunisie" in body
    assert "img-src 'self' data: https:" in response.headers["Content-Security-Policy"]


def test_storefront_port_falls_back_to_the_app_for_unknown_paths():
    with running_surface(railway_server.StorefrontHandler) as port:
        response, body = _get(port, "/une-page-inconnue")

    assert response.status == 200
    assert b"<div id=\"root\">" in body


@pytest.mark.parametrize(
    ("path", "content_type", "marker"),
    [
        ("/robots.txt", "text/plain; charset=utf-8", b"Sitemap: https://www.ourblackmarket.com/sitemap.xml"),
        ("/sitemap.xml", "application/xml; charset=utf-8", b"<loc>https://www.ourblackmarket.com/</loc>"),
    ],
)
def test_storefront_port_serves_crawler_files(path, content_type, marker):
    with running_surface(railway_server.StorefrontHandler) as port:
        response, body = _get(port, path)

    assert response.status == 200
    assert response.headers["Content-Type"] == content_type
    assert response.headers["Cache-Control"] == "public, max-age=3600"
    assert marker in body


def test_storefront_port_refuses_paths_escaping_the_build():
    with running_surface(railway_server.StorefrontHandler) as port:
        response, body = _get(port, "/assets/%2e%2e%2f%2e%2e%2fconfig.py")

    assert response.status == 200
    assert b"MONGODB_URI" not in body


def test_storefront_port_exposes_only_the_storefront_api():
    blocked = (
        "/api/webhook",
        "/api/v2/telegram-buyer/products",
        "/api/cron/restock",
        "/api/openapi.json",
        "/admin",
        "/admin/api/data",
    )
    with running_surface(railway_server.StorefrontHandler) as port:
        for path in blocked:
            response, body = _get(port, path)

            assert response.status == 404, path
            assert b"NOT_FOUND" in body, path
            assert response.headers.get("Location") is None


def test_storefront_port_blocks_non_storefront_writes():
    requests = (
        ("POST", "/api/webhook"),
        ("POST", "/admin/api/login"),
        ("OPTIONS", "/admin/api/data"),
    )
    with running_surface(railway_server.StorefrontHandler) as port:
        for method, path in requests:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request(method, path, body="{}", headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            body = response.read()
            connection.close()

            assert response.status == 404, path
            assert b"NOT_FOUND" in body, path


def test_all_three_surfaces_need_distinct_ports(monkeypatch):
    monkeypatch.setattr(railway_server, "deployment_issues", lambda: [])
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("ADMIN_PORT", "8081")
    monkeypatch.setenv("STOREFRONT_PORT", "8080")

    with pytest.raises(RuntimeError, match="must all be different"):
        railway_server.main()


def test_slow_restock_does_not_block_payment_scheduler():
    import asyncio

    from app.jobs.scheduler import ScheduledJob, Scheduler

    release = threading.Event()
    calls = []

    def slow_restock():
        calls.append("restock")
        release.wait(3)
        return 200, {}

    def payments():
        calls.append("payments")
        return 200, {}

    async def main():
        stop = asyncio.Event()
        scheduler = Scheduler([
            ScheduledJob("restock", 0.01, slow_restock),
            ScheduledJob("pending-payments", 0.01, payments),
        ])
        task = asyncio.create_task(scheduler.run(stop))
        for _ in range(200):
            if calls.count("payments") >= 3:
                break
            await asyncio.sleep(0.01)
        stop.set()
        release.set()
        await asyncio.wait_for(task, 3)
        return scheduler

    scheduler = asyncio.run(main())
    assert calls.count("payments") >= 3
    assert calls.count("restock") == 1
    restock = scheduler.snapshot()[0]
    assert restock["runs"] == 1 and restock["last_status"] == 200


def test_scheduled_failures_are_counted():
    import asyncio

    from app.jobs.scheduler import ScheduledJob, Scheduler

    def broken():
        raise RuntimeError("supplier down")

    job = ScheduledJob("prices", 60, broken)
    asyncio.run(Scheduler([job]).run_once(job))
    assert job.failures == 1 and job.last_status == 500
