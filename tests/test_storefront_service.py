"""Tunisian storefront catalog projection and signed-in cart checkout."""

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import inventory_service, storefront_service, storefront_wallet_service
from tests.conftest import RECEIPT

TRANSFER = {"payment_method": "d17", "transaction_reference": "D17-778899", "receipt": RECEIPT}


def _catalog_offer(name="ChatGPT Plus 1 mois", millimes=25000, stock=5, service="ChatGPT"):
    service_id = db.add_service(service, "✦", sales_channels=["bot", "tn_site"])
    offer_id = db.add_offer(
        service_id,
        name,
        6.0,
        stock,
        description="Compte premium prêt à utiliser",
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=millimes,
    )
    return service_id, offer_id


@pytest.fixture
def customer(site_customer):
    return site_customer()


def _create(customer, **overrides):
    return storefront_service.create_order({**TRANSFER, **overrides}, customer)


def test_official_subscriptions_become_product_categories(mock_mongodb):
    service_id = db.add_service("officiels subscribes", "⭐", sales_channels=["bot", "tn_site"])
    chatgpt = db.add_offer(
        service_id, "ChatGPT Plus 1 mois", 6.0, 4,
        sales_channels=["bot", "tn_site"], tn_price_millimes=25000,
    )
    google = db.add_offer(
        service_id, "Google AI Pro | 12 months", 18.0, 2,
        sales_channels=["bot", "tn_site"], tn_price_millimes=60000,
    )
    streaming_id = db.add_service("Netflix", "🎬", sales_channels=["bot", "tn_site"])
    db.add_offer(
        streaming_id, "Premium", 5.0, 3,
        sales_channels=["bot", "tn_site"], tn_price_millimes=15000,
    )

    services = storefront_service.catalog()["services"]
    names = [service["name"] for service in services]

    assert "officiels subscribes" not in names
    assert names[:2] == ["ChatGPT Plus", "Google AI Pro"]
    assert "Netflix" in names
    chatgpt_service = services[0]
    assert chatgpt_service["offers"][0]["id"] == chatgpt
    assert chatgpt_service["offers"][0]["service_name"] == "ChatGPT Plus"
    assert chatgpt_service["offers"][0]["service_id"] == chatgpt_service["id"]
    assert services[1]["offers"][0]["id"] == google
    assert services[1]["offers"][0]["service_name"] == "Google AI Pro"


def test_catalog_uses_live_mongo_offers_and_tnd(mock_mongodb):
    _, offer_id = _catalog_offer()
    result = storefront_service.catalog()
    offer = result["services"][0]["offers"][0]
    assert offer["id"] == offer_id
    assert offer["price_millimes"] == 25000
    assert offer["service_name"] == "ChatGPT"
    assert result["currency"] == "TND"
    assert result["max_cart_lines"] == storefront_service.MAX_CART_LINES
    assert {item["id"] for item in result["payment_methods"]} == {"d17", "flouci"}
    assert "whatsapp" not in result


def test_catalog_projects_a_real_bulk_discount_onto_the_dinar_price(mock_mongodb):
    _, offer_id = _catalog_offer(millimes=8000)
    db.update_offer(offer_id, bulk_quantity=5, bulk_unit_price=3.72)
    offer = storefront_service.catalog()["services"][0]["offers"][0]
    assert offer["bulk_quantity"] == 5
    assert offer["bulk_unit_millimes"] == 4960


def test_catalog_hides_a_bulk_price_that_is_not_cheaper(mock_mongodb):
    _, offer_id = _catalog_offer(millimes=8000)
    db.update_offer(offer_id, bulk_quantity=5, bulk_unit_price=9)
    offer = storefront_service.catalog()["services"][0]["offers"][0]
    assert offer["bulk_quantity"] == 0
    assert offer["bulk_unit_millimes"] == 0


