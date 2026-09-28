"""Tests for Telegram keyboard labels."""

import admin
import database as db
import keyboards as kb
from keyboards import offer_button_label, stock_badge, stock_button_style


def test_quantity_keyboard_uses_stock_as_maximum():
    keyboard = kb.quantity_keyboard("fr", {"id": 9, "stock": 7})

    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "buyq:9:1" in callbacks
    assert "buyq:9:7" in callbacks
    assert "buyq:9:8" not in callbacks


def test_delivery_keeps_customer_inside_bot_without_admin_contact():
    keyboard = kb.post_delivery_keyboard("en", 6074)
    button = keyboard.inline_keyboard[0][0]

    assert button.callback_data == "catalog"
    assert button.url is None


def test_profile_keyboard_matches_customer_profile_navigation():
    keyboard = kb.profile_keyboard("en")
    callbacks = [
        [button.callback_data for button in row]
        for row in keyboard.inline_keyboard
    ]
    assert callbacks == [
        ["topup"],
        ["profile_withdraw", "profile_notifications"],
        ["orders", "warranty"],
        ["affiliate", "catalog"],
        ["reseller_api"],
        ["home"],
    ]
    styles = {
        button.callback_data: button.style
        for row in keyboard.inline_keyboard
        for button in row
    }
    assert styles["topup"] == "success"
    assert styles["reseller_api"] == "success"
    assert styles["home"] == "danger"
    assert {
        styles[action]
        for action in ("profile_withdraw", "profile_notifications", "orders", "warranty", "affiliate", "catalog")
    } == {"primary"}


def test_notification_manager_lists_every_product_with_pagination(monkeypatch):
    offers = [
        {"id": index, "name": f"Plan {index}", "service_name": "AI"}
        for index in range(1, 11)
    ]
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: offers)
    monkeypatch.setattr(
        kb.db, "disabled_catalog_notification_offer_ids", lambda _uid, _ids: {2},
    )

    keyboard = kb.profile_notifications_keyboard("en", 42, True)
    product_buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data.startswith("profile_product_notification:")
    ]

    assert len(product_buttons) == 8
    assert product_buttons[0].text.startswith("🔔")
    assert product_buttons[1].text.startswith("🔕")
    assert any(
        button.callback_data == "profile_notifications_page:1"
        for row in keyboard.inline_keyboard
        for button in row
    )

def test_catalog_reuses_shared_translation_and_icon_lookups(monkeypatch):
    offers = [
        {
            "id": index,
            "name": f"Offer {index}",
            "price": 1.0,
            "stock": 10,
            "service_id": 1,
        }
        for index in range(1, 21)
    ]
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: offers)
    translation_calls = []
    icon_calls = []

    def fake_t(_lang, key, **_kwargs):
        translation_calls.append(key)
        return {
            "stock_label": "Stock",
            "price_tbd": "Price TBD",
            "catalog_request_button": "Request",
            "catalog_preorder_button": "Pre-order",
            "catalog_notifications_on": "Catalog alerts: on",
            "catalog_notifications_off": "Catalog alerts: off",
            "btn_refresh_short": "Refresh",
            "btn_main_menu_short": "Home",
            "menu_lovable": "Lovable Unlimited Credit",
        }[key]

    def fake_icon(key, lang):
        icon_calls.append((key, lang))
        return ""

    monkeypatch.setattr(kb, "t", fake_t)
    monkeypatch.setattr(kb.db, "get_text_override_icon", fake_icon)

    keyboard = kb.catalog_offers_keyboard("en")

    assert len(keyboard.inline_keyboard) >= 3
    assert translation_calls.count("stock_label") >= 1
    assert translation_calls.count("price_tbd") >= 1
    assert icon_calls.count(("stock_label", "en")) >= 1


def test_quantity_confirmation_keeps_selected_quantity():
    keyboard = kb.confirm_buy_keyboard("fr", 9, 4)

    assert keyboard.inline_keyboard[0][0].callback_data == "pay_wallet:9:4"
    assert keyboard.inline_keyboard[1][0].callback_data == "pay_binance:9:4"
    assert keyboard.inline_keyboard[2][0].callback_data == "pay_bsc:9:4"
    assert keyboard.inline_keyboard[3][0].callback_data == "pay_polygon:9:4"


def test_onchain_payment_keyboard_submits_txid_without_auto_confirmation():
    keyboard = kb.onchain_payment_keyboard("en", 81, "0xabc")

    assert keyboard.inline_keyboard[0][0].text == "📋 Copy address"
    assert keyboard.inline_keyboard[0][0].copy_text.text == "0xabc"
    assert keyboard.inline_keyboard[1][0].callback_data == "paid_chain:81"
    assert keyboard.inline_keyboard[2][0].callback_data == "change_payment:81"
    assert keyboard.inline_keyboard[3][0].callback_data == "home"


def test_onchain_topup_keyboard_copies_address_and_keeps_navigation():
    keyboard = kb.topup_provider_keyboard("en", "polygon", "0xabc")

    assert keyboard.inline_keyboard[0][0].text == "📋 Copy address"
    assert keyboard.inline_keyboard[0][0].copy_text.text == "0xabc"
    assert keyboard.inline_keyboard[1][0].callback_data == "topup"
    assert keyboard.inline_keyboard[2][0].callback_data == "home"


