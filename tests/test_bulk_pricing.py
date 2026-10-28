"""Bulk prices stay synchronized with normal and flash-sale prices."""

import database as db
from app.bot.offer_cards import compact_offer_text


def _offer(mock_mongodb, *, price=10, bulk_price=8, bulk_options=None):
    service_id = db.add_service("Bulk pricing", "📦")
    return db.add_offer(
        service_id,
        "Bulk product",
        price,
        100,
        bulk_quantity=5,
        bulk_unit_price=bulk_price,
        bulk_options=bulk_options,
    )


def test_normal_price_change_preserves_fixed_bulk_margin(mock_mongodb):
    offer_id = _offer(mock_mongodb, price=10, bulk_price=8)

    db.update_offer(offer_id, price=15)

    increased = db.get_offer(offer_id)
    assert increased["price"] == 15
    assert increased["bulk_unit_price"] == 13

    db.update_offer(offer_id, price=6)

    decreased = db.get_offer(offer_id)
    assert decreased["price"] == 6
    assert decreased["bulk_unit_price"] == 4


def test_normal_price_change_preserves_each_bulk_tier_amount(mock_mongodb):
    offer_id = _offer(
        mock_mongodb,
        price=10,
        bulk_price=8,
        bulk_options=[
            {"name": "5+", "min_quantity": 5, "unit_price": 8},
            {"name": "10+", "min_quantity": 10, "unit_price": 7},
        ],
    )

    db.update_offer(offer_id, price=12)

    offer = db.get_offer(offer_id)
    assert offer["bulk_unit_price"] == 10
    assert offer["bulk_options"] == [
        {"name": "5+", "min_quantity": 5, "unit_price": 10},
        {"name": "10+", "min_quantity": 10, "unit_price": 9},
    ]


def test_flash_sale_lowers_bulk_price_instead_of_undercutting_it(mock_mongodb):
    offer_id = _offer(mock_mongodb, price=10, bulk_price=8)

    sale = db.start_flash_sale(offer_id, 7, 60)

    assert sale["price"] == 7
    assert sale["bulk_unit_price"] == 7
    assert db.resolve_bulk_unit_price(sale, 5, sale["price"]) == 7

    restored = db.stop_flash_sale(offer_id)
    assert restored["price"] == 10
    assert restored["bulk_unit_price"] == 7


def test_flash_sale_above_bulk_price_keeps_bulk_price(mock_mongodb):
    offer_id = _offer(mock_mongodb, price=10, bulk_price=8)

    sale = db.start_flash_sale(offer_id, 9, 60)

    assert sale["price"] == 9
    assert sale["bulk_unit_price"] == 8


def test_flash_sale_clamps_every_bulk_tier(mock_mongodb):
    offer_id = _offer(
        mock_mongodb,
        price=10,
        bulk_price=9,
        bulk_options=[
            {"name": "5+", "min_quantity": 5, "unit_price": 9},
            {"name": "10+", "min_quantity": 10, "unit_price": 8},
        ],
    )

    sale = db.start_flash_sale(offer_id, 7, 60)

    assert sale["bulk_unit_price"] == 7
    assert [option["unit_price"] for option in sale["bulk_options"]] == [7, 7]


def test_bulk_price_may_equal_normal_price(mock_mongodb):
    offer_id = _offer(mock_mongodb, price=10, bulk_price=10)
    offer = db.get_offer(offer_id)

    assert db.resolve_bulk_unit_price(offer, 5, offer["price"]) == 10
    assert db.bulk_fields_from_form(
        {"bulk_quantity": "5", "bulk_unit_price": "10"},
        10,
    ) == {"bulk_quantity": 5, "bulk_unit_price": 10.0}
    assert "BULK PRICE:" in compact_offer_text(offer, "en")


def test_direct_writes_cannot_store_bulk_above_normal_price(mock_mongodb):
    service_id = db.add_service("Direct pricing", "🧱")
    offer_id = db.add_offer(
        service_id,
        "Direct product",
        10,
        100,
        bulk_quantity=5,
        bulk_unit_price=12,
    )

    created = db.get_offer(offer_id)
    assert created["bulk_unit_price"] == 10

    db.update_offer(offer_id, price=8, bulk_unit_price=9)

    updated = db.get_offer(offer_id)
    assert updated["price"] == 8
    assert updated["bulk_unit_price"] == 8


def test_existing_invalid_bulk_prices_are_migrated(mock_mongodb):
    mock_mongodb.offers.insert_one({
        "id": 900,
        "price": 5,
        "bulk_quantity": 5,
        "bulk_unit_price": 7,
        "bulk_options": [
            {"name": "5+", "min_quantity": 5, "unit_price": 7},
            {"name": "10+", "min_quantity": 10, "unit_price": 4},
        ],
    })

    assert db._normalize_stored_bulk_prices(mock_mongodb) == 1

    offer = db.get_offer(900)
    assert offer["bulk_unit_price"] == 5
    assert [option["unit_price"] for option in offer["bulk_options"]] == [5, 4]


def test_supplier_price_change_preserves_fixed_bulk_margin(mock_mongodb):
    service_id = db.add_service("Supplier pricing", "🔌")
    offer_id = db.add_offer(
        service_id,
        "Supplier product",
        10,
        100,
        bulk_quantity=5,
        bulk_unit_price=8,
        supplier_provider="mailreader",
        supplier_product_id="bulk-sku",
    )
    db.save_reseller_product_config(
        "mailreader",
        "bulk-sku",
        name="Supplier product",
        wholesale_price=5,
        currency="USDT",
        retail_price=10,
        enabled=True,
        service_id=service_id,
        local_offer_id=offer_id,
    )

    db.sync_reseller_supplier_price("mailreader", "bulk-sku", 8)

    offer = db.get_offer(offer_id)
    assert offer["price"] == 13
    assert offer["bulk_unit_price"] == 11