def test_catalog_does_not_refetch_each_offer_and_keeps_prices_live(mock_mongodb, monkeypatch):
    from unittest.mock import Mock

    _, offer_id = _catalog_offer()
    get_offer = Mock(side_effect=AssertionError("Catalog should use its existing offer rows"))
    monkeypatch.setattr(db, "get_offer", get_offer)
    result = storefront_service.catalog()
    offer = result["services"][0]["offers"][0]
    assert offer["price_millimes"] == 25000
    assert offer["stock"] == 5
    assert not get_offer.called

    mock_mongodb.offers.update_one({"id": offer_id}, {"$set": {"stock": 0}})
    assert storefront_service.catalog()["services"][0]["offers"][0]["available"] is False


def test_offer_without_a_dinar_price_is_hidden_and_cannot_be_ordered(mock_mongodb, customer):
    _, priced = _catalog_offer(millimes=25000)
    _, unpriced = _catalog_offer(name="Outlook Mail", millimes=None, service="Mails")

    offers = [offer["id"] for service in storefront_service.catalog()["services"] for offer in service["offers"]]
    assert offers == [priced]
    with pytest.raises(storefront_service.StorefrontError, match="pas disponible"):
        _create(customer, items=[{"offer_id": unpriced, "quantity": 1}])


@pytest.mark.parametrize("service, offer, category", [
    ("Mails", "Outlook Mail Accounts", "communication"),
    ("Tools", "Perplexity AI Pro", "ai"),
    ("ChatGPT", "Plus 1 mois", "ai"),
])
def test_category_matches_whole_words(service, offer, category):
    assert storefront_service._category({"name": service}, {"name": offer}) == category


def test_runtime_settings_change_payment_methods_and_their_details(mock_mongodb, customer):
    from app.domain import site_settings_service

    _, offer_id = _catalog_offer()
    site_settings_service.save({
        "tnd_per_usdt": "3.3",
        "payment_wafacash": "on",
        "details_wafacash": "Wafa Cash au nom de BlackMarket, CIN 01234567",
    })

    result = storefront_service.catalog()
    assert result["payment_methods"] == [
        {"id": "wafacash", "label": "Wafa Cash", "details": "Wafa Cash au nom de BlackMarket, CIN 01234567"},
    ]
    with pytest.raises(ValueError, match="Wafa Cash"):
        _create(customer, items=[{"offer_id": offer_id, "quantity": 1}])
    cart = _create(customer, payment_method="wafacash", items=[{"offer_id": offer_id, "quantity": 1}])
    assert cart["status"] == "to_verify"
    assert storefront_service.suggested_price_millimes({"price": 6.0}) == 19800


def test_transfer_cart_stores_one_order_per_line_with_the_receipt(mock_mongodb, customer):
    _, first = _catalog_offer(millimes=25000)
    _, second = _catalog_offer(name="Canva Pro", millimes=12500, service="Canva")

    result = _create(customer, items=[
        {"offer_id": first, "quantity": 2},
        {"offer_id": second, "quantity": 1},
    ])

    assert result["status"] == "to_verify"
    assert result["total_millimes"] == 62500
    assert len(result["order_ids"]) == 2
    orders = [db.get_order(order_id) for order_id in result["order_ids"]]
    assert {order["offer_id"] for order in orders} == {first, second}
    assert {order["cart_reference"] for order in orders} == {result["reference"]}
    assert [order["cart_position"] for order in orders] == [1, 2]
    receipt = mock_mongodb.storefront_receipts.find_one({})
    for order in orders:
        assert order["status"] == OrderStatus.MANUAL_REVIEW
        assert order["currency"] == "TND"
        assert order["paid_at"] is None
        assert order["verification_channel"] == "receipt"
        assert order["customer_id"] == customer["id"]
        assert order["payment_reference"] == "D17-778899"
        assert order["receipt_id"] == receipt["id"]
        assert order["cart_total_millimes"] == 62500
    assert orders[0]["total_millimes"] == 50000
    assert receipt["content_type"] == "image/png"


