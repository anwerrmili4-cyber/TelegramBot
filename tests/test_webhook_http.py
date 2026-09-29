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

import pytest

import api.webhook as webhook_module
import database as database_module
from api.webhook import handler


@pytest.fixture(autouse=True)
def reset_login_throttle(monkeypatch):
    monkeypatch.setattr(webhook_module, "_login_failures", {})


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


def _basic_auth(password):
    return "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()


def test_notification_routes_require_auth_and_sync_reads(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "notification-test")
    token = webhook_module.dashboard_write_token()
    auth = _basic_auth("notification-test")
    with running_server() as base_url:
        for path in ("/admin/api/notifications", "/admin/api/notifications/config"):
            try:
                urlopen(base_url + path, timeout=5)
                raise AssertionError("Expected authentication error")
            except HTTPError as exc:
                assert exc.code == 401
        request = Request(base_url + "/admin/api/notifications", data=json.dumps({"action": "read", "ids": ["order:123"]}).encode(),
                          headers={"Content-Type": "application/json", "X-Dashboard-Write-Token": token, "Authorization": auth}, method="POST")
        with urlopen(request, timeout=5) as response:
            assert json.load(response)["ok"]
        request = Request(base_url + "/admin/api/notifications", headers={"Authorization": auth})
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
            assert "order:123" in result["read_ids"]
            assert response.headers["Cache-Control"] == "no-store"
            assert result["poll_after_seconds"] == 5
        # Cookie/Basic authentication alone must not permit cross-site writes.
        basic = base64.b64encode(b"admin:notification-test").decode()
        request = Request(base_url + "/admin/api/notifications", data=b'{"action":"read","ids":[]}',
                          headers={"Content-Type": "application/json", "Authorization": "Basic " + basic}, method="POST")
        try:
            urlopen(request, timeout=5)
            raise AssertionError("Expected CSRF protection")
        except HTTPError as exc:
            assert exc.code == 403


def test_notification_worker_served_with_correct_scope_and_no_cache():
    with running_server() as base_url, urlopen(base_url + "/admin/notification-sw.js", timeout=5) as response:
        assert response.headers["Service-Worker-Allowed"] == "/admin"
        assert response.headers["Cache-Control"] == "no-cache"
        assert "javascript" in response.headers["Content-Type"]
        assert b'notificationclick' in response.read()


def test_web_app_manifest_is_revalidated_for_ios_updates():
    with running_server() as base_url, urlopen(base_url + "/admin-v2/manifest.webmanifest", timeout=5) as response:
        manifest = json.load(response)
        assert response.headers["Cache-Control"] == "no-cache"
        assert manifest["display"] == "standalone"
        assert manifest["scope"] == "/admin"


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


