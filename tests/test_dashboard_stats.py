"""Tests for dashboard comparisons and operational alerts."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import admin
import database as db


def test_dashboard_comparisons_and_alerts(mock_mongodb):
    now = int(time.time())
    today_start = now - (now % 86400)
    mock_mongodb.orders.insert_many([
        {"id": 1, "status": "delivered", "total_price": 10.0, "created_at": today_start + 1},
        {"id": 2, "status": "delivered", "total_price": 4.0, "created_at": today_start - 100},
        {"id": 3, "status": "payment_confirmed", "total_price": 8.0, "created_at": today_start, "paid_at": now - 1800},
        {"id": 4, "status": "manual_review", "total_price": 6.0, "created_at": today_start},
    ])
    mock_mongodb.audit_events.insert_one({"action": "system.error", "created_at": datetime.now(UTC)})

    data = db.dashboard_data()
    summary = data["summary"]
    alert_types = {alert["type"] for alert in data["alerts"]}

    assert summary["orders_day_delta"] == 2
    assert summary["revenue_day_delta"] == 14.0
    assert summary["paid_not_delivered"] == 1
    assert summary["failed_payments"] == 1
    assert {"paid_not_delivered", "payment_review", "recent_errors"} <= alert_types


def test_dashboard_revenue_includes_wallet_payments(mock_mongodb):
    now = int(time.time())
    mock_mongodb.orders.insert_one({
        "id": 10,
        "status": "delivered",
        "total_price": 0.0,
        "wallet_amount": 14.5,
        "created_at": now,
    })

    assert db.dashboard_data()["summary"]["revenue_today"] == 14.5


def test_dashboard_statistics_exclude_every_admin_purchase(monkeypatch, mock_mongodb):
    monkeypatch.setattr("config.ADMIN_ID", 999)
    now = int(time.time())
    service_id = db.add_service("Statistics", "📊")
    offer_id = db.add_offer(service_id, "Real sale", 10.0, 10)
    mock_mongodb.orders.insert_many([
        {"id": 20, "user_id": 42, "offer_id": offer_id, "qty": 1, "status": "delivered", "total_price": 10.0, "created_at": now},
        {"id": 21, "user_id": 999, "offer_id": offer_id, "qty": 1, "status": "delivered", "total_price": 500.0, "created_at": now},
        {"id": 22, "user_id": 999, "offer_id": offer_id, "qty": 1, "status": "manual_review", "total_price": 700.0, "created_at": now},
    ])

    data = db.dashboard_data()
    summary = data["summary"]
    service = next(item for item in data["services"] if item["id"] == service_id)

    assert summary["orders"] == 1
    assert summary["orders_today"] == 1
    assert summary["paid_orders"] == 1
    assert summary["delivered_orders"] == 1
    assert summary["pending_orders"] == 0
    assert summary["failed_payments"] == 0
    assert summary["revenue_today"] == 10.0
    assert service["total_sales"] == 1
    assert service["total_revenue"] == 10.0
    assert db.offer_sold_count(offer_id) == 1


def test_dashboard_services_include_offers(mock_mongodb):
    service_id = db.add_service("Streaming", "🎬")
    db.add_offer(service_id, "Monthly", 5.0, 2, "Instant")

    service = next(item for item in db.dashboard_data()["services"] if item["id"] == service_id)

    assert service["offers"][0]["name"] == "Monthly"
    assert service["offer_count"] == 1


def test_official_subscribes_catalog_is_always_first(mock_mongodb):
    regular_id = db.add_service("Streaming", "🎬")
    official_id = db.add_service("officiels subscribes", "✅")
    db.add_offer(regular_id, "Regular", 2.0, 1)
    official_offer = db.add_offer(official_id, "Official", 3.0, 1)

    assert db.list_services()[0]["id"] == official_id
    assert db.list_services_with_stock()[0]["id"] == official_id
    assert db.dashboard_data()["services"][0]["id"] == official_id
    assert db.list_catalog_offers()[0]["id"] == official_offer

    admin_button = admin.catalog_admin_keyboard().inline_keyboard[0][0]
    assert admin_button.callback_data == f"adm_svc:{official_id}"
    assert admin_button.style is None


def test_official_subscriptions_name_variant_is_pinned(mock_mongodb):
    regular_id = db.add_service("Chat GPT", "🤖")
    official_id = db.add_service("Officiels subscriptions", "✅")

    services = db.list_services()

    assert services[0]["id"] == official_id
    assert services[1]["id"] == regular_id
    assert db.is_official_subscriptions_service(services[0])


def test_offer_can_move_between_services_and_keeps_api_config_in_sync(mock_mongodb):
    source_id = db.add_service("Source", "📦")
    destination_id = db.add_service("Destination", "🚀")
    offer_id = db.add_offer(source_id, "Movable", 4.0, 2)
    mock_mongodb.reseller_products.insert_one({
        "provider": "mailreader", "product_id": "sku-move",
        "local_offer_id": offer_id, "service_id": source_id,
    })

    result = db.move_offer(offer_id, destination_id)

    assert result["previous_service_id"] == source_id
    assert db.get_offer(offer_id)["service_id"] == destination_id
    assert mock_mongodb.reseller_products.find_one({"product_id": "sku-move"})["service_id"] == destination_id


def test_archived_catalog_items_are_hidden_but_preserved(mock_mongodb):
    service_id = db.add_service("Archive me", "📦")
    offer_id = db.add_offer(service_id, "Old product", 5.0, 2)
    db.archive_offer(offer_id)

    service = next(item for item in db.dashboard_data()["services"] if item["id"] == service_id)
    assert service["offers"] == []
    assert db.get_offer(offer_id)["archived"] == 1

    db.archive_service(service_id)
    assert all(item["id"] != service_id for item in db.dashboard_data()["services"])
    assert db.get_service(service_id)["archived"] == 1


def test_offer_metadata_can_be_administered(mock_mongodb):
    service_id = db.add_service("AI", "🤖")
    offer_id = db.add_offer(
        service_id,
        "Pro",
        12.0,
        3,
        description="Premium account",
        auto_delivery=False,
        low_stock_threshold=2,
        delivery_delay="Within one hour",
    )
    db.update_offer(offer_id, sort_order=9, description="Updated")

    offer = db.get_offer(offer_id)
    assert offer["description"] == "Updated"
    assert offer["auto_delivery"] is False
    assert offer["low_stock_threshold"] == 2
    assert offer["delivery_delay"] == "Within one hour"
    assert offer["sort_order"] == 9

    duplicate_id = db.duplicate_offer(offer_id)
    duplicate = db.get_offer(duplicate_id)
    assert duplicate["name"].endswith("(copie)")
    assert duplicate["stock"] == 0
    assert duplicate["description"] == "Updated"
