"""Storefront dinar wallet: receipts, deposits, admin review and adjustments."""

import pytest

from app.domain import storefront_receipt_service, storefront_wallet_service
from tests.conftest import RECEIPT

wallet = storefront_wallet_service


@pytest.fixture
def customer(site_customer):
    return site_customer()


def _deposit(customer, **overrides):
    payload = {"method": "d17", "amount": "25,5", "transaction_reference": "D17-445566", "receipt": RECEIPT}
    return wallet.create_deposit(customer, {**payload, **overrides})["deposit"]


@pytest.mark.parametrize("value, millimes", [("25", 25000), ("25,5", 25500), ("0.125", 125), (" 1 000 ", 1_000_000)])
def test_parse_amount_reads_dinars_as_millimes(value, millimes):
    assert wallet.parse_amount(value) == millimes


@pytest.mark.parametrize("value", ["", "abc", "-5", "1,2345"])
def test_parse_amount_rejects_invalid_input(value):
    with pytest.raises(wallet.WalletError):
        wallet.parse_amount(value)


def test_credit_and_debit_keep_a_ledger_and_never_go_negative(mock_mongodb, customer):
    assert wallet.credit(customer["id"], 10000, kind="deposit") == 10000
    assert wallet.debit(customer["id"], 4000, kind="purchase", reference="TN-ABC") == 6000
    assert wallet.debit(customer["id"], 4000, kind="purchase", reference="TN-ABC") == 6000
    assert wallet.debit(customer["id"], 7000, kind="purchase") is None
    assert wallet.balance(customer["id"]) == 6000

    summary = wallet.summary(customer)
    assert [(row["label"], row["amount_millimes"]) for row in summary["transactions"]] == [("Achat", -4000), ("Recharge", 10000)]
    assert summary["transactions"][0]["balance_after_millimes"] == 6000


def test_receipts_must_be_real_images(mock_mongodb):
    receipt_id = storefront_receipt_service.store(RECEIPT, customer_id=1, purpose="deposit")
    data, content_type = storefront_receipt_service.load(receipt_id)
    assert content_type == "image/png"
    assert data.startswith(b"\x89PNG")
    assert storefront_receipt_service.load("nope") is None

    for bad in ["", "data:text/html;base64,PGI+", "data:image/jpeg;base64,iVBORw0KGgo="]:
        with pytest.raises(storefront_receipt_service.ReceiptError):
            storefront_receipt_service.store(bad, customer_id=1, purpose="deposit")


def test_deposit_is_pending_until_the_admin_approves_it(mock_mongodb, customer, sent_emails):
    deposit = _deposit(customer)

    assert deposit["status"] == "pending"
    assert deposit["amount_millimes"] == 25500
    assert wallet.balance(customer["id"]) == 0
    assert "25,500 DT" in sent_emails[-1]["text"]

    listed = wallet.list_deposits({})
    assert listed["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    assert listed["items"][0]["receipt_id"]
    assert listed["items"][0]["customer_email"] == "amine@example.com"

    result = wallet.approve_deposit(deposit["id"], "25")
    assert result["credited_millimes"] == 25000
    assert wallet.balance(customer["id"]) == 25000
    assert "25,000 DT" in sent_emails[-1]["text"]
    with pytest.raises(wallet.WalletError, match="déjà été traitée"):
        wallet.approve_deposit(deposit["id"])
    assert wallet.summary(customer)["deposits"][0]["credited_millimes"] == 25000


def test_rejected_deposit_needs_a_reason_and_frees_its_reference(mock_mongodb, customer, sent_emails):
    deposit = _deposit(customer)
    with pytest.raises(wallet.WalletError, match="motif"):
        wallet.reject_deposit(deposit["id"], " ")

    wallet.reject_deposit(deposit["id"], "Aucun virement reçu")

    assert wallet.balance(customer["id"]) == 0
    assert "Aucun virement reçu" in sent_emails[-1]["text"]
    assert _deposit(customer)["status"] == "pending"


@pytest.mark.parametrize("overrides, message", [
    ({"method": "paypal"}, "D17"),
    ({"amount": "0,5"}, "compris entre"),
    ({"amount": "6000"}, "compris entre"),
    ({"transaction_reference": "1"}, "référence"),
    ({"receipt": ""}, "capture"),
])
def test_invalid_deposits_are_rejected(mock_mongodb, customer, overrides, message):
    with pytest.raises(wallet.WalletError, match=message):
        _deposit(customer, **overrides)


def test_deposit_references_are_unique_and_pending_requests_are_capped(mock_mongodb, customer):
    _deposit(customer)
    with pytest.raises(wallet.WalletError, match="déjà été déclarée"):
        _deposit(customer, transaction_reference="d17-445566")
    _deposit(customer, transaction_reference="D17-2")
    _deposit(customer, transaction_reference="D17-3")
    with pytest.raises(wallet.WalletError, match="en attente"):
        _deposit(customer, transaction_reference="D17-4")


def test_admin_adjustment_credits_or_debits_with_a_note(mock_mongodb, customer):
    assert wallet.adjust(customer["id"], "+10", "Geste commercial")["balance_millimes"] == 10000
    assert wallet.adjust(customer["id"], "-2,5", "Correction")["balance_millimes"] == 7500
    with pytest.raises(wallet.WalletError, match="insuffisant"):
        wallet.adjust(customer["id"], "-100", "Trop")
    with pytest.raises(wallet.WalletError, match="motif"):
        wallet.adjust(customer["id"], "5", "")
    with pytest.raises(wallet.WalletError, match="introuvable"):
        wallet.adjust(999, "5", "Test")
    assert wallet.summary(customer)["transactions"][0]["note"] == "Correction"
