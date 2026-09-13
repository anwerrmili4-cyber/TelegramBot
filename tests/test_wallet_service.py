"""Tests for verified wallet top-ups and balance usage."""

import pytest

import database as db
from app.domain import order_service, payment_service, wallet_service


def test_verified_topup_credits_real_transfer_amount(mock_mongodb, monkeypatch):
    monkeypatch.setattr(wallet_service, "verify_incoming_transfer", lambda *_args, **_kwargs: {
        "status": "confirmed", "amount": 12.5, "currency": "USDT",
    })

    result = wallet_service.claim_transfer(42, "TXID_TOPUP_123")

    assert result["status"] == "confirmed"
    assert result["amount"] == 12.5
    assert result["balance"] == 12.5


def test_topup_txid_cannot_be_used_twice(mock_mongodb, monkeypatch):
    monkeypatch.setattr(wallet_service, "verify_incoming_transfer", lambda *_args, **_kwargs: {
        "status": "confirmed", "amount": 5.0, "currency": "USDT",
    })
    assert wallet_service.claim_transfer(42, "TXID_UNIQUE_123")["status"] == "confirmed"
    assert wallet_service.claim_transfer(99, "TXID_UNIQUE_123")["code"] == "already_used"


def test_bybit_topup_credits_verified_real_amount(mock_mongodb, monkeypatch):
    monkeypatch.setattr(
        wallet_service,
        "verify_bybit_incoming_transfer",
        lambda *_args, **_kwargs: {
            "status": "confirmed", "amount": 7.25, "currency": "USDT",
        },
    )

    result = wallet_service.claim_transfer(
        42, "BYBIT_TOPUP_123", provider="bybit",
    )

    assert result["status"] == "confirmed"
    assert result["amount"] == 7.25
    assert result["balance"] == 7.25
    saved = mock_mongodb.wallet_topups.find_one({"txid": "BYBIT_TOPUP_123"})
    assert saved["provider"] == "bybit"


def test_topup_txid_cannot_be_reused_across_providers(mock_mongodb, monkeypatch):
    monkeypatch.setattr(
        wallet_service,
        "verify_bybit_incoming_transfer",
        lambda *_args, **_kwargs: {
            "status": "confirmed", "amount": 2.0, "currency": "USDT",
        },
    )
    monkeypatch.setattr(
        wallet_service,
        "verify_incoming_transfer",
        lambda *_args, **_kwargs: {
            "status": "confirmed", "amount": 2.0, "currency": "USDT",
        },
    )

    assert wallet_service.claim_transfer(
        42, "SHARED_TXID_123", provider="bybit",
    )["status"] == "confirmed"
    assert wallet_service.claim_transfer(
        42, "SHARED_TXID_123", provider="binance",
    )["code"] == "already_used"


def test_onchain_topup_is_automatically_verified_and_credited(
    mock_mongodb, monkeypatch,
):
    monkeypatch.setattr(
        wallet_service, "verify_onchain_usdt",
        lambda *_args, **_kwargs: {"status": "confirmed", "code": "confirmed"},
    )
    submitted = wallet_service.submit_onchain_topup(
        42, "0x" + "a" * 64, 8.5, "polygon",
    )

    assert submitted["status"] == "confirmed"
    assert submitted["balance"] == 8.5
    assert wallet_service.balance_cents(42) == 850
    saved = mock_mongodb.wallet_topups.find_one({"id": submitted["id"]})
    assert saved["verification_method"] == "automatic_onchain"


def test_token_conversion_calculation_is_preserved():
    assert wallet_service.convert_token_amount_to_usdt_cents(0.25, 80.0) == 2000


def test_solana_scan_credits_only_balance_increase_once(mock_mongodb, monkeypatch):
    monkeypatch.setattr(
        wallet_service, "get_recent_balance_increase",
        lambda *_args: {
            "status": "confirmed", "signature": "S" * 64,
            "sol_amount": 0.02, "current_lamports": 30023580,
            "received_at": 1_700_000_000,
        },
    )
    monkeypatch.setattr(
        wallet_service, "fetch_sol_usdt_quote",
        lambda: {"status": "confirmed", "price": 150.0, "source": "test"},
    )

    result = wallet_service.submit_solana_scan(42, 1_700_000_000)

    assert result["status"] == "confirmed"
    assert result["amount"] == 3.0
    saved = mock_mongodb.wallet_topups.find_one({"txid": "S" * 64})
    assert saved["baseline_lamports"] == 10023580
    assert saved["balance_after_lamports"] == 30023580
    assert wallet_service.submit_solana_scan(42, 1_700_000_000)["code"] == "already_used"


