"""Regression tests for the customer-facing Telegram navigation."""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.constants import ParseMode
from telegram.ext import ApplicationHandlerStop

import database as db
import keyboards as kb
from app.domain import affiliate_service, support_service
from bot import (
    PENDING,
    admin_text_preview,
    announce_api_flash_sale,
    announce_channel_purchase,
    announce_channel_restock,
    announce_flash_sale,
    announce_restock_digest,
    announce_supplier_price_update,
    block_maintenance_users,
    block_non_channel_members,
    broadcast_admin_message,
    broadcast_maintenance_notice,
    cb_admin,
    cb_navigation,
    cmd_replacement,
    cmd_start,
    compact_offer_text,
    custom_emoji_from_message,
    custom_emojis_from_message,
    delete_broadcast_messages,
    deliver_order,
    handle_buy_confirmed,
    handle_pending_attachment,
    handle_pending_input,
    handle_ticket_attachment,
    monitor_codex_number_deadlines,
    _method_announcement_text,
    notify_admin_interaction,
    notify_successful_referral,
    numbered_delivery_content,
    on_text_menu,
    onchain_payment_screen,
    order_service_groups,
    orders_text_export,
    premium_customer_text,
    rich_text_from_message,
    send_admin_message_to_client,
    send_main_menu,
    send_payment_result,
    show_account,
    text_with_custom_emoji_tokens,
    text_without_custom_emojis,
    top_selling_products_text,
    topup_onchain_screen,
)
from i18n import t


def test_profile_uses_quote_panels_and_dedicated_navigation(mock_mongodb):
    mock_mongodb.users.insert_one({
        "telegram_id": 42,
        "first_name": "Anwer - BMC",
        "username": "Anwer_07",
        "lang": "en",
    })
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1250})
    mock_mongodb.orders.insert_many([
        {"id": 1, "user_id": 42, "status": "delivered", "total_price": 5.0},
        {"id": 2, "user_id": 42, "status": "pending", "total_price": 4.0},
    ])
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, full_name="Anwer - BMC"),
        effective_message=message,
    )

    asyncio.run(show_account(update, SimpleNamespace()))

    call = message.reply_text.await_args
    assert call.kwargs["parse_mode"] == ParseMode.HTML
    assert call.args[0].count("<blockquote>") == 2
    assert "Total Orders: <b>2</b>" in call.args[0]
    assert "Delivered: <b>1</b>" in call.args[0]
    assert "<code>ref_42</code>" in call.args[0]
    callbacks = {
        button.callback_data
        for row in call.kwargs["reply_markup"].inline_keyboard
        for button in row
    }
    assert {"topup", "orders", "affiliate", "catalog", "reseller_api", "home"} <= callbacks


def test_warranty_route_lists_active_products_and_explains_expired_warranty(mock_mongodb):
    now = int(time.time())
    mock_mongodb.orders.insert_many([
        {
            "id": 71, "user_id": 42, "status": "delivered",
            "offer_name": "Active subscription", "period_days": 30,
            "warranty_days": 3, "delivered_at": now - 5 * 86400,
        },
        {
            "id": 72, "user_id": 42, "status": "delivered",
            "offer_name": "Expired subscription", "period_days": 3,
            "warranty_days": 3, "delivered_at": now - 5 * 86400,
        },
    ])
    menu_query = SimpleNamespace(
        data="warranty", from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Menu", reply_text=AsyncMock()),
        answer=AsyncMock(), edit_message_text=AsyncMock(),
    )

    asyncio.run(cb_navigation(
        SimpleNamespace(callback_query=menu_query),
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
    ))

    markup = menu_query.edit_message_text.await_args.kwargs["reply_markup"]
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }
    assert "warranty_order:71" in callbacks
    assert "warranty_order:72" not in callbacks

    product_message = SimpleNamespace(reply_text=AsyncMock())
    product_query = SimpleNamespace(
        data="warranty_order:71", from_user=SimpleNamespace(id=42),
        message=product_message, answer=AsyncMock(),
    )
    asyncio.run(cb_navigation(
        SimpleNamespace(callback_query=product_query),
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
    ))

    notice = product_message.reply_text.await_args.args[0]
    assert "Product out of warranty" in notice
    assert "Active subscription" in notice
    assert "Product period: <b>30 days</b>" in notice
    assert PENDING.get(42) is None


def test_warranty_replacement_prompts_admin_and_delivers_content(mock_mongodb, monkeypatch):
    admin_id = 9001
    customer_id = 42
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    mock_mongodb.users.insert_one({"telegram_id": customer_id, "lang": "en"})
    mock_mongodb.warranty_requests.insert_one({
        "id": 3,
        "user_id": customer_id,
        "order_id": 280,
        "status": "accepted",
        "refund_amount": 1.0,
    })
    query_message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="adm_warranty_resolve:replacement:3",
        from_user=SimpleNamespace(id=admin_id),
        message=query_message,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    telegram_bot = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(cb_admin(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(bot=telegram_bot),
    ))

    assert PENDING.get(admin_id) == ("adm_warranty_replacement", 3)
    assert mock_mongodb.warranty_requests.find_one({"id": 3})["status"] == "replacement_pending"
    assert "Send the replacement account" in query_message.reply_text.await_args.args[0]

    admin_message = SimpleNamespace(
        text="new@example.com | replacement-password",
        reply_text=AsyncMock(),
    )
    asyncio.run(handle_pending_input(
        SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            message=admin_message,
        ),
        SimpleNamespace(bot=telegram_bot),
        "en",
    ))

    delivered_call = telegram_bot.send_message.await_args_list[-1]
    assert delivered_call.kwargs["chat_id"] == customer_id
    assert "new@example.com" in delivered_call.kwargs["text"]
    request = mock_mongodb.warranty_requests.find_one({"id": 3})
    assert request["status"] == "replacement_delivered"
    assert request["replacement_delivered_at"]
    assert PENDING.get(admin_id) is None
    assert "Replacement sent" in admin_message.reply_text.await_args.args[0]


def test_replacement_command_resumes_stuck_request(mock_mongodb, monkeypatch):
    admin_id = 9001
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    mock_mongodb.warranty_requests.insert_one({
        "id": 3,
        "user_id": 42,
        "order_id": 280,
        "status": "replacement_pending",
    })
    message = SimpleNamespace(reply_text=AsyncMock())

    asyncio.run(cmd_replacement(
        SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            effective_message=message,
        ),
        SimpleNamespace(args=["3"]),
    ))

    assert PENDING.get(admin_id) == ("adm_warranty_replacement", 3)
    assert "Your next text message" in message.reply_text.await_args.args[0]


def test_admin_update_sections_render_live_lists(mock_mongodb, monkeypatch):
    admin_id = 9001
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    mock_mongodb.offers.insert_one({
        "id": 7,
        "supplier_provider": "mailreader",
        "supplier_product_id": "sku-7",
    })
    mock_mongodb.orders.insert_one({
        "id": 81, "user_id": 42, "offer_id": 7,
        "offer_name": "API plan", "status": "paid",
        "total_price": 5.0, "paid_at": 100, "updated_at": 101,
    })
    mock_mongodb.warranty_requests.insert_one({
        "id": 3, "user_id": 42, "order_id": 81,
        "status": "pending_admin_check", "created_at": 100, "updated_at": 101,
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "mailreader", "external_order_id": "BM-81",
        "order_id": 81, "status": "delivery_pending",
        "created_at": 100, "updated_at": 101,
    })

    for callback, heading in [
        ("adm_warranties:0", "Warranty updates"),
        ("adm_payments:0", "Payment Confirmed"),
        ("adm_api_pending:0", "Livraison API en attente"),
    ]:
        query = SimpleNamespace(
            data=callback,
            from_user=SimpleNamespace(id=admin_id),
            message=SimpleNamespace(text="Admin panel", reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        asyncio.run(cb_admin(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        ))
        assert heading in query.edit_message_text.await_args.args[0]


def test_warranty_submission_sends_supplier_and_real_content_report(mock_mongodb, monkeypatch):
    admin_id = 9001
    customer_id = 42
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    mock_mongodb.users.insert_one({
        "telegram_id": customer_id,
        "first_name": "Buyer",
        "username": "buyer42",
        "lang": "en",
    })
    mock_mongodb.offers.insert_one({
        "id": 7,
        "service_id": 1,
        "name": "Supplier product",
        "supplier_provider": "mailreader",
        "supplier_product_id": "sku-7",
    })
    mock_mongodb.orders.insert_one({
        "id": 280,
        "user_id": customer_id,
        "offer_id": 7,
        "service_name": "Canva",
        "offer_name": "Canva panel",
        "status": "delivered",
        "unit_price": 9.0,
        "wallet_amount": 9.0,
        "total_price": 0,
        "currency": "USDT",
        "delivery_text": "[encrypted reseller delivery]",
        "delivered_at": 100,
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "mailreader",
        "external_order_id": "BM-280",
        "order_id": 280,
        "supplier_order_id": "SUP-99",
        "supplier_product_id": "sku-7",
        "status": "completed",
    })
    mock_mongodb.inventory.insert_one({
        "id": 90,
        "offer_id": 7,
        "delivered_order_id": 280,
        "status": "delivered",
        "payload": db._fernet().encrypt(b"real@example.com | secret").decode(),
    })
    PENDING[customer_id] = ("warranty_reason", {
        "order_id": 280,
        "days_used": 2,
        "refund": 1.25,
    })
    customer_message = SimpleNamespace(
        text="The supplier account no longer works",
        reply_text=AsyncMock(),
    )
    telegram_bot = SimpleNamespace(
        send_message=AsyncMock(),
        send_document=AsyncMock(),
    )

    asyncio.run(handle_pending_input(
        SimpleNamespace(
            effective_user=SimpleNamespace(id=customer_id, full_name="Buyer"),
            message=customer_message,
        ),
        SimpleNamespace(bot=telegram_bot),
        "en",
    ))

    request = mock_mongodb.warranty_requests.find_one({"order_id": 280})
    assert request["reason"] == "The supplier account no longer works"
    admin_report = telegram_bot.send_message.await_args.args[1]
    assert "mailreader" in admin_report
    assert "real@example.com | secret" in admin_report
    telegram_bot.send_document.assert_awaited_once()
    assert "real delivered content" in telegram_bot.send_document.await_args.kwargs["caption"]


def test_admin_can_create_method_without_image_and_activate_only_after_content(
    mock_mongodb, monkeypatch,
):
    admin_id = 9001
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    service_id = db.ensure_methods_service()
    admin_message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=f"adm_addoff:{service_id}",
        from_user=SimpleNamespace(id=admin_id),
        message=admin_message,
        answer=AsyncMock(),
    )

    asyncio.run(cb_admin(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(),
    ))
    assert PENDING.get(admin_id) == ("adm_addoff_image", service_id)

    def send_text(value):
        message = SimpleNamespace(text=value, reply_text=AsyncMock())
        asyncio.run(handle_pending_input(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), message=message),
            SimpleNamespace(),
            "en",
        ))
        return message

    send_text("skip")
    assert PENDING.get(admin_id)[0] == "adm_addoff_name"
    send_text("Python automation method")
    assert PENDING.get(admin_id)[0] == "adm_addoff_description"
    send_text("Step-by-step automation instructions")
    assert PENDING.get(admin_id)[0] == "adm_addoff_price"
    send_text("4.99")

    pending = PENDING.get(admin_id)
    assert pending[0] == "adm_method_media"
    offer_id = int(pending[1])
    offer = db.get_offer(offer_id)
    assert offer["active"] == 0
    assert offer["unlimited_stock"] is False
    assert offer["period_days"] == 0
    assert db.offer_has_stock(offer) is False

    send_text("Open this private guide: https://example.com/method")
    offer = db.get_offer(offer_id)
    assert offer["method_media"][0]["type"] == "text"
    assert offer["active"] == 0

    send_text("done")
    offer = db.get_offer(offer_id)
    assert PENDING.get(admin_id) is None
    assert offer["active"] == 1
    assert offer["unlimited_stock"] is True
    assert db.offer_has_stock(offer) is True