def test_manual_delivery_keyboard_separates_message_from_order_delivery():
    keyboard = admin.manual_delivery_request_keyboard(503)

    assert keyboard.inline_keyboard[0][0].callback_data == "adm_client_message:503"
    assert keyboard.inline_keyboard[0][1].callback_data == "adm_deliver:503"


def test_manual_order_reply_keyboard_targets_the_same_order():
    keyboard = kb.manual_order_reply_keyboard("en", 503)

    assert keyboard.inline_keyboard[0][0].callback_data == "manual_reply:503"


def test_offer_button_label_uses_store_style():
    label = offer_button_label(
        "en",
        {
            "name": "SuperGrok 12 Months",
            "period_days": 365,
            "price": 30.0,
            "stock": 12,
        },
    )

    assert label == "SuperGrok 12 Months | 365 days | $30"


def test_offer_button_label_uses_sky_blue_for_low_stock():
    label = offer_button_label(
        "en",
        {
            "name": "Low Stock Product",
            "price": 5.0,
            "stock": 2,
        },
    )

    assert label == "Low Stock Product | 30 days | $5"


def test_offer_button_keeps_non_dollar_currency_visible():
    label = offer_button_label(
        "en",
        {"name": "European plan", "price": 4.5, "currency": "EUR", "stock": 3},
    )

    assert label == "European plan | 30 days | 4.5 EUR"


def test_offer_button_places_unicode_emoji_and_period_before_price():
    label = offer_button_label(
        "en",
        {
            "name": "Premium",
            "service_emoji": "⭐",
            "period_days": 30,
            "price": 5,
            "stock": 4,
        },
    )

    assert label == "⭐ Premium | 30 days | $5"


def test_offer_button_always_keeps_price_visible_with_long_name():
    label = offer_button_label(
        "en", {"name": "A" * 100, "price": 2.5, "stock": 35},
    )

    assert label.endswith("| $2.5")
    assert len(label) <= 64


def test_unlimited_offer_hides_stock_and_remains_buyable():
    offer = {
        "id": 9, "service_id": 1, "name": "Managed accounts",
        "price": 5.0, "stock": 0, "unlimited_stock": True,
    }

    assert "Stock" not in offer_button_label("en", offer)
    callbacks = [
        button.callback_data
        for row in kb.offer_detail_keyboard("en", offer).inline_keyboard
        for button in row
    ]
    assert "buy:9" in callbacks
    assert any(c in callbacks for c in ("catalog", "svc:1"))


def test_offer_button_uses_bulk_unit_price_when_configured():
    label = offer_button_label("en", {
        "name": "Bulk plan", "period_days": 30, "price": 5.0, "stock": 20,
        "bulk_quantity": 5, "bulk_unit_price": 3.25,
    })

    assert label == "Bulk plan | 30 days | $3.25"
    assert "Stock" not in label


def test_preorder_checkout_keeps_flag_in_every_payment_callback():
    callbacks = [
        button.callback_data
        for row in kb.confirm_buy_keyboard("en", 9, 3, preorder=True).inline_keyboard
        for button in row
    ]

    payment_callbacks = [value for value in callbacks if value.startswith("pay_")]
    assert payment_callbacks
    assert all(value.endswith(":9:3:preorder") for value in payment_callbacks)


def test_catalog_has_a_dedicated_preorder_button(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [])

    keyboard = kb.catalog_offers_keyboard("en")
    preorder = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "preorder_catalog"
    )

    assert preorder.text == "⏳ Pre-order"
    assert preorder.style == "primary"


def test_catalog_footer_uses_requested_action_colors(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [])

    keyboard = kb.catalog_offers_keyboard("en")
    actions = {
        button.callback_data: button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }

    assert actions["preorder_catalog"].style == "primary"
    assert actions["catalog_request"].style == "primary"
    assert actions["catalog"].style == "success"
    assert actions["home"].style == "danger"


def test_normal_catalog_does_not_launch_legacy_direct_preorder(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [{
        "id": 11, "service_id": 1, "service_name": "ChatGPT",
        "name": "Plus", "price": 10.0, "currency": "USDT",
        "stock": 0, "unlimited_stock": False,
    }])

    keyboard = kb.catalog_offers_keyboard("en")
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]

    assert "off:11" in callbacks
    assert "svc:1" not in callbacks
    assert "preorder_start:11" not in callbacks
    assert callbacks.count("preorder_catalog") == 1


def test_catalog_product_backgrounds_match_stock_availability(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [
        {
            "id": 11, "service_id": 1, "service_name": "Available",
            "name": "In stock", "price": 10.0, "currency": "USDT",
            "stock": 1, "unlimited_stock": False,
        },
        {
            "id": 12, "service_id": 2, "service_name": "Unavailable",
            "name": "Out of stock", "price": 10.0, "currency": "USDT",
            "stock": 0, "unlimited_stock": False,
        },
    ])

    keyboard = kb.catalog_offers_keyboard("en")
    products = {
        button.callback_data: button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data in {"off:11", "off:12"}
    }

    assert products["off:11"].style == "success"
    assert products["off:12"].style == "danger"


