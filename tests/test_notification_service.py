import base64
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import database as db
from app.web import dashboard_api
from app.web import notification_service as service


def subscription(endpoint="https://fcm.googleapis.com/fcm/send/test-device"):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
    )
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")
    return {"endpoint": endpoint, "keys": {"p256dh": encode(key), "auth": encode(b"0123456789abcdef")}}


def event(id="order:42:paid", category="order", severity="warning"):
    return {"id": id, "title": "Commande", "message": "Client privé", "category": category,
            "severity": severity, "target": {"page": "orders"}}


def test_keys_persist_and_public_config_never_leaks_private_key():
    from py_vapid import Vapid
    pair = service._keypair()
    assert service._keypair() == pair
    assert "private" not in service.push_config()
    assert service.push_config()["public_key"] == pair["public"]
    assert Vapid.from_string(pair["private"]).public_key


@pytest.mark.parametrize("endpoint", ["http://fcm.googleapis.com/test", "https://localhost/test", "https://127.0.0.1/test",
    "https://fcm.googleapis.com.evil.test/test", "https://fcm.googleapis.com:444/test", "https://user@fcm.googleapis.com/test"])
def test_rejects_unsafe_endpoints(endpoint):
    with pytest.raises(ValueError):
        service.validate_subscription(subscription(endpoint))


def test_read_state_shared_and_bounded():
    service.device_action({"action": "read", "ids": ["order:1", "order:2"]})
    service.device_action({"action": "read", "ids": ["order:2", "order:3"]})
    assert set(service.read_ids()) == {"order:1", "order:2", "order:3"}
    with pytest.raises(ValueError):
        service.device_action({"action": "read", "ids": ["x"] * 201})


def test_delete_all_hides_current_notifications_and_blocks_push_delivery(monkeypatch):
    items = [event("old"), event("keep")]
    service.device_action({"action": "delete_all", "ids": ["old"]})
    assert service.dismissed_ids() == ["old"]
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    sub = subscription()
    service.device_action({"action": "subscribe", "subscription": sub})
    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    items.append(event("new"))

    service.deliver_pending()

    assert sent == ["new"]


def test_delivery_deduplicates_baseline_and_retries_failure(monkeypatch, mock_mongodb):
    items = [event("old")]
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    sub = subscription()
    service.device_action({"action": "subscribe", "subscription": sub})
    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or False)
    service.deliver_pending()
    assert sent == []
    items.append(event("new"))
    service.deliver_pending()
    assert sent == ["new"]
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    service.deliver_pending()
    service.deliver_pending()
    assert sent == ["new", "new"]
    assert mock_mongodb.admin_push_devices.find_one()["lease_until"] == 0


def test_device_preferences_pause_and_no_replay(monkeypatch):
    items = []
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    sub = subscription()
    preferences = {"categories": ["support"], "urgent_only": True, "pause_minutes": 60}
    service.device_action({"action": "subscribe", "subscription": sub, "preferences": preferences})
    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    items.append(event("paused", "support", "error"))
    service.deliver_pending()
    preferences["pause_minutes"] = 0
    service.device_action({"action": "subscribe", "subscription": sub, "preferences": preferences})
    items.extend([event("wrong-category"), event("not-critical", "support"), event("urgent", "support", "error")])
    service.deliver_pending()
    assert sent == ["urgent"]
    service.device_action({"action": "disable", "subscription": sub})
    assert not service.device_action({"action": "status", "subscription": sub})["enabled"]


def test_delivery_to_two_devices_and_auth_rotation(monkeypatch):
    items = []
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    for name in ("pc", "phone"):
        service.device_action({"action": "subscribe", "subscription": subscription(f"https://fcm.googleapis.com/{name}")})
    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(device["_id"]) or True)
    items.append(event())
    service.deliver_pending()
    assert len(set(sent)) == 2
    monkeypatch.setattr(service, "DASHBOARD_PASSWORD", "rotated-password")
    items.append(event("second"))
    service.deliver_pending()
    assert len(sent) == 2


