"""Tunisian storefront catalog projection and manual cart checkout."""

from urllib.parse import unquote

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import storefront_service

CUSTOMER = {"name": "Amine Ben Salah", "phone": "21 111 222", "payment_method": "d17"}


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


def _create(**overrides):
    return storefront_service.create_order({**CUSTOMER, **overrides})


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


def test_offer_without_a_dinar_price_is_hidden_and_cannot_be_ordered(mock_mongodb):
    _, priced = _catalog_offer(millimes=25000)
    _, unpriced = _catalog_offer(name="Outlook Mail", millimes=None, service="Mails")

    offers = [offer["id"] for service in storefront_service.catalog()["services"] for offer in service["offers"]]
    assert offers == [priced]
    with pytest.raises(storefront_service.StorefrontError, match="pas disponible"):
        _create(items=[{"offer_id": unpriced, "quantity": 1}])


@pytest.mark.parametrize("service, offer, category", [
    ("Mails", "Outlook Mail Accounts", "communication"),
    ("Tools", "Perplexity AI Pro", "ai"),
    ("ChatGPT", "Plus 1 mois", "ai"),
])
def test_category_matches_whole_words(service, offer, category):
    assert storefront_service._category({"name": service}, {"name": offer}) == category


def test_runtime_settings_change_whatsapp_and_payment_methods(mock_mongodb):
    from app.domain import site_settings_service

    _, offer_id = _catalog_offer()
    site_settings_service.save({"whatsapp_number": "+216 55 000 111", "tnd_per_usdt": "3.3", "payment_flouci": "on"})

    result = storefront_service.catalog()
    assert result["whatsapp"] == "21655000111"
    assert [item["id"] for item in result["payment_methods"]] == ["flouci"]
    with pytest.raises(ValueError, match="Flouci"):
        _create(items=[{"offer_id": offer_id, "quantity": 1}])
    cart = _create(payment_method="flouci", items=[{"offer_id": offer_id, "quantity": 1}])
    assert cart["whatsapp_url"].startswith("https://wa.me/21655000111?text=")
    assert storefront_service.suggested_price_millimes({"price": 6.0}) == 19800


def test_cart_stores_one_order_per_line_under_a_shared_reference(mock_mongodb):
    _, first = _catalog_offer(millimes=25000)
    _, second = _catalog_offer(name="Canva Pro", millimes=12500, service="Canva")

    result = _create(items=[
        {"offer_id": first, "quantity": 2},
        {"offer_id": second, "quantity": 1},
    ])

    assert result["total_millimes"] == 62500
    assert len(result["order_ids"]) == 2
    orders = [db.get_order(order_id) for order_id in result["order_ids"]]
    assert {order["offer_id"] for order in orders} == {first, second}
    assert {order["cart_reference"] for order in orders} == {result["reference"]}
    assert [order["cart_position"] for order in orders] == [1, 2]
    for order in orders:
        assert order["status"] == OrderStatus.MANUAL_REVIEW
        assert order["currency"] == "TND"
        assert order["paid_at"] is None
        assert order["verification_channel"] == "whatsapp"
        assert order["customer_phone"] == "+21621111222"
        assert order["cart_size"] == 2
        assert order["cart_total_millimes"] == 62500
    assert orders[0]["total_millimes"] == 50000
    assert orders[0]["total_price"] == 50.0


def test_cart_whatsapp_handoff_quotes_the_reference_and_grand_total(mock_mongodb):
    _, offer_id = _catalog_offer(name="ChatGPT Plus", millimes=25000)
    result = _create(items=[{"offer_id": offer_id, "quantity": 2}])

    assert result["whatsapp_url"].startswith("https://wa.me/21621994132?text=")
    message = unquote(result["whatsapp_url"].split("?text=", 1)[1])
    assert result["reference"] in message
    assert "D17" in message
    assert "• 2 × ChatGPT Plus" in message
    assert "Total : 50,000 DT" in message
    assert result["automatic_confirmation"] is False


def test_repeated_offer_lines_are_merged_into_one_order(mock_mongodb):
    _, offer_id = _catalog_offer(millimes=10000)
    result = _create(items=[
        {"offer_id": offer_id, "quantity": 1},
        {"offer_id": offer_id, "quantity": 2},
    ])
    assert len(result["order_ids"]) == 1
    assert db.get_order(result["order_ids"][0])["qty"] == 3
    assert result["total_millimes"] == 30000


def test_single_offer_payload_without_items_still_creates_a_cart(mock_mongodb):
    _, offer_id = _catalog_offer(millimes=25000)
    result = _create(offer_id=offer_id, quantity=1)
    assert result["order_id"] == result["order_ids"][0]
    assert db.get_order(result["order_id"])["status"] == OrderStatus.MANUAL_REVIEW


def test_a_rejected_line_creates_no_orders_at_all(mock_mongodb):
    _, available = _catalog_offer(millimes=25000, stock=5)
    _, short = _catalog_offer(name="Netflix", millimes=9000, stock=1, service="Netflix")

    with pytest.raises(storefront_service.StorefrontError, match="stock"):
        _create(items=[
            {"offer_id": available, "quantity": 1},
            {"offer_id": short, "quantity": 4},
        ])
    assert mock_mongodb.orders.count_documents({}) == 0


@pytest.mark.parametrize("payload, message", [
    ({"items": []}, "panier"),
    ({"items": [{"offer_id": 999_999, "quantity": 1}]}, "disponible"),
    ({"name": "A"}, "nom complet"),
    ({"phone": "12345"}, "numéro tunisien"),
    ({"payment_method": "bitcoin"}, "D17"),
])
def test_invalid_checkout_payloads_are_rejected(mock_mongodb, payload, message):
    _, offer_id = _catalog_offer()
    request = {**CUSTOMER, "items": [{"offer_id": offer_id, "quantity": 1}], **payload}
    with pytest.raises(ValueError, match=message):
        storefront_service.create_order(request)


def test_cart_larger_than_the_line_limit_is_rejected(mock_mongodb):
    _, offer_id = _catalog_offer()
    items = [{"offer_id": offer_id, "quantity": 1}] * (storefront_service.MAX_CART_LINES + 1)
    with pytest.raises(storefront_service.StorefrontError, match="au maximum"):
        _create(items=items)


def test_cart_status_requires_the_tracking_token(mock_mongodb):
    _, first = _catalog_offer(millimes=25000)
    _, second = _catalog_offer(name="Canva Pro", millimes=12500, service="Canva")
    result = _create(payment_method="flouci", items=[
        {"offer_id": first, "quantity": 1},
        {"offer_id": second, "quantity": 1},
    ])

    status = storefront_service.cart_status(result["reference"], result["tracking_token"])
    assert status["payment_method"] == "flouci"
    assert status["total_millimes"] == 37500
    assert [item["status"] for item in status["items"]] == [OrderStatus.MANUAL_REVIEW] * 2

    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.cart_status(result["reference"], "wrong-token")


def test_order_status_returns_a_single_line_of_the_cart(mock_mongodb):
    _, offer_id = _catalog_offer()
    result = _create(items=[{"offer_id": offer_id, "quantity": 1}])
    status = storefront_service.order_status(result["order_ids"][0], result["tracking_token"])
    assert status["order"]["status"] == OrderStatus.MANUAL_REVIEW
    assert status["order"]["reference"] == result["reference"]

    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.order_status(result["order_ids"][0], "wrong-token")