def test_preorder_catalog_lists_only_empty_services_and_adjusted_offers(monkeypatch):
    offers = [
        {
            "id": 11, "service_id": 1, "service_name": "ChatGPT",
            "service_emoji": "🤖", "name": "Plus", "price": 10.0,
            "currency": "USDT", "stock": 0,
        },
        {
            "id": 12, "service_id": 1, "service_name": "ChatGPT",
            "service_emoji": "🤖", "name": "Team", "price": 20.0,
            "currency": "USDT", "stock": 3,
        },
        {
            "id": 13, "service_id": 2, "service_name": "Unlimited",
            "service_emoji": "♾️", "name": "Managed", "price": 5.0,
            "currency": "USDT", "stock": 0, "unlimited_stock": True,
        },
    ]
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: offers)

    services = kb.preorder_services_keyboard("en")
    service_buttons = [
        button for row in services.inline_keyboard for button in row
        if button.callback_data and button.callback_data.startswith("preorder_svc:")
    ]
    assert [button.callback_data for button in service_buttons] == ["preorder_svc:1"]
    assert service_buttons[0].style == "primary"

    products = kb.preorder_offers_keyboard("en", 1)
    product_buttons = [
        button for row in products.inline_keyboard for button in row
        if button.callback_data and button.callback_data.startswith("preorder_start:")
    ]
    assert [button.callback_data for button in product_buttons] == ["preorder_start:11"]
    assert "$11" in product_buttons[0].text
    assert product_buttons[0].style == "danger"


def test_stock_label_is_listed_in_catalog_admin_category():
    assert admin.text_category_for_key("stock_label") == "catalog"


def test_stock_and_flash_templates_have_a_dedicated_editable_admin_section():
    expected_keys = {
        "channel_stock_announcement", "offer_stock_announcement",
        "flash_sale_announcement",
    }
    assert all(admin.text_category_for_key(key) == "alerts" for key in expected_keys)

    callbacks = {
        button.callback_data
        for row in admin.alert_design_keyboard().inline_keyboard
        for button in row
    }
    assert {f"adm_text_key:{key}" for key in expected_keys} <= callbacks
    assert any(
        button.callback_data == "adm_alert_design"
        for row in admin.customize_keyboard().inline_keyboard
        for button in row
    )


def test_official_preorder_catalog_uses_its_own_row(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [
        {
            "id": 1, "service_id": 2,
            "service_name": "Officiels subscriptions",
            "name": "Official", "price": 5, "stock": 0,
        },
        {
            "id": 2, "service_id": 1,
            "service_name": "Chat GPT",
            "name": "Plus", "price": 5, "stock": 0,
        },
    ])

    keyboard = kb.preorder_services_keyboard("fr")

    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == [
        "preorder_svc:2"
    ]
    assert keyboard.inline_keyboard[0][0].style == "primary"
    assert keyboard.inline_keyboard[1][0].callback_data == "preorder_svc:1"


def test_stock_label_accepts_admin_premium_emoji(monkeypatch):
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [{
        "id": 8, "name": "Premium", "stock": 2, "custom_emoji_id": "offer-icon",
    }])
    monkeypatch.setattr(
        kb.db,
        "get_text_override_icon",
        lambda key, lang: "premium-stock-icon" if key == "stock_label" else "",
    )

    button = kb.offers_keyboard("en", 1).inline_keyboard[0][0]

    assert button.icon_custom_emoji_id == "premium-stock-icon"


def test_stock_badge_and_product_button_styles_show_availability():
    assert stock_badge(4) in {"🟢", "🟩"}
    assert stock_badge(3) in {"🔵", "🟦"}
    assert stock_badge(2) in {"🔵", "🟦"}
    assert stock_badge(1) in {"🔵", "🟦"}
    assert stock_badge(0) in {"🔴", "🟥"}
    assert stock_button_style(4) == "success"
    assert stock_button_style(3) == "success"
    assert stock_button_style(2) == "success"
    assert stock_button_style(1) == "success"
    assert stock_button_style(0) == "danger"


def test_services_keyboard_is_always_sky_blue(monkeypatch):
    services = [
        {"id": 1, "name": "Large", "emoji": "📦"},
        {"id": 2, "name": "Low", "emoji": "📦"},
        {"id": 3, "name": "Empty", "emoji": "📦"},
    ]
    services[0]["total_stock"] = 4
    services[1]["total_stock"] = 3
    services[2]["total_stock"] = 0
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: services)

    keyboard = kb.services_keyboard("fr")
    labels = [
        button.text
        for row in keyboard.inline_keyboard[:-2]
        for button in row
    ]

    assert labels == ["📦 Large", "📦 Low", "📦 Empty"]
    assert keyboard.inline_keyboard[0][0].style == "primary"
    assert keyboard.inline_keyboard[0][1].style == "primary"
    assert keyboard.inline_keyboard[1][0].style == "primary"


def test_offer_buttons_use_native_telegram_styles(monkeypatch):
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [
        {"id": 1, "name": "Large", "price": 10.0, "stock": 4, "note": ""},
        {"id": 2, "name": "Low", "price": 10.0, "stock": 3, "note": ""},
        {"id": 3, "name": "Empty", "price": 10.0, "stock": 0, "note": ""},
    ])

    keyboard = kb.offers_keyboard("en", 1)

    assert keyboard.inline_keyboard[0][0].style == "success"
    assert keyboard.inline_keyboard[1][0].style == "success"
    assert keyboard.inline_keyboard[2][0].style == "danger"


def test_orders_services_keyboard_matches_grouped_design():
    keyboard = kb.orders_services_keyboard("en", [
        {"name": "ChatGPT", "emoji": "🤖", "count": 6},
        {"name": "Gemini", "emoji": "💡", "count": 2},
    ], total=8)

    assert keyboard.inline_keyboard[0][0].text == "🤖 ChatGPT (6)"
    assert keyboard.inline_keyboard[0][0].callback_data == "orders_group:0"
    assert keyboard.inline_keyboard[2][0].text == "📊 All Orders (8)"
    assert keyboard.inline_keyboard[-1][0].callback_data == "home"


