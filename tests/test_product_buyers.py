"""Sold products stay selectable after they leave the live catalog."""

from app.web import product_buyers


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
