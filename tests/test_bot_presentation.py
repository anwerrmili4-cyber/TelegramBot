"""Compatibility checks for presentation helpers extracted from ``bot``."""

from types import SimpleNamespace


def test_bot_facade_reexports_rich_text_helpers():
    import bot
    from app.bot import presentation

    message = SimpleNamespace(
        text="A⭐",
        caption=None,
        entities=[
            SimpleNamespace(
                type="custom_emoji",
                custom_emoji_id="premium-star",
                offset=1,
                length=1,
            )
        ],
        caption_entities=[],
    )

    assert bot.rich_text_from_message is presentation.rich_text_from_message
    assert bot.render_stored_rich_text is presentation.render_stored_rich_text
    stored = presentation.rich_text_from_message(message)
    assert presentation.render_stored_rich_text(stored) == (
        'A<tg-emoji emoji-id="premium-star">⭐</tg-emoji>'
    )


def test_bot_facade_reexports_methods_presentation_helpers():
    import bot
    from app.bot import methods_presentation

    text = "📅 Duration: 30 days\n💬 Description:\nPremium access\n📦 Stock: 2"

    assert bot._without_method_detail_rows is methods_presentation.without_method_detail_rows
    assert bot._join_methods_description_title is methods_presentation.join_methods_description_title
    assert bot._without_method_detail_rows(text) == "💬 Description:\nPremium access"
    assert bot._join_methods_description_title("💬 Description:\nPremium access") == (
        "💬 Description: Premium access"
    )


def test_local_product_announcement_matches_the_external_template():
    from i18n import TRANSLATIONS

    assert "announcement_no_terms" not in TRANSLATIONS


def test_bot_facade_reexports_offer_card_helpers():
    import bot
    from app.bot import offer_cards

    assert bot.offer_detail_fields is offer_cards.offer_detail_fields
    assert bot.parse_duration_input is offer_cards.parse_duration_input
    assert bot.decomposed_bulk_price_template is offer_cards.decomposed_bulk_price_template
    assert bot.decompose_legacy_bulk_line is offer_cards.decompose_legacy_bulk_line
    assert bot.compact_offer_text is offer_cards.compact_offer_text
    assert bot.OFFER_CARD_TEMPLATE_VARIABLES is offer_cards.OFFER_CARD_TEMPLATE_VARIABLES


def test_bot_facade_reexports_admin_preview_helpers():
    import bot
    from app.bot import text_previews

    assert bot.render_admin_text_preview is text_previews.render_admin_text_preview
    assert bot.admin_text_preview is text_previews.admin_text_preview
    assert bot._preview_link_placeholders is text_previews.preview_link_placeholders
    assert bot.TERMS_OF_SERVICE_URL == text_previews.TERMS_OF_SERVICE_URL


def test_bot_facade_reexports_customer_text_renderer():
    import bot
    from app.bot import customer_text

    assert bot.premium_customer_text is customer_text.premium_customer_text


def test_bot_facade_reexports_home_presentation():
    import bot
    from app.bot import home_presentation

    assert bot.top_selling_products_text is home_presentation.top_selling_products_text
    assert bot.welcome_home_text is home_presentation.welcome_home_text


def test_bot_facade_reexports_payment_presentation():
    import bot
    from app.bot import payment_presentation

    assert bot.topup_provider_screen is payment_presentation.topup_provider_screen
    assert bot.topup_onchain_screen is payment_presentation.topup_onchain_screen
    assert bot.onchain_payment_screen is payment_presentation.onchain_payment_screen


def test_bot_facade_reexports_order_history_presentation():
    import bot
    from app.bot import order_history

    assert bot.order_service_groups is order_history.order_service_groups
    assert bot.orders_text_export is order_history.orders_text_export


def test_bot_facade_reexports_order_warranty_queries():
    import bot
    from app.bot import order_warranty

    assert bot.order_delivery_timestamp is order_warranty.order_delivery_timestamp
    assert bot.warranty_days_used is order_warranty.warranty_days_used
    assert bot.product_warranty_days is order_warranty.product_warranty_days
    assert bot.product_period_days is order_warranty.product_period_days


def test_bot_facade_reexports_support_presentation():
    import bot
    from app.bot import support_presentation

    assert bot.ticket_conversation_text is support_presentation.ticket_conversation_text


def test_bot_facade_reexports_delivery_presentation():
    import bot
    from app.bot import delivery_presentation

    assert bot.numbered_delivery_content is delivery_presentation.numbered_delivery_content
    assert bot.manual_delivery_waiting_text is delivery_presentation.manual_delivery_waiting_text
    assert bot.bmc_vip_channel_message is delivery_presentation.bmc_vip_channel_message


def test_bot_facade_reexports_supplier_incident_presentation():
    import bot
    from app.bot import supplier_incidents

    assert bot.supplier_delivery_problem_text is supplier_incidents.supplier_delivery_problem_text


def test_bot_facade_reexports_order_rules():
    import bot
    from app.bot import order_rules

    assert bot.is_otp_order is order_rules.is_otp_order
    assert bot.collects_customer_email is order_rules.collects_customer_email
    assert bot._CUSTOMER_EMAIL_RE is order_rules.CUSTOMER_EMAIL_RE
