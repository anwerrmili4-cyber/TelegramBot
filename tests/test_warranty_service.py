import pytest

import database as db
from app.domain import warranty_service


def test_offer_warranty_label():
    assert warranty_service.offer_warranty_label({"warranty_days": 0}) == "NW"
    assert warranty_service.offer_warranty_label({"warranty_days": 30}) == "30 days"
    assert warranty_service.offer_warranty_label({"warranty_days": 30}, lang="fr") == "30 j"
    assert warranty_service.offer_warranty_label({"note": "NW"}) == "NW"
    assert warranty_service.offer_warranty_label({}) == "NW"
    assert warranty_service.offer_warranty_label(None) == "NW"
    assert warranty_service.offer_warranty_label({
        "warranty_days": 180, "warranty_value": 6, "warranty_unit": "months",
    }) == "6 months"
    assert warranty_service.offer_warranty_label({
        "warranty_days": 365, "warranty_value": 1, "warranty_unit": "years",
    }) == "1 year"


def test_period_label_preserves_selected_unit():
    assert warranty_service.offer_period_label({
        "period_days": 90, "period_value": 3, "period_unit": "months",
    }) == "3 months"
    assert warranty_service.offer_period_label({
        "period_days": 730, "period_value": 2, "period_unit": "years",
    }) == "2 years"
    assert warranty_service.duration_to_days(6, "months") == 180
    assert warranty_service.duration_to_days(2, "years") == 730


def test_order_warranty_label():
    assert warranty_service.order_warranty_label({"warranty_days": 0}) == "NW"
    assert warranty_service.order_warranty_label({"warranty_days": 15}) == "15 days"
    assert warranty_service.order_warranty_label({"warranty": "NW"}) == "NW"
    assert warranty_service.order_warranty_label({}) == "NW"
    assert warranty_service.order_warranty_label(None) == "NW"


def test_full_warranty_is_shown_when_warranty_matches_period():
    assert warranty_service.offer_warranty_label({
        "period_days": 365,
        "period_value": 1,
        "period_unit": "years",
        "warranty_days": 365,
        "warranty_value": 12,
        "warranty_unit": "months",
    }) == "FW"
    assert warranty_service.order_warranty_label({
        "period_days": 90,
        "warranty_days": 90,
    }) == "FW"
    assert warranty_service.offer_warranty_label({
        "period_days": 365,
        "warranty_days": 180,
        "warranty_value": 6,
        "warranty_unit": "months",
    }) == "6 months"


def test_offer_and_order_store_period_and_warranty(mock_mongodb):
    service_id = db.add_service("Warranty products", "🛡")
    offer_id = db.add_offer(
        service_id,
        "Protected account",
        5.0,
        2,
        period_days=45,
        warranty_days=30,
    )

    offer = db.get_offer(offer_id)
    order_id = db.create_order(42, offer, 1)
    order = db.get_order(order_id)

    assert offer["period_days"] == 45
    assert offer["warranty_days"] == 30
    assert order["period_days"] == 45
    assert order["warranty_days"] == 30
    assert order["warranty"] == "30 days"


def test_offer_and_order_store_month_and_year_units(mock_mongodb):
    service_id = db.add_service("Long subscriptions", "📅")
    offer_id = db.add_offer(
        service_id, "Annual plan", 20.0, 2,
        period_days=365, period_value=1, period_unit="years",
        warranty_days=90, warranty_value=3, warranty_unit="months",
    )

    offer = db.get_offer(offer_id)
    order_id = db.create_order(42, offer, 1)
    order = db.get_order(order_id)

    assert warranty_service.offer_period_label(offer) == "1 year"
    assert warranty_service.offer_warranty_label(offer) == "3 months"
    assert order["period_value"] == 1
    assert order["period_unit"] == "years"
    assert order["warranty_value"] == 3
    assert order["warranty_unit"] == "months"
    assert order["warranty"] == "3 months"


def test_legacy_warranty_migration_backfills_period_days(mock_mongodb):
    mock_mongodb.offers.insert_many([
        {"id": 1, "name": "Offer 1"},
        {"id": 2, "name": "Offer 2", "period_days": 60},
        {"id": 3, "name": "Offer 3"},
    ])

    assert db._backfill_structured_warranties(mock_mongodb) == 2
    assert mock_mongodb.offers.find_one({"id": 1})["period_days"] == 30
    assert mock_mongodb.offers.find_one({"id": 2})["period_days"] == 60
    assert mock_mongodb.offers.find_one({"id": 3})["period_days"] == 30
