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
        "price": 10,
        "currency": "USDT",
        "stock": 12,
        "unlimited_stock": False,
        "warranty_days": 0,
        "description": "Compte premium prêt à utiliser",
    }

    preview = compact_offer_text(offer, "fr")

    assert "Perplexity Pro" in preview
    assert "<b>PRIX:</b> 10.00 USDT" in preview
    assert "<b>STOCK:</b> 12" in preview
    assert "<b>VENDUS:</b> 7" in preview
    assert "<b>GARANTIE:</b> NW" in preview
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
    assert "<b>Pro &amp; Plus</b> · 14.00 USDT" in preview
    assert "Available: 7 · Purchased: 4" in preview
    assert "Ready &lt;b&gt;today&lt;/b&gt;" in preview


def test_product_card_admin_preview_preserves_variable_names(mock_mongodb):
    preview = admin_text_preview("offer_card_template")

    assert "<code>{bulk_price_line}</code>" in preview
    assert "bulk<i>price</i>line" not in preview
