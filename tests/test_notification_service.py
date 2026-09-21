import base64
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

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
    assert json.loads(captured[0]["data"])["url"] == "/admin/orders"
    def expired(**kwargs):
        raise pywebpush.WebPushException("gone", response=SimpleNamespace(status_code=410))
    monkeypatch.setattr(pywebpush, "webpush", expired)
    assert not service._send(device, event())
    assert mock_mongodb.admin_push_devices.count_documents({}) == 0


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