def test_empty_method_cannot_be_finished_and_text_delivery_is_supported(mock_mongodb, monkeypatch):
    from app.domain import payment_service

    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda *_args, **_kwargs: {"status": "confirmed", "reason": "test"},
    )

    service_id = db.ensure_methods_service()
    offer_id = db.add_offer(
        service_id, "Empty method", 4.0, 0,
        period_days=0, warranty_days=0, unlimited_stock=True, active=True,
    )
    offer = db.get_offer(offer_id)
    assert db.offer_has_stock(offer) is False

    db.update_offer(
        offer_id,
        method_media=[{"type": "text", "text": "Private method steps"}],
        active=True,
        unlimited_stock=True,
    )
    offer = db.get_offer(offer_id)
    assert db.offer_has_stock(offer) is True
    now = int(time.time())
    db.get_conn().orders.insert_one({
        "id": 999,
        "user_id": 42,
        "offer_id": offer_id,
        "service_name": "Methods",
        "offer_name": "Empty method",
        "qty": 1,
        "total_price": 4.0,
        "status": "pending_payment",
        "txid": "",
        "created_at": now - 10,
        "expires_at": now + 1800,
    })
    result = payment_service.submit_payment(999, "METHOD_TXID_123", 42)
    assert result["status"] == "delivered"
    assert result["delivered_content"] == ["__method_media__"]
    assert db.get_order(999)["status"] == "delivered"


def test_inventory_restock_is_broadcast_privately_to_all_bot_users(mock_mongodb):
    service_id = db.add_service("Chat GPT", "🤖")
    offer_id = db.add_offer(service_id, "Premium 30 days", 5.0, 3)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "en"},
    ])
    bot_client = SimpleNamespace(username="blackmarketa_bot", send_message=AsyncMock())

    sent = asyncio.run(announce_channel_restock(SimpleNamespace(bot=bot_client), offer_id, 3, 3))

    assert sent == 2
    assert bot_client.send_message.await_count == 2
    calls = bot_client.send_message.await_args_list
    assert {call.kwargs["chat_id"] for call in calls} == {101, 202}
    assert all(call.kwargs["chat_id"] != "@blackmarketBotChannel" for call in calls)
    assert all("NEW DROP AVAILABLE" in call.kwargs["text"] for call in calls)
    assert all("API" not in call.kwargs["text"] for call in calls)
    assert all("━━━━━━━━" not in call.kwargs["text"] for call in calls)
    assert all("🤖" in call.kwargs["text"] for call in calls)
    assert all(
        call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"buy:{offer_id}"
        for call in calls
    )


def test_catalog_updates_skip_customers_who_disabled_alerts(mock_mongodb):
    service_id = db.add_service("Chat GPT", "🤖")
    offer_id = db.add_offer(service_id, "Premium 30 days", 5.0, 3)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {
            "telegram_id": 202,
            "lang": "en",
            "catalog_notifications_enabled": False,
        },
    ])
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(
        announce_channel_restock(SimpleNamespace(bot=bot_client), offer_id, 3, 3)
    )

    assert sent == 1
    assert bot_client.send_message.await_args.kwargs["chat_id"] == 101


def test_catalog_updates_respect_each_customers_product_preferences(mock_mongodb):
    service_id = db.add_service("AI", "🤖")
    muted_offer_id = db.add_offer(service_id, "Muted product", 5.0, 3)
    followed_offer_id = db.add_offer(service_id, "Followed product", 6.0, 3)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "en"},
    ])
    db.set_product_notifications_enabled(202, muted_offer_id, False)
    bot_client = SimpleNamespace(send_message=AsyncMock())

    muted_sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client), muted_offer_id, 3, 3,
    ))
    muted_recipients = {
        call.kwargs["chat_id"] for call in bot_client.send_message.await_args_list
    }
    bot_client.send_message.reset_mock()
    followed_sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client), followed_offer_id, 3, 3,
    ))

    assert muted_sent == 1
    assert muted_recipients == {101}
    assert followed_sent == 2
    assert {
        call.kwargs["chat_id"] for call in bot_client.send_message.await_args_list
    } == {101, 202}


def test_profile_product_notification_callback_toggles_one_offer(monkeypatch):
    service_id = db.add_service("AI", "🤖")
    offer_id = db.add_offer(service_id, "Claude Pro", 5.0, 3)
    query = SimpleNamespace(
        data=f"profile_product_notification:{offer_id}:0",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Notifications"),
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert db.product_notifications_enabled(42, offer_id) is False
    markup = query.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    product_button = next(
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("profile_product_notification:")
    )
    assert product_button.text.startswith("🔕")


def test_catalog_notification_toggle_updates_preference_and_button(monkeypatch):
    query = SimpleNamespace(
        data="catalog_notifications_toggle",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Catalog"),
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert db.catalog_notifications_enabled(42) is False
    markup = query.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    toggle = next(
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data == "catalog_notifications_toggle"
    )
    assert "off" in toggle.text.lower()


def test_service_premium_emoji_is_included_in_customized_announcement(mock_mongodb):
    service_id = db.add_service(
        "Capcut", emoji="📦", custom_emoji_id="5978895591894161700",
    )
    offer_id = db.add_offer(service_id, "Capcut Pro", 5.0, 2)
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})
    db.set_text_override(
        "channel_stock_announcement",
        "en",
        "[[HTML]]{emoji} <b>{service}</b> — {offer}",
    )
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client), offer_id, 2, 2,
    ))

    assert sent == 1
    text = bot_client.send_message.await_args.kwargs["text"]
    assert "[[TGEMOJI:" not in text
    assert '<tg-emoji emoji-id="5978895591894161700">📦</tg-emoji>' in text
    assert "<b>Capcut</b> — Capcut Pro" in text


def test_schema_migration_removes_only_obsolete_announcement_designs(mock_mongodb):
    mock_mongodb.text_overrides.insert_many([
        {
            "key": "channel_stock_announcement", "lang": "en",
            "text": "❗ NEW STOCK JUST DROPPED ❗\n{emoji} {service}",
        },
        {
            "key": "flash_sale_announcement", "lang": "fr",
            "text": "🔥 Vente flash personnalisée {service}",
        },
        {
            "key": "welcome", "lang": "en",
            "text": "NEW STOCK JUST DROPPED is harmless here",
        },
    ])

    removed = db._remove_legacy_announcement_overrides(mock_mongodb)

    assert removed == 1
    assert mock_mongodb.text_overrides.find_one({
        "key": "channel_stock_announcement", "lang": "en",
    }) is None
    assert mock_mongodb.text_overrides.find_one({
        "key": "flash_sale_announcement", "lang": "fr",
    })["text"].startswith("🔥")
    assert mock_mongodb.text_overrides.find_one({"key": "welcome"}) is not None


def test_ventebot_retirement_archives_offers_but_preserves_history(mock_mongodb):
    mock_mongodb.offers.insert_many([
        {"id": 701, "supplier_provider": "ventebot", "active": 1, "auto_delivery": True},
        {"id": 702, "supplier_provider": "mailreader", "active": 1, "auto_delivery": True},
    ])
    mock_mongodb.reseller_products.insert_one({
        "provider": "ventebot", "product_id": "12", "enabled": True,
    })
    mock_mongodb.orders.insert_one({
        "id": 703, "offer_id": 701, "status": "delivered",
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "ventebot", "external_order_id": "BM-703", "status": "completed",
    })

    result = db._retire_ventebot_provider(mock_mongodb)

    retired = mock_mongodb.offers.find_one({"id": 701})
    assert result == {"offers_archived": 1, "products_disabled": 1}
    assert retired["active"] == 0
    assert retired["archived"] == 1
    assert retired["auto_delivery"] is False
    assert mock_mongodb.offers.find_one({"id": 702})["active"] == 1
    assert mock_mongodb.reseller_products.find_one({"provider": "ventebot"})["enabled"] is False
    assert mock_mongodb.orders.find_one({"id": 703}) is not None
    assert mock_mongodb.reseller_fulfillments.find_one({"external_order_id": "BM-703"}) is not None


def test_supplier_restocks_are_sent_as_individual_product_messages(mock_mongodb):
    first_service = db.add_service("AI", "🤖")
    second_service = db.add_service("Learning", "🎓")
    first_offer = db.add_offer(first_service, "ChatGPT Plus", 5.0, 8)
    second_offer = db.add_offer(second_service, "Coursera Plus", 3.0, 4)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "fr"},
    ])
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_restock_digest(SimpleNamespace(bot=bot_client), [
        {"offer_id": first_offer, "added": 3, "stock": 8},
        {"offer_id": second_offer, "added": 2, "stock": 4},
    ]))

    assert sent == 4
    assert bot_client.send_message.await_count == 4
    texts = [call.kwargs["text"] for call in bot_client.send_message.await_args_list]
    assert sum("ChatGPT Plus" in text for text in texts) == 2
    assert sum("Coursera Plus" in text for text in texts) == 2
    for call in bot_client.send_message.await_args_list:
        assert "API" not in call.kwargs["text"]
        assert "NEW DROP" in call.kwargs["text"] or "NOUVEAU DROP" in call.kwargs["text"]
        assert "━━━━━━━━" not in call.kwargs["text"]
        assert len(call.kwargs["reply_markup"].inline_keyboard) == 2


def test_broadcast_jobs_are_persisted_claimed_and_completed(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})
    job, created = db.create_broadcast_job(
        "stock", {"offer_id": 7, "added": 2, "stock": 3}, dedupe_key="stock:test:3",
    )

    assert created is True
    assert job["status"] == "queued"
    assert job["recipient_count"] == 1
    assert db.claim_broadcast_job(job["id"])["status"] == "running"
    db.complete_broadcast_job(job["id"], 1)
    saved = mock_mongodb.broadcast_jobs.find_one({"id": job["id"]})
    assert saved["status"] == "completed"
    assert saved["sent_count"] == 1
    duplicate, duplicate_created = db.create_broadcast_job(
        "stock", {"offer_id": 7}, dedupe_key="stock:test:3",
    )
    assert duplicate_created is False
    assert duplicate["id"] == job["id"]


def test_supplier_price_update_job_targets_all_customers(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 101},
        {"telegram_id": 102},
    ])

    job, created = db.create_broadcast_job(
        "supplier_price_update",
        {"event": {"offer_id": 7, "previous_price": 5, "price": 6}},
    )

    assert created is True
    assert job["recipient_count"] == 2


def test_sent_campaign_can_be_deleted_for_every_recipient(mock_mongodb):
    service_id = db.add_service("AI", "✨")
    offer_id = db.add_offer(service_id, "Premium", 5.0, 3)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "en"},
    ])
    job, _created = db.create_broadcast_job(
        "stock", {"offer_id": offer_id, "added": 3, "stock": 3},
    )
    send_message = AsyncMock(side_effect=[
        SimpleNamespace(message_id=501),
        SimpleNamespace(message_id=502),
    ])
    send_context = SimpleNamespace(
        bot=SimpleNamespace(send_message=send_message),
        broadcast_job_id=job["id"],
        broadcast_kind="stock",
    )

    sent = asyncio.run(announce_channel_restock(send_context, offer_id, 3, 3))
    db.complete_broadcast_job(job["id"], sent)

    assert len(db.list_broadcast_messages(job["id"])) == 2
    assert db.list_broadcast_history()[0]["active_message_count"] == 2

    delete_message = AsyncMock(return_value=True)
    deleted = asyncio.run(delete_broadcast_messages(
        SimpleNamespace(bot=SimpleNamespace(delete_message=delete_message)),
        job["id"],
    ))

    assert deleted == 2
    assert delete_message.await_count == 2
    assert db.list_broadcast_messages(job["id"]) == []
    assert db.get_broadcast_job(job["id"])["deletion_status"] == "deleted"


def test_flash_sale_is_broadcast_with_buy_button(mock_mongodb):
    service_id = db.add_service("AI", "⚡")
    offer_id = db.add_offer(service_id, "Gemini Pro 18M", 8.0, 4)
    db.start_flash_sale(offer_id, 3.0, 480)
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_flash_sale(SimpleNamespace(bot=bot_client), offer_id))

    assert sent == 1
    call = bot_client.send_message.await_args
    assert "FLASH SALE" in call.kwargs["text"]
    assert "8.00 USDT" in call.kwargs["text"]
    assert "3.00 USDT" in call.kwargs["text"]
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"buy:{offer_id}"