def test_binance_wallet_endpoint_is_authenticated_and_never_cached(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    monkeypatch.setattr(
        webhook_module.binance_dashboard_service,
        "snapshot",
        lambda **kwargs: {"ok": True, "days": kwargs["days"], "balances": [], "transactions": []},
    )
    with running_server() as base_url:
        try:
            urlopen(f"{base_url}/admin/api/binance-wallet", timeout=5)
            raise AssertionError("Expected authentication error")
        except HTTPError as exc:
            assert exc.code == 401

        encoded = base64.b64encode(b"admin:secret").decode()
        request = Request(
            f"{base_url}/admin/api/binance-wallet?days=30",
            headers={"Authorization": f"Basic {encoded}"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert payload == {"ok": True, "days": 30, "balances": [], "transactions": []}


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
            "X-Dashboard-Write-Token": webhook_module.dashboard_write_token(),
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


def test_react_admin_order_detail_route_serves_spa(monkeypatch):
    monkeypatch.setattr("api.webhook.DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    request = Request(
        "http://placeholder/admin/orders/598",
        headers={"Authorization": f"Basic {encoded}"},
    )
    with running_server() as base_url:
        request.full_url = f"{base_url}/admin/orders/598"
        with urlopen(request, timeout=5) as response:
            body = response.read().decode()

    assert response.status == 200
    assert '<div id="root"></div>' in body


def test_react_finance_deep_link_serves_spa(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    encoded = base64.b64encode(b"admin:secret").decode()
    with running_server() as base_url:
        request = Request(
            f"{base_url}/admin/finance",
            headers={"Authorization": f"Basic {encoded}"},
        )
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


def test_finance_endpoint_is_authenticated_and_returns_calendar(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    mock_mongodb.orders.insert_one({
        "id": 501, "user_id": 42, "status": "delivered", "total_price": 9,
        "created_at": 1788350400,  # 2026-09-02 12:00 UTC
    })
    with running_server() as base_url:
        try:
            urlopen(f"{base_url}/admin/api/finance?month=2026-09", timeout=5)
            raise AssertionError("Expected authentication error")
        except HTTPError as exc:
            assert exc.code == 401
        encoded = base64.b64encode(b"admin:secret").decode()
        request = Request(
            f"{base_url}/admin/api/finance?month=2026-09",
            headers={"Authorization": f"Basic {encoded}"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)

    assert response.status == 200
    assert payload["month"] == "2026-09"
    assert payload["totals"]["revenue"] == 9
    assert next(day for day in payload["days"] if day["date"] == "2026-09-02")["orders"] == 1


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


def _catalog_action(base_url, token, values):
    request = Request(base_url + "/admin", data=urlencode(values).encode(), headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Dashboard-Write-Token": token,
        "Authorization": _basic_auth(webhook_module.DASHBOARD_PASSWORD),
    }, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def test_catalog_edit_preserves_existing_delivery_contracts(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "catalog-test")
    token = webhook_module.dashboard_write_token()
    sid = database_module.add_service("Formats", "🎬", suffix_emoji="⭐", sales_channels=["bot", "api"])
    formats = [
        {"manual_stock": True, "auto_delivery": False, "stock": 8},
        {"unlimited_stock": True},
        {"method_media": [{"type": "document", "file_id": "telegram-file"}], "unlimited_stock": True},
        {"feature_key": "bot_like_mine", "delivery_url": "https://github.com/example/bot", "benefits_document_file_id": "doc"},
        {"supplier_provider": "vex", "supplier_product_id": "external-1"},
    ]
    with running_server() as base_url:
        for extra in formats:
            oid = database_module.add_offer(sid, "Original", 2, 0, custom_emoji_id="123456", sales_channels=["bot", "api"])
            mock_mongodb.offers.update_one({"id": oid}, {"$set": extra})
            result = _catalog_action(base_url, token, {
                "action": "update_offer", "offer_id": oid, "name": "Renamed", "price": "3",
                "auto_delivery": "" if extra.get("auto_delivery") is False else "on",
                "period_value": "3", "period_unit": "months", "warranty_value": "1", "warranty_unit": "years",
            })
            assert result["ok"]
            saved = database_module.get_offer(oid)
            assert saved["name"] == "Renamed"
            assert saved["price"] == 3
            assert saved["sales_channels"] == ["bot", "api"]
            assert saved["custom_emoji_id"] == "123456"
            assert saved["period_days"] == 90
            assert saved["warranty_days"] == 365
            for key, value in extra.items():
                assert saved[key] == value
        assert _catalog_action(base_url, token, {"action": "update_service", "service_id": sid, "name": "Renamed collection"})["ok"]
    service = database_module.get_service(sid)
    assert service["emoji"] == "🎬"
    assert service["suffix_emoji"] == "⭐"
    assert service["sales_channels"] == ["bot", "api"]


def test_invalid_initial_inventory_does_not_create_a_catalog_item(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "catalog-test")
    before = mock_mongodb.offers.count_documents({})
    with running_server() as base_url:
        try:
            _catalog_action(base_url, webhook_module.dashboard_write_token(), {
                "action": "add_offer", "name": "Invalid import", "price": "2", "initial_inventory": "#1\npassword",
            })
        except HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("Malformed inventory was accepted")
    assert mock_mongodb.offers.count_documents({}) == before
    assert mock_mongodb.services.count_documents({"name": "Catalogue"}) == 0


def test_catalog_name_edit_preserves_legacy_and_advanced_settings(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "catalog-test")
    sid = database_module.add_service("Legacy", "")
    oid = database_module.add_offer(sid, "Original", 10, 0, "6 months", auto_delivery=False)
    advanced = {"description": "Full description", "period_value": 3, "period_unit": "months", "period_days": 90,
                "warranty_value": 6, "warranty_unit": "months", "warranty_days": 180,
                "name_ar": "منتج", "description_ar": "وصف", "low_stock_threshold": 9,
                "bulk_quantity": 10, "bulk_unit_price": 8, "delivery_delay": "2 hours", "sort_order": 7}
    mock_mongodb.offers.update_one({"id": oid}, {"$set": advanced})
    with running_server() as base_url:
        assert _catalog_action(base_url, webhook_module.dashboard_write_token(), {"action": "update_offer", "offer_id": oid, "name": "Renamed"})["ok"]
    saved = database_module.get_offer(oid)
    assert saved["note"] == "6 months"
    assert saved["auto_delivery"] is False
    assert saved["price"] == 10
    for key, value in advanced.items():
        assert saved[key] == value


def _status(opener, request):
    try:
        with opener(request, timeout=5) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def test_write_token_alone_does_not_authenticate(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    token = webhook_module.dashboard_write_token()
    with running_server() as base_url:
        read = Request(base_url + "/admin/api/data", headers={"X-Dashboard-Write-Token": token})
        assert _status(urlopen, read) == 401
        write = Request(base_url + "/admin", data=b"action=save_settings", method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded", "X-Dashboard-Write-Token": token,
        })
        assert _status(urlopen, write) == 401


def test_admin_actions_require_session_bound_write_token(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with running_server() as base_url:
        login = Request(base_url + "/admin/api/login", method="POST",
                        data=json.dumps({"username": "admin", "password": "secret"}).encode(),
                        headers={"Content-Type": "application/json"})
        with opener.open(login, timeout=5):
            pass
        with opener.open(base_url + "/admin/api/data", timeout=5) as response:
            session_token = json.load(response)["dashboard_write_token"]
        assert session_token and session_token != webhook_module.dashboard_write_token()

        def action(token):
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            if token is not None:
                headers["X-Dashboard-Write-Token"] = token
            return Request(base_url + "/admin", data=b"action=unknown_action", method="POST", headers=headers)

        assert _status(opener.open, action(None)) == 403
        assert _status(opener.open, action(webhook_module.dashboard_write_token())) == 403
        assert _status(opener.open, action(session_token)) != 403


def test_login_is_throttled_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "secret")

    def login(password):
        return Request(base_url + "/admin/api/login", method="POST",
                       data=json.dumps({"username": "admin", "password": password}).encode(),
                       headers={"Content-Type": "application/json"})

    with running_server() as base_url:
        for _ in range(webhook_module.LOGIN_MAX_FAILURES_PER_IP):
            assert _status(urlopen, login("wrong")) == 401
        assert _status(urlopen, login("wrong")) == 429
        assert _status(urlopen, login("secret")) == 429


def test_login_throttle_expires_and_is_per_ip():
    webhook_module._login_failures.clear()
    for _ in range(webhook_module.LOGIN_MAX_FAILURES_PER_IP):
        webhook_module.record_login_failure("1.1.1.1", now=1_000)
    assert webhook_module.login_retry_after("1.1.1.1", now=1_001) > 0
    assert webhook_module.login_retry_after("2.2.2.2", now=1_001) == 0
    later = 1_000 + webhook_module.LOGIN_FAILURE_WINDOW_SECONDS + 1
    assert webhook_module.login_retry_after("1.1.1.1", now=later) == 0


def test_site_orders_admin_lists_and_processes_storefront_carts(monkeypatch, mock_mongodb, site_customer):
    from app.domain import storefront_service
    from tests.conftest import RECEIPT

    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "site-test")
    token = webhook_module.dashboard_write_token()
    sid = database_module.add_service("Netflix", "🎬", sales_channels=["bot", "tn_site"])
    oid = database_module.add_offer(sid, "Netflix 1 mois", 6.0, 3, sales_channels=["bot", "tn_site"], tn_price_millimes=15000)
    cart = storefront_service.create_order({
        "payment_method": "d17", "transaction_reference": "D17-123456", "receipt": RECEIPT,
        "items": [{"offer_id": oid, "quantity": 1}],
    }, site_customer(name="Sana", email="sana@example.com"))
    reference = cart["reference"]

    with running_server() as base_url:
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(f"{base_url}/admin/api/site-orders", timeout=5)
        assert unauthorized.value.code == 401

        request = Request(f"{base_url}/admin/api/site-orders?status=to_verify", headers={"Authorization": _basic_auth("site-test")})
        with urlopen(request, timeout=5) as response:
            listed = json.load(response)
        assert [item["reference"] for item in listed["items"]] == [reference]
        receipt_id = listed["items"][0]["receipt_id"]

        with pytest.raises(HTTPError) as hidden:
            urlopen(f"{base_url}/admin/api/site-receipt?id={receipt_id}", timeout=5)
        assert hidden.value.code == 401
        receipt = Request(f"{base_url}/admin/api/site-receipt?id={receipt_id}", headers={"Authorization": _basic_auth("site-test")})
        with urlopen(receipt, timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG")

        with urlopen(f"{base_url}/admin/site-orders", timeout=5) as response:
            assert '<div id="root">' in response.read().decode()

        confirmed = _catalog_action(base_url, token, {"action": "site_cart_confirm", "reference": reference})
        assert confirmed == {"ok": True, "message": f"Paiement du panier {reference} confirmé. 1 article(s) à livrer manuellement."}
        with pytest.raises(HTTPError) as empty:
            _catalog_action(base_url, token, {"action": "site_cart_deliver", "reference": reference, "note": ""})
        assert "Saisis les accès" in json.load(empty.value)["error"]
        delivered = _catalog_action(base_url, token, {"action": "site_cart_deliver", "reference": reference, "note": "Envoyé"})
        assert delivered["ok"] is True

        with pytest.raises(HTTPError) as rejected:
            _catalog_action(base_url, token, {"action": "site_cart_cancel", "reference": reference, "reason": "x"})
        assert rejected.value.code == 400
        assert "ne peut plus être annulé" in json.load(rejected.value)["error"]

    assert database_module.get_offer(oid)["stock"] == 2
    assert {row["status"] for row in mock_mongodb.orders.find({"cart_reference": reference})} == {"delivered"}


def test_storefront_wallet_deposit_then_wallet_checkout_end_to_end(monkeypatch, mock_mongodb, site_customer):
    from app.domain import inventory_service, storefront_auth_service
    from tests.conftest import RECEIPT

    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "site-test")
    admin_token = webhook_module.dashboard_write_token()
    sid = database_module.add_service("Netflix", "🎬", sales_channels=["bot", "tn_site"])
    oid = database_module.add_offer(sid, "Netflix 1 mois", 6.0, 0, sales_channels=["bot", "tn_site"], tn_price_millimes=15000)
    inventory_service.add_items(oid, ["netflix@mail.tn:secret"])
    customer = site_customer(name="Sana", email="sana@example.com")
    session = storefront_auth_service._open_session(customer)["token"]

    def storefront(base_url, path, payload=None, token=session):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"{base_url}{path}", data=data, method="POST" if data else "GET", headers=headers)
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    with running_server() as base_url:
        order = {"payment_method": "wallet", "items": [{"offer_id": oid, "quantity": 1}]}
        with pytest.raises(HTTPError) as anonymous:
            storefront(base_url, "/api/storefront/orders", order, token=None)
        assert anonymous.value.code == 401
        with pytest.raises(HTTPError) as short:
            storefront(base_url, "/api/storefront/orders", order)
        assert "Solde insuffisant" in json.load(short.value)["error"]

        deposit = storefront(base_url, "/api/storefront/auth/deposits", {
            "method": "d17", "amount": "20", "transaction_reference": "D17-990011", "receipt": RECEIPT,
        })["deposit"]
        assert deposit["status"] == "pending"

        approved = _catalog_action(base_url, admin_token, {"action": "site_deposit_approve", "deposit_id": str(deposit["id"]), "amount": ""})
        assert approved["message"] == f"Recharge #{deposit['id']} validée : 20.000 DT crédités."
        assert storefront(base_url, "/api/storefront/auth/wallet")["balance_millimes"] == 20000

        paid = storefront(base_url, "/api/storefront/orders", order)
        assert paid["status"] == "delivered"
        assert paid["balance_millimes"] == 5000

        (history,) = storefront(base_url, "/api/storefront/auth/orders")["orders"]
        assert history["reference"] == paid["reference"]
        assert history["items"][0]["delivery"] == "netflix@mail.tn:secret"

        adjusted = _catalog_action(base_url, admin_token, {
            "action": "site_wallet_adjust", "customer_id": str(customer["id"]), "amount": "-5", "note": "Correction",
        })
        assert adjusted["message"] == "Solde mis à jour : 0.000 DT."


def test_site_admin_space_edits_catalog_and_settings(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "site-test")
    token = webhook_module.dashboard_write_token()
    sid = database_module.add_service("Canva", "🎨", sales_channels=["bot"])
    oid = database_module.add_offer(sid, "Canva Pro", 2.0, 5, sales_channels=["bot"])
    auth = {"Authorization": _basic_auth("site-test")}

    def get(base_url, path):
        with urlopen(Request(f"{base_url}{path}", headers=auth), timeout=5) as response:
            return json.load(response)

    with running_server() as base_url:
        for path in ("site-overview", "site-catalog", "site-customers", "site-settings"):
            with pytest.raises(HTTPError) as unauthorized:
                urlopen(f"{base_url}/admin/api/{path}", timeout=5)
            assert unauthorized.value.code == 401
            with urlopen(f"{base_url}/admin/{path}", timeout=5) as response:
                assert '<div id="root">' in response.read().decode()

        listed = get(base_url, "/admin/api/site-catalog?status=no_price")
        assert [row["id"] for row in listed["items"]] == [oid]

        updated = _catalog_action(base_url, token, {
            "action": "site_offer_update", "offer_id": str(oid), "tn_price": "12,500",
            "site_enabled": "1", "site_featured": "1", "site_badge": "Promo", "site_category": "design",
        })
        assert updated["ok"] is True
        assert get(base_url, "/admin/api/site-catalog?status=on_sale")["items"][0]["tn_price_millimes"] == 12500

        service = _catalog_action(base_url, token, {"action": "site_service_save", "name": "Spotify", "emoji": "🎧"})
        assert service["message"] == "Service « Spotify » créé."
        product = _catalog_action(base_url, token, {
            "action": "site_offer_save", "service_id": str(service["service_id"]),
            "name": "Spotify Premium", "tn_price": "9", "price": "2,5",
        })
        assert product["message"] == "Produit « Spotify Premium » créé."
        on_sale = {row["id"] for row in get(base_url, "/admin/api/site-catalog?status=on_sale")["items"]}
        assert product["offer_id"] in on_sale

        logo = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        _catalog_action(base_url, token, {
            "action": "site_service_save", "service_id": str(service["service_id"]), "name": "Spotify",
            "logo": "data:image/png;base64," + base64.b64encode(logo).decode(),
        })
        (spotify,) = [row for row in get(base_url, "/admin/api/site-catalog")["services"] if row["name"] == "Spotify"]
        with urlopen(f"{base_url}{spotify['logo_url']}", timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == logo

        saved = _catalog_action(base_url, token, {
            "action": "site_settings_save", "tnd_per_usdt": "3,4",
            "payment_flouci": "1", "details_flouci": "Flouci : 55 000 000",
        })
        assert saved["ok"] is True
        settings = get(base_url, "/admin/api/site-settings")
        assert settings["payment_methods"] == ["flouci"]
        assert settings["payment_details"]["flouci"] == "Flouci : 55 000 000"

        with pytest.raises(HTTPError) as rejected:
            _catalog_action(base_url, token, {"action": "site_settings_save", "tnd_per_usdt": "3"})
        assert rejected.value.code == 400
        assert "moyen de paiement" in json.load(rejected.value)["error"]

        overview = get(base_url, "/admin/api/site-overview")
        assert overview["catalog"]["on_sale"] == 2