def test_offer_button_label_truncates_long_names():
    label = offer_button_label(
        "en",
        {
            "name": "Very Long Product Name With Many Details And Devices",
            "note": "",
            "price": 2.5,
            "stock": 0,
        },
    )

    assert "$2.5" in label
    assert len(label) <= 64


def test_offer_button_uses_admin_selected_animated_emoji(monkeypatch):
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [{
        "id": 8,
        "name": "Premium",
        "price": 5,
        "stock": 2,
        "custom_emoji_id": "admin-selected-id",
    }])

    button = kb.offers_keyboard("en", 1).inline_keyboard[0][0]

    assert button.text == "Premium | 30 days | $5"
    assert button.icon_custom_emoji_id == "admin-selected-id"


def test_service_button_uses_admin_selected_animated_emoji(monkeypatch):
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: [{
        "id": 3,
        "name": "Streaming",
        "total_stock": 8,
        "custom_emoji_id": "premium-service-emoji",
    }])

    button = kb.services_keyboard("en").inline_keyboard[0][0]

    assert button.text == "Streaming"
    assert button.icon_custom_emoji_id == "premium-service-emoji"


def test_official_catalog_button_supports_left_and_right_emojis(monkeypatch):
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: [{
        "id": 7,
        "name": "officiels subscribes",
        "emoji": "⭐",
        "suffix_emoji": "✅",
        "total_stock": 4,
    }])

    button = kb.services_keyboard("fr").inline_keyboard[0][0]

    assert button.text == "⭐ officiels subscribes ✅"
    assert button.icon_custom_emoji_id is None
    assert button.style == "primary"


def test_official_subscriptions_variant_is_first_and_sky_blue(monkeypatch):
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: sorted([
        {"id": 1, "name": "Chat GPT", "total_stock": 5},
        {"id": 2, "name": "Officiels subscriptions", "total_stock": 5},
    ], key=db._service_sort_key))

    keyboard = kb.services_keyboard("fr")
    button = keyboard.inline_keyboard[0][0]

    assert button.callback_data == "svc:2"
    assert button.style == "primary"
    assert len(keyboard.inline_keyboard[0]) == 1
    assert keyboard.inline_keyboard[1][0].callback_data == "svc:1"


def test_official_grouped_catalog_is_first_and_sky_blue(mock_mongodb):
    regular_id = db.add_service("Streaming", "🎬")
    official_id = db.add_service("officiels subscribes", "⭐")
    db.add_offer(regular_id, "Netflix", 5.0, 4)
    db.add_offer(regular_id, "Disney", 5.0, 4)
    db.add_offer(official_id, "Official monthly", 4.0, 4)
    db.add_offer(official_id, "Official yearly", 40.0, 4)

    keyboard = kb.catalog_offers_keyboard("fr")
    first_catalog_button = keyboard.inline_keyboard[0][0]

    assert first_catalog_button.callback_data == f"svc:{official_id}"
    assert first_catalog_button.style == "primary"
    assert len(keyboard.inline_keyboard[0]) == 1
    assert keyboard.inline_keyboard[1][0].callback_data == f"svc:{regular_id}"


def test_premium_left_icon_keeps_unicode_suffix(monkeypatch):
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: [{
        "id": 7,
        "name": "officiels subscribes",
        "emoji": "⭐",
        "suffix_emoji": "✅",
        "custom_emoji_id": "premium-left-icon",
        "total_stock": 4,
    }])

    button = kb.services_keyboard("fr").inline_keyboard[0][0]

    assert button.text == "officiels subscribes ✅"
    assert button.icon_custom_emoji_id == "premium-left-icon"


def test_admin_catalog_button_uses_premium_emoji(monkeypatch):
    monkeypatch.setattr(admin.db, "list_services", lambda active_only=False: [{
        "id": 4,
        "name": "Chat GPT",
        "active": 1,
        "custom_emoji_id": "admin-premium-id",
    }])

    button = admin.catalog_admin_keyboard().inline_keyboard[0][0]

    assert button.text == "𝐂𝐡𝐚𝐭 𝐆𝐏𝐓"
    assert button.icon_custom_emoji_id == "admin-premium-id"


def test_admin_service_ignores_unicode_stored_as_custom_emoji_id(monkeypatch):
    monkeypatch.setattr(admin.db, "get_service", lambda _service_id: {
        "id": 52, "name": "Cursor", "active": 1,
    })
    monkeypatch.setattr(admin.db, "list_offers", lambda *_args, **_kwargs: [{
        "id": 84,
        "name": "Cursor Pro 12m",
        "active": 1,
        "custom_emoji_id": "📦",
    }])

    button = admin.service_admin_keyboard(52).inline_keyboard[0][0]

    assert button.callback_data == "adm_off:84"
    assert button.icon_custom_emoji_id is None
    assert button.text == "📦 𝐂𝐮𝐫𝐬𝐨𝐫 𝐏𝐫𝐨 𝟏𝟐𝐦"


