"""Admin space for the Tunisian storefront: overview, catalog, customers, settings."""

import pytest

import database as db
from app.domain import site_admin_service, site_orders_service, site_settings_service, storefront_service


def _offer(name="Netflix 1 mois", millimes=15000, service="Netflix", stock=10):
    service_id = db.add_service(service, "🎬", sales_channels=["bot"])
    offer_id = db.add_offer(service_id, name, 5.0, stock, sales_channels=["bot"], tn_price_millimes=millimes)
    return service_id, offer_id


def _cart(offer_id, phone="22 333 444", name="Sana", quantity=1, method="d17"):
    return storefront_service.create_order({
        "name": name, "email": "sana@example.com", "phone": phone, "payment_method": method,
        "items": [{"offer_id": offer_id, "quantity": quantity}],
    })


def test_catalog_groups_offers_by_site_status(mock_mongodb):
    _, priced = _offer()
    _, unpriced = _offer(name="Outlook", millimes=None, service="Mails")
    hidden_service, hidden = _offer(name="Spotify", service="Spotify")
    site_admin_service.set_service_visibility({"service_id": hidden_service, "site_enabled": "0"})

    result = site_admin_service.catalog({})
    assert result["counts"] == {"all": 3, "on_sale": 1, "no_price": 1, "hidden": 1}
    rows = {row["id"]: row for row in result["items"]}
    assert rows[priced]["on_sale"] is True
    assert rows[unpriced]["tn_price_millimes"] is None
    assert rows[unpriced]["suggested_price_millimes"] == 16000
    assert rows[hidden]["service_visible"] is False

    only_unpriced = site_admin_service.catalog({"status": ["no_price"]})
    assert [row["id"] for row in only_unpriced["items"]] == [unpriced]


def test_update_offer_sets_and_clears_the_dinar_price(mock_mongodb):
    _, offer_id = _offer(millimes=None)
    site_admin_service.update_offer({
        "offer_id": str(offer_id), "tn_price": "25,5", "site_enabled": "1",
        "site_badge": " Top ", "site_category": "streaming", "site_description_fr": "Profil privé",
    })
    offer = db.get_offer(offer_id)
    assert offer["tn_price_millimes"] == 25500
    assert offer["site_badge"] == "Top"
    assert offer["site_description_fr"] == "Profil privé"
    assert storefront_service.catalog()["services"][0]["offers"][0]["price_millimes"] == 25500

    site_admin_service.update_offer({"offer_id": str(offer_id), "tn_price": "", "site_enabled": "1"})
    assert "tn_price_millimes" not in mock_mongodb.offers.find_one({"id": offer_id})
    assert storefront_service.catalog()["services"] == []


@pytest.mark.parametrize("form, message", [
    ({"tn_price": "abc"}, "nombre"),
    ({"tn_price": "-2"}, "compris"),
    ({"site_category": "weapons"}, "Catégorie"),
])
def test_update_offer_rejects_invalid_input(mock_mongodb, form, message):
    _, offer_id = _offer()
    with pytest.raises(site_admin_service.SiteAdminError, match=message):
        site_admin_service.update_offer({"offer_id": str(offer_id), **form})


def test_overview_counts_revenue_only_for_confirmed_carts(mock_mongodb):
    _, offer_id = _offer(millimes=15000)
    confirmed = _cart(offer_id, quantity=2)
    _cart(offer_id, phone="55 111 222", name="Karim")
    site_orders_service.confirm_cart(confirmed["reference"])

    result = site_admin_service.overview()
    assert result["revenue_today_millimes"] == 30000
    assert result["revenue_month_millimes"] == 30000
    assert result["carts"]["to_verify"] == 1
    assert result["carts"]["confirmed"] == 1
    assert result["customers"] == 2
    assert result["top_products"][0] == {
        "offer_name": "Netflix 1 mois", "service_name": "Netflix", "quantity": 2, "revenue_millimes": 30000,
    }
    assert len(result["recent_carts"]) == 2


def test_customers_are_grouped_by_phone_with_history(mock_mongodb):
    _, offer_id = _offer(millimes=10000)
    first = _cart(offer_id)
    _cart(offer_id, quantity=3)
    _cart(offer_id, phone="55 111 222", name="Karim")
    site_orders_service.confirm_cart(first["reference"])

    result = site_admin_service.customers({})
    assert result["total"] == 2
    sana = result["items"][0]
    assert sana["phone"] == "+21622333444"
    assert sana["carts_count"] == 2
    assert sana["pending_count"] == 1
    assert sana["total_spent_millimes"] == 10000
    assert sana["whatsapp_url"] == "https://wa.me/21622333444"

    assert [row["name"] for row in site_admin_service.customers({"search": ["55111"]})["items"]] == ["Karim"]


def test_settings_validation(mock_mongodb):
    assert site_settings_service.get()["payment_methods"] == ["d17", "flouci"]
    with pytest.raises(site_settings_service.SiteSettingsError, match="WhatsApp"):
        site_settings_service.save({"whatsapp_number": "123", "tnd_per_usdt": "3", "payment_d17": "1"})
    with pytest.raises(site_settings_service.SiteSettingsError, match="taux"):
        site_settings_service.save({"whatsapp_number": "21621994132", "tnd_per_usdt": "0", "payment_d17": "1"})

    saved = site_settings_service.save({"whatsapp_number": "21994132", "tnd_per_usdt": "3,25", "payment_d17": "1"})
    assert saved["whatsapp_number"] == "21621994132"
    assert saved["tnd_per_usdt"] == 3.25
    assert saved["payment_methods"] == ["d17"]
