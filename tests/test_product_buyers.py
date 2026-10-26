"""Sold products stay selectable after they leave the live catalog."""

import time

from app.web import product_buyers
import pytest


def test_bot_product_filter_keeps_deleted_and_inactive_sales(mock_mongodb):
    mock_mongodb.services.insert_many([
        {"id": 1, "name": "Canva", "emoji": "🎨", "active": 1},
        {"id": 2, "name": "Gamma", "emoji": "✨", "active": 0},
    ])
    mock_mongodb.offers.insert_many([
        {
            "id": 10, "service_id": 1, "name": "Canva Pro", "price": 1, "stock": 4,
            "active": 0, "archived": 1, "warranty_value": 0, "warranty_unit": "days",
            "period_value": 30, "period_unit": "days", "description": "<b>Design</b>",
            "supplier_provider": "", "unlimited_stock": True,
        },
        {
            "id": 11, "service_id": 2, "name": "Gamma Pro", "price": 40, "stock": 0,
            "active": 0, "product_enabled": False, "warranty_days": 7,
            "period_days": 365, "description": "Old gamma",
        },
    ])
    mock_mongodb.users.insert_many([
        {"telegram_id": 42, "username": "amina", "first_name": "Amina", "last_name": "Salah", "lang": "fr", "created_at": 1_700_000_000},
        {"telegram_id": 43, "username": "karim", "first_name": "Karim", "lang": "en", "banned": True, "created_at": 1_700_000_100},
    ])
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 250})
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 42, "offer_id": 10, "offer_name": "Canva Pro", "service_name": "Canva", "status": "delivered", "qty": 1, "unit_price": 1, "total_price": 1, "wallet_amount": 0, "paid_at": 100, "created_at": 100, "warranty": "NW", "period_days": 30},
        {"id": 2, "user_id": 43, "offer_id": 10, "offer_name": "Canva Pro", "service_name": "Canva", "status": "paid", "qty": 2, "unit_price": 1, "total_price": 1, "wallet_amount": 1, "paid_at": 200, "created_at": 200},
        {"id": 3, "user_id": 42, "offer_id": 11, "offer_name": "Gamma Pro", "service_name": "Gamma", "status": "delivered", "qty": 1, "total_price": 40, "paid_at": 300, "created_at": 300, "product_description_snapshot": "Snapshot gamma"},
        {"id": 4, "user_id": 42, "offer_id": 99, "offer_name": "Old Cursor", "service_name": "Cursor", "status": "delivered", "qty": 1, "unit_price": 20, "total_price": 20, "paid_at": 400, "created_at": 400, "warranty": "14 days", "period_days": 30, "product_description_snapshot": "Removed from the catalog"},
        {"id": 5, "user_id": 42, "offer_id": 10, "offer_name": "Canva Pro", "service_name": "Canva", "status": "pending_payment", "qty": 1, "total_price": 1, "created_at": 500},
        {"id": 6, "user_id": 42, "offer_id": 12, "offer_name": "Site only", "service_name": "Site", "sales_channel": "tn_site", "status": "delivered", "qty": 1, "total_price": 9, "paid_at": 600, "created_at": 600},
    ])

    listed = product_buyers.report({"channel": ["bot"]})
    names = [item["name"] for item in listed["products"]]

    assert names == ["Canva Pro", "Gamma Pro", "Old Cursor"]
    canva = listed["products"][0]
    assert canva["catalog_state"] == "archived"
    assert canva["sales_count"] == 2
    assert canva["buyer_count"] == 2
    assert canva["quantity"] == 3
    assert canva["spent"] == 3
    assert listed["products"][1]["catalog_label"] == "Désactivé"
    assert listed["products"][2]["catalog_state"] == "deleted"

    detail = product_buyers.report({"channel": ["bot"], "product": ["offer:10"]})
    product = detail["product"]
    assert product["facts"][0] == {"label": "Nom", "value": "Canva Pro"}
    assert any(fact["value"] == "Archivé" for fact in product["facts"])
    assert any(fact["label"] == "Description" and fact["value"] == "Design" for fact in product["facts"])
    assert [buyer["name"] for buyer in product["buyers"]] == ["Karim", "Amina Salah"]
    amina = product["buyers"][1]
    assert amina["details"][1]["value"] == "@amina"
    assert amina["details"][6]["value"] == "2.50 USDT"
    assert amina["orders"][0]["order_id"] == 1
    assert "password" not in str(product)

    removed = product_buyers.report({"channel": ["bot"], "product": ["offer:99"], "search": ["cursor"]})
    assert removed["product"]["catalog_label"] == "Supprimé"
    assert removed["product"]["name"] == "Old Cursor"
    assert any(fact["value"] == "Removed from the catalog" for fact in removed["product"]["facts"])
    assert removed["product"]["buyers"][0]["name"] == "Amina Salah"

    assert product_buyers.report({"channel": ["bot"], "search": ["gamma"]})["products"][0]["name"] == "Gamma Pro"
    assert product_buyers.report({"channel": ["bot"], "product": ["offer:404"]})["ok"] is False