def test_admin_service_can_configure_both_button_emojis(monkeypatch):
    monkeypatch.setattr(admin.db, "get_service", lambda _service_id: {
        "id": 52, "name": "officiels subscribes", "active": 1,
    })
    monkeypatch.setattr(admin.db, "list_offers", lambda *_args, **_kwargs: [])

    callbacks = [
        button.callback_data
        for row in admin.service_admin_keyboard(52).inline_keyboard
        for button in row
    ]

    assert "adm_svcemoji:52" in callbacks
    assert "adm_svcsuffix:52" in callbacks


def test_admin_service_products_are_arranged_two_per_row(monkeypatch):
    monkeypatch.setattr(admin.db, "get_service", lambda _service_id: {
        "id": 52, "name": "Subscriptions", "active": 1,
    })
    monkeypatch.setattr(admin.db, "list_offers", lambda *_args, **_kwargs: [
        {"id": offer_id, "name": f"Offer {offer_id}", "active": 1}
        for offer_id in range(1, 6)
    ])

    rows = admin.service_admin_keyboard(52).inline_keyboard

    assert [len(row) for row in rows[:3]] == [2, 2, 1]
    assert [button.callback_data for button in rows[0]] == ["adm_off:1", "adm_off:2"]
    assert all(len(row) == 2 for row in rows[3:-1])
    assert rows[-1][0].callback_data == "adm_catalog"


def test_admin_cannot_manually_modify_offer_stock(monkeypatch):
    monkeypatch.setattr(admin.db, "get_offer", lambda _offer_id: {
        "id": 4, "service_id": 1, "active": 1,
    })

    keyboard = admin.offer_admin_keyboard(4)
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    }

    assert not any(value and value.startswith("adm_setstock:") for value in callbacks)


def test_admin_offer_panel_can_broadcast_current_price_and_stock(monkeypatch):
    monkeypatch.setattr(
        admin.db,
        "get_offer",
        lambda _offer_id: {
            "id": 4, "service_id": 1, "active": 1,
            "unlimited_stock": False,
        },
    )

    callbacks = [
        button.callback_data
        for row in admin.offer_admin_keyboard(4).inline_keyboard
        for button in row
    ]

    assert "adm_broadcast_offer:4" in callbacks
    assert "adm_inventory:4" in callbacks
    assert "adm_offmove:4" in callbacks


def test_admin_offer_panel_can_start_and_stop_flash_sale(monkeypatch):
    offer = {
        "id": 4, "service_id": 1, "active": 1,
        "unlimited_stock": False, "flash_sale_active": False,
    }
    monkeypatch.setattr(admin.db, "get_offer", lambda _offer_id: offer)
    callbacks = {
        button.callback_data
        for row in admin.offer_admin_keyboard(4).inline_keyboard
        for button in row
    }
    assert "adm_flash_start:4" in callbacks

    offer["flash_sale_active"] = True
    callbacks = {
        button.callback_data
        for row in admin.offer_admin_keyboard(4).inline_keyboard
        for button in row
    }
    assert "adm_flash_stop:4" in callbacks


def test_admin_offer_options_are_arranged_two_per_row(monkeypatch):
    monkeypatch.setattr(admin.db, "get_offer", lambda _offer_id: {
        "id": 4, "service_id": 1, "active": 1,
        "unlimited_stock": False, "flash_sale_active": False,
    })
    monkeypatch.setattr(admin.db, "get_service", lambda _service_id: {
        "id": 1, "name": "Subscriptions",
    })

    rows = admin.offer_admin_keyboard(4).inline_keyboard

    assert all(len(row) == 2 for row in rows[:-1])
    assert len(rows[-1]) == 1
    assert rows[-1][0].callback_data == "adm_svc:1"


def test_admin_panel_has_custom_announcement_button():
    callbacks = [
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    ]

    assert "adm_broadcast_message" in callbacks


def test_admin_panel_has_available_products_button(mock_mongodb):
    callbacks = [
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    ]

    assert "adm_stock_products" in callbacks


def test_available_products_screen_uses_catalog_premium_emoji(monkeypatch):
    monkeypatch.setattr(admin.db, "list_catalog_offers", lambda: [
        {
            "id": 43,
            "service_name": "Adobe",
            "service_emoji": "🔥",
            "service_custom_emoji_id": "4960958119057295483",
            "name": "Creative Cloud Pro",
            "period_value": 1,
            "period_unit": "months",
            "price": 6,
            "currency": "USDT",
            "stock": 1,
        },
        {
            "id": 44,
            "service_name": "Adobe",
            "name": "Out of stock",
            "price": 2,
            "stock": 0,
        },
    ])

    text, keyboard = admin.available_products_screen()

    assert '<tg-emoji emoji-id="4960958119057295483">🔥</tg-emoji>' in text
    assert "<b>Adobe - Creative Cloud Pro</b> | 1 month | <b>$6</b>" in text
    assert "Out of stock" not in text
    assert keyboard.inline_keyboard[-1][0].callback_data == "adm_panel"


