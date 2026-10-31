"""Tests for persistent shop settings."""

from __future__ import annotations

import database as db
import keyboards
from i18n import t


def test_shop_settings_defaults_and_typed_overrides(mock_mongodb):
    defaults = db.shop_settings()
    assert defaults["maintenance_enabled"] is False
    assert isinstance(defaults["order_expiry_seconds"], int)

    db.set_setting("maintenance_enabled", True)
    db.set_setting("affiliate_target", 25)
    db.set_setting("maintenance_message", "Maintenance planifiée")

    settings = db.shop_settings()
    assert settings["maintenance_enabled"] is True
    assert settings["affiliate_target"] == 25
    assert settings["maintenance_message"] == "Maintenance planifiée"


def test_active_languages_control_keyboard(mock_mongodb):
    db.set_setting("active_languages", "fr,ar")

    keyboard = keyboards.lang_keyboard()
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert callback_data == ["lang:ar"]


def test_french_is_not_an_available_language(mock_mongodb):
    db.set_setting("active_languages", "fr,en,ar")

    keyboard = keyboards.lang_keyboard()

    assert [button.callback_data for row in keyboard.inline_keyboard for button in row] == ["lang:en", "lang:ar"]
def test_admin_can_override_any_translated_text(mock_mongodb):
    db.set_text_override("menu_catalog", "en", "My products", "premium-menu-icon")
    assert t("en", "menu_catalog") == "My products"
    assert db.get_text_override_icon("menu_catalog", "en") == "premium-menu-icon"
    button = keyboards.home_keyboard("en", 42).inline_keyboard[0][0]
    assert button.icon_custom_emoji_id == "premium-menu-icon"


def test_premium_emoji_button_uses_icon_without_html_in_label(mock_mongodb):
    db.set_text_override(
        "menu_catalog",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-catalog">🛍️</tg-emoji> <b>Premium Catalog</b>',
        "premium-catalog",
    )

    button = keyboards.home_keyboard("en", 42).inline_keyboard[0][0]

    assert button.text == "Premium Catalog"
    assert button.icon_custom_emoji_id == "premium-catalog"
    assert keyboards.is_button_text_key("menu_catalog")

def test_join_channel_button_accepts_exact_premium_emoji(mock_mongodb):
    db.set_text_override(
        "btn_join_channel",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-buy">🛒</tg-emoji> <b>Get it now</b>',
        "premium-buy",
    )

    button = keyboards.channel_join_keyboard("en").inline_keyboard[0][0]

    assert button.text == "Get it now"
    assert button.icon_custom_emoji_id == "premium-buy"
    assert button.url.endswith("/blackmarketBotChannel")

def test_custom_url_buttons_can_be_added_and_deleted(mock_mongodb):
    button_id = db.add_custom_button("Site", "Website", "الموقع", "https://example.com")
    assert db.list_custom_buttons()[0]["label_en"] == "Website"
    assert db.delete_custom_button(button_id)
    assert db.list_custom_buttons() == []