def test_site_product_filter_lists_buyers_with_their_account(mock_mongodb):
    mock_mongodb.offers.insert_one({
        "id": 8, "service_id": 3, "name": "Netflix", "price": 5, "active": 0, "stock": 0,
    })
    mock_mongodb.storefront_customers.insert_one({
        "id": 7, "name": "Amine Ben Salah", "email": "amine@example.com", "phone": "+21621111222",
        "email_verified": True, "created_at": 1_700_000_000, "password_hash": "secret-hash",
    })
    mock_mongodb.storefront_wallets.insert_one({"customer_id": 7, "balance_millimes": 1500})
    mock_mongodb.orders.insert_many([
        {
            "id": 20, "sales_channel": "tn_site", "customer_id": 7, "customer_name": "Amine Ben Salah",
            "customer_email": "amine@example.com", "customer_phone": "+21621111222",
            "offer_id": 8, "offer_name": "Netflix", "service_name": "Streaming",
            "status": "delivered", "quantity": 2, "total_millimes": 25000, "unit_price_millimes": 12500,
            "paid_at": 800, "created_at": 800, "cart_reference": "TN-1",
        },
        {
            "id": 21, "sales_channel": "tn_site", "customer_id": 7,
            "offer_id": 8, "offer_name": "Netflix", "service_name": "Streaming",
            "status": "manual_review", "quantity": 1, "total_millimes": 12500, "created_at": 900,
        },
        {
            "id": 22, "user_id": 42, "offer_id": 8, "offer_name": "Netflix", "service_name": "Streaming",
            "status": "delivered", "qty": 1, "total_price": 5, "paid_at": 700, "created_at": 700,
        },
    ])

    listed = product_buyers.report({"channel": ["site"]})
    assert [item["name"] for item in listed["products"]] == ["Netflix"]
    assert listed["products"][0]["sales_count"] == 1
    assert listed["products"][0]["spent"] == 25000
    assert listed["currency"] == "TND"

    detail = product_buyers.report({"channel": ["site"], "product": ["offer:8"]})
    assert any(fact["label"] == "Prix catalogue" and fact["value"] == "12.500 DT" for fact in detail["product"]["facts"])
    assert detail["product"]["catalog_label"] == "Désactivé"
    buyer = detail["product"]["buyers"][0]
    assert buyer["name"] == "Amine Ben Salah"
    assert buyer["email"] == "amine@example.com"
    assert any(fact["value"] == "+21621111222" for fact in buyer["details"])
    assert buyer["orders"][0]["cart_reference"] == "TN-1"
    assert buyer["orders"][0]["quantity"] == 2
    assert "secret-hash" not in str(detail)


@pytest.mark.parametrize("channel", ["bot", "site"])
def test_period_filters_products_buyers_orders_and_totals(mock_mongodb, channel):
    common = {"offer_id": 8, "offer_name": "Archived", "status": "delivered"}
    if channel == "site":
        common.update(sales_channel="tn_site", total_millimes=5000, customer_id=7)
    else:
        common.update(total_price=5, user_id=7)
    mock_mongodb.orders.insert_many([
        {**common, "id": 1, "paid_at": 99, "created_at": 100},
        {**common, "id": 2, "paid_at": 100, "created_at": 10, "qty": 2},
        {**common, "id": 3, "paid_at": 199, "created_at": 10},
        {**common, "id": 4, "paid_at": 200, "created_at": 100},
        {**common, "id": 5, "created_at": 150},
        {**common, "id": 6, "paid_at": 0, "created_at": 160},
        {**common, "id": 7, "paid_at": None, "created_at": 170},
        {**common, "id": 8, "offer_id": 99, "paid_at": 300},
        {**common, "id": 9, "paid_at": 0, "created_at": 150, "status": "pending_payment"},
        {**common, "id": 10, "paid_at": 120, "sales_channel": "tn_site" if channel == "bot" else "bot"},
    ])
    payload = product_buyers.report({"channel": [channel], "product": ["offer:8"], "from_ts": ["100"], "to_ts": ["200"]})
    assert payload["ok"] is True
    assert len(payload["products"]) == 1
    product = payload["product"]
    assert product["catalog_state"] == "deleted"
    assert product["sales_count"] == 5
    assert product["buyer_count"] == 1
    assert product["quantity"] == 6
    assert product["spent"] == (25000 if channel == "site" else 25)
    assert product["first_sale_at"] == 100
    assert product["last_sale_at"] == 199
    assert {row["order_id"] for row in product["buyers"][0]["orders"]} == {2, 3, 5, 6, 7}
    empty = product_buyers.report({"channel": [channel], "product": ["offer:8"], "from_ts": ["400"]})
    assert empty["ok"] is True
    assert empty["product"] is None
    assert empty["products"] == []


