"""Tests for translated bot copy."""

from i18n import t


def test_removed_french_language_falls_back_to_english():
    values = {
        "first_name": "Anwer - BMC",
        "terms_url": "https://blackmarket.today/terms",
    }
    message = t("fr", "welcome", **values)

    assert message == t("en", "welcome", **values)
    assert "Welcome to Black Market" in message
    assert "Anwer - BMC" in message
    assert "premium digital products" in message
    assert "Binance" not in message
    assert "paiement" not in message.lower()


def test_removed_french_payment_message_falls_back_to_english():
    message = t(
        "fr",
        "order_created",
        oid=6074,
        service="AI",
        offer="Gemini AI Pro 18m",
        qty=1,
        total="0.65",
        cur="USDT",
        binance_id="904169573",
    )

    assert "*Binance Pay*" in message
    assert "Order ID" in message
    assert "Verify with TXID" in message
    assert "Product: *Gemini AI Pro 18m*" in message
    assert "SEND EXACTLY: 0.65 USDT" in message
    assert "Binance ID: `904169573`" in message
    assert "Order: *#6074*" in message


def test_bybit_payment_message_uses_uid_and_receipt_txid():
    message = t(
        "fr", "bybit_order_created", oid=6075, service="AI",
        offer="Lovable", qty=1, total="12.00", cur="USDT",
        bybit_uid="545988761",
    )

    assert "*Bybit Pay*" in message
    assert "Bybit UID: `545988761`" in message
    assert "12.00 USDT" in message
    assert "TXID" in t("fr", "ask_bybit_txid", oid=6075)


def test_topup_failure_hides_internal_binance_error():
    message = t("en", "topup_failed")

    assert "temporarily unavailable" in message
    assert "HTTP" not in message
    assert "451" not in message
    assert "Copy Binance ID" in t("fr", "btn_copy_binance_id")
    assert "Copy exact amount" in t("fr", "btn_copy_amount")
    assert "`904169573`" in t("fr", "copy_binance_id_msg", binance_id="904169573")
    assert "TXID" in t("fr", "verifying")
    assert "payment screenshot" in t("fr", "payment_contact_admin", oid=6074)


def test_already_confirmed_topup_has_a_clear_customer_message():
    message = t("en", "topup_already_confirmed")

    assert "already confirmed" in message
    assert "already verified and credited" in message
    assert "not been credited again" in message


def test_removed_french_quantity_prompt_falls_back_to_english():
    message = t("fr", "choose_quantity", offer="Chat GPT Plus", stock=9, price="1.23", cur="USDT")

    assert "Enter quantity" in message
    assert "1-9" in message
    assert "Available stock: *9*" in message
    assert "1.23 USDT" in message


def test_admin_text_prompt_formats_text_key_without_argument_collision():
    message = t(
        "en", "admin_send_new_text",
        text_key="btn_pay_wallet", selected_lang="en", current="Pay with my balance",
    )
    assert "btn_pay_wallet" in message
    assert "Pay with my balance" in message


def test_offer_detail_template_has_premium_sections():
    message = t(
        "en",
        "offer_detail",
        emoji="🌀",
        service="Chat GPT",
        offer="Chat GPT Plus",
        price="4.50",
        cur="USDT",
        stock=5,
        note="Full",
        duration="30 Days",
        mail="iCloud",
        access="Ready-made account",
        delivery="Instantané",
        description="• Premium tools",
    )

    assert "*Warranty*" in message
    assert "*Duration*" in message
    assert "*Mail*" in message
    assert "*Access*" in message


def test_announcement_templates_include_product_catalog_period_and_warranty():
    for key in ("channel_stock_announcement", "offer_stock_announcement", "flash_sale_announcement"):
        for lang in ("en", "ar"):
            msg = t(
                lang,
                key,
                emoji="🍿",
                service="Streaming VOD",
                offer="Netflix 4K Ultra",
                period="30 days",
                warranty="NW",
                price="4.99",
                cur="USDT",
                stock=10,
                added=5,
                old_price="7.99",
                discount=38,
                remaining="2h 15m",
            )
            assert "Streaming VOD" in msg
            assert "Netflix 4K Ultra" in msg
            assert "30 days" in msg
            assert "NW" in msg