def test_automatic_flash_sale_uses_common_design_without_api_mention(mock_mongodb):
    service_id = db.add_service("AI", "🔥")
    offer_id = db.add_offer(service_id, "Claude Pro", 6.0, 4)
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_api_flash_sale(SimpleNamespace(bot=bot_client), {
        "offer_id": offer_id,
        "previous_price": 10.0,
        "price": 6.0,
    }))

    assert sent == 1
    text = bot_client.send_message.await_args.kwargs["text"]
    assert "FLASH SALE — LIMITED DROP" in text
    assert "API" not in text
    assert "40%" in text


def test_inactive_supplier_restock_falls_back_to_private_admin_alert(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    service_id = db.add_service("Learning", "📚")
    offer_id = db.add_offer(service_id, "Coursera", 3.0, 11)
    db.update_offer(offer_id, active=0)
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client),
        offer_id,
        5,
        11,
        {
            "provider": "mailreader",
            "product_id": "coursera-premium-12m",
            "offer_id": offer_id,
            "added": 5,
            "stock": 11,
        },
    ))

    assert sent == 1
    call = bot_client.send_message.await_args.kwargs
    assert call["chat_id"] == 999
    assert "NEW DROP AVAILABLE" in call["text"]
    assert "11" in call["text"]
    assert "Supplier" not in call["text"]
    assert call["reply_markup"].inline_keyboard[-1][0].callback_data == "catalog"


def test_out_of_stock_supplier_discount_uses_bot_flash_sale_design(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    offer_id = db.add_offer(db.add_service("AI", "🤖"), "Codex", 8.0, 0)
    mock_mongodb.users.insert_one({"telegram_id": 999, "lang": "en"})
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_api_flash_sale(
        SimpleNamespace(bot=bot_client),
        {
            "provider": "canboso",
            "offer_id": offer_id,
            "previous_price": 8.01,
            "price": 8.0,
        },
    ))

    assert sent == 1
    call = bot_client.send_message.await_args.kwargs
    assert call["chat_id"] == 999
    assert "FLASH SALE" in call["text"]
    assert "8.01 USDT" in call["text"]
    assert "8.00 USDT" in call["text"]
    assert "Supplier" not in call["text"]
    assert call["reply_markup"].inline_keyboard[-1][0].callback_data == "catalog"


def test_supplier_price_increase_is_broadcast_as_customer_new_drop(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    offer_id = db.add_offer(db.add_service("AI", "🤖"), "AI Plan", 7.0, 3)
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 102, "lang": "fr"},
    ])
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(announce_supplier_price_update(
        SimpleNamespace(bot=bot_client),
        {
            "provider": "mailreader",
            "offer_id": offer_id,
            "previous_price": 6.0,
            "price": 7.0,
        },
    ))

    assert sent == 2
    calls = bot_client.send_message.await_args_list
    assert {call.kwargs["chat_id"] for call in calls} == {101, 102}
    assert "NEW DROP AVAILABLE" in calls[0].kwargs["text"]
    assert "7.00 USDT" in calls[0].kwargs["text"]
    assert "Previous price" not in calls[0].kwargs["text"]
    assert calls[0].kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"buy:{offer_id}"


def test_admin_can_reannounce_current_offer_without_adding_stock(mock_mongodb):
    service_id = db.add_service("Chat GPT", "🤖")
    offer_id = db.add_offer(service_id, "Premium 30 days", 7.5, 4)
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(
        announce_channel_restock(SimpleNamespace(bot=bot_client), offer_id, None, 4)
    )

    assert sent == 1
    text = bot_client.send_message.await_args.kwargs["text"]
    assert "NEW DROP AVAILABLE" in text
    assert "7.50 USDT" in text
    assert "Stock: <b>4</b>" in text


def test_admin_custom_announcement_is_copied_to_all_active_users(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "en"},
        {"telegram_id": 303, "lang": "en", "banned": True},
    ])
    bot_client = SimpleNamespace(copy_message=AsyncMock())

    sent = asyncio.run(
        broadcast_admin_message(
            SimpleNamespace(bot=bot_client),
            source_chat_id=999,
            message_id=55,
        )
    )

    assert sent == 2
    assert bot_client.copy_message.await_count == 2
    assert {
        call.kwargs["chat_id"]
        for call in bot_client.copy_message.await_args_list
    } == {101, 202}
    assert all(
        call.kwargs["from_chat_id"] == 999 and call.kwargs["message_id"] == 55
        for call in bot_client.copy_message.await_args_list
    )


def test_maintenance_notice_is_sent_to_every_active_user(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 101, "lang": "en"},
        {"telegram_id": 202, "lang": "en"},
        {"telegram_id": 303, "lang": "en", "banned": True},
    ])
    bot_client = SimpleNamespace(send_message=AsyncMock())

    sent = asyncio.run(
        broadcast_maintenance_notice(
            SimpleNamespace(bot=bot_client),
            "The shop is temporarily unavailable.",
        )
    )

    assert sent == 2
    assert {
        call.kwargs["chat_id"]
        for call in bot_client.send_message.await_args_list
    } == {101, 202}
    assert all(
        "The shop is temporarily unavailable." in call.kwargs["text"]
        for call in bot_client.send_message.await_args_list
    )


def test_full_maintenance_blocks_every_customer_command(monkeypatch):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.db.shop_settings", lambda: {
        "maintenance_enabled": True,
        "maintenance_message": "We will be back shortly.",
    })
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        callback_query=None,
        effective_message=message,
    )

    with pytest.raises(Exception) as stopped:
        asyncio.run(block_maintenance_users(update, SimpleNamespace()))

    assert stopped.value.__class__.__name__ == "ApplicationHandlerStop"
    message.reply_text.assert_awaited_once()
    assert "BOT UNDER MAINTENANCE" in message.reply_text.await_args.args[0]
    assert "We will be back shortly." in message.reply_text.await_args.args[0]


def test_full_maintenance_blocks_customer_buttons(monkeypatch):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.db.shop_settings", lambda: {
        "maintenance_enabled": True,
        "maintenance_message": "Please try later.",
    })
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(answer=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        callback_query=query,
        effective_message=message,
    )

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(block_maintenance_users(update, SimpleNamespace()))

    query.answer.assert_awaited_once_with("Maintenance mode is active.", show_alert=True)
    message.reply_text.assert_awaited_once()


def test_full_maintenance_never_blocks_admin(monkeypatch):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.db.shop_settings", Mock(side_effect=AssertionError("not needed")))
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        callback_query=None,
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )

    asyncio.run(block_maintenance_users(update, SimpleNamespace()))

    update.effective_message.reply_text.assert_not_awaited()


def test_customer_button_click_is_reported_to_private_channel(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.CLICK_REPORT_CHAT_ID", -1004349965359)
    bot_client = SimpleNamespace(send_message=AsyncMock())
    message = SimpleNamespace(
        text="Offer screen",
        caption=None,
        reply_markup=SimpleNamespace(inline_keyboard=[[
            SimpleNamespace(text="Buy Premium now", callback_data="buy:17"),
        ]]),
    )
    query = SimpleNamespace(data="buy:17", message=message)
    user = SimpleNamespace(
        id=42, full_name="Test Buyer", first_name="Test",
        username="buyer",
    )
    update = SimpleNamespace(
        effective_user=user,
        callback_query=query,
        effective_message=message,
    )

    asyncio.run(
        notify_admin_interaction(update, SimpleNamespace(bot=bot_client))
    )

    bot_client.send_message.assert_awaited_once()
    call = bot_client.send_message.await_args
    assert call.args[0] == -1004349965359
    assert "buy:17" in call.args[1]
    assert "Buy Premium now" in call.args[1]
    assert "CUSTOMER CLICK" in call.args[1]
    assert "Test Buyer" in call.args[1]
    assert "42" in call.args[1]
    event = mock_mongodb.interaction_events.find_one({"user_id": 42})
    assert event["interaction_type"] == "button"
    assert event["action"] == "buy:17"


def test_customer_message_is_not_sent_to_click_channel(mock_mongodb):
    bot_client = SimpleNamespace(send_message=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        callback_query=None,
        effective_message=SimpleNamespace(text="support message"),
    )

    asyncio.run(
        notify_admin_interaction(update, SimpleNamespace(bot=bot_client))
    )

    bot_client.send_message.assert_not_awaited()
    assert mock_mongodb.interaction_events.count_documents({}) == 0


def test_admin_interaction_does_not_notify_itself(monkeypatch):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    bot_client = SimpleNamespace(send_message=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        callback_query=None,
        effective_message=SimpleNamespace(text="/admin"),
    )

    asyncio.run(
        notify_admin_interaction(update, SimpleNamespace(bot=bot_client))
    )

    bot_client.send_message.assert_not_awaited()


def test_successful_purchase_is_not_announced_to_channel(mock_mongodb):
    service_id = db.add_service("Chat GPT", "🤖")
    offer_id = db.add_offer(service_id, "Premium 30 days", 5.0, 4)
    mock_mongodb.orders.insert_one({
        "id": 77,
        "user_id": 987654321,
        "offer_id": offer_id,
        "service_name": "Chat GPT",
        "offer_name": "Premium 30 days",
        "qty": 2,
        "unit_price": 5.0,
        "gross_total": 10.0,
        "currency": "USDT",
        "status": "delivered",
        "txid": "REAL_TXID_SECRET",
        "verify_method": "binance",
    })
    bot_client = SimpleNamespace(username="blackmarketa_bot", send_message=AsyncMock())
    context = SimpleNamespace(bot=bot_client)

    first = asyncio.run(announce_channel_purchase(context, 77))
    second = asyncio.run(announce_channel_purchase(context, 77))

    assert first is False
    assert second is False
    bot_client.send_message.assert_not_awaited()


def test_admin_test_purchase_is_never_announced(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 78, "offer_id": 1, "status": "delivered", "verify_method": "admin_test",
    })
    bot_client = SimpleNamespace(username="blackmarketa_bot", send_message=AsyncMock())

    sent = asyncio.run(announce_channel_purchase(SimpleNamespace(bot=bot_client), 78))

    assert sent == 0
    bot_client.send_message.assert_not_awaited()

def test_zero_added_inventory_does_not_announce(mock_mongodb):
    bot_client = SimpleNamespace(username="blackmarketa_bot", send_message=AsyncMock())

    sent = asyncio.run(announce_channel_restock(SimpleNamespace(bot=bot_client), 99, 0, 4))

    assert sent == 0
    bot_client.send_message.assert_not_awaited()

def test_delivery_accounts_use_numeric_labels_and_preserve_hash_content():
    assert numbered_delivery_content([
        "first@example.com:pass",
        "#second@example.com:pass",
        "#3\nthird@example.com:pass",
    ]) == (
        "1.\nfirst@example.com:pass\n\n2.\n#second@example.com:pass\n\n3.\nthird@example.com:pass"
    )

def test_start_requires_official_channel_membership(monkeypatch):
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=42, username="buyer", first_name="Buyer")
    bot_client = SimpleNamespace(
        username="blackmarketa_bot",
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left")),
    )
    update = SimpleNamespace(effective_user=user, message=message)
    context = SimpleNamespace(bot=bot_client, args=[])
    monkeypatch.setattr("bot.ADMIN_ID", 999)

    asyncio.run(cmd_start(update, context))

    message.reply_text.assert_awaited_once()
    call = message.reply_text.await_args
    assert "MEMBERS-ONLY ACCESS" in call.args[0]
    assert call.kwargs["reply_markup"] is not None
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].url.endswith("/bmcmethods")
    bot_client.get_chat_member.assert_awaited_once_with("@bmcmethods", 42)
    assert PENDING.get(42) == ("await_channel_join", 0)


def test_verified_membership_is_cached_for_fast_button_clicks(monkeypatch):
    from bot import _membership_cache

    _membership_cache.clear()
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@cache_channel")
    monkeypatch.setattr("bot.MEMBERSHIP_CACHE_SECONDS", 300)
    bot_client = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )
    message = SimpleNamespace(text="Catalog", reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=4200),
        effective_message=message,
        callback_query=None,
    )
    context = SimpleNamespace(bot=bot_client)

    asyncio.run(block_non_channel_members(update, context))
    asyncio.run(block_non_channel_members(update, context))

    bot_client.get_chat_member.assert_awaited_once_with("@cache_channel", 4200)
    message.reply_text.assert_not_awaited()
    _membership_cache.clear()


