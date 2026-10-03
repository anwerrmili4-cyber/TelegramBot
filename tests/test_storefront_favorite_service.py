"""A customer can save a product and receive its public sheet once."""

import database as db
from app.domain import storefront_favorite_service


def _offer(stock=4):
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(
        service_id,
        "ChatGPT Plus 1 mois",
        6.0,
        stock,
        description="Compte premium pour un mois.",
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=25000,
        period_days=30,
    )


def test_saving_a_product_emails_its_sheet_once(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    offer_id = _offer()
    sent_emails.clear()

    first = storefront_favorite_service.set_saved(customer, offer_id, True)
    again = storefront_favorite_service.set_saved(customer, offer_id, True)

    assert first["emailed"] is True
    assert again["emailed"] is False
    assert len(sent_emails) == 1
    message = sent_emails[0]
    assert message["to"] == ["amine@example.com"]
    assert message["subject"] == "Ton favori : ChatGPT Plus 1 mois"
    assert "25,000 DT" in message["text"]
    assert "1 mois" in message["text"]
    assert "4 en stock" in message["text"]
    assert "Compte premium" in message["text"]
    assert f"/produit/{offer_id}" in message["text"]
    assert "onglet=favoris" in message["html"]
    listed = storefront_favorite_service.for_customer(customer["id"])["favorites"]
    assert [item["offer_id"] for item in listed] == [offer_id]
    assert listed[0]["in_catalog"] is True


def test_a_favorite_stays_private_and_can_be_removed(mock_mongodb, site_customer, sent_emails):
    owner = site_customer()
    other = site_customer(name="Sana", email="sana@example.com")
    offer_id = _offer()
    storefront_favorite_service.set_saved(owner, offer_id, True)

    assert storefront_favorite_service.for_customer(other["id"])["favorites"] == []
    storefront_favorite_service.set_saved(owner, offer_id, False)
    assert storefront_favorite_service.for_customer(owner["id"])["favorites"] == []
    assert len(sent_emails) == 1


def test_an_unknown_product_cannot_be_saved(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    try:
        storefront_favorite_service.set_saved(customer, 999, True)
    except storefront_favorite_service.FavoriteError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("an unknown product was saved")
    assert sent_emails == []
