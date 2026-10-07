"""Transfer references are claimed atomically across site orders and deposits."""

import time

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import storefront_service, storefront_wallet_service
from app.web import dashboard_api
from tests.conftest import RECEIPT


def _offer():
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(
        service_id, "ChatGPT Plus 1 mois", 6.0, 5,
        sales_channels=["bot", "tn_site"], tn_price_millimes=25000,
    )


def _order(customer, offer_id, reference="D17-555111"):
    return storefront_service.create_order({
        "payment_method": "d17",
        "transaction_reference": reference,
        "receipt": RECEIPT,
        "items": [{"offer_id": offer_id, "quantity": 1}],
    }, customer)


def test_a_fresh_claim_blocks_a_concurrent_submission(mock_mongodb):
    assert db.claim_payment_reference("d17", "ref-1", lambda: False)
    assert db.claim_payment_reference("d17", "ref-1", lambda: False) is None
    assert db.claim_payment_reference("flouci", "ref-1", lambda: False)


def test_a_stale_claim_is_taken_over_once_its_owner_is_gone(mock_mongodb):
    token = db.claim_payment_reference("d17", "ref-2", lambda: False)
    mock_mongodb.payment_reference_claims.update_one(
        {"_id": "d17:ref-2"},
        {"$set": {"created_at": int(time.time()) - db.PAYMENT_REFERENCE_CLAIM_GRACE_SECONDS - 1}},
    )

    assert db.claim_payment_reference("d17", "ref-2", lambda: True) is None
    replacement = db.claim_payment_reference("d17", "ref-2", lambda: False)
    assert replacement and replacement != token


def test_release_only_removes_the_matching_claim(mock_mongodb):
    token = db.claim_payment_reference("d17", "ref-3", lambda: False)
    db.release_payment_reference("d17", "ref-3", "someone-else")
    assert mock_mongodb.payment_reference_claims.count_documents({"_id": "d17:ref-3"}) == 1
    db.release_payment_reference("d17", "ref-3", token)
    assert mock_mongodb.payment_reference_claims.count_documents({"_id": "d17:ref-3"}) == 0


def test_a_deposit_cannot_reuse_a_reference_claimed_by_an_order(mock_mongodb, site_customer):
    customer = site_customer()
    _order(customer, _offer())

    with pytest.raises(storefront_wallet_service.WalletError, match="déjà été déclarée"):
        storefront_wallet_service.create_deposit(customer, {
            "method": "d17",
            "amount": "20",
            "transaction_reference": "d17-555111",
            "receipt": RECEIPT,
        })


def test_a_failed_receipt_gives_the_reference_back(mock_mongodb, site_customer):
    customer = site_customer()
    offer_id = _offer()
    with pytest.raises(storefront_service.StorefrontError):
        storefront_service.create_order({
            "payment_method": "d17",
            "transaction_reference": "D17-999000",
            "receipt": "not-an-image",
            "items": [{"offer_id": offer_id, "quantity": 1}],
        }, customer)

    assert mock_mongodb.payment_reference_claims.count_documents({}) == 0
    assert _order(customer, offer_id, reference="D17-999000")["reference"]


def test_a_cancelled_order_frees_its_reference_immediately(mock_mongodb, site_customer):
    customer = site_customer()
    offer_id = _offer()
    _order(customer, offer_id)
    with pytest.raises(storefront_service.StorefrontError, match="déjà été utilisée"):
        _order(customer, offer_id)
    mock_mongodb.orders.update_many({}, {"$set": {"status": OrderStatus.CANCELLED}})

    assert _order(customer, offer_id)["reference"]


def test_customers_sorted_by_spending_only_summarise_the_page(mock_mongodb, monkeypatch):
    mock_mongodb.users.insert_many([
        {"telegram_id": user_id, "created_at": user_id} for user_id in (1, 2, 3, 4)
    ])
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 3, "status": "delivered", "total_price": 9},
        {"id": 2, "user_id": 1, "status": "paid", "total_price": 4, "wallet_amount": 1},
        {"id": 3, "user_id": 2, "status": "cancelled", "total_price": 50},
    ])
    summarised = []
    original = dashboard_api._customer_summary

    def counting(user):
        summarised.append(user["telegram_id"])
        return original(user)

    monkeypatch.setattr(dashboard_api, "_customer_summary", counting)

    result = dashboard_api.list_customers({"sort": ["spent"], "per_page": ["2"]})

    assert [item["telegram_id"] for item in result["items"]] == [3, 1]
    assert result["total"] == 4 and result["pages"] == 2
    assert summarised == [3, 1]
