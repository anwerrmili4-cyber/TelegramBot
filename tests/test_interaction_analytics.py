from __future__ import annotations

import time

import database as db


def test_interaction_analytics_tracks_daily_users_types_and_details(mock_mongodb):
    db.log_interaction(
        42,
        first_name="Test",
        full_name="Test Buyer",
        username="buyer",
        interaction_type="button",
        action="buy:17",
        screen="Offer screen",
    )
    db.log_interaction(
        42,
        first_name="Test",
        full_name="Test Buyer",
        username="buyer",
        interaction_type="message",
        content="hello",
    )

    result = db.interaction_analytics(days=30, limit=1000)

    assert result["summary"]["total"] == 2
    assert result["summary"]["today"] == 2
    assert result["summary"]["active_today"] == 1
    assert result["summary"]["live_users"] == 1
    assert result["summary"]["button_clicks"] == 1
    assert result["summary"]["messages"] == 1
    assert sum(point["count"] for point in result["daily"]) == 2
    assert len(result["events"]) == 2
    assert result["events"][0]["full_name"] == "Test Buyer"


def test_user_activity_summary_includes_recent_today_and_total(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 42},
        {"telegram_id": 43},
    ])
    db.log_interaction(42, interaction_type="button", action="home")

    result = db.user_activity_summary()

    assert result == {
        "online_now": 1,
        "active_today": 1,
        "total_users": 2,
    }


def test_interaction_analytics_groups_service_clicks_by_day(mock_mongodb):
    streaming_id = db.add_service("Streaming", "🎬")
    ai_id = db.add_service("AI", "🤖")
    now = int(time.time())
    today_start = now - (now % 86400)
    mock_mongodb.interaction_events.insert_many([
        {
            "user_id": 10, "interaction_type": "button",
            "action": f"svc:{streaming_id}", "created_at": today_start + 10,
        },
        {
            "user_id": 11, "interaction_type": "button",
            "action": f"svc:{streaming_id}", "created_at": today_start + 20,
        },
        {
            "user_id": 12, "interaction_type": "button",
            "action": f"svc:{ai_id}", "created_at": today_start - 86400 + 30,
        },
        {
            "user_id": 12, "interaction_type": "button",
            "action": "off:99", "created_at": today_start + 40,
        },
    ])

    service_clicks = db.interaction_analytics(days=30)["service_clicks"]

    assert service_clicks["total"] == 3
    assert service_clicks["services"][0] == {
        "service_id": streaming_id, "name": "Streaming", "count": 2,
    }
    assert len(service_clicks["daily"]) == 2
    assert service_clicks["daily"][-1]["total"] == 2
    assert service_clicks["daily"][-1]["services"][0]["name"] == "Streaming"


def _freeze_interaction_clock(monkeypatch, when):
    clock = {"now": int(when)}
    monkeypatch.setattr(db.time, "time", lambda: clock["now"])
    return clock


def test_one_thousand_bot_interactions_in_a_utc_day_do_not_ban(mock_mongodb, monkeypatch):
    db.upsert_user(42, "busy", "Busy")
    day = db.interaction_day_start(1_800_000_000)
    _freeze_interaction_clock(monkeypatch, day + 30)

    for _ in range(db.BOT_DAILY_INTERACTION_LIMIT):
        db.log_interaction(42, interaction_type="button", action="catalog")

    assert db.is_user_banned(42) is False
    assert mock_mongodb.users.find_one({"telegram_id": 42})["username"] == "busy"


def test_passing_one_thousand_daily_interactions_bans_until_an_admin_unbans(mock_mongodb, monkeypatch):
    db.upsert_user(42, "robot", "Robot")
    day = db.interaction_day_start(1_800_000_000)
    clock = _freeze_interaction_clock(monkeypatch, day + 30)
    for _ in range(db.BOT_DAILY_INTERACTION_LIMIT):
        db.log_interaction(42, interaction_type="button", action="catalog")

    db.log_interaction(42, interaction_type="button", action="off:9")

    assert db.is_user_banned(42) is True
    user = mock_mongodb.users.find_one({"telegram_id": 42})
    assert user["username"] == "robot"
    assert mock_mongodb.interaction_events.count_documents({"user_id": 42}) == 1001
    audit = mock_mongodb.audit_events.find_one({"action": "user.banned"})
    assert audit["details"]["reason"] == "daily_interaction_limit"

    db.set_user_banned(42, False)
    db.log_interaction(42, interaction_type="button", action="catalog")
    assert db.is_user_banned(42) is False

    clock["now"] = day + 86400 + 15
    for _ in range(db.BOT_DAILY_INTERACTION_LIMIT + 1):
        db.log_interaction(42, interaction_type="button", action="catalog")
    assert db.is_user_banned(42) is True


def test_interactions_from_the_previous_utc_day_do_not_count(mock_mongodb, monkeypatch):
    db.upsert_user(7, "human", "Human")
    day = db.interaction_day_start(1_800_000_000)
    mock_mongodb.interaction_events.insert_many([
        {
            "user_id": 7,
            "interaction_type": "button",
            "action": "home",
            "created_at": day - 10,
        }
        for _ in range(db.BOT_DAILY_INTERACTION_LIMIT + 5)
    ])
    _freeze_interaction_clock(monkeypatch, day + 20)

    db.log_interaction(7, interaction_type="button", action="home")

    assert db.is_user_banned(7) is False


def test_shop_admin_is_not_auto_banned_for_daily_interactions(mock_mongodb, monkeypatch):
    monkeypatch.setattr(db, "ADMIN_ID", 99)
    db.upsert_user(99, "owner", "Owner")
    day = db.interaction_day_start(1_800_000_000)
    _freeze_interaction_clock(monkeypatch, day + 5)

    for _ in range(db.BOT_DAILY_INTERACTION_LIMIT + 1):
        db.log_interaction(99, interaction_type="button", action="adm_panel")

    assert db.is_user_banned(99) is False