def test_transfer_needs_a_reference_and_a_valid_receipt(mock_mongodb, customer):
    _, offer_id = _catalog_offer()
    items = [{"offer_id": offer_id, "quantity": 1}]
    with pytest.raises(storefront_service.StorefrontError, match="référence"):
        _create(customer, items=items, transaction_reference="")
    with pytest.raises(storefront_service.StorefrontError, match="capture"):
        _create(customer, items=items, receipt="")
    with pytest.raises(storefront_service.StorefrontError, match="illisible"):
        _create(customer, items=items, receipt="data:image/png;base64,bm90IGFuIGltYWdl")
    assert mock_mongodb.orders.count_documents({}) == 0


def test_a_transaction_reference_cannot_be_reused(mock_mongodb, customer):
    _, offer_id = _catalog_offer()
    items = [{"offer_id": offer_id, "quantity": 1}]
    _create(customer, items=items)
    with pytest.raises(storefront_service.StorefrontError, match="déjà été utilisée"):
        _create(customer, items=items, transaction_reference=" d17-778899 ")


def test_wallet_payment_is_debited_and_delivered_from_inventory(mock_mongodb, customer, sent_emails):
    _, offer_id = _catalog_offer(millimes=20000, stock=0)
    inventory_service.add_items(offer_id, ["user1@mail.tn:pass1", "user2@mail.tn:pass2"])
    storefront_wallet_service.credit(customer["id"], 50000, kind="deposit")
    sent_emails.clear()

    result = _create(customer, payment_method="wallet", items=[{"offer_id": offer_id, "quantity": 2}])

    assert result["status"] == "delivered"
    assert result["balance_millimes"] == 10000
    message, invoice = sent_emails
    assert message["subject"] == f"Ta commande {result['reference']} est livrée"
    assert invoice["subject"].endswith(result["reference"]) and invoice["attachments"]
    assert "user1@mail.tn:pass1" in message["text"]
    (cart,) = storefront_service.customer_carts(customer["id"])
    assert cart["status"] == "delivered"
    assert "user2@mail.tn:pass2" in cart["items"][0]["delivery"]


def test_wallet_payment_without_inventory_waits_for_the_admin(mock_mongodb, customer, sent_emails):
    _, offer_id = _catalog_offer(millimes=20000, stock=3)
    storefront_wallet_service.credit(customer["id"], 20000, kind="deposit")
    sent_emails.clear()

    result = _create(customer, payment_method="wallet", items=[{"offer_id": offer_id, "quantity": 1}])

    assert result["status"] == "confirmed"
    assert result["balance_millimes"] == 0
    assert db.get_order(result["order_ids"][0])["status"] == OrderStatus.PAYMENT_CONFIRMED
    confirmed, invoice = sent_emails
    assert confirmed["subject"] == f"Paiement confirmé — {result['reference']}"
    assert invoice["subject"].startswith("Ta facture FAC-")


def test_wallet_payment_with_insufficient_balance_creates_nothing(mock_mongodb, customer):
    _, offer_id = _catalog_offer(millimes=20000)
    storefront_wallet_service.credit(customer["id"], 5000, kind="deposit")
    with pytest.raises(storefront_service.StorefrontError, match="Solde insuffisant"):
        _create(customer, payment_method="wallet", items=[{"offer_id": offer_id, "quantity": 1}])
    assert mock_mongodb.orders.count_documents({}) == 0
    assert storefront_wallet_service.balance(customer["id"]) == 5000


def test_repeated_offer_lines_are_merged_into_one_order(mock_mongodb, customer):
    _, offer_id = _catalog_offer(millimes=10000)
    result = _create(customer, items=[
        {"offer_id": offer_id, "quantity": 1},
        {"offer_id": offer_id, "quantity": 2},
    ])
    assert len(result["order_ids"]) == 1
    assert db.get_order(result["order_ids"][0])["qty"] == 3
    assert result["total_millimes"] == 30000


