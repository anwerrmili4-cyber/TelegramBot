"""Telegram update dedupe (``processed_updates``) and per-user input state (``pending_states``)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from app.repositories._mongo import conn


def get_pending_state(user_id):
    row = conn().pending_states.find_one({"user_id": user_id})
    return (row["kind"], row["ref"]) if row else None


def set_pending_state(user_id, state):
    kind, ref = state
    conn().pending_states.update_one(
        {"user_id": user_id},
        {"$set": {"kind": kind, "ref": ref, "updated_at": int(time.time())}},
        upsert=True,
    )


def pop_pending_state(user_id, default=None):
    row = conn().pending_states.find_one_and_delete({"user_id": user_id})
    return (row["kind"], row["ref"]) if row else default


def claim_update(update_id):
    """Return False when Telegram retries an update already being processed."""
    try:
        conn().processed_updates.insert_one({"_id": update_id, "created_at": datetime.now(UTC)})
        return True
    except DuplicateKeyError:
        return False


def release_update(update_id):
    conn().processed_updates.delete_one({"_id": update_id})
