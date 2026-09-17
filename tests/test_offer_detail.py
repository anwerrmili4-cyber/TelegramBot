"""Tests for offer detail formatting helpers."""

import bot
from bot import compact_offer_text, offer_detail_fields


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
