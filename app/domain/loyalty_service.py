"""Three-day customer levels based on cumulative confirmed purchases."""
from __future__ import annotations

import time
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


def total_spend(user_id: int) -> float:
    rows = db.get_conn().orders.find(
        {
            "user_id": int(user_id),
            "status": {"$in": [str(status) for status in PAID_STATUSES]},
        },
        {"gross_total": 1, "total_price": 1, "_id": 0},
    )
    return round(sum(float(row.get("gross_total", row.get("total_price", 0))) for row in rows), 2)


def level_for_spend(spend: float) -> tuple[str, float, int] | None:
    current = None
    for level in LEVELS:
        if spend >= level[1]:
            current = level
    return current


def record_purchase(user_id: int) -> dict[str, Any]:
    """Activate or upgrade a level for seven days when a threshold is reached."""
    conn = db.get_conn()
    spend = total_spend(user_id)
    level = level_for_spend(spend)
    if not level:
        return {
            "level": None, "discount_percent": 0, "total_spend": spend,
            "expires_at": None, "activated": False,
        }
    name, threshold, discount = level
    existing = conn.loyalty.find_one({"user_id": user_id}) or {}
    now = int(time.time())
    existing_expires_at = int(existing.get("expires_at", 0) or 0)
    if existing.get("activated_at"):
        existing_expires_at = min(
            existing_expires_at,
            int(existing["activated_at"]) + LEVEL_DURATION_SECONDS,
        )
    if existing.get("level") != name or existing_expires_at <= now:
        activated = True
        expires_at = now + LEVEL_DURATION_SECONDS
        conn.loyalty.update_one(
            {"user_id": user_id},
            {"$set": {
                "level": name,
                "threshold": threshold,
                "discount_percent": discount,
                "activated_at": now,
                "expires_at": expires_at,
                "total_spend": spend,
            }},
            upsert=True,
        )
    else:
        activated = False
        expires_at = existing_expires_at
        conn.loyalty.update_one({"user_id": user_id}, {"$set": {"total_spend": spend}})
    return {
        "level": name,
        "discount_percent": discount,
        "total_spend": spend,
        "expires_at": expires_at,
        "activated": activated,
    }


def active_benefit(user_id: int) -> dict[str, Any]:
    row = db.get_conn().loyalty.find_one({"user_id": user_id}) or {}
    expires_at = int(row.get("expires_at", 0) or 0)
    if row.get("activated_at"):
        expires_at = min(expires_at, int(row["activated_at"]) + LEVEL_DURATION_SECONDS)
    if expires_at <= int(time.time()):
        return {"level": None, "discount_percent": 0, "expires_at": None}
    configured_discount = next(
        (discount for name, _threshold, discount in LEVELS if name == row.get("level")),
        0,
    )
    return {
        "level": row.get("level"),
        "discount_percent": configured_discount,
        "expires_at": expires_at,
    }


def discount_for_order(user_id: int, gross_total: float) -> dict[str, Any]:
    benefit = active_benefit(user_id)
    amount = round(gross_total * benefit["discount_percent"] / 100, 2)
    return {**benefit, "amount": amount}