@pytest.mark.parametrize("bounds", [
    {"from_ts": ["invalid"]}, {"to_ts": ["NaN"]}, {"from_ts": ["-1"]},
    {"from_ts": ["100"], "to_ts": ["100"]}, {"from_ts": ["200"], "to_ts": ["100"]},
    {"to_ts": ["999999999999999999999999999999"]},
])
def test_invalid_period_returns_explicit_error(bounds):
    payload = product_buyers.report(bounds)
    assert payload["ok"] is False
    assert "Période invalide" in payload["error"]
    assert payload["products"] == []


def test_full_warranty_tracking_filters_active_and_finished_orders(mock_mongodb):
    now = int(time.time())
    day = 86400
    common = {
        "offer_id": 51,
        "offer_name": "Protected account",
        "service_name": "Protection",
        "user_id": 42,
        "status": "delivered",
        "qty": 1,
        "total_price": 10,
        "period_days": 30,
        "warranty_days": 30,
        "warranty": "FW",
    }
    mock_mongodb.orders.insert_many([
        {**common, "id": 501, "created_at": now - 12 * day, "paid_at": now - 11 * day, "delivered_at": now - 10 * day},
        {**common, "id": 502, "created_at": now - 42 * day, "paid_at": now - 41 * day, "delivered_at": now - 40 * day},
        {**common, "id": 503, "created_at": now - 5 * day, "paid_at": now - 4 * day, "delivered_at": now - 3 * day, "warranty_days": 7, "warranty": "7 days"},
    ])

    all_sales = product_buyers.report({"channel": ["bot"], "product": ["offer:51"]})
    assert all_sales["product"]["fw_total"] == 2
    assert all_sales["product"]["fw_active"] == 1
    assert all_sales["product"]["fw_finished"] == 1
    tracked = {
        order["order_id"]: order
        for order in all_sales["product"]["buyers"][0]["orders"]
    }
    assert tracked[501]["is_full_warranty"] is True
    assert tracked[501]["fw_status"] == "active"
    assert 19 <= tracked[501]["remaining_days"] <= 20
    assert tracked[501]["expires_at"] == common.get("expires_at", now - 10 * day + 30 * day)
    assert tracked[502]["fw_status"] == "finished"
    assert tracked[502]["remaining_days"] == 0
    assert tracked[503]["is_full_warranty"] is False
    assert tracked[503]["fw_status"] == ""

    active = product_buyers.report({"channel": ["bot"], "coverage": ["fw_active"], "product": ["offer:51"]})
    assert active["product"]["sales_count"] == 1
    assert active["product"]["buyers"][0]["orders"][0]["order_id"] == 501

    finished = product_buyers.report({"channel": ["bot"], "coverage": ["fw_finished"], "product": ["offer:51"]})
    assert finished["product"]["sales_count"] == 1
    assert finished["product"]["buyers"][0]["orders"][0]["order_id"] == 502

    full_warranty = product_buyers.report({"channel": ["bot"], "coverage": ["fw"]})
    assert full_warranty["products"][0]["sales_count"] == 2


def test_product_summary_pipeline_groups_without_unbounded_order_arrays():
    pipeline = product_buyers._summary_pipeline("site", 100, 200, "fw_active", now=150)
    assert list(pipeline[0]) == ["$match"]
    group = next(stage["$group"] for stage in pipeline if "$group" in stage)
    assert group["sales_count"] == {"$sum": 1}
    assert group["buyer_keys"] == {"$addToSet": "$_buyer_key"}
    assert all("$push" not in accumulator for accumulator in group.values() if isinstance(accumulator, dict))
    assert any(stage.get("$match") == {"_fw_status": "active"} for stage in pipeline)


def test_product_buyers_compound_index_covers_workspace_status_date_and_product(mock_mongodb):
    index = mock_mongodb.orders.index_information()["product_buyers_workspace_status_paid_product"]
    assert index["key"] == [
        ("sales_channel", 1),
        ("status", 1),
        ("paid_at", -1),
        ("offer_id", 1),
    ]