def test_push_payload_privacy_and_expired_subscription(monkeypatch, mock_mongodb):
    import pywebpush
    captured = []
    monkeypatch.setattr(pywebpush, "webpush", lambda **kwargs: captured.append(kwargs))
    sub = subscription()
    device = {"_id": "device", "subscription": sub, "preferences": {"private": True}}
    mock_mongodb.admin_push_devices.insert_one(device.copy())
    assert service._send(device, event())
    assert "Client privé" not in captured[0]["data"]
    payload = json.loads(captured[0]["data"])
    assert payload["web_push"] == 8030
    assert payload["notification"]["navigate"].endswith("/admin/orders")
    assert payload["notification"]["data"]["url"] == "/admin/orders"
    assert payload["notification"]["mutable"] is True
    assert payload["notification"]["app_badge"] == 1
    assert captured[0]["ttl"] == 86400
    assert captured[0]["headers"]["Urgency"] == "high"
    assert len(captured[0]["headers"]["Topic"]) == 32
    assert mock_mongodb.admin_push_devices.find_one()["last_sent_at"] > 0
    def expired(**kwargs):
        raise pywebpush.WebPushException("gone", response=SimpleNamespace(status_code=410))
    monkeypatch.setattr(pywebpush, "webpush", expired)
    assert not service._send(device, event())
    assert mock_mongodb.admin_push_devices.count_documents({}) == 0


def test_subscription_keeps_admin_origin_for_background_navigation(monkeypatch, mock_mongodb):
    monkeypatch.setattr(service, "DASHBOARD_PASSWORD", "secret")
    sub = subscription("https://web.push.apple.com/device-token")

    service.device_action({
        "action": "subscribe",
        "subscription": sub,
        "app_origin": "https://admin.example.com",
    })

    device = mock_mongodb.admin_push_devices.find_one()
    assert device["app_origin"] == "https://admin.example.com"

    result = service.device_action({"action": "status", "subscription": sub})
    assert result["diagnostics"]["provider"] == "Apple Push"


def test_order_push_opens_the_full_order_page(monkeypatch, mock_mongodb):
    import pywebpush

    captured = []
    monkeypatch.setattr(pywebpush, "webpush", lambda **kwargs: captured.append(kwargs))
    device = {"_id": "device", "subscription": subscription(), "preferences": {"private": False}}
    item = event()
    item["target"]["entity_id"] = 598

    assert service._send(device, item)

    payload = json.loads(captured[0]["data"])["notification"]
    assert payload["navigate"].endswith("/admin/orders/598")
    assert payload["data"]["url"] == "/admin/orders/598"


def test_configured_admin_origin_rejects_another_origin(monkeypatch):
    monkeypatch.setenv("HP_ADMIN_BASE_URL", "https://admin.example.com")

    with pytest.raises(ValueError):
        service.device_action({
            "action": "subscribe",
            "subscription": subscription(),
            "app_origin": "https://attacker.example",
        })


def test_active_lease_prevents_duplicate_worker(monkeypatch, mock_mongodb):
    items = []
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    service.device_action({"action": "subscribe", "subscription": subscription()})
    mock_mongodb.admin_push_devices.update_one({}, {"$set": {"lease_until": int(time.time()) + 60}})
    items.append(event())
    sent = []
    monkeypatch.setattr(service, "_send", lambda *args: sent.append(args))
    service.deliver_pending()
    assert not sent


def test_withdrawal_created_and_resolved_between_scans_is_delivered(monkeypatch, mock_mongodb):
    service.device_action({"action": "subscribe", "subscription": subscription()})
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 5000})
    withdrawal = db.create_withdrawal(42, 10, "USDT", "destination")
    assert db.update_withdrawal(withdrawal["id"], "completed")
    assert not any(item["id"] == f'withdrawal:{withdrawal["id"]}:pending'
                   for item in dashboard_api.list_admin_notifications()["items"])

    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    service.deliver_pending()
    service.deliver_pending()

    assert sent == [f'withdrawal:{withdrawal["id"]}:pending']