def test_a_rejected_line_creates_no_orders_at_all(mock_mongodb, customer):
    _, available = _catalog_offer(millimes=25000, stock=5)
    _, short = _catalog_offer(name="Netflix", millimes=9000, stock=1, service="Netflix")

    with pytest.raises(storefront_service.StorefrontError, match="stock"):
        _create(customer, items=[
            {"offer_id": available, "quantity": 1},
            {"offer_id": short, "quantity": 4},
        ])
    assert mock_mongodb.orders.count_documents({}) == 0


@pytest.mark.parametrize("payload, message", [
    ({"items": []}, "panier"),
    ({"items": [{"offer_id": 999_999, "quantity": 1}]}, "disponible"),
    ({"payment_method": "bitcoin"}, "D17"),
])
def test_invalid_checkout_payloads_are_rejected(mock_mongodb, customer, payload, message):
    _, offer_id = _catalog_offer()
    request = {**TRANSFER, "items": [{"offer_id": offer_id, "quantity": 1}], **payload}
    with pytest.raises(ValueError, match=message):
        storefront_service.create_order(request, customer)


def test_checkout_sends_the_order_received_email(mock_mongodb, customer, sent_emails):
    _, offer_id = _catalog_offer(millimes=25000)
    result = _create(customer, items=[{"offer_id": offer_id, "quantity": 2}])

    (message,) = sent_emails
    assert message["to"] == ["amine@example.com"]
    assert message["subject"] == f"Commande {result['reference']} reçue"
    assert "2 x ChatGPT Plus 1 mois : 50,000 DT" in message["text"]
    assert "D17" in message["text"]
    assert "whatsapp" not in message["text"].lower()


def test_cart_larger_than_the_line_limit_is_rejected(mock_mongodb, customer):
    _, offer_id = _catalog_offer()
    items = [{"offer_id": offer_id, "quantity": 1}] * (storefront_service.MAX_CART_LINES + 1)
    with pytest.raises(storefront_service.StorefrontError, match="au maximum"):
        _create(customer, items=items)


def test_cart_status_requires_the_tracking_token(mock_mongodb, customer):
    _, first = _catalog_offer(millimes=25000)
    _, second = _catalog_offer(name="Canva Pro", millimes=12500, service="Canva")
    result = _create(customer, payment_method="flouci", items=[
        {"offer_id": first, "quantity": 1},
        {"offer_id": second, "quantity": 1},
    ])

    status = storefront_service.cart_status(result["reference"], result["tracking_token"])
    assert status["payment_method"] == "flouci"
    assert status["total_millimes"] == 37500
    assert [item["status"] for item in status["items"]] == [OrderStatus.MANUAL_REVIEW] * 2

    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.cart_status(result["reference"], "wrong-token")


def test_order_status_returns_a_single_line_of_the_cart(mock_mongodb, customer):
    _, offer_id = _catalog_offer()
    result = _create(customer, items=[{"offer_id": offer_id, "quantity": 1}])
    status = storefront_service.order_status(result["order_ids"][0], result["tracking_token"])
    assert status["order"]["status"] == OrderStatus.MANUAL_REVIEW
    assert status["order"]["reference"] == result["reference"]

    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.order_status(result["order_ids"][0], "wrong-token")


def test_customer_history_only_shows_their_own_carts(mock_mongodb, site_customer):
    amine, karim = site_customer(), site_customer(name="Karim", email="karim@example.com")
    _, offer_id = _catalog_offer()
    mine = _create(amine, items=[{"offer_id": offer_id, "quantity": 1}])
    _create(karim, items=[{"offer_id": offer_id, "quantity": 1}], transaction_reference="D17-000111")

    carts = storefront_service.customer_carts(amine["id"], amine["email"])
    assert [cart["reference"] for cart in carts] == [mine["reference"]]
    assert carts[0]["payment_label"] == "D17"
    assert carts[0]["transaction_reference"] == "D17-778899"