def test_verify_joining_unlocks_marketing_welcome(monkeypatch):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="verify_channel_join",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    bot_client = SimpleNamespace(
        username="blackmarket_test_bot",
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    db.upsert_user(42, "buyer", "Buyer")
    PENDING[42] = ("await_channel_join", 0)

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace(bot=bot_client)))

    query.edit_message_text.assert_awaited_once()
    rendered = query.edit_message_text.await_args.args[0]
    assert "WELCOME TO" in rendered
    assert "1 USDT" in rendered
    assert "12% OFF" in rendered
    assert query.edit_message_text.await_args.kwargs["parse_mode"] == ParseMode.HTML
    bot_client.get_chat_member.assert_awaited_once_with("@bmcmethods", 42)


def test_only_official_channel_membership_is_required(monkeypatch):
    from bot import is_required_channel_member

    bot_client = SimpleNamespace(get_chat_member=AsyncMock(side_effect=[
        SimpleNamespace(status="member"),
        SimpleNamespace(status="left"),
    ]))
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@channel")

    assert asyncio.run(is_required_channel_member(bot_client, 42)) is True
    assert [call.args[0] for call in bot_client.get_chat_member.await_args_list] == [
        "@channel",
    ]


def test_membership_check_accepts_links_and_numeric_chat_ids(monkeypatch):
    from bot import is_required_channel_member

    bot_client = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")))
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "https://t.me/blackmarketBotChannel")

    assert asyncio.run(is_required_channel_member(bot_client, 42)) is True
    bot_client.get_chat_member.assert_awaited_once_with("@blackmarketBotChannel", 42)


def test_membership_check_resolves_usernames_to_numeric_chat_ids(monkeypatch):
    from bot import required_membership_status

    bot_client = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(
            id=-100111, title="Black Market Channel",
        )),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@blackmarketBotChannel")

    allowed, details = asyncio.run(required_membership_status(bot_client, 42))

    assert allowed is True
    assert [call.args[0] for call in bot_client.get_chat_member.await_args_list] == [
        -100111,
    ]
    assert [detail["title"] for detail in details] == [
        "Black Market Channel",
    ]


def test_membership_check_accepts_owner_status(monkeypatch):
    from bot import is_required_channel_member

    bot_client = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="owner")))
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@channel")

    assert asyncio.run(is_required_channel_member(bot_client, 42)) is True


def test_membership_status_reports_failed_chat(monkeypatch):
    from bot import required_membership_status

    bot_client = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left")),
    )
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@channel")

    allowed, details = asyncio.run(required_membership_status(bot_client, 42))

    assert allowed is False
    assert details == [
        {"chat": "@channel", "ok": False, "status": "left"},
    ]


def test_verify_button_refuses_access_without_membership(monkeypatch):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="verify_channel_join",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    bot_client = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left")),
        send_message=AsyncMock(),
        username="blackmarket_test_bot",
    )
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@channel")

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace(bot=bot_client)))

    bot_client.get_chat_member.assert_awaited_once_with("@channel", 42)
    bot_client.send_message.assert_not_awaited()
    query.edit_message_text.assert_awaited_once()
    assert "MEMBERSHIP NOT DETECTED" in query.edit_message_text.await_args.args[0]

@pytest.mark.parametrize(
    ("key", "incoming_text", "emoji_id"),
    [
        ("menu_topup", "💳 Top Up Balance", "premium-topup"),
        ("menu_account", "👤 My account", "premium-profile"),
    ],
)
def test_admin_can_edit_topup_and_profile_even_when_text_matches_current_button(
    mock_mongodb, monkeypatch, key, incoming_text, emoji_id,
):
    admin_id = 999
    db.upsert_user(admin_id, "admin", "Admin")
    db.set_user_lang(admin_id, "en")
    PENDING[admin_id] = ("adm_text_override", f"{key}|en")
    message = SimpleNamespace(
        text=incoming_text,
        caption=None,
        entities=[SimpleNamespace(type="custom_emoji", custom_emoji_id=emoji_id, offset=0, length=2)],
        caption_entities=[],
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=admin_id),
        message=message,
    )
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)

    asyncio.run(on_text_menu(update, SimpleNamespace()))

    assert db.get_text_override(key, "en") in {"Top Up Balance", "My account"}
    assert db.get_text_override_icon(key, "en") == emoji_id
    assert PENDING.get(admin_id) is None
    assert "enregistr" in message.reply_text.await_args.args[0].lower()

def test_main_menu_is_compact_and_actions_match_labels():
    keyboard = kb.main_menu_keyboard("en", user_id=42)

    labels = [[button.text for button in row] for row in keyboard.keyboard[:3]]
    assert labels == [
        [t("en", "menu_catalog"), t("en", "menu_orders")],
        [t("en", "menu_bot_like_mine")],
        [t("en", "menu_topup")],
    ]
    assert [[button.text for button in row] for row in keyboard.keyboard[3:5]] == [
        [t("en", "menu_account"), t("en", "menu_affiliate")],
        [t("en", "menu_support"), t("en", "menu_lang")],
    ]
    assert "account" in t("en", "menu_account").lower()


def test_admin_custom_emoji_is_extracted_from_telegram_entity():
    message = SimpleNamespace(entities=[SimpleNamespace(
        type="custom_emoji",
        custom_emoji_id="animated-emoji-123",
    )])

    assert custom_emoji_from_message(message) == "animated-emoji-123"


def test_admin_custom_emoji_is_extracted_from_custom_emoji_sticker():
    message = SimpleNamespace(
        entities=[],
        caption_entities=[],
        sticker=SimpleNamespace(custom_emoji_id="5413879192267805083"),
    )

    assert custom_emoji_from_message(message) == "5413879192267805083"


def test_admin_can_save_service_right_emoji(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 42)
    service_id = db.add_service("officiels subscribes", "⭐")
    PENDING[42] = ("adm_svcsuffix", service_id)
    message = SimpleNamespace(
        text="✅",
        entities=[],
        caption_entities=[],
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )

    asyncio.run(handle_pending_input(update, SimpleNamespace(), "fr"))

    assert db.get_service(service_id)["suffix_emoji"] == "✅"
    assert PENDING.get(42) is None
    message.reply_text.assert_awaited_once()


def test_admin_offer_accepts_custom_emoji_sticker(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 42)
    service_id = db.add_service("Cursor", "📦")
    offer_id = db.add_offer(service_id, "Cursor Pro 12m", 60, 14)
    PENDING[42] = ("adm_offemoji", offer_id)
    message = SimpleNamespace(
        entities=[],
        caption_entities=[],
        sticker=SimpleNamespace(custom_emoji_id="5413879192267805083"),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=message,
    )

    asyncio.run(handle_pending_attachment(update, SimpleNamespace()))

    offer = db.get_offer(offer_id)
    assert offer["emoji"] == ""
    assert offer["custom_emoji_id"] == "5413879192267805083"
    assert PENDING.get(42) is None
    message.reply_text.assert_awaited_once()


def test_admin_right_emoji_accepts_premium_sticker_fallback(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 42)
    service_id = db.add_service("officiels subscribes", "⭐")
    PENDING[42] = ("adm_svcsuffix", service_id)
    message = SimpleNamespace(
        text=None,
        caption=None,
        entities=[],
        caption_entities=[],
        sticker=SimpleNamespace(
            custom_emoji_id="5413879192267805083",
            emoji="✅",
        ),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_message=message,
    )

    asyncio.run(handle_pending_attachment(update, SimpleNamespace()))

    assert db.get_service(service_id)["suffix_emoji"] == "✅"
    assert PENDING.get(42) is None
    message.reply_text.assert_awaited_once()


