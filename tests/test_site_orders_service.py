"""Admin handling of Tunisian storefront carts."""

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import site_orders_service, storefront_service

CUSTOMER = {"name": "Amine Ben Salah", "phone": "21 111 222", "payment_method": "flouci"}


def _offer(name, stock=5, millimes=20000):
    service_id = db.add_service(f"Service {name}", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(service_id, name, 6.0, stock, sales_channels=["bot", "tn_site"], tn_price_millimes=millimes)


def _cart(*lines):
    return storefront_service.create_order({**CUSTOMER, "items": [{"offer_id": o, "quantity": q} for o, q in lines]})


def _statuses(reference):
    return {row["status"] for row in db.get_conn().orders.find({"cart_reference": reference})}


def _stock(offer_id):
    return db.get_offer(offer_id)["stock"]


def test_list_groups_lines_into_one_cart_with_customer_details(mock_mongodb):
    netflix, spotify = _offer("Netflix"), _offer("Spotify", millimes=5000)
    cart = _cart((netflix, 2), (spotify, 1))

    result = site_orders_service.list_carts({})

    assert result["total"] == 1
    assert result["counts"]["to_verify"] == 1
    item = result["items"][0]
    assert item["reference"] == cart["reference"]
    assert item["status"] == "to_verify"
    assert item["customer_name"] == "Amine Ben Salah"
    assert item["customer_phone"] == "+21621111222"
    assert item["whatsapp_url"] == "https://wa.me/21621111222"
    assert item["payment_method"] == "flouci"
    assert item["total_millimes"] == 45000
    assert [(line["offer_name"], line["quantity"]) for line in item["items"]] == [("Netflix", 2), ("Spotify", 1)]


def test_list_filters_by_status_and_searches_reference_name_and_phone(mock_mongodb):
    offer = _offer("Canva")
    first, second = _cart((offer, 1)), _cart((offer, 1))
    site_orders_service.confirm_cart(second["reference"])

    assert [c["reference"] for c in site_orders_service.list_carts({"status": ["to_verify"]})["items"]] == [first["reference"]]
    assert [c["reference"] for c in site_orders_service.list_carts({"status": ["confirmed"]})["items"]] == [second["reference"]]
    assert site_orders_service.list_carts({"status": ["all"], "search": [first["reference"].lower()]})["total"] == 1
    assert site_orders_service.list_carts({"status": ["all"], "search": ["amine"]})["total"] == 2
    assert site_orders_service.list_carts({"status": ["all"], "search": ["21 111"]})["total"] == 2


def test_reference_search_does_not_match_phone_digits(mock_mongodb):
    offer = _offer("Canva")
    first, _ = _cart((offer, 1)), _cart((offer, 1))
    db.get_conn().orders.update_many({"cart_reference": first["reference"]}, {"$set": {"cart_reference": "TN-A21111"}})

    result = site_orders_service.list_carts({"status": ["all"], "search": ["TN-A21111"]})
    assert [cart["reference"] for cart in result["items"]] == ["TN-A21111"]


def test_list_ignores_bot_orders(mock_mongodb):
    offer = _offer("Bot only")
    db.create_order(123, db.get_offer(offer), 1)
    assert site_orders_service.list_carts({"status": ["all"]})["total"] == 0


def test_confirm_marks_every_line_paid_and_reserves_stock(mock_mongodb):
    netflix, spotify = _offer("Netflix", stock=5), _offer("Spotify", stock=3)
    cart = _cart((netflix, 2), (spotify, 1))

    site_orders_service.confirm_cart(cart["reference"])

    assert _statuses(cart["reference"]) == {str(OrderStatus.PAYMENT_CONFIRMED)}
    assert (_stock(netflix), _stock(spotify)) == (3, 2)
    with pytest.raises(site_orders_service.SiteOrderError, match="plus en attente"):
        site_orders_service.confirm_cart(cart["reference"])


def test_confirm_rolls_back_the_whole_cart_when_one_line_is_out_of_stock(mock_mongodb):
    netflix, spotify = _offer("Netflix", stock=5), _offer("Spotify", stock=3)
    cart = _cart((netflix, 2), (spotify, 1))
    mock_mongodb.offers.update_one({"id": spotify}, {"$set": {"stock": 0}})

    with pytest.raises(site_orders_service.SiteOrderError, match="Stock insuffisant pour « Spotify »"):
        site_orders_service.confirm_cart(cart["reference"])

    assert _statuses(cart["reference"]) == {str(OrderStatus.MANUAL_REVIEW)}
    assert _stock(netflix) == 5


def test_deliver_requires_confirmation_then_records_the_note(mock_mongodb):
    offer = _offer("ChatGPT")
    cart = _cart((offer, 1))

    with pytest.raises(site_orders_service.SiteOrderError, match="Confirme d'abord"):
        site_orders_service.deliver_cart(cart["reference"])

    site_orders_service.confirm_cart(cart["reference"])
    site_orders_service.deliver_cart(cart["reference"], "Compte envoyé sur WhatsApp")

    listed = site_orders_service.list_carts({"status": ["delivered"]})["items"][0]
    assert listed["status"] == "delivered"
    assert listed["delivery_note"] == "Compte envoyé sur WhatsApp"
    assert listed["delivered_at"]


def test_cancel_confirmed_cart_returns_stock_and_blocks_delivered_carts(mock_mongodb):
    offer = _offer("Adobe", stock=4)
    confirmed, delivered = _cart((offer, 2)), _cart((offer, 1))
    site_orders_service.confirm_cart(confirmed["reference"])
    site_orders_service.confirm_cart(delivered["reference"])
    site_orders_service.deliver_cart(delivered["reference"])
    assert _stock(offer) == 1

    site_orders_service.cancel_cart(confirmed["reference"], "Client injoignable")

    assert _statuses(confirmed["reference"]) == {str(OrderStatus.CANCELLED)}
    assert _stock(offer) == 3
    with pytest.raises(site_orders_service.SiteOrderError, match="ne peut plus être annulé"):
        site_orders_service.cancel_cart(delivered["reference"], "Trop tard")


def test_cancel_unverified_cart_leaves_stock_untouched(mock_mongodb):
    offer = _offer("Figma", stock=4)
    cart = _cart((offer, 2))
    site_orders_service.cancel_cart(cart["reference"], "Reçu jamais reçu")
    assert _statuses(cart["reference"]) == {str(OrderStatus.CANCELLED)}
    assert _stock(offer) == 4


def test_unknown_reference_is_reported(mock_mongodb):
    with pytest.raises(site_orders_service.SiteOrderError, match="introuvable"):
        site_orders_service.confirm_cart("TN-ZZZZZZ")