def test_admin_panel_has_live_warranty_payment_and_pending_api_sections(mock_mongodb):
    mock_mongodb.users.insert_one({"telegram_id": 42, "username": "buyer"})
    mock_mongodb.offers.insert_one({
        "id": 7,
        "service_id": 1,
        "name": "API product",
        "supplier_provider": "mailreader",
        "supplier_product_id": "product-7",
    })
    mock_mongodb.orders.insert_many([
        {
            "id": 80, "user_id": 42, "offer_id": 7,
            "offer_name": "Delivered product", "service_name": "API",
            "status": "delivered", "wallet_amount": 4.0, "total_price": 0,
            "paid_at": 100, "updated_at": 101,
        },
        {
            "id": 81, "user_id": 42, "offer_id": 7,
            "offer_name": "Pending product", "service_name": "API",
            "status": "paid", "wallet_amount": 0, "total_price": 5.0,
            "paid_at": 102, "updated_at": 103,
        },
    ])
    mock_mongodb.warranty_requests.insert_one({
        "id": 3, "user_id": 42, "order_id": 80,
        "status": "replacement_pending", "refund_amount": 1.0,
        "reason": "The delivered account stopped working",
        "created_at": 100, "updated_at": 104,
    })
    mock_mongodb.inventory.insert_one({
        "id": 900,
        "offer_id": 7,
        "delivered_order_id": 80,
        "status": "delivered",
        "payload": db._fernet().encrypt(b"real-user@example.com | real-password").decode(),
    })
    mock_mongodb.reseller_fulfillments.insert_one({
        "provider": "mailreader", "external_order_id": "BM-81",
        "order_id": 81, "supplier_product_id": "product-7",
        "status": "delivery_pending", "created_at": 102, "updated_at": 103,
    })

    panel = {
        button.callback_data: button.text
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    }
    assert "Warranty (1)" in panel["adm_warranties:0"]
    assert "Payment Confirmed (2)" in panel["adm_payments:0"]
    assert "Livraison API en attente (1)" in panel["adm_api_pending:0"]

    warranty_keyboard, requests, warranty_total = admin.warranty_requests_keyboard()
    assert warranty_total == 1
    assert requests[0]["id"] == 3
    assert warranty_keyboard.inline_keyboard[0][0].callback_data == "adm_warranty_view:3"
    warranty_actions = {
        button.callback_data
        for row in admin.warranty_request_keyboard(requests[0]).inline_keyboard
        for button in row
    }
    assert "adm_warranty_send:3" in warranty_actions
    assert "adm_warranty_report:3" in warranty_actions
    warranty_report = admin.warranty_request_report(requests[0])
    assert "mailreader" in warranty_report
    assert "The delivered account stopped working" in warranty_report
    assert "real-user@example.com | real-password" in warranty_report

    payment_keyboard, orders, payment_total = admin.confirmed_payments_keyboard()
    assert payment_total == 2
    assert {order["id"] for order in orders} == {80, 81}
    assert any(
        button.callback_data == "adm_order:81"
        for row in payment_keyboard.inline_keyboard for button in row
    )

    api_keyboard, fulfillments, api_total = admin.pending_api_deliveries_keyboard()
    assert api_total == 1
    assert fulfillments[0]["order_id"] == 81
    assert api_keyboard.inline_keyboard[0][0].callback_data == "adm_api_pending_view:81"
    api_report = admin.pending_api_delivery_report(fulfillments[0])
    assert "DELIVERY REQUEST" in api_report
    assert "delivery_pending" in api_report
    assert "mailreader" in api_report


def test_admin_can_customize_and_preview_ticket_design():
    customize_callbacks = {
        button.callback_data
        for row in admin.customize_keyboard().inline_keyboard
        for button in row
    }
    style_callbacks = {
        button.callback_data
        for row in admin.ticket_style_keyboard().inline_keyboard
        for button in row
    }

    assert "adm_ticket_style" in customize_callbacks
    assert {
        "adm_ticket_style_edit:title",
        "adm_ticket_style_edit:reply_hint",
        "adm_ticket_style_edit:footer",
        "adm_ticket_style_preview",
        "adm_ticket_style_reset",
    } <= style_callbacks


def test_home_menu_hides_channel_and_group_links(mock_mongodb):
    keyboard = kb.home_keyboard("en", 42)
    urls = {
        button.url
        for row in keyboard.inline_keyboard
        for button in row
        if button.url
    }

    assert "https://t.me/blackmarketBotChannel" not in urls
    assert "https://t.me/Blackmarketgrp" not in urls

    required_keyboard = kb.channel_join_keyboard("en")
    assert required_keyboard.inline_keyboard[0][0].url == "https://t.me/blackmarketBotChannel"


def test_home_uses_green_shop_blue_actions_and_red_support(mock_mongodb):
    keyboard = kb.home_keyboard("en", 42)
    actions = {
        button.callback_data: button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }

    assert keyboard.inline_keyboard[0][0].callback_data == "catalog"
    assert actions["catalog"].text == "🛍️ Shop"
    assert actions["catalog"].style == "success"
    assert {actions[action].style for action in ("topup", "account", "language")} == {"primary"}
    assert {"profile_withdraw", "profile_notifications", "warranty"}.isdisjoint(actions)
    assert actions["support"].style == "danger"
    assert [len(row) for row in keyboard.inline_keyboard[:4]] == [1, 2, 2, 2]
    assert [button.callback_data for button in keyboard.inline_keyboard[1]] == [
        "methods", "bot_like_mine",
    ]
    assert [button.callback_data for button in keyboard.inline_keyboard[3]] == [
        "language", "support",
    ]
    assert actions["bot_like_mine"].text == "🤖 BOT LIKE MINE"
    assert actions["bot_like_mine"].style == "success"
    assert "lovable" not in actions

    shop = kb.catalog_offers_keyboard("en")
    shop_callbacks = [
        button.callback_data for row in shop.inline_keyboard for button in row
        if button.callback_data
    ]
    assert "lovable" not in shop_callbacks