def test_admin_text_category_button_opens_category(monkeypatch):
    query = SimpleNamespace(
        data="adm_text_cat:payments:0",
        from_user=SimpleNamespace(id=999),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    monkeypatch.setattr("bot.ADMIN_ID", 999)

    asyncio.run(cb_admin(SimpleNamespace(callback_query=query), SimpleNamespace()))

    query.edit_message_text.assert_awaited_once()
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "adm_text_key:order_created" in callbacks or any(
        value and value.startswith("adm_text_cat:payments:") for value in callbacks
    )


def test_all_premium_emojis_are_detected_with_text_and_duplicates_removed():
    message = SimpleNamespace(
        entities=[
            SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-1"),
            SimpleNamespace(type="bold", custom_emoji_id=None),
            SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-2"),
            SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-1"),
        ],
        caption_entities=[],
        text="Premium offer with animated emojis",
    )
    assert custom_emojis_from_message(message) == ["premium-1", "premium-2"]
    assert custom_emoji_from_message(message) == "premium-1"


def test_premium_emoji_placeholder_is_removed_from_button_text():
    message = SimpleNamespace(
        text="🔄 Refresh",
        caption=None,
        entities=[SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-refresh", offset=0, length=2)],
        caption_entities=[],
    )
    assert text_without_custom_emojis(message) == "Refresh"


def test_multiple_premium_emojis_keep_exact_ids_and_positions():
    message = SimpleNamespace(
        text="A⭐ B🔥",
        caption=None,
        entities=[
            SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-star", offset=1, length=1),
            SimpleNamespace(type="custom_emoji", custom_emoji_id="premium-fire", offset=4, length=2),
        ],
        caption_entities=[],
    )
    stored = text_with_custom_emoji_tokens(message)
    db.set_text_override("order_created", "en", stored, "premium-star")

    rendered = premium_customer_text("en", "order_created")

    assert rendered.startswith('A<tg-emoji emoji-id="premium-star">⭐</tg-emoji> B')
    assert '<tg-emoji emoji-id="premium-fire">🔥</tg-emoji>' in rendered
    assert rendered.count("<tg-emoji") == 2


def test_channel_message_accepts_exact_premium_emojis_and_rich_text(mock_mongodb):
    db.set_text_override(
        "channel_purchase_success",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-sale">🎉</tg-emoji> <b>New sale</b>',
        "premium-sale",
    )

    rendered = premium_customer_text("en", "channel_purchase_success")

    assert '<tg-emoji emoji-id="premium-sale">🎉</tg-emoji>' in rendered
    assert "<b>New sale</b>" in rendered


def test_admin_text_editor_shows_rendered_telegram_preview_not_html_source(mock_mongodb):
    db.set_text_override(
        "channel_stock_announcement",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-drop">💫</tg-emoji> <b>New drop</b>',
        "premium-drop",
    )

    preview = admin_text_preview("channel_stock_announcement")

    assert "[[HTML]]" not in preview
    assert "<pre>" not in preview
    assert "&lt;tg-emoji" not in preview
    assert '<tg-emoji emoji-id="premium-drop">💫</tg-emoji>' in preview
    assert "<b>New drop</b>" in preview


def test_delivery_template_accepts_legacy_single_html_marker(mock_mongodb):
    db.set_text_override(
        "delivery_received",
        "en",
        '[HTML]<tg-emoji emoji-id="premium-gift">🎁</tg-emoji> '
        '<b>Your order #{oid} has been delivered!</b>\n\n'
        'Service: <b>{service}</b> — {offer}\n\n<pre>{content}</pre>',
    )

    rendered = premium_customer_text(
        "en",
        "delivery_received",
        oid=180,
        service="Chat GPT",
        offer="Chat GPT Plus",
        content="55",
    )

    assert "[HTML]" not in rendered
    assert '<tg-emoji emoji-id="premium-gift">🎁</tg-emoji>' in rendered
    assert "<b>Your order #180 has been delivered!</b>" in rendered
    assert "Service: <b>Chat GPT</b> — Chat GPT Plus" in rendered
    assert "<pre>55</pre>" in rendered

def test_premium_channel_html_also_renders_admin_markdown_markers(mock_mongodb):
    db.set_text_override(
        "channel_stock_announcement",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-new">🆕</tg-emoji> *NEW STOCK* — _limited_',
        "premium-new",
    )

    rendered = premium_customer_text("en", "channel_stock_announcement")

    assert '<tg-emoji emoji-id="premium-new">🆕</tg-emoji>' in rendered
    assert "<b>NEW STOCK</b>" in rendered
    assert "<i>limited</i>" in rendered
    assert "*NEW STOCK*" not in rendered


def test_methods_announcement_strips_legacy_html_but_keeps_premium_description_emoji():
    text = (
        "💫 <b>NEW DROP</b>\n"
        '<tg-emoji emoji-id="premium-duration">📅</tg-emoji> Duration: <b>30 Days</b>\n'
        '<tg-emoji emoji-id="premium-warranty">🛡</tg-emoji> Warranty: <b>Full</b>\n'
        '<tg-emoji emoji-id="premium-stock">📦</tg-emoji> Stock: <b>1</b>'
    )
    description = (
        '[[HTML]]<tg-emoji emoji-id="premium-method">💡</tg-emoji> '
        '<b>Instant access</b> <code>legacy-wrapper</code>'
    )

    rendered = _method_announcement_text(
        text,
        {"name": "Methods"},
        {"description": description},
    )

    assert "Duration:" not in rendered
    assert "Warranty:" not in rendered
    assert "Stock:" not in rendered
    assert '💬 <b>Description:</b> <tg-emoji emoji-id="premium-method">💡</tg-emoji>' in rendered
    assert "<b>Instant access</b>" in rendered
    assert "<code>legacy-wrapper</code>" not in rendered


def test_methods_announcement_removes_unmarked_html_source():
    rendered = _method_announcement_text(
        "📅 Period: 30 Days\n🛡 Warranty: Full",
        {"name": "Methods"},
        {"description": "<p>Use <strong>this</strong> method</p>"},
    )

    assert "Use this method" in rendered
    assert "<p>" not in rendered
    assert "<strong>" not in rendered

def test_offer_description_preserves_telegram_rich_formatting(monkeypatch):
    message = SimpleNamespace(
        text="Premium description",
        text_html=(
            '<tg-emoji emoji-id="premium-description">💬</tg-emoji> '
            '<b>Premium</b> <i>description</i>'
        ),
        caption_html=None,
    )
    stored = rich_text_from_message(message)
    monkeypatch.setattr("bot.db.offer_sold_count", lambda _offer_id: 0)

    rendered = compact_offer_text({
        "id": 1, "name": "Plan", "price": 5.0, "stock": 2,
        "description": stored, "instructions": "—", "note": "Warranty",
    }, "en")

    assert '<tg-emoji emoji-id="premium-description">💬</tg-emoji>' in rendered
    assert "<b>Premium</b> <i>description</i>" in rendered


def test_plain_offer_description_does_not_treat_stars_or_underscores_as_markup(monkeypatch):
    monkeypatch.setattr("bot.db.offer_sold_count", lambda _offer_id: 0)

    rendered = compact_offer_text({
        "id": 1, "name": "Plan", "price": 5.0, "stock": 2,
        "description": "* ChatGPT: Icloud_mail\n* Mailbox: Icloud_mail",
        "instructions": "—", "note": "Warranty",
    }, "en")

    assert "* ChatGPT: Icloud_mail" in rendered
    assert "<i>" not in rendered
    assert "INSTRUCTIONS" not in rendered
    assert "Tap Buy now" not in rendered


def test_payment_keyboard_prioritizes_verification():
    keyboard = kb.paid_keyboard("fr", order_id=17, binance_id="454813844", total="5.00")

    assert keyboard.inline_keyboard[0][0].callback_data == "paid:17"
    assert all(
        button.copy_text is None
        for row in keyboard.inline_keyboard
        for button in row
    )
    assert kb.txid_verify_keyboard("fr", 17).inline_keyboard[0][0].callback_data == "paid:17"
    assert kb.txid_verify_keyboard("fr", 17).inline_keyboard[1][0].callback_data == "cancel_buy:17"


@pytest.mark.parametrize("callback", ["paid:17", "verify_auto:17"])
def test_payment_buttons_route_to_txid_entry(callback, monkeypatch, mock_mongodb):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=callback,
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(
        SimpleNamespace(callback_query=query), SimpleNamespace(),
    ))

    assert PENDING.get(42) == ("await_txid", 17)
    assert "transaction ID" in message.reply_text.await_args.args[0]


def test_support_flow_always_offers_a_home_action():
    keyboard = kb.support_category_keyboard("fr")

    assert keyboard.inline_keyboard[-1][0].callback_data == "home"


def test_referrer_receives_progress_and_wallet_success_messages(mock_mongodb, monkeypatch):
    referrer_id = 999
    mock_mongodb.users.insert_one({"telegram_id": referrer_id, "lang": "en"})
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    monkeypatch.setattr("bot.REQUIRED_CHANNEL", "@affiliate_channel")

    for index in range(9):
        user_id = 100 + index
        mock_mongodb.users.insert_one({"telegram_id": user_id})
        assert affiliate_service.register_referral_link(user_id, referrer_id)
        mock_mongodb.orders.insert_one({"id": index + 1, "user_id": user_id, "total_price": 1.0})
        affiliate_service.on_confirmed_payment(user_id, index + 1)
    asyncio.run(notify_successful_referral(context, referrer_id))
    progress_message = context.bot.send_message.await_args.args[1]
    assert "9/10" in progress_message
    assert "2 USDT" in progress_message

    mock_mongodb.users.insert_one({"telegram_id": 109})
    assert affiliate_service.register_referral_link(109, referrer_id)
    mock_mongodb.orders.insert_one({"id": 10, "user_id": 109, "total_price": 1.0})
    affiliate_service.on_confirmed_payment(109, 10)
    asyncio.run(notify_successful_referral(context, referrer_id))
    private_call = context.bot.send_message.await_args_list[-1]
    success_message = private_call.args[1]
    assert private_call.args[0] == referrer_id
    assert "10 valid referrals" in success_message
    assert "2 USDT" in success_message
    assert "2.00 USDT" in success_message
    assert context.bot.send_message.await_count == 2


def test_order_payment_values_are_individually_copyable():
    db.set_text_override(
        "order_created",
        "en",
        "SEND EXACTLY: {total} {cur}\nBinance ID: {binance_id}",
    )

    rendered = premium_customer_text(
        "en", "order_created", total="10.00", cur="USDT",
        binance_id="454813844",
    )

    assert "<code>10.00</code> USDT" in rendered
    assert "Binance ID: <code>454813844</code>" in rendered
    assert "Memo" not in rendered


@pytest.mark.parametrize("key", [
    "order_created", "verifying", "verify_ok",
    "already_paid", "txid_too_short", "payment_wrong_amount",
    "payment_wrong_currency", "payment_not_found",
    "payment_txid_used", "verify_failed", "delivery_received",
    "loyalty_activated", "affiliate_rewarded",
    "topup_message", "topup_ask_txid",
    "topup_success", "topup_already_confirmed", "topup_failed",
    "channel_stock_announcement", "offer_stock_announcement",
    "flash_sale_announcement",
    "affiliate_referral_success", "affiliate_ten_success", "channel_affiliate_reward",
])
def test_all_payment_flow_texts_support_exact_premium_emoji(key):
    emoji_id = f"premium-{key}"
    db.set_text_override(key, "en", "Configurable payment text", emoji_id)

    rendered = premium_customer_text("en", key)

    assert f'<tg-emoji emoji-id="{emoji_id}">' in rendered


def test_dynamic_orders_button_supports_admin_premium_emoji():
    db.set_text_override("orders_all", "en", "All orders ({count})", "premium-orders-all")

    keyboard = kb.orders_services_keyboard("en", [], 8)

    assert keyboard.inline_keyboard[0][0].icon_custom_emoji_id == "premium-orders-all"


def test_inline_home_avoids_actions_repeated_in_profile():
    keyboard = kb.home_keyboard("fr", user_id=42)
    callbacks = {button.callback_data for row in keyboard.inline_keyboard for button in row}

    assert {"catalog", "topup", "account", "support", "language"} <= callbacks
    assert "lovable" not in callbacks
    assert {"orders", "affiliate"}.isdisjoint(callbacks)
    assert "help" not in callbacks


def test_welcome_banner_is_packaged_with_the_bot():
    banner = Path(__file__).resolve().parents[1] / "assets" / "blackmarket-welcome-v2.png"

    assert banner.exists()
    assert banner.stat().st_size > 100_000


def test_top_selling_products_are_ranked_and_rendered_with_premium_emoji(monkeypatch):
    offers = [
        {"id": 1, "name": "Basic", "emoji": "📦"},
        {"id": 2, "name": "Pro & Plus", "emoji": "⭐", "custom_emoji_id": "12345"},
        {"id": 3, "name": "Starter", "emoji": "🚀"},
    ]
    sales = {1: 2, 2: 7, 3: 4}
    monkeypatch.setattr("bot.db.list_catalog_offers", lambda: offers)
    monkeypatch.setattr("bot.db.offer_sold_count", lambda offer_id: sales[offer_id])

    text = top_selling_products_text("en")

    assert "TOP 5 BEST-SELLING PRODUCTS" in text
    assert text.index("Pro &amp; Plus") < text.index("Starter") < text.index("Basic")
    assert '<tg-emoji emoji-id="12345">⭐</tg-emoji>' in text


def test_main_menu_sends_welcome_banner_by_cached_url(monkeypatch):
    message = SimpleNamespace(reply_photo=AsyncMock(), reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
        callback_query=None,
    )
    monkeypatch.setenv("HP_PUBLIC_BASE_URL", "https://shop.example")
    monkeypatch.setattr("bot.db.shop_settings", lambda: {"welcome_message": ""})

    asyncio.run(send_main_menu(update, SimpleNamespace(), "en"))

    message.reply_photo.assert_awaited_once()
    assert message.reply_photo.await_args.kwargs["photo"] == (
        "https://shop.example/assets/blackmarket-welcome-v2.png"
    )
    message.reply_text.assert_not_awaited()


def test_catalog_button_opens_the_services_catalog(monkeypatch):
    query = SimpleNamespace(
        data="catalog",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Home"),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(update, SimpleNamespace()))

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    call = query.edit_message_text.await_args
    assert "CATALOG" in call.args[0]
    callbacks = {
        button.callback_data
        for row in call.kwargs["reply_markup"].inline_keyboard
        for button in row
    }
    assert {"catalog", "home"} <= callbacks


def test_preorder_catalog_opens_red_out_of_stock_services(monkeypatch):
    message = SimpleNamespace(text="Catalog")
    query = SimpleNamespace(
        data="preorder_catalog",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    keyboard = Mock()
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr("bot.kb.preorder_services_keyboard", lambda _lang: keyboard)

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    query.edit_message_text.assert_awaited_once()
    call = query.edit_message_text.await_args
    assert "PRE-ORDER" in call.args[0]
    assert "2 hours maximum" in call.args[0]
    assert call.kwargs["reply_markup"] is keyboard


def test_preorder_service_opens_only_its_empty_offers(monkeypatch):
    message = SimpleNamespace(text="Pre-order")
    query = SimpleNamespace(
        data="preorder_svc:7",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    keyboard = Mock()
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr(
        "bot.db.get_service",
        lambda _sid: {"id": 7, "name": "ChatGPT", "emoji": "🤖"},
    )
    monkeypatch.setattr("bot.kb.preorder_offers_keyboard", lambda _lang, _sid: keyboard)

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    query.edit_message_text.assert_awaited_once()
    call = query.edit_message_text.await_args
    assert "Pre-order ChatGPT" in call.args[0]
    assert "2 hours maximum" in call.args[0]
    assert call.kwargs["reply_markup"] is keyboard


def test_catalog_from_photo_caption_sends_a_new_text_screen(monkeypatch):
    message = SimpleNamespace(text=None, reply_text=AsyncMock())
    query = SimpleNamespace(
        data="catalog",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(update, SimpleNamespace()))

    message.reply_text.assert_awaited_once()
    assert "CATALOG" in message.reply_text.await_args.args[0]
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)


def test_out_of_stock_offer_click_has_no_legacy_preorder_button(monkeypatch):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="off:9",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr(
        "bot.db.get_offer",
        lambda _oid: {"id": 9, "service_id": 1, "name": "Plan", "price": 10.0, "stock": 0},
    )

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    message.reply_text.assert_awaited_once()
    assert "Out of stock" in message.reply_text.await_args.args[0]
    assert message.reply_text.await_args.kwargs["parse_mode"] == ParseMode.HTML
    callbacks = [
        button.callback_data
        for row in message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["catalog"]
    assert not any(callback.startswith("preorder:") for callback in callbacks)


def test_compact_offer_repairs_dashboard_truncated_html(monkeypatch):
    monkeypatch.setattr("bot.db.offer_sold_count", lambda _offer_id: 0)
    offer = {
        "id": 83,
        "name": "Linkedin Career 3M",
        "price": 0.7,
        "stock": 1,
        "note": "24 hours",
        "description": "[[HTML]]<blockquote>Activation guide</blockquote>\n<i>Delivery i",
    }

    rendered = compact_offer_text(offer, "en")

    assert rendered.endswith("<i>Delivery i</i>")
    assert rendered.count("<blockquote>") == rendered.count("</blockquote>")


def test_compact_offer_removes_tag_truncated_mid_attribute(monkeypatch):
    monkeypatch.setattr("bot.db.offer_sold_count", lambda _offer_id: 0)
    offer = {
        "id": 43,
        "name": "Creative Cloud Pro",
        "price": 6.0,
        "stock": 1,
        "description": (
            '[[HTML]]<blockquote><b>Adobe apps</b>\n'
            '<b><tg-emoji emoji-id="4960958'
        ),
    }

    rendered = compact_offer_text(offer, "en")

    assert '<tg-emoji emoji-id="4960958' not in rendered
    assert rendered.endswith("<b></b></blockquote>")
    assert rendered.count("<blockquote>") == rendered.count("</blockquote>")

def test_single_offer_service_from_photo_opens_offer_without_editing_photo(monkeypatch):
    message = SimpleNamespace(text=None, reply_text=AsyncMock())
    query = SimpleNamespace(
        data="svc:7",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr("bot.db.get_service", lambda _sid: {"id": 7, "name": "Chat GPT", "emoji": "🤖"})
    monkeypatch.setattr("bot.db.list_offers", lambda _sid: [{"id": 9, "name": "30 days", "stock": 5}])
    monkeypatch.setattr(
        "bot.db.get_offer",
        lambda _oid: {"id": 9, "service_id": 7, "name": "30 days", "price": 5.0, "stock": 5},
    )

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    message.reply_text.assert_awaited_once()
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert "30 days" in message.reply_text.await_args.args[0]


def test_support_button_from_photo_opens_ticket_categories(monkeypatch):
    message = SimpleNamespace(text=None, reply_text=AsyncMock())
    query = SimpleNamespace(
        data="support",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=query.from_user,
        effective_message=message,
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(update, SimpleNamespace()))

    message.reply_text.assert_awaited_once()
    call = message.reply_text.await_args
    assert "Choose the category" in call.args[0]
    callbacks = [
        button.callback_data for row in call.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "support_cat:other" in callbacks


def test_admin_from_photo_caption_sends_a_new_text_panel(monkeypatch):
    message = SimpleNamespace(text=None, reply_text=AsyncMock())
    query = SimpleNamespace(
        data="adm_panel",
        from_user=SimpleNamespace(id=999),
        message=message,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    monkeypatch.setattr("bot.ADMIN_ID", 999)

    asyncio.run(cb_admin(update, SimpleNamespace()))

    message.reply_text.assert_awaited_once()
    assert "Panneau Admin" in message.reply_text.await_args.args[0]
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)


def test_cancel_payment_button_cancels_the_customers_order(monkeypatch):
    query = SimpleNamespace(
        data="cancel_buy:17",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Payment"),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    cancelled = []
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr("bot.db.get_order", lambda order_id: {"id": order_id, "user_id": 42})
    monkeypatch.setattr(
        "bot.order_service.cancel_order",
        lambda order_id, reason="": cancelled.append((order_id, reason)) or True,
    )

    asyncio.run(cb_navigation(update, SimpleNamespace()))

    assert cancelled == [(17, "Cancelled by customer")]
    query.edit_message_text.assert_awaited_once()


def test_cancel_payment_button_cannot_cancel_another_users_order(monkeypatch):
    query = SimpleNamespace(
        data="cancel_buy:17",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(text="Payment"),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    cancel_order = Mock()
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")
    monkeypatch.setattr("bot.db.get_order", lambda _order_id: {"id": 17, "user_id": 99})
    monkeypatch.setattr("bot.order_service.cancel_order", cancel_order)

    asyncio.run(cb_navigation(update, SimpleNamespace()))

    cancel_order.assert_not_called()


def test_orders_are_grouped_by_service_with_counts(monkeypatch):
    monkeypatch.setattr("bot.db.list_services", lambda: [
        {"name": "ChatGPT", "emoji": "🤖"},
        {"name": "Gemini", "emoji": "💡"},
    ])
    groups = order_service_groups([
        {"id": 1, "service_name": "Gemini"},
        {"id": 2, "service_name": "ChatGPT"},
        {"id": 3, "service_name": "ChatGPT"},
    ])

    assert [(group["name"], group["count"]) for group in groups] == [
        ("ChatGPT", 2),
        ("Gemini", 1),
    ]
    assert groups[0]["emoji"] == "🤖"


def test_orders_export_contains_complete_purchase_and_delivery_content(monkeypatch):
    monkeypatch.setattr("bot.db.get_offer", lambda _offer_id: {
        "note": "Replacement warranty for 30 days",
    })
    content = orders_text_export("en", [{
        "id": 7,
        "offer_id": 70,
        "service_name": "ChatGPT",
        "offer_name": "Plus",
        "qty": 2,
        "unit_price": 9.0,
        "gross_total": 18.0,
        "total_price": 18.0,
        "currency": "USDT",
        "status": "delivered",
        "created_at": 1_700_000_000,
        "delivered_at": 1_700_000_060,
        "payment_method": "binance",
        "txid": "TXID-123456",
        "delivery_text": "SECRET-CREDENTIAL",
    }], "ChatGPT")

    assert "ORDER #7" in content
    assert "ChatGPT" in content
    assert "18.00 USDT" in content
    assert "Replacement warranty for 30 days" in content
    assert "Purchase date: 2023-11-14 22:13:20 UTC" in content
    assert "Delivery date: 2023-11-14 22:14:20 UTC" in content
    assert "Transaction ID: TXID-123456" in content
    assert "PURCHASE CONTENT" in content
    assert "SECRET-CREDENTIAL" in content


def test_catalog_request_button_supports_admin_premium_emoji(mock_mongodb):
    db.set_text_override(
        "catalog_request_button", "en", "Request a product", "premium-catalog-request"
    )

    keyboard = kb.services_keyboard("en")
    button = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "catalog_request"
    )

    assert button.text == "Request a product"
    assert button.icon_custom_emoji_id == "premium-catalog-request"


def test_catalog_request_button_prompts_for_customer_need(monkeypatch, mock_mongodb):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data="catalog_request",
        from_user=SimpleNamespace(id=42),
        message=message,
        answer=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert PENDING.get(42) == ("catalog_request", 0)
    message.reply_text.assert_awaited_once()
    assert "Tell us what you need" in message.reply_text.await_args.args[0]
    PENDING.pop(42, None)


def test_catalog_request_is_saved_and_sent_to_support_channel(monkeypatch, mock_mongodb):
    create_ticket = Mock(return_value={
        "id": 17,
        "user_id": 42,
        "category": "catalog_request",
    })
    monkeypatch.setattr("bot.support_service.create_ticket", create_ticket)
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=801)),
    )
    message = SimpleNamespace(
        text="I need Microsoft 365 for one year",
        text_html=None,
        caption_html=None,
        entities=[],
        reply_text=AsyncMock(),
        delete=AsyncMock(),
    )
    user = SimpleNamespace(id=42, full_name="Test Customer", username="buyer")
    update = SimpleNamespace(effective_user=user, message=message)
    PENDING[42] = ("catalog_request", 0)

    asyncio.run(handle_pending_input(update, SimpleNamespace(bot=bot_client), "en"))

    create_ticket.assert_called_once_with(
        42, "I need Microsoft 365 for one year", category="catalog_request"
    )
    bot_client.send_message.assert_awaited_once()
    channel_call = bot_client.send_message.await_args
    assert channel_call.args[0] == -1004326329551
    assert "New catalog request" in channel_call.args[1]
    assert "Microsoft 365" in channel_call.args[1]
    assert PENDING.get(42) is None
    assert "Request sent" in message.reply_text.await_args.args[0]
    message.delete.assert_awaited_once()

def test_topup_keyboard_offers_supported_deposit_methods(mock_mongodb):
    callbacks = [
        button.callback_data
        for row in kb.topup_keyboard("en").inline_keyboard
        for button in row
    ]

    assert callbacks == ["topup_txid", "topup_onchain", "home"]


def test_topup_instructions_are_txid_only(mock_mongodb):
    message = t("en", "topup_message", binance_id="123", bybit_uid="456")

    assert "Memo" not in message
    assert "DEPOSIT" in message
    assert "456" not in message


@pytest.mark.parametrize(("network", "label", "suffix"), [
    ("bsc", "BSC (BEP20)", "97955"),
    ("polygon", "Polygon", "58e8f"),
])
def test_onchain_topup_uses_binance_style_card(network, label, suffix):
    message = topup_onchain_screen("en", network, 6)

    assert f"USDT TOP UP — {label}" in message
    assert "How to deposit" in message
    assert "Send exactly <b>6.00 USDT</b>" in message
    assert "Paste the TXID here in this chat" in message
    assert "Auto-verify and instant credit" in message
    assert f"ends in <b>{suffix}</b>" in message
    assert "within 30 minutes" in message


@pytest.mark.parametrize(("method", "label", "suffix"), [
    ("usdt_bsc", "BSC (BEP20)", "97955"),
    ("usdt_polygon", "Polygon", "58e8f"),
])
def test_onchain_order_payment_uses_binance_style_card(method, label, suffix):
    message = onchain_payment_screen("en", {
        "id": 81,
        "offer_name": "ChatGPT K12",
        "qty": 1,
        "total_price": 6,
        "payment_method": method,
    })

    assert f"USDT PAYMENT — {label}" in message
    assert "ChatGPT K12" in message
    assert "Order</b>\n#81" in message
    assert "Send exactly <b>6.00 USDT</b>" in message
    assert "Tap Submit TXID and paste it" in message
    assert f"ends in <b>{suffix}</b>" in message

def test_every_topup_button_supports_exact_premium_emoji(mock_mongodb):
    overrides = {
        "topup_verify_txid": ("Verify Binance TXID", "premium-topup-txid"),
        "topup_home_button": ("Home", "premium-topup-home"),
    }
    for key, (label, emoji_id) in overrides.items():
        db.set_text_override(key, "en", label, emoji_id)

    initial = kb.topup_keyboard("en")
    buttons = {
        button.callback_data: button
        for keyboard in (initial,)
        for row in keyboard.inline_keyboard
        for button in row
    }

    assert buttons["topup_txid"].icon_custom_emoji_id == "premium-topup-txid"
    assert buttons["home"].icon_custom_emoji_id == "premium-topup-home"
    assert buttons["topup_txid"].text == "Verify Binance TXID"


def test_empty_wallet_click_always_returns_a_visible_message(monkeypatch):
    query = SimpleNamespace(
        data="pay_wallet:9:1",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    update = SimpleNamespace(callback_query=query)
    monkeypatch.setattr("bot.db.get_offer", lambda _offer_id: {
        "id": 9, "price": 5.0, "stock": 1,
    })

    def reject_empty_wallet(*_args, **_kwargs):
        raise ValueError("Insufficient balance: 0.00 USDT available.")

    monkeypatch.setattr("bot.order_service.create_order", reject_empty_wallet)

    asyncio.run(handle_buy_confirmed(update, SimpleNamespace(), "en", "wallet"))

    query.message.reply_text.assert_awaited_once_with(
        "Insufficient balance: 0.00 USDT available."
    )


def test_codex_number_catalog_is_always_half_a_dollar_and_manual(mock_mongodb):
    service_id = db.add_service("OTP numbers", "OTP")
    offers = db.list_offers(service_id)
    assert len(offers) == 1
    offer_id = offers[0]["id"]

    raw = mock_mongodb.offers.find_one({"id": offer_id})
    offer = db.get_offer(offer_id)

    assert db.get_service(service_id)["name"] == "Codex number"
    assert raw["price"] == 0.5
    assert raw["unlimited_stock"] is True
    assert raw["manual_stock"] is True
    assert raw["auto_delivery"] is False
    assert offer["price"] == 0.5
    assert db.offer_has_stock(offer, 50) is True

    db.update_offer(offer_id, price=25.0, auto_delivery=True, unlimited_stock=False)
    updated = mock_mongodb.offers.find_one({"id": offer_id})
    assert updated["price"] == 0.5
    assert updated["auto_delivery"] is False
    assert updated["unlimited_stock"] is True


def test_existing_otp_service_migrates_to_codex_number_and_self_heals(mock_mongodb):
    mock_mongodb.services.insert_one({
        "id": 77,
        "name": "OTP Numbers",
        "emoji": "OTP",
        "sort_order": 1,
        "active": 1,
    })

    first = db.list_offers(77)
    second = db.list_offers(77)

    assert len(first) == 1
    assert len(second) == 1
    assert db.get_service(77)["name"] == "Codex number"
    assert first[0]["name"] == "Codex number"
    assert first[0]["price"] == 0.5
    assert first[0]["unlimited_stock"] is True
    assert first[0]["manual_stock"] is True
    assert mock_mongodb.offers.count_documents({"service_id": 77}) == 1


def test_automatically_delivered_paid_order_is_notified_to_admin(
    monkeypatch, mock_mongodb,
):
    mock_mongodb.orders.insert_one({
        "id": 500,
        "user_id": 42,
        "service_name": "Canva",
        "offer_name": "Canva Pro",
        "qty": 1,
        "status": "delivered",
    })
    notify_new_order = AsyncMock()
    monkeypatch.setattr("bot.admin.notify_new_order", notify_new_order)
    message = SimpleNamespace(reply_text=AsyncMock())

    asyncio.run(send_payment_result(
        message,
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        "en",
        500,
        {
            "status": "delivered",
            "affiliate": None,
            "loyalty": None,
            "delivered_content": ["account@example.com"],
        },
        42,
    ))

    notify_new_order.assert_awaited_once()
    assert notify_new_order.await_args.args[1]["id"] == 500


def test_manual_delivery_sends_admin_an_in_bot_reply_request(
    monkeypatch, mock_mongodb,
):
    mock_mongodb.orders.insert_one({
        "id": 503,
        "user_id": 42,
        "service_name": "Manual service",
        "offer_name": "Manual account",
        "qty": 1,
        "status": "paid",
    })
    notify_manual = AsyncMock()
    notify_new_order = AsyncMock()
    monkeypatch.setattr("bot.admin.notify_manual_delivery_request", notify_manual)
    monkeypatch.setattr("bot.admin.notify_new_order", notify_new_order)
    message = SimpleNamespace(reply_text=AsyncMock())

    asyncio.run(send_payment_result(
        message,
        SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        "en",
        503,
        {
            "status": "confirmed_no_delivery",
            "affiliate": None,
            "loyalty": None,
            "delivered_content": None,
        },
        42,
    ))

    notify_manual.assert_awaited_once()
    notify_new_order.assert_not_awaited()
    customer_keyboard = message.reply_text.await_args.kwargs["reply_markup"]
    assert customer_keyboard.inline_keyboard[0][0].callback_data == "catalog"


def test_created_supplier_order_offers_admin_message_or_manual_fallback(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.orders.insert_one({
        "id": 504,
        "user_id": 42,
        "offer_id": 12,
        "service_name": "Coursera",
        "offer_name": "Coursera account",
        "qty": 1,
        "unit_price": 7.5,
        "total_price": 7.5,
        "txid": "PAY-504",
        "verify_method": "binance",
        "status": "payment_confirmed",
    })
    mock_mongodb.users.insert_one({
        "telegram_id": 42,
        "username": "buyer42",
        "first_name": "Buyer Name",
        "lang": "en",
    })
    mock_mongodb.offers.insert_one({
        "id": 12,
        "service_id": 99,
        "name": "Coursera account",
        "supplier_provider": "cgpt_active",
        "supplier_product_id": "789",
        "price": 7.5,
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "cgpt_active",
        "external_order_id": "BM-504",
        "supplier_order_id": "SUP-88",
        "status": "delivery_pending",
    })
    notify_manual = AsyncMock()
    monkeypatch.setattr("bot.admin.notify_manual_delivery_request", notify_manual)
    message = SimpleNamespace(reply_text=AsyncMock())
    bot_client = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(send_payment_result(
        message,
        SimpleNamespace(bot=bot_client),
        "en",
        504,
        {
            "status": "confirmed_no_delivery",
            "affiliate": None,
            "loyalty": None,
            "delivered_content": None,
            "error_code": "supplier_delivery_pending",
            "error_message": "Supplier order created; delivery is pending.",
        },
        42,
    ))

    notify_manual.assert_not_awaited()
    admin_alert = bot_client.send_message.await_args
    assert admin_alert.args[0] == 999
    assert "BM-504" in admin_alert.args[1]
    assert "éviter une double livraison" in admin_alert.args[1]
    assert "Rich AI Store" in admin_alert.args[1]
    assert "@RichAIStoreBot" in admin_alert.args[1]
    assert "SUP-88" in admin_alert.args[1]
    assert "buyer42" in admin_alert.args[1]
    assert "Buyer Name" in admin_alert.args[1]
    assert "PAY-504" in admin_alert.args[1]
    assert "789" in admin_alert.args[1]
    keyboard = admin_alert.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "adm_client_message:504"
    assert keyboard.inline_keyboard[0][1].callback_data == "adm_deliver:504"


def test_rejected_supplier_order_sends_detailed_admin_incident(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.users.insert_one({
        "telegram_id": 42, "username": "api_buyer", "first_name": "API Buyer",
    })
    mock_mongodb.offers.insert_one({
        "id": 13,
        "service_id": 99,
        "name": "Mailbox",
        "supplier_provider": "mailreader",
        "supplier_product_id": "mail-7",
        "price": 2.0,
    })
    mock_mongodb.orders.insert_one({
        "id": 505,
        "user_id": 42,
        "offer_id": 13,
        "service_name": "Mail",
        "offer_name": "Mailbox",
        "qty": 2,
        "unit_price": 2.0,
        "total_price": 4.0,
        "status": "payment_confirmed",
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "mailreader",
        "external_order_id": "BM-505",
        "status": "not_created",
    })
    notify_manual = AsyncMock()
    monkeypatch.setattr("bot.admin.notify_manual_delivery_request", notify_manual)
    bot_client = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(send_payment_result(
        SimpleNamespace(reply_text=AsyncMock()),
        SimpleNamespace(bot=bot_client),
        "fr",
        505,
        {
            "status": "confirmed_no_delivery",
            "affiliate": None,
            "loyalty": None,
            "delivered_content": None,
            "error_code": "supplier_order_not_created",
            "error_message": "Supplier balance is insufficient.",
        },
        42,
    ))

    notify_manual.assert_not_awaited()
    incident = bot_client.send_message.await_args.args[1]
    assert "@dodistore_bot" in incident
    assert "api_buyer" in incident
    assert "supplier_order_not_created" in incident
    assert "Supplier balance is insufficient." in incident


def test_manual_fallback_does_not_send_if_api_already_delivered(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 507,
        "user_id": 42,
        "service_name": "Coursera",
        "offer_name": "Coursera account",
        "status": "delivered",
    })
    message = SimpleNamespace(reply_text=AsyncMock())
    bot_client = SimpleNamespace(send_message=AsyncMock())

    delivered = asyncio.run(deliver_order(
        SimpleNamespace(message=message),
        SimpleNamespace(bot=bot_client),
        507,
        "manual duplicate",
    ))

    assert delivered is False
    bot_client.send_message.assert_not_awaited()
    assert "Aucun contenu n’a été envoyé" in message.reply_text.await_args.args[0]


def test_paid_codex_order_is_sent_to_admin_for_number(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 501,
        "user_id": 42,
        "service_name": "OTP numbers",
        "offer_name": "OTP code",
        "qty": 2,
        "status": "payment_confirmed",
    })
    message = SimpleNamespace(reply_text=AsyncMock())

    bot_client = SimpleNamespace(send_message=AsyncMock())
    asyncio.run(send_payment_result(
        message,
        SimpleNamespace(bot=bot_client),
        "en",
        501,
        {
            "status": "confirmed_no_delivery",
            "affiliate": None,
            "loyalty": None,
            "delivered_content": None,
        },
        42,
    ))

    assert PENDING.get(42) is None
    assert "preparing your Codex number" in message.reply_text.await_args.args[0]
    assert mock_mongodb.orders.find_one({"id": 501})["otp_workflow_status"] == "awaiting_admin_number"
    admin_call = bot_client.send_message.await_args
    assert "New paid Codex number order" in admin_call.args[1]
    assert admin_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "adm_codex_number:501"


def test_codex_number_agreement_then_otp_completes_order(monkeypatch, mock_mongodb):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.orders.insert_one({
        "id": 502,
        "user_id": 42,
        "service_name": "Codex number",
        "offer_name": "Codex number",
        "qty": 1,
        "wallet_amount": 0.5,
        "total_price": 0.0,
        "payment_method": "wallet",
        "verify_method": "wallet",
        "txid": "",
        "status": "payment_confirmed",
        "otp_workflow_status": "awaiting_admin_number",
    })
    bot_client = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(bot=bot_client)

    admin_query = SimpleNamespace(
        from_user=SimpleNamespace(id=999),
        data="adm_codex_number:502",
        answer=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    asyncio.run(cb_admin(SimpleNamespace(callback_query=admin_query), context))
    assert PENDING.get(999) == ("adm_codex_number", 502)

    number_message = SimpleNamespace(text="+234 555 0100", reply_text=AsyncMock())
    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=SimpleNamespace(id=999), message=number_message),
        context,
        "en",
    ))
    order = mock_mongodb.orders.find_one({"id": 502})
    assert order["otp_workflow_status"] == "number_sent"
    assert order["codex_number"] == "+234 555 0100"
    assert order["codex_agree_deadline"] - order["codex_number_sent_at"] == 300
    customer_call = bot_client.send_message.await_args
    assert customer_call.args[0] == 42
    assert "within *5 minutes*" in customer_call.args[1]
    assert customer_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "codex_number_agree:502"

    agree_query = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        data="codex_number_agree:502",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    asyncio.run(cb_navigation(SimpleNamespace(callback_query=agree_query), context))
    order = mock_mongodb.orders.find_one({"id": 502})
    assert order["otp_workflow_status"] == "customer_agreed"
    admin_call = bot_client.send_message.await_args
    assert admin_call.args[0] == 999
    assert "Customer accepted" in admin_call.args[1]
    assert admin_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "adm_codex_otp:502"

    otp_query = SimpleNamespace(
        from_user=SimpleNamespace(id=999),
        data="adm_codex_otp:502",
        answer=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    asyncio.run(cb_admin(SimpleNamespace(callback_query=otp_query), context))
    assert PENDING.get(999) == ("adm_codex_otp", 502)

    otp_message = SimpleNamespace(text="847201", reply_text=AsyncMock())
    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=SimpleNamespace(id=999), message=otp_message),
        context,
        "en",
    ))
    order = mock_mongodb.orders.find_one({"id": 502})
    assert order["status"] == "delivered"
    assert order["otp_workflow_status"] == "completed"
    assert "OTP: 847201" in order["delivery_text"]


def test_codex_order_cannot_use_generic_admin_delivery(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 504,
        "user_id": 42,
        "service_name": "Codex number",
        "offer_name": "Codex number",
        "status": "payment_confirmed",
        "otp_workflow_status": "awaiting_admin_number",
    })
    message = SimpleNamespace(reply_text=AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    asyncio.run(deliver_order(
        SimpleNamespace(message=message), context, 504, "bypass content",
    ))

    order = mock_mongodb.orders.find_one({"id": 504})
    assert order["status"] == "payment_confirmed"
    context.bot.send_message.assert_not_awaited()
    assert "Generic delivery is disabled" in message.reply_text.await_args.args[0]


def test_codex_monitor_expires_unaccepted_number_and_notifies_both_sides(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.users.insert_one({"telegram_id": 42, "lang": "en"})
    mock_mongodb.orders.insert_many([
        {
            "id": 505,
            "user_id": 42,
            "service_name": "Codex number",
            "status": "payment_confirmed",
            "otp_workflow_status": "number_sent",
            "codex_agree_deadline": 100,
        },
        {
            "id": 506,
            "user_id": 42,
            "service_name": "Codex number",
            "status": "payment_confirmed",
            "otp_workflow_status": "number_sent",
            "codex_agree_deadline": 500,
        },
    ])
    bot_client = SimpleNamespace(send_message=AsyncMock())

    expired = asyncio.run(monitor_codex_number_deadlines(bot_client, now=101))

    assert [order["id"] for order in expired] == [505]
    overdue = mock_mongodb.orders.find_one({"id": 505})
    future = mock_mongodb.orders.find_one({"id": 506})
    assert overdue["status"] == "expired"
    assert overdue["otp_workflow_status"] == "acceptance_expired"
    assert future["status"] == "payment_confirmed"
    assert bot_client.send_message.await_count == 2
    assert {call.args[0] for call in bot_client.send_message.await_args_list} == {42, 999}


def test_admin_message_does_not_complete_manual_order(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 601,
        "user_id": 42,
        "status": "payment_confirmed",
    })
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    bot_client = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(send_admin_message_to_client(
        update, SimpleNamespace(bot=bot_client), 601, "Your account is being prepared.",
    ))

    assert db.get_order(601)["status"] == "payment_confirmed"
    customer_call = bot_client.send_message.await_args
    assert customer_call.args[0] == 42
    assert "Your account is being prepared." in customer_call.args[1]
    assert customer_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "manual_reply:601"
    assert "reste en attente" in update.message.reply_text.await_args.args[0]


def test_customer_can_reply_until_manual_order_is_delivered(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.orders.insert_one({
        "id": 604,
        "user_id": 42,
        "service_name": "Canva",
        "offer_name": "Canva Pro invitation",
        "status": "payment_confirmed",
    })
    PENDING[42] = ("manual_order_reply", 604)
    message = SimpleNamespace(
        text="customer@example.com",
        reply_text=AsyncMock(),
    )
    bot_client = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=SimpleNamespace(id=42), message=message),
        SimpleNamespace(bot=bot_client),
        "en",
    ))

    admin_call = bot_client.send_message.await_args
    assert admin_call.args[0] == 999
    assert "customer@example.com" in admin_call.args[1]
    assert admin_call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "adm_client_message:604"
    assert admin_call.kwargs["reply_markup"].inline_keyboard[0][1].callback_data == "adm_deliver:604"
    assert db.get_order(604)["status"] == "payment_confirmed"
    assert PENDING.get(42) is None

    mock_mongodb.orders.update_one(
        {"id": 604}, {"$set": {"status": "delivered"}},
    )
    PENDING[42] = ("manual_order_reply", 604)
    closed_message = SimpleNamespace(
        text="another@example.com",
        reply_text=AsyncMock(),
    )
    bot_client.send_message.reset_mock()

    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=SimpleNamespace(id=42), message=closed_message),
        SimpleNamespace(bot=bot_client),
        "en",
    ))

    bot_client.send_message.assert_not_awaited()
    assert "conversation is closed" in closed_message.reply_text.await_args.args[0]
    assert PENDING.get(42) is None