def test_wallet_pays_order_and_reduces_external_total(mock_mongodb):
    db.add_service("AI", "🤖")
    offer_id = db.add_offer(1, "Premium", 10.0, 1)
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1000})

    order = order_service.create_order(42, db.get_offer(offer_id), payment_method="wallet")

    assert order["wallet_amount"] == 10.0
    assert order["total_price"] == 0.0
    assert wallet_service.balance_cents(42) == 0


def test_partial_wallet_balance_reduces_amount_left_for_binance(mock_mongodb):
    db.add_service("AI", "T")
    offer_id = db.add_offer(1, "Premium", 10.0, 1)
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 300})

    order = order_service.create_order(
        42, db.get_offer(offer_id), payment_method="wallet"
    )

    assert order["wallet_amount"] == 3.0
    assert order["total_price"] == 7.0
    assert order["payment_method"] == "wallet_binance"
    assert wallet_service.balance_cents(42) == 0


def test_wallet_button_rejects_an_empty_balance(mock_mongodb):
    db.add_service("AI", "T")
    offer_id = db.add_offer(1, "Premium", 10.0, 1)

    with pytest.raises(ValueError, match="Insufficient balance: 0.00 USDT available"):
        order_service.create_order(
            42, db.get_offer(offer_id), payment_method="wallet"
        )


def test_full_wallet_payment_confirms_and_delivers(mock_mongodb):
    db.add_service("AI", "T")
    offer_id = db.add_offer(1, "Premium", 10.0, 0)
    db.add_inventory_items(offer_id, ["delivered_from_wallet"])
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1000})
    order = order_service.create_order(
        42, db.get_offer(offer_id), payment_method="wallet"
    )

    result = payment_service.confirm_wallet_order(order["id"], 42)

    assert result["status"] == "delivered"
    assert result["delivered_content"] == ["delivered_from_wallet"]
    assert db.get_order(order["id"])["verify_method"] == "wallet"


def test_bulk_wallet_credit_is_applied_once_per_user(mock_mongodb):
    for user_id in (10, 20, 30):
        db.upsert_user(user_id, f"user{user_id}", f"User {user_id}")
    mock_mongodb.wallets.insert_one({"user_id": 20, "balance_cents": 125})

    first = wallet_service.credit_all_users(2.50, "bulk_credit_test_123", 999)
    second = wallet_service.credit_all_users(2.50, "bulk_credit_test_123", 999)

    assert first["user_count"] == 3
    assert first["credited_count"] == 3
    assert second["credited_count"] == 0
    assert second["already_credited_count"] == 3
    assert wallet_service.balance_cents(10) == 250
    assert wallet_service.balance_cents(20) == 375
    assert wallet_service.balance_cents(30) == 250


def test_bulk_wallet_credit_rejects_invalid_amount(mock_mongodb):
    with pytest.raises(ValueError, match="compris entre"):
        wallet_service.credit_all_users(0, "bulk_credit_test_456", 999)


def test_admin_can_credit_and_debit_one_wallet(mock_mongodb):
    db.upsert_user(42, "buyer", "Buyer")

    credited = wallet_service.adjust_balance(42, 25, 999, "Bonus")
    debited = wallet_service.adjust_balance(42, -7.50, 999, "Correction")

    assert credited["balance"] == 25
    assert debited["balance"] == 17.5
    assert wallet_service.balance_cents(42) == 1750
    audit = mock_mongodb.audit_events.find_one({"action": "wallet.admin_adjustment"})
    assert audit["actor_id"] == 999
    assert audit["details"]["user_id"] == 42


def test_admin_wallet_debit_cannot_make_balance_negative(mock_mongodb):
    db.upsert_user(42, "buyer", "Buyer")
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 500})

    with pytest.raises(ValueError, match="Solde insuffisant"):
        wallet_service.adjust_balance(42, -5.01, 999)

    assert wallet_service.balance_cents(42) == 500
