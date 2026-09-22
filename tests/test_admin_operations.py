from __future__ import annotations

import database as db
from app.web import dashboard_api


def test_rejected_withdrawal_restores_reserved_wallet_balance(mock_mongodb):
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 5000})
    withdrawal = db.create_withdrawal(42, 15, "bep20", "0xabc")

    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 3500
    rejected = db.reject_withdrawal(withdrawal["id"], "Destination invalide")

    assert rejected["status"] == "rejected"
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 5000
    assert db.reject_withdrawal(withdrawal["id"], "Second attempt") is None
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 5000


def test_warranty_refund_uses_existing_bot_workflow_once(mock_mongodb):
    request = db.create_warranty_request(42, 9, 2, 7.5, "Account stopped working")

    assert db.accept_warranty_request(request["id"])["status"] == "accepted"
    refunded = db.resolve_warranty_request(request["id"], "refund", "Approved on site")

    assert refunded["status"] == "refunded"
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 750
    assert db.resolve_warranty_request(request["id"], "refund") is None
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 750


def test_dashboard_lists_enriched_withdrawals_and_warranties(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer", "full_name": "Buyer"})
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 5000})
    mock_mongodb.orders.insert_one({"id": 9, "user_id": 42, "offer_name": "Premium account", "status": "delivered", "warranty": "30 j"})
    withdrawal = db.create_withdrawal(42, 10, "binance", "123456")
    warranty = db.create_warranty_request(42, 9, 1, 9, "Login failed")

    withdrawals = dashboard_api.list_withdrawals({"status": ["pending"]})
    warranties = dashboard_api.list_warranties({"status": ["pending_admin_check"]})

    assert withdrawals["items"][0]["id"] == withdrawal["id"]
    assert withdrawals["items"][0]["username"] == "buyer"
    assert withdrawals["items"][0]["amount"] == 10
    assert warranties["items"][0]["id"] == warranty["id"]
    assert warranties["items"][0]["product"] == "Premium account"
    assert warranties["items"][0]["warranty"] == "30 j"
