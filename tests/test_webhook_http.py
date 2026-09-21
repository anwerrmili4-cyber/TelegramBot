"""HTTP-level smoke tests for the production webhook handler."""

from __future__ import annotations

import base64
import json
import threading
from contextlib import contextmanager
from http.cookiejar import CookieJar
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import api.webhook as webhook_module
import database as database_module
from api.webhook import handler


@contextmanager
def running_server():
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_public_health_endpoint():
    with running_server() as base_url, urlopen(f"{base_url}/health", timeout=5) as response:
        payload = json.load(response)

    assert response.status == 200
    assert payload["ok"] is True
    assert payload["version"]
    assert payload["timestamp"]


def test_dashboard_uses_first_configured_reseller_provider(monkeypatch, mock_mongodb):
    mock_mongodb.reseller_products.insert_many([
        {"provider": "cgpt_active", "product_id": "1", "enabled": True},
        {"provider": "mailreader", "product_id": "2", "enabled": True},
        {"provider": "cgpt_active", "product_id": "3", "enabled": False},
    ])
    monkeypatch.setattr(
        webhook_module.reseller_service,
        "provider_summaries",
        lambda: [
            {"id": "mailreader", "configured": False},
            {"id": "cgpt_active", "configured": True},
        ],
    )

    assert webhook_module.reseller_dashboard_summary() == {
        "configured": True,
        "default_provider": "cgpt_active",
        "selected_count": 2,
    }


def test_public_homepage_is_site():
    with running_server() as base_url, urlopen(f"{base_url}/", timeout=5) as response:
        body = response.read().decode()

    assert response.status == 200
    assert "text/html" in response.headers["Content-Type"]
    assert "BlackMarket" in body
    assert "Lancer @" in body


