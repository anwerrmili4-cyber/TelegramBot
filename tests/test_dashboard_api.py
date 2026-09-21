"""Tests for server-side dashboard filters and pagination."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from datetime import UTC, datetime

import pytest

from api.dashboard import render_dashboard
from app.web import dashboard_api


def test_order_filters_and_pagination(mock_mongodb):
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 10, "offer_id": 5, "offer_name": "Alpha", "service_name": "AI", "status": "pending_payment", "created_at": 1},
        {"id": 2, "user_id": 20, "offer_id": 6, "offer_name": "Beta", "service_name": "Video", "status": "delivered", "created_at": 2},
        {"id": 3, "user_id": 10, "offer_id": 5, "offer_name": "Alpha Plus", "service_name": "AI", "status": "delivered", "created_at": 3},
    ])
    result = dashboard_api.list_orders({"status": ["delivered"], "page": ["1"], "per_page": ["1"]})

    assert result["total"] == 2
    assert result["pages"] == 2
    assert result["items"][0]["id"] == 3
    assert result["analytics"]["total"] == 3
    assert result["analytics"]["delivered"] == 2
    assert result["analytics"]["statuses"] == {"pending_payment": 1, "delivered": 2}


def test_order_analytics_exclude_admin_purchases_but_keep_order_history(monkeypatch, mock_mongodb):
    monkeypatch.setattr("config.ADMIN_ID", 999)
    now = int(time.time())
    mock_mongodb.orders.insert_many([
        {"id": 10, "user_id": 42, "status": "delivered", "total_price": 8.0, "created_at": now},
        {"id": 11, "user_id": 999, "status": "delivered", "total_price": 200.0, "created_at": now},
    ])

    result = dashboard_api.list_orders({})

    assert result["total"] == 2
    assert {item["id"] for item in result["items"]} == {10, 11}
    assert result["analytics"]["total"] == 1
    assert result["analytics"]["delivered"] == 1
    assert result["analytics"]["revenue"] == 8.0


def test_pending_onchain_topups_include_customer_and_explorer(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer", "first_name": "Buyer"})
    mock_mongodb.wallet_topups.insert_many([
        {
            "id": 7,
            "user_id": 42,
            "txid": "0xabcdef1234567890",
            "amount_cents": 1250,
            "currency": "USDT",
            "network": "bsc",
            "verification_method": "manual_onchain",
            "status": "manual_review",
            "created_at": 10,
        },
        {
            "id": 8,
            "user_id": 42,
            "txid": "ignored",
            "amount_cents": 500,
            "network": "polygon",
            "verification_method": "manual_onchain",
            "status": "confirmed",
            "created_at": 20,
        },
    ])

    result = dashboard_api.list_wallet_topups({"status": ["manual_review"]})

    assert result["total"] == 1
    assert result["items"][0]["username"] == "buyer"
    assert result["items"][0]["amount"] == 12.5
    assert result["items"][0]["explorer_url"].startswith("https://bscscan.com/tx/")


def test_wallet_topup_history_includes_every_provider_and_paginates(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 10, "username": "alice"},
        {"telegram_id": 20, "first_name": "Bob"},
    ])
    mock_mongodb.wallet_topups.insert_many([
        {"txid": "BINANCE-ONE", "user_id": 10, "amount_cents": 500, "currency": "USDT", "provider": "binance", "created_at": 10},
        {"id": 2, "txid": "SOLANA-TWO", "user_id": 20, "amount_cents": 750, "currency": "USDT", "source_currency": "SOL", "source_amount": 0.05, "network": "solana", "status": "confirmed", "created_at": 20},
        {"id": 3, "txid": "POLYGON-THREE", "user_id": 20, "amount_cents": 900, "network": "polygon", "status": "rejected", "created_at": 30},
    ])

    first_page = dashboard_api.list_wallet_topups({"status": ["all"], "page": ["1"], "per_page": ["2"]})
    confirmed = dashboard_api.list_wallet_topups({"status": ["confirmed"]})
    alice = dashboard_api.list_wallet_topups({"search": ["alice"], "search_field": ["customer"]})

    assert first_page["total"] == 3
    assert first_page["pages"] == 2
    assert [item["provider"] for item in first_page["items"]] == ["polygon", "solana"]
    assert confirmed["summary"]["confirmed_amount"] == 12.5
    assert {item["provider"] for item in confirmed["items"]} == {"binance", "solana"}
    assert alice["items"][0]["username"] == "alice"


def test_customer_filters_and_metric_sort(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 10, "username": "active", "banned": False, "created_at": 10},
        {"telegram_id": 20, "username": "blocked", "banned": True, "created_at": 20},
        {"telegram_id": 30, "username": "empty", "banned": False, "created_at": 30},
    ])
    mock_mongodb.wallets.insert_many([
        {"user_id": 10, "balance_cents": 500},
        {"user_id": 20, "balance_cents": 1200},
    ])
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 10, "status": "delivered", "total_price": 4},
        {"id": 2, "user_id": 20, "status": "delivered", "total_price": 9},
        {"id": 3, "user_id": 20, "status": "delivered", "total_price": 3},
    ])

    active_funded = dashboard_api.list_customers({
        "status": ["active"],
        "wallet": ["funded"],
    })
    without_orders = dashboard_api.list_customers({"orders": ["without_orders"]})
    by_balance = dashboard_api.list_customers({"sort": ["balance"]})

    assert [item["telegram_id"] for item in active_funded["items"]] == [10]
    assert [item["telegram_id"] for item in without_orders["items"]] == [30]
    assert [item["telegram_id"] for item in by_balance["items"]] == [20, 10, 30]


def test_order_search_matches_numeric_customer(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 9,
        "user_id": 12345,
        "offer_name": "Netflix",
        "service_name": "VOD",
        "status": "delivered",
        "created_at": 1,
    })

    result = dashboard_api.list_orders({"search": ["12345"]})

    assert result["total"] == 1


def test_order_search_can_target_txid_or_product_name(mock_mongodb):
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 10, "offer_name": "ChatGPT Plus", "txid": "TX-ALPHA-99", "created_at": 1},
        {"id": 2, "user_id": 20, "offer_name": "Canva Pro", "txid": "TX-BETA-12", "created_at": 2},
    ])

    by_txid = dashboard_api.list_orders({"search": ["alpha"], "search_field": ["txid"]})
    by_name = dashboard_api.list_orders({"search": ["canva"], "search_field": ["name"]})

    assert [item["id"] for item in by_txid["items"]] == [1]
    assert [item["id"] for item in by_name["items"]] == [2]


def test_order_date_service_and_amount_sort(mock_mongodb):
    mock_mongodb.offers.insert_many([{"id": 700, "service_id": 200}, {"id": 800, "service_id": 300}])
    mock_mongodb.orders.insert_many([
        {"id": 1, "offer_id": 700, "total_price": 5.0, "created_at": 100},
        {"id": 2, "offer_id": 700, "total_price": 12.0, "created_at": 200},
        {"id": 3, "offer_id": 800, "total_price": 50.0, "created_at": 200},
    ])

    result = dashboard_api.list_orders({"service_id": ["200"], "sort": ["amount"]})

    assert [item["id"] for item in result["items"]] == [2, 1]


def test_order_attention_queue_and_customer_names(mock_mongodb, monkeypatch):
    now = 2_000_000
    monkeypatch.setattr(dashboard_api.time, "time", lambda: now)
    mock_mongodb.users.insert_many([
        {"telegram_id": 10, "username": "alice"},
        {"telegram_id": 20, "first_name": "Bob"},
    ])
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 10, "status": "manual_review", "created_at": now - 10},
        {"id": 2, "user_id": 20, "status": "preparing_delivery", "created_at": now - 1000},
        {"id": 3, "user_id": 30, "status": "preparing_delivery", "created_at": now - 20},
        {"id": 4, "user_id": 40, "status": "delivered", "created_at": now - 2000},
    ])

    result = dashboard_api.list_orders({"queue": ["attention"]})

    assert [item["id"] for item in result["items"]] == [1, 2]
    assert result["items"][0]["customer_name"] == "@alice"
    assert result["items"][1]["customer_name"] == "Bob"
    assert result["items"][1]["attention_reason"] == "Livraison en retard"
    assert all(item["needs_attention"] for item in result["items"])


def test_order_attention_queue_combines_with_search(mock_mongodb, monkeypatch):
    now = 2_000_000
    monkeypatch.setattr(dashboard_api.time, "time", lambda: now)
    mock_mongodb.orders.insert_many([
        {"id": 10, "user_id": 1, "offer_name": "Wanted", "status": "stock_issue", "created_at": now},
        {"id": 11, "user_id": 2, "offer_name": "Other", "status": "stock_issue", "created_at": now},
        {"id": 12, "user_id": 3, "offer_name": "Wanted", "status": "delivered", "created_at": now},
    ])

    result = dashboard_api.list_orders({"queue": ["attention"], "search": ["Wanted"]})

    assert [item["id"] for item in result["items"]] == [10]


def test_wallet_orders_show_and_sort_by_full_charged_amount(mock_mongodb):
    mock_mongodb.orders.insert_many([
        {"id": 1, "total_price": 5.0, "wallet_amount": 0.0, "status": "delivered", "created_at": 1},
        {"id": 2, "total_price": 0.0, "wallet_amount": 12.0, "status": "delivered", "created_at": 2},
    ])

    result = dashboard_api.list_orders({"sort": ["amount"]})

    assert [item["id"] for item in result["items"]] == [2, 1]
    assert result["items"][0]["charged_total"] == 12.0
    assert result["analytics"]["revenue"] == 17.0


def test_ticket_filters(mock_mongodb):
    now = datetime.now(UTC)
    mock_mongodb.support_tickets.insert_many([
        {"id": 1, "user_id": 10, "status": "waiting_admin", "updated_at": now},
        {"id": 2, "user_id": 10, "status": "closed", "updated_at": now},
    ])

    result = dashboard_api.list_tickets({"status": ["waiting_admin"]})

    assert result["total"] == 1
    assert result["items"][0]["id"] == 1


def test_ticket_search_uses_full_collection(mock_mongodb):
    mock_mongodb.support_tickets.insert_many([
        {"id": 4, "user_id": 10, "category": "Paiement", "message": "TXID manquant", "updated_at": 1},
        {"id": 5, "user_id": 20, "category": "Stock", "message": "Produit absent", "updated_at": 2},
    ])

    result = dashboard_api.list_tickets({"search": ["txid"], "search_field": ["message"]})

    assert [item["id"] for item in result["items"]] == [4]


def test_inventory_never_exposes_encrypted_payload(mock_mongodb):
    mock_mongodb.inventory.insert_one({
        "offer_id": 4,
        "payload": "encrypted-secret",
        "fingerprint": "hash",
        "masked_preview": "us***@example.com",
        "status": "available",
        "created_at": 1,
    })

    result = dashboard_api.list_inventory({"offer_id": ["4"]})

    assert result["total"] == 1
    assert result["items"][0]["masked_preview"] == "us***@example.com"
    assert "payload" not in result["items"][0]
    assert "fingerprint" not in result["items"][0]


def test_reseller_clients_include_safe_keys_wallet_and_api_metrics(mock_mongodb):
    now = int(time.time())
    mock_mongodb.users.insert_many([
        {"telegram_id": 42, "username": "reseller", "first_name": "API Buyer", "lang": "en", "created_at": 10},
        {"telegram_id": 99, "username": "revoked", "first_name": "Old Buyer", "created_at": 20},
    ])
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1250})
    mock_mongodb.buyer_api_keys.insert_many([
        {"id": 1, "user_id": 42, "prefix": "tgb_abcd1234", "key_hash": "secret-hash", "label": "Shop API", "active": True, "created_at": now - 100, "last_used_at": now - 10},
        {"id": 2, "user_id": 99, "prefix": "tgb_deadbeef", "key_hash": "other-secret-hash", "label": "Old API", "active": False, "created_at": now - 200, "revoked_at": now - 50},
    ])
    mock_mongodb.buyer_api_purchases.insert_many([
        {
            "buyer_key_id": 1, "idempotency_key": "successful-order", "user_id": 42,
            "order_id": 501, "status": "completed", "created_at": now,
            "response": {
                "success": True, "amount": 3.5, "productType": "Premium Account",
                "quantity": 2, "deliveredAccounts": ["must:not-leak"],
            },
        },
        {
            "buyer_key_id": 1, "idempotency_key": "failed-order", "user_id": 42,
            "status": "failed", "created_at": now - 5,
            "response": {"success": False, "code": "INSUFFICIENT_STOCK"},
        },
    ])

    result = dashboard_api.list_reseller_clients({"status": ["active"]})

    assert result["summary"] == {
        "clients": 2,
        "active_clients": 1,
        "active_keys": 1,
        "api_orders": 1,
        "total_spent": 3.5,
        "spent_30d": 3.5,
    }
    assert result["total"] == 1
    client = result["items"][0]
    assert client["telegram_id"] == 42
    assert client["wallet_balance"] == 12.5
    assert client["api_order_count"] == 1
    assert client["failed_order_count"] == 1
    assert client["keys"][0]["prefix"] == "tgb_abcd1234"
    assert "key_hash" not in str(result)
    assert "must:not-leak" not in str(result)


def test_reseller_clients_support_search_sort_and_pagination(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 10, "username": "small"},
        {"telegram_id": 20, "username": "large"},
    ])
    mock_mongodb.buyer_api_keys.insert_many([
        {"id": 1, "user_id": 10, "prefix": "tgb_small000", "key_hash": "small-hash", "active": True, "created_at": 1},
        {"id": 2, "user_id": 20, "prefix": "tgb_large000", "key_hash": "large-hash", "active": True, "created_at": 2},
    ])
    mock_mongodb.buyer_api_purchases.insert_one({
        "buyer_key_id": 2, "idempotency_key": "large-order", "user_id": 20,
        "created_at": int(time.time()), "response": {"success": True, "amount": 20},
    })

    searched = dashboard_api.list_reseller_clients({
        "search": ["large"], "search_field": ["username"], "sort": ["spent"],
        "page": ["1"], "per_page": ["1"],
    })

    assert searched["total"] == 1
    assert searched["items"][0]["telegram_id"] == 20
    assert searched["pages"] == 1


def test_customer_detail_metrics(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer", "created_at": 1})
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1234})
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 42, "status": "delivered", "total_price": 7.5, "created_at": 2},
        {"id": 2, "user_id": 42, "status": "pending_payment", "total_price": 3.0, "created_at": 3},
    ])

    customer = dashboard_api.customer_detail(42)

    assert customer is not None
    assert customer["order_count"] == 2
    assert customer["paid_order_count"] == 1
    assert customer["total_spent"] == 7.5
    assert customer["wallet_balance"] == 12.34


def test_customer_detail_returns_complete_order_history(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer"})
    mock_mongodb.orders.insert_many([
        {"id": index, "user_id": 42, "status": "delivered", "created_at": index}
        for index in range(1, 56)
    ])

    customer = dashboard_api.customer_detail(42)

    assert customer is not None
    assert len(customer["orders"]) == 55
    assert customer["orders"][0]["id"] == 55


def test_customer_detail_builds_complete_crm_profile(mock_mongodb):
    now = int(time.time())
    mock_mongodb.users.insert_many([
        {"telegram_id": 42, "username": "buyer", "first_name": "Sam", "created_at": 1},
        {"telegram_id": 77, "username": "friend"},
    ])
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1234})
    mock_mongodb.offers.insert_one({"id": 9, "name": "Pro Plan", "description": "Current catalog description"})
    mock_mongodb.orders.insert_one({
        "id": 7, "user_id": 42, "offer_id": 9, "offer_name": "Pro Plan",
        "status": "delivered", "total_price": 12, "created_at": now - 80,
    })
    mock_mongodb.wallet_topups.insert_one({
        "id": 3, "user_id": 42, "amount_cents": 2000, "provider": "binance",
        "status": "confirmed", "created_at": now - 70,
    })
    mock_mongodb.withdrawals.insert_one({
        "id": 4, "user_id": 42, "amount_cents": 500, "method": "USDT",
        "status": "completed", "created_at": now - 60,
    })
    mock_mongodb.support_tickets.insert_one({
        "id": 5, "user_id": 42, "message": "Need help", "status": "open",
        "created_at": now - 50, "updated_at": now - 49,
    })
    mock_mongodb.warranty_requests.insert_one({
        "id": 6, "user_id": 42, "order_id": 7, "reason": "Login issue",
        "refund_amount": 4, "status": "pending_admin_check", "created_at": now - 40,
        "updated_at": now - 39,
    })
    mock_mongodb.referrals.insert_one({
        "referrer_id": 42, "referred_id": 77, "valid": True, "created_at": now - 30,
    })
    mock_mongodb.affiliate_rewards.insert_one({
        "referrer_id": 42, "milestone": 1, "amount_cents": 200, "created_at": now - 20,
    })
    mock_mongodb.loyalty.insert_one({"user_id": 42, "level": "Gold", "discount_percent": 8})
    mock_mongodb.buyer_api_purchases.insert_one({
        "user_id": 42, "idempotency_key": "api-1", "created_at": now - 10,
        "response": {"success": True, "amount": 3},
    })
    mock_mongodb.audit_events.insert_one({
        "id": 8, "action": "wallet.admin_adjustment", "actor_id": 1,
        "details": {"user_id": 42, "amount_cents": 100, "balance_cents": 1234, "reason": "Bonus"},
        "created_at": datetime.now(UTC),
    })
    mock_mongodb.interaction_events.insert_one({
        "user_id": 42, "interaction_type": "button", "action": "catalog", "created_at": now,
    })

    customer = dashboard_api.customer_detail(42)

    assert customer is not None
    assert customer["orders"][0]["product_description"] == "Current catalog description"
    assert customer["deposit_total"] == 20
    assert customer["withdrawal_total"] == 5
    assert customer["affiliate_earned"] == 2
    assert customer["loyalty"]["level"] == "Gold"
    assert customer["referrals"][0]["customer"]["username"] == "friend"
    assert customer["wallet_adjustments"][0]["details"]["amount"] == 1
    assert customer["interaction_total"] == 1
    assert {event["type"] for event in customer["timeline"]} == {
        "order", "topup", "withdrawal", "ticket", "warranty", "reward", "adjustment",
    }


def test_live_admin_notifications_reference_real_entities(mock_mongodb):
    now = int(time.time())
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer"})
    mock_mongodb.orders.insert_many([
        {"id": 10, "user_id": 42, "offer_name": "Pro", "status": "manual_review", "created_at": now - 60},
        {"id": 11, "user_id": 42, "offer_name": "Done", "status": "delivered", "total_price": 8, "created_at": now - 30},
    ])
    mock_mongodb.wallet_topups.insert_one({
        "id": 20, "user_id": 42, "amount_cents": 1500, "status": "manual_review",
        "network": "bsc", "created_at": now - 20,
    })
    mock_mongodb.support_tickets.insert_one({
        "id": 30, "user_id": 42, "status": "waiting_admin", "message": "Help",
        "created_at": now - 15, "updated_at": now - 10,
    })
    mock_mongodb.withdrawals.insert_one({
        "id": 40, "user_id": 42, "amount_cents": 1000, "status": "pending",
        "method": "USDT", "created_at": now - 9,
    })
    mock_mongodb.warranty_requests.insert_one({
        "id": 50, "user_id": 42, "order_id": 11, "status": "pending_admin_check",
        "created_at": now - 8, "updated_at": now - 7,
    })
    mock_mongodb.offers.insert_one({
        "id": 60, "name": "Empty product", "active": 1, "stock": 0, "created_at": now - 6,
    })

    result = dashboard_api.list_admin_notifications()
    items = result["items"]
    categories = {item["category"] for item in items}

    assert {"order", "sale", "deposit", "support", "withdrawal", "warranty", "stock"} <= categories
    order = next(item for item in items if item["id"] == "order:10:manual_review")
    assert order["target"] == {"page": "orders", "entity_id": 10}
    assert "@buyer" in order["message"]
    assert result["summary"]["actionable"] >= 6
    assert result["summary"]["critical"] == 1


def test_order_detail_exposes_manual_delivery_and_customer(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer", "first_name": "Sam"})
    mock_mongodb.orders.insert_one({
        "id": 7,
        "user_id": 42,
        "status": "delivered",
        "delivery_text": "login@example.com\nsecret-password",
    })

    order = dashboard_api.order_detail(7)

    assert order is not None
    assert order["delivery_content"] == "login@example.com\nsecret-password"
    assert order["customer"]["username"] == "buyer"


def test_order_detail_decrypts_automatic_delivery(mock_mongodb):
    import database as db

    cipher = db._fernet()
    mock_mongodb.orders.insert_one({
        "id": 8,
        "user_id": 99,
        "status": "delivered",
        "delivery_text": "[encrypted automatic delivery]",
    })
    mock_mongodb.inventory.insert_many([
        {
            "id": 1,
            "delivered_order_id": 8,
            "status": "delivered",
            "payload": cipher.encrypt(b"first-login:first-secret").decode(),
        },
        {
            "id": 2,
            "delivered_order_id": 8,
            "status": "delivered",
            "payload": cipher.encrypt(b"second-login:second-secret").decode(),
        },
    ])

    order = dashboard_api.order_detail(8)

    assert order is not None
    assert order["delivery_content"] == (
        "first-login:first-secret\n\nsecond-login:second-secret"
    )


def test_dashboard_renders_mongodb_dates():
    page = render_dashboard({
        "summary": {},
        "orders": [],
        "users": [{"telegram_id": 1, "created_at": datetime.now(UTC)}],
        "tickets": [],
        "services": [],
        "audits": [],
    })

    assert "<!doctype html>" in page.lower()
    assert "customer-detail-modal" in page
    assert 'id="inventory-table"' in page
    assert "revealInventory" in page
    assert "toggleInventory" in page
    assert "/admin/api/inventory-export" in page


def test_dashboard_support_tab_has_real_page_link():
    page = render_dashboard({"summary": {}, "alerts": []}, active_tab="support")

    assert 'href="/admin/support" data-tab="support" class="active"' in page
    assert 'id="support" class="panel active"' in page


def test_dashboard_interactions_page_has_live_graphs_and_detail_table():
    page = render_dashboard({
        "summary": {},
        "alerts": [],
        "interactions": {
            "summary": {"total": 8, "today": 3, "active_today": 2, "live_users": 1},
            "daily": [{"date": "2026-07-26", "count": 3}],
            "service_clicks": {
                "total": 3,
                "services": [{"service_id": 7, "name": "Streaming", "count": 3}],
                "daily": [{
                    "date": "2026-07-26", "total": 3,
                    "services": [{"service_id": 7, "name": "Streaming", "count": 3}],
                }],
            },
            "types": {"button": 2, "message": 1},
            "events": [{
                "created_at": 1785024000,
                "user_id": 42,
                "full_name": "Test Buyer",
                "username": "buyer",
                "interaction_type": "button",
                "action": "buy:17",
                "content": "",
                "screen": "Offer screen",
            }],
        },
    }, active_tab="interactions")

    assert 'href="/admin/interactions"' in page
    assert 'id="interactions" class="panel active"' in page
    assert 'id="interactions-daily-chart"' in page
    assert 'id="service-clicks-daily"' in page
    assert "Services consultés par jour" in page
    assert "@media (max-width: 600px)" in page
    assert 'id="interactions-table"' in page
    assert "Interactions clients en direct" in page
    assert "__ACTIVE_" not in page
    assert "__PANEL_" not in page


def test_dashboard_contains_order_management_controls():
    page = render_dashboard({"summary": {}, "alerts": []}, active_tab="orders")

    assert "updateOrderAdmin" in page
    assert "manualDeliverOrder" in page
    assert "manual_deliver_order" in page
    assert "update_order_admin" in page


def test_dashboard_contains_product_sync_fields():
    page = render_dashboard({"summary": {}, "alerts": []}, active_tab="catalog")

    assert "Nouveau produit" in page
    assert "Catalogue par defaut" in page
    assert 'name="description"' in page
    assert 'name="initial_inventory"' in page
    assert "Comptes initiaux — stock automatique (# = 1 produit)" in page
    assert 'name="stock"' not in page
    assert "Livraison :" in page


def test_dashboard_has_mailreader_api_products_management():
    page = render_dashboard(
        {"summary": {}, "alerts": [], "services": []},
        active_tab="api-products",
        dashboard_write_token="safe-write-token",
    )

    assert 'href="/admin/api-products"' in page
    assert 'id="api-products" class="panel active"' in page
    assert "/admin/api/reseller-products" in page
    assert "save_reseller_product" in page
    assert "Centre des API" in page
    assert "Dashboard des API" in page
    assert "Shamekh’s bot" in page
    assert "selectApiProvider('shamekh')" in page
    assert "Kakao Shop" in page
    assert "selectApiProvider('kakao')" in page
    assert "VEX Reseller" in page
    assert "selectApiProvider('vex')" in page
    assert "Piggy AI" in page
    assert "selectApiProvider('canboso')" in page
    assert "GPT Cheap" in page
    assert "selectApiProvider('gpt_cheap')" in page
    assert "Shop Cron" in page
    assert "selectApiProvider('shop_cron')" in page
    assert "UPIBot Shop" in page
    assert "selectApiProvider('upibot')" in page
    assert "Clés Buyer API" in page
    assert "/api/swagger" in page
    assert "createBuyerApiKey" in page
    assert "revokeBuyerApiKey" in page
    assert "Produits & services" in page
    assert "Description, prix & garantie" in page
    assert "openApiProductEditor" in page
    assert "Votre prix client" in page
    assert "Service affiché dans le bot" in page
    assert "Créer un nouveau service" in page
    assert "Nom visible du produit" in page
    assert "Garantie affichée dans le bot" in page
    assert "Aperçu dans le bot" in page
    assert "Publier et revendre dans le bot" in page
    assert "low_stock_threshold" in page
    assert 'const dashboardWriteToken = "safe-write-token"' in page
    assert '"X-Dashboard-Write-Token": dashboardWriteToken' in page
    assert "__ACTIVE_" not in page
    assert "__PANEL_" not in page


def test_dashboard_attaches_write_token_to_every_admin_request():
    page = render_dashboard(
        {"summary": {}, "alerts": [], "services": []},
        active_tab="catalog",
        dashboard_write_token="safe-write-token",
    )

    assert "window.fetch = (input, options = {}) =>" in page
    assert 'requestUrl.pathname.startsWith("/admin")' in page
    assert 'headers.set("X-Dashboard-Write-Token", dashboardWriteToken)' in page
    assert 'credentials: "same-origin"' in page


def test_dashboard_uses_midnight_merchant_command_center():
    page = render_dashboard({
        "summary": {"orders": 2, "pending_orders": 1, "open_tickets": 1},
        "alerts": [],
        "services": [],
        "orders": [],
        "interactions": {"summary": {"live_users": 2, "active_today": 5}},
    })

    assert "Midnight Merchant" in page
    assert 'class="merchant-topbar"' in page
    assert 'id="overview-orders-table"' in page
    assert "Actions rapides" in page
    assert "Fournisseur API" in page
    assert "runGlobalSearch" in page
    assert "syncSupplierCatalog" in page


def test_dashboard_has_notification_center_without_auto_refresh():
    page = render_dashboard({"summary": {}, "alerts": []})

    assert 'id="notification-panel"' in page
    assert 'id="notification-badge"' in page
    assert "admin-notifications-v1" in page
    assert "Notification.requestPermission()" in page
    assert "setInterval(() => refreshDashboardData(true), 15000)" not in page
    assert 'document.addEventListener("visibilitychange"' not in page


def test_dashboard_contains_binance_health_test():
    page = render_dashboard({"summary": {}, "alerts": []}, active_tab="overview")

    assert "Tester Binance" in page
    assert "/admin/api/binance-health" in page
    assert "testBinanceConnection" in page


def test_dashboard_contains_telegram_webhook_repair():
    page = render_dashboard({"summary": {}, "alerts": []}, active_tab="overview")

    assert "Réparer Telegram" in page
    assert "/admin/api/telegram-health" in page
    assert "repair_telegram_webhook" in page


def test_dashboard_contains_bulk_wallet_credit_control():
    page = render_dashboard(
        {"summary": {}, "alerts": []},
        active_tab="customers",
        dashboard_write_token="safe-write-token",
    )

    assert 'action: "bulk_credit_wallets"' in page
    assert "CREDIT ALL" in page
    assert "bulk-wallet-amount" in page


def test_dashboard_javascript_syntax_is_valid(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is not installed")

    page = render_dashboard({"summary": {}, "alerts": [], "services": []}, active_tab="catalog")
    script = re.search(r"<script>(.*?)</script>", page, flags=re.S).group(1)
    script_path = tmp_path / "dashboard.js"
    script_path.write_text(script, encoding="utf-8")

    result = subprocess.run(["node", "--check", str(script_path)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