def test_manual_order_is_delivered_and_retried_to_channel(monkeypatch, mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 602,
        "user_id": 42,
        "service_name": "Manual service",
        "offer_name": "Manual account",
        "status": "payment_confirmed",
        "delivery_text": "",
    })
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    bot_client = SimpleNamespace(send_message=AsyncMock())
    channel_post = AsyncMock()
    monkeypatch.setattr("bot.admin.post_purchase_to_channel", channel_post)

    asyncio.run(deliver_order(
        update, SimpleNamespace(bot=bot_client), 602, "login:password",
    ))

    delivered = db.get_order(602)
    assert delivered["status"] == "delivered"
    assert delivered["delivery_text"] == "login:password"
    sent = bot_client.send_message.await_args
    assert sent.kwargs["parse_mode"] == ParseMode.HTML
    assert "[HTML]" not in sent.kwargs["text"]
    assert "<b>Your order #602 has been delivered!</b>" in sent.kwargs["text"]
    channel_post.assert_not_awaited()


def test_manual_delivery_preserves_urls_and_special_characters(mock_mongodb):
    content = "https://example.com/a_b?token=x&next=#part\nPassword: #a_b*c<d>"

    rendered = premium_customer_text(
        "en",
        "delivery_received",
        oid=602,
        service="Manual service",
        offer="Manual account",
        content=content,
    )

    assert "https://example.com/a_b?token=x&amp;next=#part" in rendered
    assert "Password: #a_b*c&lt;d&gt;" in rendered
    assert "<i>" not in rendered


