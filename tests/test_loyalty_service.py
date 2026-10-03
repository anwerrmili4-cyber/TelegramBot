"""Tests for three-day customer loyalty levels."""

import time

import database as db
from app.domain import loyalty_service, order_service


def _paid_order(conn, order_id, user_id, amount, paid_at=None):
    paid_at = int(time.time()) if paid_at is None else int(paid_at)
    conn.orders.insert_one({
        "id": order_id,
        "user_id": user_id,
        "status": "delivered",
        "gross_total": amount,
        "total_price": amount,
        "paid_at": paid_at,
        "created_at": paid_at,
    })


def test_levels_match_spend_thresholds(mock_mongodb):
    expected = [
        (25, "bronze", 3),
        (70, "silver", 6),
        (200, "platinum", 9),
        (500, "diamond", 12),
    ]
    for index, (amount, level, discount) in enumerate(expected, start=1):
        user_id = 1000 + index
        _paid_order(mock_mongodb, index, user_id, amount)
        benefit = loyalty_service.record_purchase(user_id)
        assert benefit["level"] == level
        assert benefit["discount_percent"] == discount
        assert benefit["expires_at"] > int(time.time()) + 2 * 86400
        assert benefit["expires_at"] <= int(time.time()) + 3 * 86400


def test_level_reached_more_than_three_days_ago_has_no_discount(mock_mongodb):
    now = int(time.time())
    _paid_order(mock_mongodb, 1, 77, 25, paid_at=now - 8 * 86400)
    mock_mongodb.loyalty.insert_one({
        "user_id": 77,
        "level": "bronze",
        "discount_percent": 3,
        "activated_at": now - 3600,
        "expires_at": now + 6 * 86400,
    })

    benefit = loyalty_service.active_benefit(77)

    assert benefit["discount_percent"] == 0
    assert benefit["level"] is None


def test_later_purchase_does_not_renew_an_expired_level(mock_mongodb):
    now = int(time.time())
    _paid_order(mock_mongodb, 1, 77, 25, paid_at=now - 8 * 86400)
    _paid_order(mock_mongodb, 2, 77, 10, paid_at=now)

    benefit = loyalty_service.record_purchase(77)

    assert benefit["activated"] is False
    assert benefit["discount_percent"] == 0
    assert loyalty_service.discount_for_order(77, 100)["amount"] == 0
    stored = mock_mongodb.loyalty.find_one({"user_id": 77})
    assert stored["activated_at"] <= now - 8 * 86400 + 5
    assert stored["discount_percent"] == 0


def test_higher_level_starts_a_new_three_day_window(mock_mongodb):
    now = int(time.time())
    _paid_order(mock_mongodb, 1, 77, 25, paid_at=now - 10 * 86400)
    _paid_order(mock_mongodb, 2, 77, 50, paid_at=now)
    mock_mongodb.loyalty.insert_one({
        "user_id": 77,
        "level": "bronze",
        "discount_percent": 0,
        "activated_at": now - 10 * 86400,
        "expires_at": now - 7 * 86400,
    })

    benefit = loyalty_service.record_purchase(77)

    assert benefit["activated"] is True
    assert benefit["level"] == "silver"
    assert benefit["discount_percent"] == 6
    assert benefit["expires_at"] > now + 2 * 86400

def test_active_level_discount_is_applied_to_new_order(mock_mongodb):
    db.add_service("AI", "🤖")
    offer_id = db.add_offer(1, "Premium", 100.0, 2)
    _paid_order(mock_mongodb, 90, 42, 70.0)
    loyalty_service.record_purchase(42)

    order = order_service.create_order(42, db.get_offer(offer_id))

    assert order["loyalty_level"] == "silver"
    assert order["loyalty_discount_percent"] == 6
    assert order["total_price"] == 94.0


def test_expired_level_has_no_discount(mock_mongodb):
    mock_mongodb.loyalty.insert_one({
        "user_id": 42, "level": "diamond", "discount_percent": 30, "expires_at": int(time.time()) - 1,
    })
    assert loyalty_service.discount_for_order(42, 100)["amount"] == 0
