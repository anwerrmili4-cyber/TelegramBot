"""Customer levels last three days from the purchase that first reaches them."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import database as db
from app.constants import PAID_STATUSES

LEVELS = (
    ("bronze", 25.0, 3),
    ("silver", 70.0, 6),
    ("platinum", 200.0, 9),
    ("diamond", 500.0, 12),
)
LEVEL_DURATION_SECONDS = 3 * 24 * 60 * 60


def _level_rank(name: Any) -> int:
    normalized = str(name or "").strip().lower()
    for index, (level_name, _threshold, _discount) in enumerate(LEVELS):
        if level_name == normalized:
            return index
    return -1


def _order_spend(row: dict[str, Any]) -> float:
    raw = row.get("gross_total", row.get("total_price", 0))
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _paid_timestamp(row: dict[str, Any]) -> int:
    for key in ("paid_at", "delivered_at", "updated_at", "created_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _paid_orders(user_id: int) -> list[dict[str, Any]]:
    rows = list(db.get_conn().orders.find(
        {
            "user_id": int(user_id),
            "status": {"$in": [str(status) for status in PAID_STATUSES]},
        },
        {
            "gross_total": 1,
            "total_price": 1,
            "paid_at": 1,
            "delivered_at": 1,
            "updated_at": 1,
            "created_at": 1,
            "id": 1,
            "_id": 0,
        },
    ))
    rows.sort(key=lambda row: (_paid_timestamp(row), int(row.get("id") or 0)))
    return rows


def level_for_spend(spend: float) -> tuple[str, float, int] | None:
    current = None
    for level in LEVELS:
        if spend >= level[1]:
            current = level
    return current


def status(user_id: int) -> dict[str, Any]:
    """Return the live discount. It ends three days after the level is reached."""
    spend = 0.0
    reached_at: dict[str, int] = {}
    for row in _paid_orders(user_id):
        spend += _order_spend(row)
        paid_at = _paid_timestamp(row)
        for name, threshold, _discount in LEVELS:
            if name not in reached_at and spend >= threshold and paid_at:
                reached_at[name] = paid_at
    spend = round(spend, 2)
    level = level_for_spend(spend)
    if not level:
        return {
            "level": None,
            "reached_level": None,
            "discount_percent": 0,
            "total_spend": spend,
            "activated_at": None,
            "expires_at": None,
            "active": False,
        }
    name, _threshold, discount = level
    activated_at = int(reached_at.get(name) or 0)
    expires_at = activated_at + LEVEL_DURATION_SECONDS if activated_at else 0
    active = expires_at > int(time.time())
    return {
        "level": name if active else None,
        "reached_level": name,
        "discount_percent": discount if active else 0,
        "total_spend": spend,
        "activated_at": activated_at or None,
        "expires_at": expires_at or None,
        "active": active,
    }


def total_spend(user_id: int) -> float:
    return status(user_id)["total_spend"]


def record_purchase(user_id: int) -> dict[str, Any]:
    """Open a three-day window when a higher level is reached, without renewing it."""
    conn = db.get_conn()
    existing = conn.loyalty.find_one({"user_id": int(user_id)}) or {}
    current = status(user_id)
    reached = current["reached_level"]
    if not reached:
        return {
            "level": None,
            "discount_percent": 0,
            "total_spend": current["total_spend"],
            "expires_at": None,
            "activated": False,
        }
    _name, threshold, _discount = level_for_spend(current["total_spend"])
    activated = bool(
        current["active"] and _level_rank(reached) > _level_rank(existing.get("level"))
    )
    conn.loyalty.update_one(
        {"user_id": int(user_id)},
        {"$set": {
            "level": reached,
            "threshold": threshold,
            "discount_percent": current["discount_percent"],
            "activated_at": current["activated_at"],
            "expires_at": current["expires_at"],
            "total_spend": current["total_spend"],
        }},
        upsert=True,
    )
    return {
        "level": current["level"],
        "discount_percent": current["discount_percent"],
        "total_spend": current["total_spend"],
        "expires_at": current["expires_at"] if current["active"] else None,
        "activated": activated,
    }


def active_benefit(user_id: int) -> dict[str, Any]:
    current = status(user_id)
    if not current["active"]:
        return {"level": None, "discount_percent": 0, "expires_at": None}
    return {
        "level": current["level"],
        "discount_percent": current["discount_percent"],
        "expires_at": current["expires_at"],
    }


def discount_for_order(user_id: int, gross_total: float) -> dict[str, Any]:
    benefit = active_benefit(user_id)
    amount = round(gross_total * benefit["discount_percent"] / 100, 2)
    return {**benefit, "amount": amount}