def test_manual_order_can_be_delivered_as_a_photo(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 605,
        "user_id": 42,
        "service_name": "Manual service",
        "offer_name": "Manual account",
        "status": "payment_confirmed",
        "delivery_text": "",
    })
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    bot_client = SimpleNamespace(send_photo=AsyncMock())

    delivered = asyncio.run(deliver_order(
        update,
        SimpleNamespace(bot=bot_client),
        605,
        "Image avec URL https://example.com/a_b?x=1&y=#part",
        photo_file_id="telegram-photo-id",
    ))

    assert delivered is True
    bot_client.send_photo.assert_awaited_once()
    sent = bot_client.send_photo.await_args.kwargs
    assert sent["photo"] == "telegram-photo-id"
    assert "https://example.com/a_b?x=1&amp;y=#part" in sent["caption"]
    assert db.get_order(605)["status"] == "delivered"


def test_failed_manual_send_keeps_order_waiting(mock_mongodb):
    mock_mongodb.orders.insert_one({
        "id": 603,
        "user_id": 42,
        "service_name": "Manual service",
        "offer_name": "Manual account",
        "status": "payment_confirmed",
        "delivery_text": "",
    })
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    bot_client = SimpleNamespace(
        send_message=AsyncMock(side_effect=RuntimeError("Telegram unavailable")),
    )

    asyncio.run(deliver_order(
        update, SimpleNamespace(bot=bot_client), 603, "login:password",
    ))

    waiting = db.get_order(603)
    assert waiting["status"] == "payment_confirmed"
    assert waiting["delivery_text"] == ""
    assert "Échec d'envoi" in update.message.reply_text.await_args.args[0]


