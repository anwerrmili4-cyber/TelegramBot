"""The FastAPI surfaces: native routes, the legacy bridge and port isolation."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

import database as db
from app.bot import runtime as bot_runtime
from app.web import admin_app, legacy_bridge, public_app, storefront_app

SECRET = "s" * 32


@pytest.fixture
def public():
    with TestClient(public_app.app) as client:
        yield client


@pytest.fixture
def storefront():
    with TestClient(storefront_app.app) as client:
        yield client


@pytest.fixture
def admin():
    with TestClient(admin_app.app, follow_redirects=False) as client:
        yield client


def test_health_is_native_and_carries_surface_headers(public, storefront, admin):
    for client, frame in ((public, "DENY"), (admin, "DENY"), (storefront, None)):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers.get("x-frame-options") == frame
        assert len(response.headers["x-request-id"]) == 16


def test_a_valid_request_id_is_propagated(public):
    response = public.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["x-request-id"] == "trace-abc-123"
    response = public.get("/health", headers={"X-Request-ID": "bad id!"})
    assert response.headers["x-request-id"] != "bad id!"


def test_public_surface_still_blocks_admin_paths_through_the_bridge(public):
    for path in ("/admin", "/admin/orders", "/%61dmin/api/data", "/terms/%2e%2e/admin"):
        response = public.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"] == "NOT_FOUND"
        assert response.headers["cache-control"] == "no-store"
    response = public.post("/admin/api/login", json={})
    assert response.status_code == 404


def test_public_terms_page_keeps_its_policy(public):
    response = public.get("/terms")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers.get("server") is None


def test_storefront_serves_the_spa_natively_and_hides_other_apis(storefront):
    response = storefront.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "img-src 'self' data: https:" in response.headers["content-security-policy"]
    assert '<div id="root">' in storefront.get("/une-page-inconnue").text
    assert "MONGODB_URI" not in storefront.get("/assets/%2e%2e%2f%2e%2e%2fconfig.py").text
    for path in ("/api/webhook", "/api/cron/restock", "/admin", "/api/openapi.json"):
        response = storefront.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"] == "NOT_FOUND"
    assert storefront.post("/api/webhook", json={}).status_code == 404


def test_catalog_is_native_cached_and_gzipped(storefront, mock_mongodb):
    service_id = db.add_service("Netflix", "🎬", sales_channels=["bot", "tn_site"])
    for index in range(30):
        db.add_offer(
            service_id, f"Premium {index}", 5.0, 3,
            description="x" * 50, sales_channels=["bot", "tn_site"], tn_price_millimes=15000,
        )
    response = storefront.get("/api/storefront/catalog", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "public, max-age=60"
    assert len(response.json()["services"][0]["offers"]) == 30


def test_a_burst_of_visitors_shares_one_catalog_build(storefront, mock_mongodb, monkeypatch):
    from app.core.cache import cache
    from app.domain import storefront_service

    monkeypatch.setattr(storefront_service, "CATALOG_CACHE_SECONDS", 30)
    cache.clear()
    service_id = db.add_service("Spotify", "🎵", sales_channels=["bot", "tn_site"])
    db.add_offer(service_id, "Solo", 4.0, 2, sales_channels=["bot", "tn_site"], tn_price_millimes=9000)
    builds = {"count": 0}
    real = storefront_service._build_catalog

    def counting():
        builds["count"] += 1
        return real()

    monkeypatch.setattr(storefront_service, "_build_catalog", counting)
    first = storefront.get("/api/storefront/catalog")
    second = storefront.get("/api/storefront/catalog")
    assert first.status_code == second.status_code == 200
    assert first.json()["services"][0]["offers"][0]["name"]
    assert second.content == first.content
    assert builds["count"] == 1


def test_admin_root_redirects_and_details_need_the_cron_secret(admin, monkeypatch):
    response = admin.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/admin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

    monkeypatch.setenv("CRON_SECRET", "c" * 32)
    assert admin.get("/api/health/details").status_code == 401

    async def fake_ping():
        return 3.5

    monkeypatch.setattr("app.core.db.ping_ms", fake_ping)
    response = admin.get("/api/health/details", headers={"Authorization": "Bearer " + "c" * 32})
    payload = response.json()
    assert response.status_code == 200
    assert payload["mongo_ping_ms"] == 3.5
    assert payload["jobs"] == {"due": 0, "scheduled": 0, "running": 0, "failed": 0, "failed_last_hour": 0}
    assert payload["alerts"] == []
    assert response.headers["cache-control"] == "no-store"


def test_health_details_turn_unhealthy_when_jobs_give_up(admin, monkeypatch, mock_mongodb):
    import time

    monkeypatch.setenv("CRON_SECRET", "c" * 32)

    async def fake_ping():
        return 3.5

    monkeypatch.setattr("app.core.db.ping_ms", fake_ping)
    mock_mongodb.jobs.insert_one({"id": 1, "kind": "email.send", "status": "failed", "finished_at": time.time()})

    response = admin.get("/api/health/details", headers={"Authorization": "Bearer " + "c" * 32})

    assert response.status_code == 503
    assert response.json()["alerts"] == ["1 jobs failed permanently in the last hour"]


def test_bridge_forwards_bodies_and_query_strings(admin, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "c" * 32)
    monkeypatch.setattr("app.jobs.scheduled.JOBS", {
        "/api/cron/pending-payments": lambda: (200, {"ok": True, "cancelled": 0, "order_ids": []}),
    })
    response = admin.get("/api/cron/pending-payments", headers={"Authorization": "Bearer " + "c" * 32})
    assert response.status_code == 200
    assert response.json()["cancelled"] == 0
    assert admin.get("/api/cron/pending-payments").status_code == 401


def test_bridge_rejects_oversized_bodies(public, monkeypatch):
    monkeypatch.setattr(legacy_bridge, "MAX_BODY_BYTES", 10)
    response = public.post("/api/v2/telegram-buyer/purchase", content=b"x" * 50)
    assert response.status_code == 413


def test_raw_response_parser_drops_hop_by_hop_headers():
    raw = b"HTTP/1.0 201 Created\r\nServer: x\r\nDate: y\r\nContent-Length: 2\r\nX-A: 1\r\n\r\nok"
    status, headers, body = legacy_bridge.parse_raw_response(raw)
    assert status == 201 and body == b"ok"
    assert headers == [("x-a", "1")]


def _webhook(client, payload, *, secret=SECRET, content_type="application/json"):
    return client.post(
        "/api/webhook",
        content=json.dumps(payload).encode() if not isinstance(payload, bytes) else payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret, "Content-Type": content_type},
    )


def test_webhook_checks_secret_type_and_body(public, monkeypatch):
    monkeypatch.delenv("HP_WEBHOOK_SECRET", raising=False)
    assert _webhook(public, {"update_id": 1}).status_code == 503
    monkeypatch.setenv("HP_WEBHOOK_SECRET", SECRET)
    assert _webhook(public, {"update_id": 1}, secret="wrong").status_code == 403
    assert _webhook(public, {"update_id": 1}, content_type="text/plain").status_code == 415
    assert _webhook(public, b"not json").status_code == 400
    assert _webhook(public, [1, 2]).status_code == 400


def test_webhook_acknowledges_at_once_and_dedupes(public, monkeypatch):
    monkeypatch.setenv("HP_WEBHOOK_SECRET", SECRET)
    submitted = []
    monkeypatch.setattr(bot_runtime, "submit_update", submitted.append)

    first = _webhook(public, {"update_id": 77, "message": {}})
    again = _webhook(public, {"update_id": 77, "message": {}})

    assert first.json() == {"ok": True}
    assert again.json() == {"ok": True, "duplicate": True}
    assert [payload["update_id"] for payload in submitted] == [77]


def test_webhook_releases_the_update_when_it_cannot_be_queued(public, monkeypatch):
    monkeypatch.setenv("HP_WEBHOOK_SECRET", SECRET)

    def broken(_payload):
        raise RuntimeError("bot unavailable")

    monkeypatch.setattr(bot_runtime, "submit_update", broken)
    assert _webhook(public, {"update_id": 91}).status_code == 500
    monkeypatch.setattr(bot_runtime, "submit_update", lambda _payload: None)
    assert _webhook(public, {"update_id": 91}).json() == {"ok": True}


def test_large_legacy_json_is_gzipped_by_the_middleware(admin):
    response = admin.get("/api/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert json.loads(response.content)["openapi"]
