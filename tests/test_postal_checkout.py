"""Postal checkout validation and administrator payment confirmation."""

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import site_orders_service, site_settings_service, storefront_service, storefront_wallet_service
from tests.conftest import RECEIPT


@pytest.fixture
def postal_cart(site_customer):
    customer = site_customer()
    service = db.add_service("Postal test", "", sales_channels=["tn_site"])
    offer = db.add_offer(
        service, "Manual delivery", 5.0, 3,
        sales_channels=["tn_site"], tn_price_millimes=15000,
    )
    return customer, offer, {
        "payment_method": "virement_postal",
        "receipt": RECEIPT,
        "idempotency_key": "postal-test-checkout",
        "items": [{"offer_id": offer, "quantity": 1}],
    }


@pytest.mark.parametrize("receipt", ["", "data:image/png;base64,bm90IGFuIGltYWdl"])
def test_postal_checkout_rejects_missing_or_invalid_capture(mock_mongodb, postal_cart, receipt):
    customer, offer, payload = postal_cart
    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.create_order({**payload, "receipt": receipt}, customer)
    assert mock_mongodb.orders.count_documents({}) == 0
    assert mock_mongodb.storefront_receipts.count_documents({}) == 0
    assert db.get_offer(offer)["stock"] == 3


def test_disabled_postal_method_cannot_create_an_order(mock_mongodb, postal_cart):
    customer, _, payload = postal_cart
    site_settings_service.save({
        "tnd_per_usdt": "3", "payment_d17": "1", "payment_virement_postal": "0",
        "details_d17": "21 000 000",
    })
    assert "virement_postal" not in site_settings_service.payment_methods()
    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.create_order(payload, customer)
    assert mock_mongodb.orders.count_documents({}) == 0
    assert mock_mongodb.storefront_receipts.count_documents({}) == 0


def test_postal_checkout_retries_and_admin_confirmation_preserve_money_and_stock(mock_mongodb, postal_cart):
    customer, offer, payload = postal_cart
    storefront_wallet_service.credit(customer["id"], 20000, kind="deposit")
    first = storefront_service.create_order(payload, customer)
    retry = storefront_service.create_order(payload, customer)
    assert retry["reference"] == first["reference"]
    assert first["status"] == "to_verify"
    assert mock_mongodb.orders.count_documents({}) == 1
    assert mock_mongodb.storefront_receipts.count_documents({}) == 1
    assert db.get_offer(offer)["stock"] == 3
    order = db.get_order(first["order_ids"][0])
    assert order["payment_method"] == "virement_postal"
    assert order["total_millimes"] == 15000
    assert order["paid_at"] is None
    assert order["status"] == OrderStatus.MANUAL_REVIEW
    confirmed = site_orders_service.confirm_cart(first["reference"])
    assert confirmed["waiting"] == 1
    assert db.get_order(order["id"])["status"] == OrderStatus.PAYMENT_CONFIRMED
    assert db.get_offer(offer)["stock"] == 2
    with pytest.raises(site_orders_service.SiteOrderError):
        site_orders_service.confirm_cart(first["reference"])
    assert db.get_offer(offer)["stock"] == 2
    assert storefront_wallet_service.balance(customer["id"]) == 20000