def test_onchain_txid_submission_auto_verifies_without_admin_request(
    monkeypatch, mock_mongodb,
):
    monkeypatch.setattr("bot.ADMIN_ID", 999)
    mock_mongodb.orders.insert_one({
        "id": 154,
        "user_id": 42,
        "offer_id": 1,
        "service_name": "VPN",
        "offer_name": "VPN plan",
        "qty": 1,
        "total_price": 13.20,
        "payment_method": "usdt_polygon",
        "status": "pending_payment",
        "txid": "",
        "created_at": 100,
        "expires_at": 9999999999,
    })
    txid = "0x" + "d" * 64
    PENDING[42] = (
        "await_onchain_txid",
        {"order_id": 154, "network": "Polygon"},
    )
    message = SimpleNamespace(text=txid, reply_text=AsyncMock())
    bot_client = SimpleNamespace(send_message=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )
    monkeypatch.setattr(
        "bot.payment_service.submit_onchain_payment",
        lambda *_args, **_kwargs: {
            "status": "pending", "network": "Polygon",
            "error_code": "confirming", "error_message": "Waiting",
        },
    )

    asyncio.run(
        handle_pending_input(update, SimpleNamespace(bot=bot_client), "en")
    )

    bot_client.send_message.assert_not_awaited()
    assert message.reply_text.await_count == 2
    assert "not confirmed yet" in message.reply_text.await_args.args[0]


def test_customer_support_text_is_deleted_after_channel_delivery(mock_mongodb):
    PENDING[42] = ("support", "other")
    user = SimpleNamespace(
        id=42,
        full_name="Support Client",
        first_name="Support",
        username="client42",
    )
    message = SimpleNamespace(
        text="I need help",
        reply_text=AsyncMock(),
        delete=AsyncMock(),
    )
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=800)),
    )

    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=user, message=message),
        SimpleNamespace(bot=bot_client),
        "en",
    ))

    message.delete.assert_awaited_once()
    assert bot_client.send_message.await_args.args[0] == -1004326329551
    assert "I need help" in bot_client.send_message.await_args.args[1]


def test_customer_can_close_active_support_ticket(monkeypatch, mock_mongodb):
    ticket = support_service.create_ticket(42, "Help", category="other")
    PENDING[42] = ("ticket_message", ticket["id"])
    close_notice = AsyncMock()
    monkeypatch.setattr("bot.support_bridge.send_ticket_closed", close_notice)
    query = SimpleNamespace(
        data=f"ticket_close:{ticket['id']}",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    monkeypatch.setattr("bot.lang_of", lambda _user_id: "en")

    asyncio.run(cb_navigation(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(bot=SimpleNamespace()),
    ))

    assert support_service.get_ticket(ticket["id"])["status"] == "closed"
    assert PENDING.get(42) is None
    query.edit_message_text.assert_awaited_once()
    close_notice.assert_awaited_once()


def test_attachment_can_create_the_first_ticket_message(mock_mongodb):
    PENDING[42] = ("support", "other")
    user = SimpleNamespace(
        id=42,
        full_name="Media Client",
        first_name="Media",
        username="media42",
    )
    message = SimpleNamespace(
        message_id=61,
        chat_id=42,
        chat=SimpleNamespace(id=42),
        caption="See screenshot",
        photo=[SimpleNamespace(file_id="photo")],
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        sticker=None,
        reply_text=AsyncMock(),
        delete=AsyncMock(),
    )
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=801)),
        copy_message=AsyncMock(return_value=SimpleNamespace(message_id=802)),
    )

    handled = asyncio.run(handle_ticket_attachment(
        SimpleNamespace(effective_user=user, effective_message=message),
        SimpleNamespace(bot=bot_client),
    ))

    assert handled is True
    ticket = mock_mongodb.support_tickets.find_one({"user_id": 42})
    assert ticket["category"] == "other"
    assert PENDING.get(42) == ("ticket_message", ticket["id"])
    message.reply_text.assert_awaited_once()
    message.delete.assert_awaited_once()
    bot_client.copy_message.assert_awaited_once()


def test_is_single_emoji_validation():
    from bot import _is_single_emoji
    assert _is_single_emoji("📦") is True
    assert _is_single_emoji("🎁") is True
    assert _is_single_emoji("🔥") is True
    assert _is_single_emoji("🎓") is True
    assert _is_single_emoji("630745097360") is False
    assert _is_single_emoji("6307450973606389056") is False
    assert _is_single_emoji("coursera") is False
    assert _is_single_emoji("") is False
    assert _is_single_emoji(None) is False


def test_announcement_service_emoji_sanitizes_corrupted_emoji():
    from bot import _announcement_service_emoji
    service = {"id": 40, "emoji": "630745097360", "custom_emoji_id": "6307450973606389056"}
    token = _announcement_service_emoji(service, fallback="📦")
    expected_hex = "📦".encode("utf-8").hex()
    assert f"[[TGEMOJI:6307450973606389056:{expected_hex}]]" == token


def test_render_custom_emoji_sanitizes_non_emoji_fallback():
    from bot import render_stored_rich_text
    corrupted_token = f"[[TGEMOJI:6307450973606389056:{'630745097360'.encode('utf-8').hex()}]]"
    rendered = render_stored_rich_text(corrupted_token)
    assert '<tg-emoji emoji-id="6307450973606389056">📦</tg-emoji>' in rendered


def test_send_broadcast_message_safe_falls_back_on_entity_error():
    from telegram.error import BadRequest
    from bot import _send_broadcast_message_safe

    mock_bot = Mock()
    mock_bot.send_message = AsyncMock(side_effect=[
        BadRequest("Entity_text_invalid"),
        SimpleNamespace(message_id=999),
    ])
    context = SimpleNamespace(bot=mock_bot)

    msg = asyncio.run(_send_broadcast_message_safe(
        context,
        chat_id=123,
        text="<b>Bold text</b> with <tg-emoji emoji-id='123'>invalid</tg-emoji>",
    ))
    assert msg.message_id == 999
    assert mock_bot.send_message.await_count == 2
    fallback_call = mock_bot.send_message.await_args_list[1]
    assert "Bold text with invalid" in fallback_call.kwargs["text"]
    assert "<" not in fallback_call.kwargs["text"]


def test_unarchive_offer_and_service_sanitizer(mock_mongodb):
    s_id = db.add_service("Coursera", emoji="630745097360", custom_emoji_id="6307450973606389056")
    off_id = db.add_offer(s_id, "Coursera 1 Month", 2.0, 3)
    db.archive_offer(off_id)
    off = db.get_offer(off_id)
    assert off["archived"] == 1
    assert off["active"] == 0

    db.unarchive_offer(off_id)
    off = db.get_offer(off_id)
    assert off["archived"] == 0
    assert off["active"] == 1

    svc = db.get_service(s_id)
    assert svc["emoji"] == "📦"
    assert svc["custom_emoji_id"] == "6307450973606389056"