def test_admin_shows_login_app_but_api_requires_authentication(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    with running_server() as base_url, urlopen(f"{base_url}/admin", timeout=5) as response:
        assert response.status == 200
        assert "text/html" in response.headers["Content-Type"]
        try:
            urlopen(f"{base_url}/admin/api/data", timeout=5)
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Admin API was accessible without authentication")


def test_admin_login_creates_session_cookie(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with running_server() as base_url:
        request = Request(
            f"{base_url}/admin/api/login",
            data=json.dumps({"username": "admin", "password": "secret"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(request, timeout=5) as response:
            assert json.load(response)["ok"] is True
            assert "HttpOnly" in response.headers["Set-Cookie"]
            assert "SameSite=Strict" in response.headers["Set-Cookie"]

        with opener.open(f"{base_url}/admin/api/data", timeout=5) as response:
            assert response.status == 200


def test_reseller_provider_health_metadata_is_authenticated_and_safe(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    monkeypatch.setattr(
        webhook_module.reseller_service,
        "provider_summaries",
        lambda: [{"id": "one", "name": "One API", "configured": True}],
    )
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/api/reseller-providers",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/api/reseller-providers"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload == {
        "ok": True,
        "providers": [{"id": "one", "name": "One API", "configured": True}],
    }


def test_pending_payment_monitor_requires_cron_secret_and_returns_cancellations(
    monkeypatch,
):
    monkeypatch.setenv("CRON_SECRET", "cron-secret")
    monkeypatch.setattr(
        webhook_module.order_service,
        "cancel_stale_pending_orders",
        lambda: [41, 42],
    )
    request = Request(
        "http://placeholder/api/cron/pending-payments",
        headers={"Authorization": "Bearer cron-secret"},
    )

    with running_server() as base_url:
        request.full_url = f"{base_url}/api/cron/pending-payments"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload == {"ok": True, "cancelled": 2, "order_ids": [41, 42]}


def test_bulk_price_update_is_audited_and_reversible(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    mock_mongodb.services.insert_one({"id": 1, "name": "Service", "active": 1})
    mock_mongodb.offers.insert_many([
        {"id": 10, "service_id": 1, "name": "One", "price": 2.0, "tn_price_millimes": 10000, "active": 1},
        {"id": 11, "service_id": 1, "name": "Two", "price": 4.0, "active": 1},
    ])
    encoded = base64.b64encode(b"admin:secret").decode()
    body = urlencode({
        "action": "bulk_update_offers",
        "offer_ids": "10,11",
        "operation": "price_percent",
        "value": "10",
    }).encode()
    request = Request(
        "http://placeholder/admin",
        data=body,
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert payload["modified"] == 2
    assert database_module.get_offer(10)["price"] == 2.2
    assert database_module.get_offer(10)["tn_price_millimes"] == 11000
    event = mock_mongodb.audit_events.find_one({"action": "offer.bulk_updated"})
    assert event["id"]
    assert event["details"]["reversible"] is True
    assert event["details"]["changes"][0]["before"]["price"] == 2.0

    restored = webhook_module.undo_audit_event(event["id"])
    assert restored["restored"] == 2
    assert database_module.get_offer(10)["price"] == 2.0
    assert database_module.get_offer(10)["tn_price_millimes"] == 10000


def test_undo_skips_an_entity_changed_after_the_audited_action(mock_mongodb):
    mock_mongodb.offers.insert_one({"id": 10, "name": "One", "price": 9.0, "active": 1})
    event_id = database_module.audit_event("offer.bulk_updated", details={
        "reversible": True,
        "changes": [{"id": 10, "before": {"price": 2.0}, "after": {"price": 3.0}}],
    })

    result = webhook_module.undo_audit_event(event_id)

    assert result == {
        "ok": True,
        "restored": 0,
        "skipped": 1,
        "message": "0 élément(s) restauré(s), 1 ignoré(s).",
    }
    assert database_module.get_offer(10)["price"] == 9.0


def test_react_admin_serves_production_build(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin-v2/orders",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin-v2/orders"
        with urlopen(request, timeout=5) as response:
            body = response.read().decode()

    assert response.status == 200
    assert "text/html" in response.headers["Content-Type"]
    assert '<div id="root"></div>' in body


def test_primary_admin_route_serves_react_build(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin"
        with urlopen(request, timeout=5) as response:
            body = response.read().decode()

    assert response.status == 200
    assert "Black Market · Control Room" in body
    assert '<div id="root"></div>' in body


def test_react_admin_section_route_serves_spa(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/orders",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/orders"
        with urlopen(request, timeout=5) as response:
            body = response.read().decode()

    assert response.status == 200
    assert '<div id="root"></div>' in body


def test_react_admin_data_includes_scoped_write_token(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/api/data",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/api/data"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload["dashboard_write_token"] == webhook_module.dashboard_write_token()
    assert payload["dashboard_write_token"] != "secret"


def test_admin_reseller_clients_endpoint_returns_safe_profiles(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "partner"})
    mock_mongodb.buyer_api_keys.insert_one({
        "id": 1, "user_id": 42, "prefix": "tgb_12345678",
        "key_hash": "never-return-this-hash", "active": True, "created_at": 1,
    })
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/api/reseller-clients",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/api/reseller-clients"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload["items"][0]["username"] == "partner"
    assert payload["items"][0]["keys"][0]["prefix"] == "tgb_12345678"
    assert "never-return-this-hash" not in str(payload)


def test_admin_reseller_comparison_endpoint_is_authenticated(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    with running_server() as base_url:
        try:
            urlopen(f"{base_url}/admin/api/reseller-comparison", timeout=5)
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Supplier comparison was accessible without authentication")


def test_admin_reseller_comparison_endpoint_returns_ranked_groups(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    monkeypatch.setattr(
        webhook_module.reseller_comparison_service,
        "compare_catalogs",
        lambda force=False: {
            "ok": True,
            "groups": [{"label": "Canva Pro", "offers": []}],
            "force": force,
        },
    )
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/api/reseller-comparison?refresh=1",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/api/reseller-comparison?refresh=1"
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload["groups"][0]["label"] == "Canva Pro"
    assert payload["force"] is True


def test_webhook_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv("HP_WEBHOOK_SECRET", "expected-secret")
    request = Request(
        "http://placeholder/api/webhook",
        data=json.dumps({"update_id": 1}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/api/webhook"
        try:
            urlopen(request, timeout=5)
        except HTTPError as exc:
            payload = json.load(exc)
            assert exc.code == 403
            assert payload["error"] == "invalid webhook secret"
        else:
            raise AssertionError("Webhook accepted a request without its secret")


def test_webhook_rejects_requests_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("HP_WEBHOOK_SECRET", raising=False)
    request = Request(
        "http://placeholder/api/webhook",
        data=json.dumps({"update_id": 1}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/api/webhook"
        try:
            urlopen(request, timeout=5)
        except HTTPError as exc:
            payload = json.load(exc)
            assert exc.code == 503
            assert payload["error"] == "webhook_not_configured"
        else:
            raise AssertionError("Webhook accepted a request without a configured secret")


def test_webhook_requires_json_content_type(monkeypatch):
    monkeypatch.setenv("HP_WEBHOOK_SECRET", "expected-secret")
    request = Request(
        "http://placeholder/api/webhook",
        data=b"update_id=1",
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
        method="POST",
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/api/webhook"
        try:
            urlopen(request, timeout=5)
        except HTTPError as exc:
            assert exc.code == 415
        else:
            raise AssertionError("Webhook accepted a non-JSON request")


def test_control_room_routes_support_direct_navigation():
    with running_server() as base_url:
        for page in ("control-center", "phone", "data-explorer", "ai-manager", "api-clients"):
            with urlopen(f"{base_url}/admin/{page}", timeout=5) as response:
                assert response.status == 200
                assert '<div id="root"></div>' in response.read().decode()
