import keyboards as kb
from app.domain import warranty_service
from bot import compact_offer_text, offer_description_text


def test_optional_bot_terms_are_omitted_from_labels_and_product_card(monkeypatch):
    offer = {
        "id": 17,
        "name": "Custom service",
        "price": 12,
        "stock": 3,
        "description": "Configured without a duration or warranty.",
        "period_days": 0,
        "period_value": 0,
        "period_unit": "days",
        "period_visible": False,
        "warranty_days": 0,
        "warranty_value": 0,
        "warranty_unit": "days",
        "warranty_visible": False,
    }
    monkeypatch.setattr("bot.db.offer_sold_count", lambda _offer_id: 0)

    assert warranty_service.offer_period_label(offer) == ""
    assert warranty_service.offer_warranty_label(offer) == ""
    assert "30 days" not in kb.offer_button_label("en", offer)

    rendered = compact_offer_text(offer, "en")

    assert "PERIOD:" not in rendered
    assert "WARRANTY:" not in rendered
    assert "Please read the description before buying" in rendered
    assert "Configured without a duration or warranty." not in rendered
    assert offer_description_text(offer, "en") == (
        "Configured without a duration or warranty."
    )