def test_transient_alert_retries_from_outbox_after_feed_changes(monkeypatch, mock_mongodb):
    for endpoint in ("pc", "phone"):
        service.device_action({"action": "subscribe", "subscription": subscription(f"https://fcm.googleapis.com/{endpoint}")})
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 5000})
    withdrawal = db.create_withdrawal(42, 10, "USDT", "destination")
    db.update_withdrawal(withdrawal["id"], "completed")

    attempts = []
    def send(device, item):
        attempts.append((device["_id"], item["id"]))
        return len(attempts) != 1
    monkeypatch.setattr(service, "_send", send)
    service.deliver_pending()
    service.deliver_pending()
    service.deliver_pending()

    alert_id = f'withdrawal:{withdrawal["id"]}:pending'
    assert len(attempts) == 3
    assert [item_id for _, item_id in attempts] == [alert_id] * 3
    assert len({device_id for device_id, _ in attempts}) == 2


def test_order_status_transition_between_scans_keeps_alert(monkeypatch, mock_mongodb):
    service.device_action({"action": "subscribe", "subscription": subscription()})
    mock_mongodb.orders.insert_one({
        "id": 84, "user_id": 42, "status": "awaiting_verification",
        "offer_name": "Example", "created_at": int(time.time()),
    })
    db.update_order(84, status="manual_review")
    db.update_order(84, status="cancelled")

    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    service.deliver_pending()

    assert sent == ["order:84:manual_review"]


def test_alert_created_during_pause_is_not_replayed_after_pause_ends(monkeypatch, mock_mongodb):
    sub = subscription()
    service.device_action({"action": "subscribe", "subscription": sub,
                           "preferences": {"pause_minutes": 60}})
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 5000})
    db.create_withdrawal(42, 10, "USDT", "destination")
    service.device_action({"action": "subscribe", "subscription": sub,
                           "preferences": {"pause_minutes": 0}})

    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    service.deliver_pending()

    assert sent == []


def test_payment_confirmed_then_delivered_before_scan_keeps_both_events(monkeypatch, mock_mongodb):
    service.device_action({"action": "subscribe", "subscription": subscription()})
    mock_mongodb.orders.insert_one({
        "id": 85, "user_id": 42, "status": "awaiting_verification",
        "offer_name": "Example", "qty": 1, "total_price": 10,
        "created_at": int(time.time()),
    })
    assert db.mark_order_paid(85, "manual")
    db.update_order(85, status="delivered")

    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)
    service.deliver_pending()

    assert "order:85:payment_confirmed" in sent
    assert "order:85:delivered" in sent


def test_write_time_capture_is_not_limited_to_dashboard_page(mock_mongodb):
    service.device_action({"action": "subscribe", "subscription": subscription()})
    now = int(time.time())
    mock_mongodb.withdrawals.insert_many([
        {"id": index, "user_id": 42, "amount_cents": 1000,
         "method": "USDT", "status": "pending", "created_at": now + index}
        for index in range(35)
    ])
    assert len([item for item in dashboard_api.list_admin_notifications()["items"]
                if item["category"] == "withdrawal"]) == 30
    db.audit_event("withdrawal.created")
    assert mock_mongodb.admin_notification_outbox.count_documents({
        "item.category": "withdrawal",
    }) == 35


def test_existing_device_seen_ids_are_respected_during_queue_migration(monkeypatch, mock_mongodb):
    items = [event("existing"), event("new")]
    monkeypatch.setattr(dashboard_api, "list_admin_notifications", lambda *_: {"items": items})
    mock_mongodb.admin_push_devices.insert_one({
        "_id": "old-device", "auth_version": service._auth_version(),
        "seen": ["existing"], "lease_until": 0,
        "preferences": {"categories": ["order"]},
    })
    sent = []
    monkeypatch.setattr(service, "_send", lambda device, item: sent.append(item["id"]) or True)

    service.deliver_pending()
    service.deliver_pending()

    assert sent == ["new"]
