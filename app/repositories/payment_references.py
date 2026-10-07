"""Atomic claims on bank-transfer references (``payment_reference_claims``)."""

from __future__ import annotations

import base64
import os
import time

from pymongo.errors import DuplicateKeyError

from app.repositories._mongo import conn

PAYMENT_REFERENCE_CLAIM_GRACE_SECONDS = 120


def claim_payment_reference(method, key, still_used):
    """Reserve one transfer reference so concurrent submissions cannot both pass.

    ``still_used`` reports whether a live order or deposit still owns the
    reference. A claim whose stored record was rejected or cancelled is taken
    over, but an unbound claim is respected for a grace period because its
    submission may still be storing the record. Returns a release token, or
    ``None`` when taken.
    """
    claims = conn().payment_reference_claims
    claim_id = f"{method}:{key}"
    token = base64.urlsafe_b64encode(os.urandom(12)).decode()
    now = int(time.time())
    try:
        claims.insert_one({"_id": claim_id, "token": token, "created_at": now})
        return token
    except DuplicateKeyError:
        pass
    existing = claims.find_one({"_id": claim_id})
    if existing is None:
        try:
            claims.insert_one({"_id": claim_id, "token": token, "created_at": now})
            return token
        except DuplicateKeyError:
            return None
    in_flight = not existing.get("bound")
    if in_flight and now - int(existing.get("created_at") or 0) < PAYMENT_REFERENCE_CLAIM_GRACE_SECONDS:
        return None
    if still_used():
        return None
    result = claims.update_one(
        {"_id": claim_id, "token": existing.get("token")},
        {"$set": {"token": token, "created_at": now, "bound": False}},
    )
    return token if result.modified_count else None


def bind_payment_reference(method, key, token):
    """Mark a claim as owned by a stored record, ending its grace period."""
    if token:
        conn().payment_reference_claims.update_one(
            {"_id": f"{method}:{key}", "token": token}, {"$set": {"bound": True}},
        )


def release_payment_reference(method, key, token):
    """Give a reference back when the submission that claimed it failed."""
    if token:
        conn().payment_reference_claims.delete_one({"_id": f"{method}:{key}", "token": token})
