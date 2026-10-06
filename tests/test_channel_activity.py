"""Admin activity across the bot, the Tunisian site, and the supplier API."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import admin
import database as db
from bot import cb_admin


def _seed_activity(mock_mongodb, *, admin_id=999):
    now = int(time.time())
    today_start = now - (now % 86400)

    def ago(seconds):
        return max(today_start, now - seconds)

    mock_mongodb.users.insert_many([
        {"telegram_id": 42, "created_at": ago(5)},
        {"telegram_id": admin_id, "created_at": today_start - 86400},
    ])
    db.log_interaction(42, interaction_type="button", action="home")
    mock_mongodb.storefront_customers.insert_one({
        "id": 7, "email": "amine@example.com", "email_verified": True, "created_at": now,
    })
    mock_mongodb.orders.insert_many([
        {
            "id": 10, "user_id": 42, "offer_name": "Netflix <Premium>",
            "status": "delivered", "total_price": 10.0, "created_at": ago(5),
        },
        {
            "id": 11, "user_id": 42, "offer_name": "Pending",
            "status": "pending_payment", "total_price": 4.0, "created_at": ago(4),
        },
        {
            "id": 12, "user_id": admin_id, "offer_name": "Admin sale",
            "status": "delivered", "total_price": 500.0, "created_at": ago(3),
        },
        {
            "id": 20, "sales_channel": "tn_site", "cart_reference": "TN-1", "cart_position": 1,
            "offer_name": "ChatGPT", "status": "manual_review",
            "total_millimes": 5000, "cart_total_millimes": 10000,
            "created_at": ago(8),
        },
        {
            "id": 21, "sales_channel": "tn_site", "cart_reference": "TN-1", "cart_position": 2,
            "offer_name": "Canva", "status": "manual_review",
            "total_millimes": 5000, "cart_total_millimes": 10000,
            "created_at": ago(7),
        },
        {
            "id": 22, "sales_channel": "tn_site", "cart_reference": "TN-2", "cart_position": 1,
            "offer_name": "Spotify", "status": "paid",
            "total_millimes": 7000, "cart_total_millimes": 7000,
            "created_at": today_start - 100, "paid_at": ago(1),
        },
    ])
    mock_mongodb.reseller_fulfillments.insert_many([
        {
            "order_id": 10, "provider": "mailreader", "external_order_id": "BM-10", "supplier_product_id": "sku-netflix",
            "status": "completed", "purchase_cost_total": 3.5, "purchase_cost_currency": "USDT",
            "created_at": ago(6), "updated_at": ago(3),
        },
        {
            "order_id": 22, "provider": "vex", "external_order_id": "BM-22", "supplier_product_id": "sku-spotify",
            "status": "purchasing", "purchase_cost_total": 1,
            "created_at": ago(2), "updated_at": ago(2),
        },
        {
            "order_id": 11, "provider": "mailreader", "external_order_id": "BM-11", "supplier_product_id": "old",
            "status": "completed", "purchase_cost_total": 9,
            "created_at": today_start - 86400, "updated_at": today_start - 86400,
        },
    ])
    return now


def test_channel_activity_splits_bot_site_and_supplier(monkeypatch, mock_mongodb):
    monkeypatch.setattr("config.ADMIN_ID", 999)
    _seed_activity(mock_mongodb)

    report = db.channel_activity()

    assert report["bot"]["online_now"] == 1
    assert report["bot"]["active_today"] == 1
    assert report["bot"]["users"] == 2
    assert report["bot"]["new_users_today"] == 1
    assert report["bot"]["orders_today"] == 2
    assert report["bot"]["paid_today"] == 1
    assert report["bot"]["revenue_today"] == 10.0
    assert report["site"]["customers"] == 1
    assert report["site"]["new_customers_today"] == 1
    assert report["site"]["carts_today"] == 1
    assert report["site"]["paid_carts_today"] == 1
    assert report["site"]["revenue_today_millimes"] == 7000
    assert report["site"]["to_verify"] == 1
    assert report["supplier"] == {
        "orders_today": 2,
        "from_bot_today": 1,
        "from_site_today": 1,
        "unlinked_today": 0,
        "pending": 1,
        "completed_today": 1,
        "cost_today": 4.5,
        "providers": [
            {"provider": "mailreader", "count": 1, "cost": 3.5},
            {"provider": "vex", "count": 1, "cost": 1.0},
        ],
    }
    assert {event["source"] for event in report["recent"]["all"]} == {"bot", "site", "supplier"}
    assert report["recent"]["site"][0]["reference"] == "TN-1"
    assert report["recent"]["site"][0]["title"] == "ChatGPT, Canva"
    assert report["recent"]["site"][0]["amount"] == 10000
    assert {event["reference"] for event in report["recent"]["site"]} == {"TN-1", "TN-2"}
    linked = {(event["provider"], event["channel"]) for event in report["recent"]["supplier"]}
    assert ("vex", "site") in linked
    assert ("mailreader", "bot") in linked


def test_channel_activity_screen_filters_each_source(monkeypatch, mock_mongodb):
    monkeypatch.setattr("config.ADMIN_ID", 999)
    _seed_activity(mock_mongodb)
    report = db.channel_activity()

    everything = admin.channel_activity_text(report, "all")
    site_only = admin.channel_activity_text(report, "site")
    supplier_only = admin.channel_activity_text(report, "supplier")
    fallback = admin.channel_activity_text(report, "nope")

    assert "Activité — bot, site et fournisseur" in everything
    assert "Netflix &lt;Premium&gt;" in everything
    assert "7.000 DT" in everything
    assert "Mailreader" in everything
    assert "via le site" in everything
    assert "via le bot" in everything
    assert "Paniers aujourd’hui" in site_only
    assert "En ligne" not in site_only
    assert "Fournisseur" not in site_only
    assert "Activité du fournisseur" in supplier_only
    assert "Paniers" not in supplier_only
    assert "En ligne" not in supplier_only
    assert "Activité — bot, site et fournisseur" in fallback

    callbacks = [
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    ]
    assert "adm_channel_activity" in callbacks
    keyboard = admin.channel_activity_keyboard("supplier")
    assert [button.callback_data for row in keyboard.inline_keyboard for button in row] == [
        "adm_channel_activity:bot",
        "adm_channel_activity:site",
        "adm_channel_activity:supplier",
        "adm_channel_activity:all",
        "adm_channel_activity:supplier",
        "adm_panel",
    ]
    assert keyboard.inline_keyboard[1][0].style == "success"
    assert keyboard.inline_keyboard[0][0].style == "primary"


def test_admin_opens_channel_activity_from_the_bot(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 7)
    monkeypatch.setattr("config.ADMIN_ID", 7)
    query = SimpleNamespace(
        data="adm_channel_activity:site",
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(text="panel"),
    )
    update = SimpleNamespace(callback_query=query)

    asyncio.run(cb_admin(update, SimpleNamespace()))

    text = query.edit_message_text.await_args.args[0]
    assert "Activité du site" in text
    assert "En ligne" not in text
    assert query.edit_message_text.await_args.kwargs["parse_mode"] == "HTML"