def test_bot_like_mine_offer_has_preview_and_admin_asset_controls(mock_mongodb):
    offer_id = db.ensure_bot_like_mine_feature()
    offer = db.get_offer(offer_id)

    customer_keyboard = kb.offer_detail_keyboard("en", offer)
    customer_actions = {
        button.callback_data: button
        for row in customer_keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert customer_actions[f"bot_package_preview:{offer_id}"].text == "📄 What you'll get?"
    assert customer_actions[f"bot_package_preview:{offer_id}"].style == "primary"
    assert f"buy:{offer_id}" in customer_actions

    admin_actions = {
        button.callback_data: button.text
        for row in admin.offer_admin_keyboard(offer_id).inline_keyboard
        for button in row
        if button.callback_data
    }
    assert f"adm_bot_package_doc:{offer_id}" in admin_actions
    assert f"adm_bot_package_link:{offer_id}" in admin_actions


def test_bot_like_mine_configuration_survives_feature_refresh(mock_mongodb):
    offer_id = db.ensure_bot_like_mine_feature()
    db.update_offer(
        offer_id,
        benefits_document_file_id="telegram-document-id",
        benefits_document_name="benefits.pdf",
        delivery_url="https://github.com/example/private-project",
    )

    assert db.ensure_bot_like_mine_feature() == offer_id
    refreshed = db.get_offer(offer_id)
    assert refreshed["benefits_document_file_id"] == "telegram-document-id"
    assert refreshed["benefits_document_name"] == "benefits.pdf"
    assert refreshed["delivery_url"] == "https://github.com/example/private-project"
    assert "What you'll get?" in refreshed["description"]
    assert "private link to the complete source code" in refreshed["description"]
    assert "رابط خاص للشيفرة المصدرية الكاملة" in refreshed["description_ar"]


def test_customize_menu_has_global_product_card_editor():
    callbacks = {
        button.callback_data
        for row in admin.customize_keyboard().inline_keyboard
        for button in row
    }

    assert "adm_text_key:offer_card_template" in callbacks
    assert "adm_text_key:welcome" in callbacks
    assert admin.text_category_for_key("offer_card_template") == "catalog"


def test_reseller_api_stays_in_profile_and_dashboard(mock_mongodb):
    home_callbacks = {
        button.callback_data
        for row in kb.home_keyboard("en", 42).inline_keyboard
        for button in row
        if button.callback_data
    }
    create_keyboard = kb.reseller_api_keyboard(
        "en", has_key=False, docs_url="https://shop.example/api/swagger"
    )
    active_keyboard = kb.reseller_api_keyboard(
        "en", has_key=True, docs_url="https://shop.example/api/swagger"
    )

    profile_callbacks = {
        button.callback_data
        for row in kb.profile_keyboard("en").inline_keyboard
        for button in row
        if button.callback_data
    }

    assert "reseller_api" not in home_callbacks
    assert "reseller_api" in profile_callbacks
    assert create_keyboard.inline_keyboard[0][0].callback_data == "reseller_api_create"
    assert create_keyboard.inline_keyboard[1][0].callback_data == "reseller_api_setup"
    assert create_keyboard.inline_keyboard[2][0].url == "https://shop.example/api/swagger"
    assert active_keyboard.inline_keyboard[0][0].callback_data == "reseller_api_regen"

    setup_keyboard = kb.reseller_api_setup_keyboard(
        "en",
        api_base_url="https://shop.example/api/v2/telegram-buyer",
        docs_url="https://shop.example/api/swagger",
    )
    assert setup_keyboard.inline_keyboard[0][0].copy_text.text == (
        "https://shop.example/api/v2/telegram-buyer"
    )
    assert setup_keyboard.inline_keyboard[1][0].url == "https://shop.example/api/swagger"
    assert setup_keyboard.inline_keyboard[2][0].callback_data == "reseller_api"


def test_admin_panel_has_persistent_maintenance_toggle(mock_mongodb):
    keyboard = admin.admin_panel_keyboard()
    button = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "adm_maintenance_toggle"
    )
    assert "OFF" in button.text

    db.set_setting("maintenance_enabled", True)
    keyboard = admin.admin_panel_keyboard()
    button = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data == "adm_maintenance_toggle"
    )
    assert "ON" in button.text


def test_admin_panel_has_user_activity_option(mock_mongodb):
    callbacks = {
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    }

    assert "adm_user_activity" in callbacks
    assert [
        button.callback_data
        for button in admin.user_activity_keyboard().inline_keyboard[0]
    ] == ["adm_user_activity", "adm_panel"]


def test_admin_panel_can_manage_and_delete_sent_announcements(mock_mongodb):
    panel_callbacks = {
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    }
    assert "adm_broadcast_history" in panel_callbacks

    job, _created = db.create_broadcast_job("flash_sale", {"offer_id": 7})
    db.record_broadcast_message(job["id"], "flash_sale", 101, 501)
    db.complete_broadcast_job(job["id"], 1)
    history = db.list_broadcast_history()
    keyboard = admin.broadcast_history_keyboard(history)

    assert keyboard.inline_keyboard[0][0].callback_data == f"adm_broadcast_view:{job['id']}"
    history[0]["active_message_count"] = 1
    delete_keyboard = admin.broadcast_delete_keyboard(history[0])
    assert delete_keyboard.inline_keyboard[0][0].callback_data == f"adm_broadcast_confirm:{job['id']}"


