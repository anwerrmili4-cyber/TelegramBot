"""Tests for offer detail formatting helpers."""

import bot
from bot import admin_text_preview, compact_offer_text, offer_detail_fields


def test_offer_detail_fields_parse_admin_description():
    fields = offer_detail_fields(
        "Type: Ready-Made Account\nWarranty: Full\nDuration : 30 Days\nMail : iCloud\nAccess : Full",
        "",
    )

    assert fields["access"] == "Full"
    assert fields["note"] == "Full"
    assert fields["duration"] == "30 Days"
    assert fields["mail"] == "iCloud"


def test_compact_offer_text_contains_the_complete_admin_preview(monkeypatch):
    monkeypatch.setattr(bot.db, "offer_sold_count", lambda _offer_id: 7)
    offer = {
        "id": 42,
        "name": "Perplexity Pro",
        "service_name": "AI Tools",
        "service_emoji": "🤖",
        "price": 10,
        "currency": "USDT",
        "stock": 12,
        "unlimited_stock": False,
        "warranty_days": 0,
        "description": "Compte premium prêt à utiliser",
    }

    preview = compact_offer_text(offer, "fr")

    assert "<b>🤖 AI Tools — Perplexity Pro</b>" in preview
    assert "<b>PRIX:</b> <b>10.00</b> <b>USDT</b>" in preview
    assert "<b>STOCK:</b> <b>12</b>" in preview
    assert "<b>VENDUS:</b> <b>7</b>" in preview
    assert "<b>GARANTIE:</b> <b>NW</b>" in preview
    assert "<b>DESCRIPTION:</b>\nCompte premium prêt à utiliser" in preview


def test_product_card_template_is_globally_editable_with_premium_emoji(monkeypatch, mock_mongodb):
    monkeypatch.setattr(bot.db, "offer_sold_count", lambda _offer_id: 4)
    bot.db.set_text_override(
        "offer_card_template",
        "en",
        '[[HTML]]<tg-emoji emoji-id="premium-product">💠</tg-emoji> '
        '<b>{name}</b> · {price} {currency}\n'
        'Available: {stock} · Purchased: {sold}\n{description}',
    )

    preview = compact_offer_text({
        "id": 7,
        "name": "Pro & Plus",
        "price": 14,
        "currency": "USDT",
        "stock": 7,
        "description": "Ready <b>today</b>",
    }, "en")

    assert '<tg-emoji emoji-id="premium-product">💠</tg-emoji>' in preview
    assert "<b>📦 Pro &amp; Plus</b> · <b>14.00</b> <b>USDT</b>" in preview
    assert "Available: <b>7</b> · Purchased: <b>4</b>" in preview
    assert "Ready &lt;b&gt;today&lt;/b&gt;" in preview


def test_product_card_admin_preview_preserves_variable_names(mock_mongodb):
    preview = admin_text_preview("offer_card_template")

    assert "<b>{catalog_emoji} {catalog_name} — {product_name}</b>" in preview
    assert "<b>{bulk_price}</b>" in preview
    assert "<b>{bulk_quantity}</b>" in preview
    assert "{bulk_price_line}" not in preview
    assert "<b>{price}</b>" in preview
    assert "<code>{description}</code>" not in preview
    assert "{description}" in preview
    assert "bulk<i>price</i>line" not in preview


def test_product_card_prefixes_catalog_and_restyles_code_values(monkeypatch, mock_mongodb):
    monkeypatch.setattr(bot.db, "offer_sold_count", lambda _offer_id: 2)
    bot.db.set_text_override(
        "offer_card_template", "en",
        "[[HTML]]<b>{name}</b>\nPRICE: <code>{price} {currency}</code>\n"
        "STOCK: `{stock}`\nWARRANTY: <code>{warranty}</code>",
    )

    preview = compact_offer_text({
        "id": 8,
        "name": "Premium",
        "service_name": "QuillBot",
        "service_emoji": "🪶",
        "price": 2,
        "currency": "USDT",
        "stock": 27,
        "period_days": 30,
        "warranty_days": 30,
    }, "en")

    assert "<b>🪶 QuillBot — Premium</b>" in preview
    assert "<b>2.00</b> <b>USDT</b>" in preview
    assert "<b>27</b>" in preview
    assert "<b>FW</b>" in preview
    assert "<code>" not in preview


def test_product_description_removes_code_font_but_keeps_rich_text(monkeypatch):
    monkeypatch.setattr(bot.db, "offer_sold_count", lambda _offer_id: 0)

    preview = compact_offer_text({
        "id": 9,
        "name": "Premium",
        "price": 2,
        "stock": 1,
        "description": "[[HTML]]<pre><code>Open activation link</code></pre>\n<b>Important</b>",
    }, "en")

    assert "Open activation link" in preview
    assert "<code>" not in preview
    assert "<pre>" not in preview
    assert "<b>Important</b>" in preview


def test_bulk_row_uses_editable_components_and_hides_when_disabled(monkeypatch, mock_mongodb):
    monkeypatch.setattr(bot.db, "offer_sold_count", lambda _offer_id: 0)
    template = (
        "[[HTML]]<b>{name}</b>\n"
        "WHOLESALE: {bulk_price} {currency} when buying {bulk_quantity}+\n"
        "STOCK: {stock}"
    )
    bot.db.set_text_override("offer_card_template", "en", template)

    enabled = compact_offer_text({
        "id": 10, "name": "Premium", "price": 4, "stock": 20,
        "bulk_quantity": 5, "bulk_unit_price": 2.5,
    }, "en")
    disabled = compact_offer_text({
        "id": 11, "name": "Premium", "price": 4, "stock": 20,
        "bulk_quantity": 0, "bulk_unit_price": 0,
    }, "en")

    assert "WHOLESALE: <b>2.50</b> <b>USDT</b> when buying <b>5</b>+" in enabled
    assert "WHOLESALE" not in disabled
    assert "STOCK: <b>20</b>" in disabled


def test_admin_preview_decomposes_legacy_bulk_line():
    preview = bot.render_admin_text_preview(
        "offer_card_template",
        "PRICE: {price}\n{bulk_price_line}STOCK: {stock}",
        "en",
    )

    assert "BULK PRICE" in preview
    assert "<b>{bulk_price}</b>" in preview
    assert "<b>{bulk_quantity}</b>" in preview
    assert "{bulk_price_line}" not in preview
