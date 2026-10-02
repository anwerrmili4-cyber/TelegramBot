"""A sold-out product can email the people waiting for it."""

import database as db
from app.domain import stock_alert_service


def _offer(stock=0):
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(
        service_id,
        "ChatGPT Plus 1 mois",
        6.0,
        stock,
        description="Compte premium",
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=25000,
    )


def test_a_waiting_address_is_emailed_once_when_stock_returns(mock_mongodb, sent_emails):
    offer_id = _offer(0)
    assert stock_alert_service.subscribe({"offer_id": offer_id, "email": "nina@example.com"}) == {"ok": True}
    assert stock_alert_service.subscribe({"offer_id": offer_id, "email": "Nina@example.com"}) == {"ok": True}
    assert mock_mongodb.storefront_stock_alerts.count_documents({"notified_at": None}) == 1

    db.update_offer(offer_id, stock=3)

    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["nina@example.com"]
    assert "ChatGPT Plus 1 mois" in sent_emails[0]["subject"]
    assert f"/produit/{offer_id}" in sent_emails[0]["text"]
    assert mock_mongodb.storefront_stock_alerts.count_documents({"notified_at": None}) == 0


def test_an_in_stock_product_is_not_queued(mock_mongodb, sent_emails):
    offer_id = _offer(4)
    result = stock_alert_service.subscribe({"offer_id": offer_id, "email": "nina@example.com"})
    assert result == {"ok": True, "already_available": True}
    assert mock_mongodb.storefront_stock_alerts.count_documents({}) == 0
    assert sent_emails == []


def test_unknown_product_is_refused(mock_mongodb):
    try:
        stock_alert_service.subscribe({"offer_id": 999, "email": "nina@example.com"})
    except Exception as exc:
        assert "introuvable" in str(exc)
    else:
        raise AssertionError("expected a refusal")
