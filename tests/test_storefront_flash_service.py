"""A site flash sale lowers the dinar price for a chosen duration and emails members."""

import database as db
from app.domain import (
    site_admin_service,
    storefront_flash_service,
    storefront_notification_service,
    storefront_service,
)


def _offer(millimes=25000, site_enabled=True):
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(
        service_id,
        "ChatGPT Plus",
        6.0,
        4,
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=millimes,
        site_enabled=site_enabled,
    )


def _start(offer_id, **extra):
    form = {
        "offer_id": offer_id,
        "flash_price": "19,000",
        "duration_minutes": 1440,
    }
    form.update(extra)
    return storefront_flash_service.start(form)


def test_flash_sale_lowers_the_site_price_and_emails_every_verified_member(
    mock_mongodb, site_customer, sent_emails,
):
    site_customer()
    site_customer(name="Sana", email="sana@example.com")
    unverified = {
        "id": db._next_id("storefront_customers"),
        "name": "Inconnu",
        "email": "pending@example.com",
        "email_verified": False,
        "created_at": 1,
    }
    mock_mongodb.storefront_customers.insert_one(unverified)
    offer_id = _offer()
    sent_emails.clear()

    result = _start(offer_id, title="Offre du soir", label="Flash")

    assert "2 clients" in result["message"]
    assert "25,000 DT" in result["message"]
    assert "19,000 DT" in result["message"]
    stored = db.get_offer(offer_id)
    assert stored["tn_price_millimes"] == 19000
    assert stored["site_flash_original_millimes"] == 25000
    assert stored["site_flash_active"] is True
    assert stored["price"] == 6.0
    assert not stored.get("flash_sale_active")
    public = storefront_service.catalog()["services"][0]["offers"][0]
    assert public["price_millimes"] == 19000
    assert public["compare_millimes"] == 25000
    assert public["flash_label"] == "Flash"
    assert public["flash_ends_at"] > stored["site_flash_started_at"]
    charged = storefront_service._resolved_line(offer_id, 1)
    assert charged["unit_millimes"] == 19000

    notice = mock_mongodb.storefront_notifications.find_one({"kind": "flash"})
    assert notice["offer_id"] == offer_id
    assert notice["title"] == "Offre du soir"
    assert notice["audience_count"] == 2
    customer = mock_mongodb.storefront_customers.find_one({"email": "amine@example.com"})
    flash = next(
        item for item in storefront_notification_service.for_customer(customer)["items"]
        if item["kind"] == "flash"
    )
    assert flash["kind_label"] == "Vente flash"
    assert flash["href"] == f"/produit/{offer_id}"
    recipients = [message["to"][0] for message in sent_emails]
    assert recipients.count("amine@example.com") == 1
    assert recipients.count("sana@example.com") == 1
    assert "pending@example.com" not in recipients
    mail = sent_emails[0]
    assert mail["subject"].startswith("Vente flash — ")
    assert "Offre du soir" in mail["subject"]
    assert "BLACKMARKET" in mail["html"]
    assert "Voir le produit" in mail["html"]
    assert "Voir mes notifications" in mail["html"]
    assert f"/produit/{offer_id}" in mail["text"]
    assert "onglet=notifications" in mail["text"]

    listed = storefront_flash_service.admin_list()
    row = listed["active"][0]
    assert row["id"] == offer_id
    assert row["regular_millimes"] == 25000
    assert row["price_millimes"] == 19000
    assert row["flash_active"] is True


def test_stopping_or_expiring_restores_the_dinar_price(mock_mongodb, site_customer, sent_emails):
    site_customer()
    offer_id = _offer()
    _start(offer_id)
    sent_emails.clear()

    stopped = storefront_flash_service.stop({"offer_id": offer_id})

    assert "25,000 DT" in stopped["message"]
    restored = db.get_offer(offer_id)
    assert restored["tn_price_millimes"] == 25000
    assert restored.get("site_flash_active") is False
    assert "site_flash_original_millimes" not in restored
    assert storefront_service.catalog()["services"][0]["offers"][0]["compare_millimes"] == 0
    assert sent_emails == []

    _start(offer_id, duration_minutes=15)
    db.get_conn().offers.update_one({"id": offer_id}, {"$set": {"site_flash_ends_at": 1}})
    charged = storefront_service._resolved_line(offer_id, 1)
    assert charged["unit_millimes"] == 25000
    assert db.get_offer(offer_id)["tn_price_millimes"] == 25000
    assert db.get_offer(offer_id).get("site_flash_active") is False


def test_a_flash_sale_rejects_a_price_that_is_not_lower_or_a_hidden_product(mock_mongodb, site_customer):
    site_customer()
    offer_id = _offer()
    try:
        _start(offer_id, flash_price="25,000")
    except storefront_flash_service.FlashError as exc:
        assert "inférieur" in str(exc)
    else:
        raise AssertionError("a flash price equal to the current price was accepted")
    assert db.get_offer(offer_id)["tn_price_millimes"] == 25000

    try:
        _start(offer_id, duration_minutes=10)
    except storefront_flash_service.FlashError as exc:
        assert "15 minutes" in str(exc)
    else:
        raise AssertionError("a ten minute sale was accepted")

    hidden = _offer(site_enabled=False)
    try:
        _start(hidden)
    except storefront_flash_service.FlashError as exc:
        assert "pas en vente" in str(exc)
    else:
        raise AssertionError("a hidden product was put on flash sale")


def test_a_second_sale_and_a_catalog_price_edit_wait_until_the_first_stops(mock_mongodb, site_customer):
    site_customer()
    offer_id = _offer()
    _start(offer_id)
    try:
        _start(offer_id, flash_price="15")
    except storefront_flash_service.FlashError as exc:
        assert "déjà en cours" in str(exc)
    else:
        raise AssertionError("a second flash sale replaced the first")

    try:
        site_admin_service.update_offer({
            "offer_id": str(offer_id),
            "tn_price": "30",
            "site_enabled": "1",
        })
    except site_admin_service.SiteAdminError as exc:
        assert "vente flash" in str(exc).casefold()
    else:
        raise AssertionError("the catalog replaced the flash price")
    assert db.get_offer(offer_id)["tn_price_millimes"] == 19000
    assert db.get_offer(offer_id)["site_flash_original_millimes"] == 25000

    site_admin_service.update_offer({
        "offer_id": str(offer_id),
        "tn_price": "19",
        "site_enabled": "1",
        "site_badge": "Soir",
    })
    kept = db.get_offer(offer_id)
    assert kept["tn_price_millimes"] == 19000
    assert kept["site_flash_original_millimes"] == 25000
    assert kept["site_badge"] == "Soir"
    assert kept["site_flash_active"] is True


def test_the_panel_lists_every_product_on_sale(mock_mongodb, site_customer):
    site_customer()
    first = _offer()
    service_id = db.get_offer(first)["service_id"]
    second = db.add_offer(
        service_id, "ChatGPT Team", 8.0, 2,
        sales_channels=["bot", "tn_site"], tn_price_millimes=40000, site_enabled=True,
    )
    listed = storefront_flash_service.admin_list()
    assert {row["id"] for row in listed["products"]} == {first, second}
    assert listed["active"] == []
    assert all(row["flash_active"] is False for row in listed["products"])
    prices = {row["id"]: row["regular_millimes"] for row in listed["products"]}
    assert prices == {first: 25000, second: 40000}
