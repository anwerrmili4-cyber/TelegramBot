"""Durable client/admin exchanges attached to an order."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

import database as db

_SENDERS = {"admin", "client"}
_KINDS = {"message", "customer_info"}


def record_message(
    order_id: int,
    sender_type: str,
    sender_id: int | None,
    content: str,
    *,
    kind: str = "message",
    created_at: int | None = None,
) -> dict[str, Any]:
    """Store one successful order-related exchange."""
    order_id = int(order_id)
    sender_type = str(sender_type or "").strip().lower()
    kind = str(kind or "message").strip().lower()
    content = str(content or "").strip()
    if order_id <= 0 or sender_type not in _SENDERS or not content:
        raise ValueError("Invalid order conversation message")
    if kind not in _KINDS:
        kind = "message"
    document = {
        "id": db._next_id("order_messages"),
        "order_id": order_id,
        "sender_type": sender_type,
        "sender_id": int(sender_id) if sender_id is not None else None,
        "content": content[:4000],
        "kind": kind,
        "created_at": int(time.time()) if created_at is None else int(created_at),
    }
    db.get_conn().order_messages.insert_one(document)
    return db._public(document)


def messages_by_order(order_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
    """Return chronological messages for the requested orders only."""
    clean_ids = sorted({int(order_id) for order_id in order_ids if order_id is not None})
    if not clean_ids:
        return {}
    grouped: dict[int, list[dict[str, Any]]] = {}
    cursor = db.get_conn().order_messages.find(
        {"order_id": {"$in": clean_ids}},
        {"_id": 0, "id": 1, "order_id": 1, "sender_type": 1, "sender_id": 1, "content": 1, "kind": 1, "created_at": 1},
    ).sort([("order_id", 1), ("created_at", 1), ("id", 1)])
    for stored in cursor:
        message = dict(stored)
        order_id = int(message["order_id"])
        grouped.setdefault(order_id, []).append(message)
    return grouped