def test_catalog_never_builds_an_empty_button(monkeypatch):
    monkeypatch.setattr(kb.db, "list_services_with_stock", lambda: [{
        "id": 12,
        "name": "✅",
        "total_stock": 0,
    }])

    button = kb.services_keyboard("fr").inline_keyboard[0][0]

    assert button.text == "Service #12"


def test_offers_keyboard_matches_reference_flow(monkeypatch):
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [
        {"id": 1, "name": "Available plan", "price": 10.0, "stock": 14, "note": ""},
        {"id": 2, "name": "Low stock plan", "price": 10.0, "stock": 4, "note": ""},
        {"id": 3, "name": "Unavailable plan", "price": 10.0, "stock": 0, "note": ""},
    ])

    keyboard = kb.offers_keyboard("en", 7)

    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert "off:1" in callbacks
    assert "off:2" in callbacks
    assert "off:3" in callbacks
    assert "catalog" in [row[0].callback_data for row in keyboard.inline_keyboard if len(row) > 0]


def test_admin_text_browser_exposes_every_translation_key():
    from i18n import TRANSLATIONS

    callbacks = []
    page_size = 8
    total_pages = max(1, (len(TRANSLATIONS) + page_size - 1) // page_size)
    for page in range(total_pages):
        keyboard = admin.texts_editor_keyboard(page, page_size=page_size)
        callbacks.extend(
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("adm_text_key:")
        )
    assert {value.split(":", 1)[1] for value in callbacks} == set(TRANSLATIONS)
    assert "adm_text_key:order_created" in callbacks


def test_flat_catalog_keyboard_contains_only_offer_callbacks(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [
        {"id": 11, "name": "ChatGPT Plus", "price": 5.0, "stock": 8},
        {"id": 12, "name": "Netflix Premium", "price": 4.0, "stock": 3},
    ])

    keyboard = kb.catalog_offers_keyboard("en")
    product_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data and btn.callback_data.startswith(("off:", "svc:"))
    ]

    assert len(product_callbacks) >= 1


def test_flat_catalog_ignores_unicode_stored_as_custom_emoji_id(monkeypatch):
    monkeypatch.setattr(kb.db, "get_text_override_icon", lambda *_args: "")
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [{
        "id": 84,
        "service_id": 52,
        "service_name": "Cursor",
        "name": "Cursor Pro 12m",
        "price": 60.0,
        "stock": 14,
        "custom_emoji_id": "📦",
    }])

    button = kb.catalog_offers_keyboard("en").inline_keyboard[0][0]

    assert button.callback_data == "off:84"
    assert button.icon_custom_emoji_id is None


def test_premium_service_icon_replaces_unicode_emoji_in_catalog_button(monkeypatch):
    monkeypatch.setattr(kb.db, "list_catalog_offers", lambda: [{
        "id": 11,
        "name": "Chat GPT Plus",
        "price": 5.0,
        "stock": 8,
        "service_id": 3,
        "service_name": "Chat GPT",
        "service_emoji": "🤖",
        "service_custom_emoji_id": "premium-chatgpt",
    }])

    button = kb.catalog_offers_keyboard("en").inline_keyboard[0][0]

    assert button.text == "Chat GPT Plus | 30 days | $5"
    assert button.callback_data == "off:11"
    assert button.icon_custom_emoji_id == "premium-chatgpt"


def test_premium_offer_icon_replaces_unicode_emoji_in_offer_button(monkeypatch):
    monkeypatch.setattr(kb.db, "get_service", lambda _service_id: {
        "emoji": "🤖", "custom_emoji_id": "premium-chatgpt",
    })
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [{
        "id": 11, "name": "Chat GPT Plus", "price": 5.0, "stock": 8,
    }])
    monkeypatch.setattr(kb.db, "get_text_override_icon", lambda *_args: "")

    button = kb.offers_keyboard("en", 3).inline_keyboard[0][0]

    assert button.text == "Chat GPT Plus | 30 days | $5"
    assert button.icon_custom_emoji_id == "premium-chatgpt"


def test_adobe_creative_cloud_button_falls_back_to_service_icon(monkeypatch):
    adobe_icon = "4960958119057295483"
    monkeypatch.setattr(kb.db, "get_service", lambda _service_id: {
        "id": 33,
        "name": "Adobe",
        "emoji": "🔥",
        "custom_emoji_id": adobe_icon,
    })
    monkeypatch.setattr(kb.db, "list_offers", lambda _service_id: [{
        "id": 43,
        "service_id": 33,
        "name": "Creative Cloud Pro",
        "price": 6.0,
        "stock": 1,
        "custom_emoji_id": "🔥",
    }])
    monkeypatch.setattr(kb.db, "get_text_override_icon", lambda *_args: "")

    button = kb.offers_keyboard("en", 33).inline_keyboard[0][0]

    assert button.text == "Creative Cloud Pro | 30 days | $6"
    assert button.callback_data == "off:43"
    assert button.icon_custom_emoji_id == adobe_icon


def test_ticket_conversation_keyboard_can_close_or_go_home():
    keyboard = kb.ticket_conversation_keyboard("en", 17)

    assert keyboard.inline_keyboard[0][0].callback_data == "ticket_close:17"
    assert keyboard.inline_keyboard[0][0].style == "danger"
    assert keyboard.inline_keyboard[1][0].callback_data == "home"
