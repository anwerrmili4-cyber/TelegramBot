"""Shared admin read state and persistent Web Push delivery for each device."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pymongo import ReturnDocument
from requests import Session
from requests.exceptions import RequestException

import database as db
from config import DASHBOARD_PASSWORD, env_value, public_base_url_from_environment

log = logging.getLogger(__name__)
CATEGORIES = {"order", "sale", "deposit", "support", "withdrawal", "warranty", "stock", "system"}


class _PushSession(Session):
    def request(self, *args, **kwargs):
        kwargs["allow_redirects"] = False
        return super().request(*args, **kwargs)


def _auth_version():
    return hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()


def _keypair():
    collection = db.get_conn().admin_notification_config
    row = collection.find_one({"_id": "vapid"})
    if row:
        return row
    key = ec.generate_private_key(ec.SECP256R1())
    private = base64.urlsafe_b64encode(key.private_numbers().private_value.to_bytes(32, "big")).decode().rstrip("=")
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
    )).decode().rstrip("=")
    collection.update_one({"_id": "vapid"}, {"$setOnInsert": {"private": private, "public": public}}, upsert=True)
    return collection.find_one({"_id": "vapid"})


def push_config():
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return {"available": False, "message": "Le serveur doit installer la dépendance pywebpush puis redémarrer."}
    return {"available": True, "public_key": _keypair()["public"]}


def validate_subscription(value):
    if not isinstance(value, dict):
        raise ValueError("Abonnement invalide.")
    endpoint = value.get("endpoint", "")
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError("Adresse push invalide.")
    url = urlsplit(endpoint)
    host = url.hostname or ""
    allowed = host == "fcm.googleapis.com" or any(
        host == domain or host.endswith("." + domain)
        for domain in ("push.services.mozilla.com", "push.apple.com", "notify.windows.com")
    )
    if url.scheme != "https" or not allowed or url.port not in (None, 443) or url.username or url.password or url.fragment:
        raise ValueError("Service push non pris en charge.")
    keys = value.get("keys")
    if not isinstance(keys, dict):
        raise ValueError("Clés push manquantes.")
    try:
        decoded = {name: base64.b64decode(keys[name] + "=" * (-len(keys[name]) % 4), altchars=b"-_", validate=True) for name in ("p256dh", "auth")}
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded["p256dh"])
        if len(decoded["auth"]) != 16:
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Clés push invalides.") from exc
    return {"endpoint": endpoint, "keys": {name: keys[name] for name in ("p256dh", "auth")}}


def _device_id(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()


def device_action(payload):
    action = payload.get("action")
    if action == "read":
        ids = payload.get("ids")
        if not isinstance(ids, list) or len(ids) > 200 or any(not isinstance(item, str) or len(item) > 300 for item in ids):
            raise ValueError("Liste de notifications invalide.")
        for item in ids:
            db.get_conn().admin_notification_reads.update_one({"_id": item}, {"$set": {"expires_at": datetime.now(UTC) + timedelta(days=30)}}, upsert=True)
        return {"ok": True}
    subscription = validate_subscription(payload.get("subscription"))
    device_id = _device_id(subscription["endpoint"])
    devices = db.get_conn().admin_push_devices
    if action == "disable":
        devices.delete_one({"_id": device_id})
        return {"ok": True}
    if action == "status":
        row = devices.find_one({"_id": device_id, "auth_version": _auth_version()})
        return {"ok": True, "enabled": bool(row), "preferences": row.get("preferences", {}) if row else {}}
    if action == "subscribe":
        preferences = payload.get("preferences", {})
        categories = preferences.get("categories", sorted(CATEGORIES)) if isinstance(preferences, dict) else None
        if not isinstance(categories, list) or any(not isinstance(c, str) or c not in CATEGORIES for c in categories):
            raise ValueError("Catégories invalides.")
        pause = preferences.get("pause_minutes", 0)
        if pause not in (0, 60, 480, 1440):
            raise ValueError("Durée de pause invalide.")
        from app.web.dashboard_api import list_admin_notifications
        baseline = [item["id"] for item in list_admin_notifications(200)["items"]]
        saved_preferences = {"categories": categories, "urgent_only": preferences.get("urgent_only") is True,
                             "private": preferences.get("private", True) is not False,
                             "paused_until": int(time.time()) + pause * 60 if pause else 0}
        devices.update_one({"_id": device_id}, {"$set": {
            "subscription": subscription, "auth_version": _auth_version(), "preferences": saved_preferences,
            "updated_at": int(time.time()),
        }, "$setOnInsert": {"seen": baseline, "lease_until": 0}}, upsert=True)
        return {"ok": True, "preferences": saved_preferences}
    if action == "test":
        row = devices.find_one({"_id": device_id, "auth_version": _auth_version()})
        if not row:
            raise ValueError("Activez d’abord les notifications sur cet appareil.")
        if not _send(row, {"id": "test", "title": "Notifications activées", "message": "Ce téléphone ou PC reçoit les notifications Black Market.", "target": {"page": "overview"}}, test=True):
            raise ValueError("Envoi refusé par le service push. Réactivez les notifications ou réessayez.")
        return {"ok": True, "message": "Test envoyé au service push. Vérifiez les notifications de votre appareil."}
    raise ValueError("Action inconnue.")


def read_ids():
    return [row["_id"] for row in db.get_conn().admin_notification_reads.find({"expires_at": {"$gt": datetime.now(UTC)}})]


def _send(device, item, *, test=False):
    from pywebpush import WebPushException, webpush
    private = device.get("preferences", {}).get("private", True) and not test
    payload = {"id": item["id"], "title": "Black Market · Nouvelle notification" if private else item["title"],
               "body": "Ouvrez le tableau de bord pour consulter les détails." if private else item["message"][:500],
               "url": "/admin/" + item.get("target", {}).get("page", "overview")}
    try:
        with _PushSession() as session:
            response = webpush(subscription_info=device["subscription"], data=json.dumps(payload),
                              vapid_private_key=_keypair()["private"],
                              vapid_claims={"sub": env_value("HP_WEB_PUSH_SUBJECT") or public_base_url_from_environment()},
                              ttl=3600, timeout=10, requests_session=session)
            if response is not None and not 200 <= response.status_code < 300:
                return False
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            db.get_conn().admin_push_devices.delete_one({"_id": device["_id"]})
        log.warning("Admin push delivery failed (HTTP %s)", status)
        return False
    except RequestException:
        log.warning("Admin push provider unreachable; delivery will be retried")
        return False


def deliver_pending():
    """Scan the operational feed once; retain per-device deduplication across restarts."""
    from app.web.dashboard_api import list_admin_notifications
    devices = db.get_conn().admin_push_devices
    if not devices.count_documents({"auth_version": _auth_version()}):
        return
    items = list_admin_notifications(200)["items"]
    for candidate in devices.find({"auth_version": _auth_version()}):
        now = int(time.time())
        device = devices.find_one_and_update({"_id": candidate["_id"], "lease_until": {"$lte": now}},
                                            {"$set": {"lease_until": now + 120}}, return_document=ReturnDocument.AFTER)
        if not device:
            continue
        seen = set(device.get("seen", []))
        preferences = device.get("preferences", {})
        count = 0
        try:
            for item in items:
                if item["id"] in seen:
                    continue
                muted = (preferences.get("paused_until", 0) > now
                         or item["category"] not in preferences.get("categories", CATEGORIES)
                         or preferences.get("urgent_only") and item["severity"] != "error")
                if not muted:
                    if count >= 5:
                        break
                    if not _send(device, item):
                        break
                    count += 1
                devices.update_one({"_id": device["_id"]}, {"$push": {"seen": {"$each": [item["id"]], "$slice": -2000}}})
        finally:
            devices.update_one({"_id": device["_id"]}, {"$set": {"lease_until": 0}})


def worker_loop(stop_event):
    try:
        db.get_conn().admin_notification_reads.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        log.warning("Admin notification read-state index unavailable")
    while not stop_event.is_set():
        try:
            deliver_pending()
        except Exception:
            # Do not log exception strings: push providers may include subscription URLs.
            log.warning("Admin notification scan failed; retrying shortly")
        stop_event.wait(5)
