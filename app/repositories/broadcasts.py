"""Telegram broadcasts: recipients, ``broadcast_jobs`` and the ``broadcast_messages`` they sent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.repositories._mongo import conn, next_id, public

CATALOG_UPDATE_BROADCAST_KINDS = {
    "stock", "restock_digest", "flash_sale", "api_flash_sale",
    "supplier_price_update",
}


def list_broadcast_users(*, catalog_updates_only=False, catalog_offer_id=None):
    """Return every active bot user eligible for private announcements."""
    query = {
        "telegram_id": {"$exists": True},
        "banned": {"$ne": True},
        "broadcast_blocked": {"$ne": True},
    }
    if catalog_updates_only:
        # Missing means enabled so customers created before this option stay opted in.
        query["catalog_notifications_enabled"] = {"$ne": False}
        if catalog_offer_id is not None:
            query["catalog_notification_disabled_offer_ids"] = {
                "$ne": int(catalog_offer_id),
            }
    return [
        public(row)
        for row in conn().users.find(
            query,
            {"telegram_id": 1, "lang": 1},
        )
    ]


def create_broadcast_job(kind, payload, *, dedupe_key=""):
    """Persist a Telegram broadcast before a background worker starts it."""
    kind = str(kind or "")[:60]
    payload = dict(payload or {})
    dedupe_key = str(dedupe_key or "").strip()[:240]
    if dedupe_key:
        existing = conn().broadcast_jobs.find_one({"dedupe_key": dedupe_key})
        if existing:
            return public(existing), False
    recipient_query = {
        "telegram_id": {"$exists": True},
        "banned": {"$ne": True},
        "broadcast_blocked": {"$ne": True},
    }
    if kind in CATALOG_UPDATE_BROADCAST_KINDS:
        recipient_query["catalog_notifications_enabled"] = {"$ne": False}
        offer_id = payload.get("offer_id")
        if kind in {"api_flash_sale", "supplier_price_update"}:
            offer_id = (payload.get("event") or {}).get("offer_id")
        if offer_id is not None:
            recipient_query["catalog_notification_disabled_offer_ids"] = {
                "$ne": int(offer_id),
            }
    job = {
        "id": next_id("broadcast_jobs"),
        "kind": kind,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "recipient_count": conn().users.count_documents(recipient_query),
        "sent_count": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if dedupe_key:
        job["dedupe_key"] = dedupe_key
    try:
        conn().broadcast_jobs.insert_one(job)
    except DuplicateKeyError:
        existing = conn().broadcast_jobs.find_one({"dedupe_key": dedupe_key})
        return public(existing), False
    return public(job), True


def claim_broadcast_job(job_id):
    row = conn().broadcast_jobs.find_one_and_update(
        {"id": int(job_id), "status": {"$in": ["queued", "retry"]}, "attempts": {"$lt": 3}},
        {"$set": {"status": "running", "started_at": datetime.now(UTC), "updated_at": datetime.now(UTC)}, "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return public(row)


def complete_broadcast_job(job_id, sent_count):
    conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": "completed", "sent_count": int(sent_count), "completed_at": datetime.now(UTC), "updated_at": datetime.now(UTC), "error": ""}},
    )


def record_broadcast_message(job_id, kind, chat_id, message_id):
    """Remember one bot-authored broadcast message so it can be deleted later."""
    if not job_id or not chat_id or not message_id:
        return False
    conn().broadcast_messages.update_one(
        {
            "job_id": int(job_id),
            "chat_id": int(chat_id),
            "message_id": int(message_id),
        },
        {"$setOnInsert": {
            "kind": str(kind or "broadcast")[:60],
            "deleted": False,
            "created_at": datetime.now(UTC),
        }},
        upsert=True,
    )
    return True


def list_broadcast_messages(job_id, active_only=True):
    query = {"job_id": int(job_id)}
    if active_only:
        query["deleted"] = {"$ne": True}
    return [
        public(row) for row in conn().broadcast_messages.find(query)
    ]


def mark_broadcast_message_deleted(job_id, chat_id, message_id, *, error=""):
    values = {
        "delete_error": str(error or "")[:300],
        "delete_attempted_at": datetime.now(UTC),
    }
    if not error:
        values.update({"deleted": True, "deleted_at": datetime.now(UTC)})
    conn().broadcast_messages.update_one(
        {
            "job_id": int(job_id),
            "chat_id": int(chat_id),
            "message_id": int(message_id),
        },
        {"$set": values},
    )


def get_broadcast_job(job_id):
    return public(conn().broadcast_jobs.find_one({"id": int(job_id)}))


def set_broadcast_deletion_status(job_id, status, *, deleted_count=0, failed_count=0):
    conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {
            "deletion_status": str(status),
            "deleted_count": int(deleted_count),
            "delete_failed_count": int(failed_count),
            "deletion_updated_at": datetime.now(UTC),
        }},
    )


def list_broadcast_history(limit=20):
    """Return recent customer announcements that still have tracked messages."""
    kinds = [
        "stock", "restock_digest", "flash_sale", "api_flash_sale",
        "supplier_price_update", "admin_message", "maintenance",
        "affiliate_update",
    ]
    jobs = conn().broadcast_jobs.find({
        "kind": {"$in": kinds},
        "status": "completed",
    }).sort("created_at", DESCENDING).limit(max(1, int(limit) * 3))
    history = []
    for raw in jobs:
        job = public(raw)
        total = conn().broadcast_messages.count_documents({"job_id": job["id"]})
        if not total:
            continue
        active = conn().broadcast_messages.count_documents({
            "job_id": job["id"], "deleted": {"$ne": True},
        })
        job["tracked_count"] = total
        job["active_message_count"] = active
        history.append(job)
        if len(history) >= int(limit):
            break
    return history


def fail_broadcast_job(job_id, error):
    row = conn().broadcast_jobs.find_one({"id": int(job_id)}, {"attempts": 1}) or {}
    status = "retry" if int(row.get("attempts") or 0) < 3 else "failed"
    conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": status, "error": str(error or "")[:500], "updated_at": datetime.now(UTC)}},
    )
    return status


def pending_broadcast_jobs(limit=20):
    # A deployment can stop while a worker is sending. Make abandoned jobs
    # eligible for retry on the next bot startup.
    conn().broadcast_jobs.update_many(
        {"status": "running", "started_at": {"$lt": datetime.now(UTC) - timedelta(minutes=10)}},
        {"$set": {"status": "retry", "updated_at": datetime.now(UTC)}},
    )
    return [
        public(row) for row in conn().broadcast_jobs.find(
            {"status": {"$in": ["queued", "retry"]}, "attempts": {"$lt": 3}},
        ).sort("created_at", ASCENDING).limit(max(1, int(limit)))
    ]


def mark_broadcast_blocked(user_id, blocked=True):
    conn().users.update_one(
        {"telegram_id": int(user_id)},
        {"$set": {"broadcast_blocked": bool(blocked)}},
    )
