"""Admin space for the Tunisian storefront: overview, catalog, customers, settings."""

import base64
import itertools
import time
from unittest.mock import Mock

import pytest

import database as db
from app.domain import (
    site_admin_service,
    site_logo_service,
    site_orders_service,
    site_requests_service,
    site_settings_service,
    storefront_service,
    storefront_wallet_service,
    support_service,
)
from app.web import dashboard_api
from tests.conftest import RECEIPT

_references = itertools.count(1)


def _offer(name="Netflix 1 mois", millimes=15000, service="Netflix", stock=10):
    service_id = db.add_service(service, "🎬", sales_channels=["bot"])
    offer_id = db.add_offer(service_id, name, 5.0, stock, sales_channels=["bot"], tn_price_millimes=millimes)
    return service_id, offer_id


def _cart(customer, offer_id, quantity=1):
    return storefront_service.create_order({
        "payment_method": "d17",
        "transaction_reference": f"D17-{next(_references):05d}",
        "receipt": RECEIPT,
        "items": [{"offer_id": offer_id, "quantity": quantity}],
    }, customer)


def test_catalog_query_count_does_not_grow_with_services(mock_mongodb, monkeypatch):
    watched = []
    for collection in (mock_mongodb.services, mock_mongodb.offers, mock_mongodb.settings):
        for name in ("find", "find_one"):
            spy = Mock(wraps=getattr(collection, name))
            monkeypatch.setattr(collection, name, spy)
            watched.append(spy)

    _offer()
    for spy in watched:
        spy.reset_mock()
    site_admin_service.catalog({})
    baseline = sum(spy.call_count for spy in watched)

    for index in range(12):
        _offer(name=f"Offer {index}", service=f"Service {index}")
    for spy in watched:
        spy.reset_mock()
    result = site_admin_service.catalog({})

    assert result["counts"]["all"] == 13
    assert sum(spy.call_count for spy in watched) == baseline


def test_catalog_groups_offers_by_site_status(mock_mongodb):
    _, priced = _offer()
    _, unpriced = _offer(name="Outlook", millimes=None, service="Mails")
    hidden_service, hidden = _offer(name="Spotify", service="Spotify")
    site_admin_service.set_service_visibility({"service_id": hidden_service, "site_enabled": "0"})

    result = site_admin_service.catalog({})
    assert result["counts"] == {"all": 3, "on_sale": 1, "no_price": 1, "hidden": 1, "disabled": 0}
    rows = {row["id"]: row for row in result["items"]}
    assert rows[priced]["on_sale"] is True
    assert rows[unpriced]["tn_price_millimes"] is None
    assert rows[unpriced]["suggested_price_millimes"] == 16000
    assert rows[hidden]["service_visible"] is False

    only_unpriced = site_admin_service.catalog({"status": ["no_price"]})
    assert [row["id"] for row in only_unpriced["items"]] == [unpriced]


def test_catalog_groups_offers_by_storefront_category(mock_mongodb):
    netflix_service, netflix = _offer(name="Netflix 1 mois", service="Netflix")
    divers_service, other = _offer(name="Boite mystere", millimes=None, service="Divers")

    result = site_admin_service.catalog({})
    groups = {group["id"]: group for group in result["groups"]}
    assert [group["id"] for group in result["groups"]] == [
        f"service:{netflix_service}", f"service:{divers_service}",
    ]
    assert groups[f"service:{netflix_service}"]["label"] == "Netflix"
    assert groups[f"service:{netflix_service}"]["kind"] == "service"
    assert groups[f"service:{netflix_service}"]["count"] == 1
    assert groups[f"service:{netflix_service}"]["on_sale"] == 1
    assert [row["id"] for row in groups[f"service:{netflix_service}"]["items"]] == [netflix]
    assert groups[f"service:{divers_service}"]["label"] == "Divers"
    assert [row["id"] for row in groups[f"service:{divers_service}"]["items"]] == [other]
    assert groups[f"service:{divers_service}"]["on_sale"] == 0

    filtered = site_admin_service.catalog({"status": ["no_price"]})
    assert [group["id"] for group in filtered["groups"]] == [f"service:{divers_service}"]
    assert filtered["groups"][0]["items"][0]["id"] == other
    assert [row["id"] for row in filtered["items"]] == [other]


def test_site_category_order_does_not_change_the_bot_order(mock_mongodb):
    netflix, _ = _offer(name="Netflix 1 mois", service="Netflix")
    spotify, _ = _offer(name="Spotify 1 mois", service="Spotify")
    bot_rows = [row for row in db.list_services(active_only=False) if row.get("archived") != 1]
    bot_ids = [row["id"] for row in bot_rows]
    bot_orders = [row.get("sort_order") for row in bot_rows]
    site_ids = list(reversed(bot_ids))

    site_admin_service.reorder_services({"ordered_ids": ",".join(str(item) for item in site_ids)})

    unchanged = [row for row in db.list_services(active_only=False) if row.get("archived") != 1]
    assert [row["id"] for row in unchanged] == bot_ids
    assert [row.get("sort_order") for row in unchanged] == bot_orders
    assert db.get_service(spotify)["site_sort_order"] == site_ids.index(spotify)
    assert db.get_service(netflix)["site_sort_order"] == site_ids.index(netflix)

    admin = site_admin_service.catalog({})
    assert [service["id"] for service in admin["services"]] == site_ids
    assert [group["service_id"] for group in admin["groups"][:2]] == [spotify, netflix]
    assert [service["name"] for service in storefront_service.catalog()["services"]] == ["Spotify", "Netflix"]

    db.reorder_catalog("service", bot_ids)
    assert [row["id"] for row in db.list_services() if row["id"] in {netflix, spotify}] == [netflix, spotify]
    assert [service["name"] for service in storefront_service.catalog()["services"]] == ["Spotify", "Netflix"]


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


def test_catalog_lists_disabled_offers_without_selling_them(mock_mongodb):
    _, offer_id = _offer()
    db.update_offer(offer_id, active=0)

    result = site_admin_service.catalog({})
    assert result["counts"]["disabled"] == 1
    row = result["items"][0]
    assert row["active"] is False
    assert row["on_sale"] is False
    assert storefront_service.catalog()["services"] == []


def test_move_button_sends_an_offer_to_another_service(mock_mongodb):
    source_id, offer_id = _offer(name="ChatGPT Plus 1 mois", service="ChatGPT")
    destination_id = db.add_service("Google AI Pro", "✦", sales_channels=["bot"])

    result = site_admin_service.move_catalog_offer({
        "offer_id": str(offer_id),
        "service_id": str(destination_id),
    })

    assert result["service_name"] == "Google AI Pro"
    assert db.get_offer(offer_id)["service_id"] == destination_id
    assert db.get_offer(offer_id)["service_id"] != source_id
    with pytest.raises(site_admin_service.SiteAdminError, match="déjà"):
        site_admin_service.move_catalog_offer({
            "offer_id": str(offer_id),
            "service_id": str(destination_id),
        })


def test_admin_can_rename_and_move_a_product_category(mock_mongodb):
    official_id = db.add_service("officiels subscribes", "⭐", sales_channels=["bot", "tn_site"])
    chatgpt = db.add_offer(
        official_id, "ChatGPT Plus 1 mois", 6.0, 4,
        sales_channels=["bot", "tn_site"], tn_price_millimes=25000,
    )
    google = db.add_offer(
        official_id, "Google AI Pro | 12 months", 18.0, 2,
        sales_channels=["bot", "tn_site"], tn_price_millimes=60000,
    )

    before = site_admin_service.catalog({})
    labels = [group["label"] for group in before["groups"]]
    assert labels == ["ChatGPT Plus", "Google AI Pro"]
    assert all(group["kind"] == "product" for group in before["groups"])

    site_admin_service.rename_product_category({
        "name": "ChatGPT",
        "offer_ids": str(chatgpt),
    })
    renamed = storefront_service.catalog()["services"]
    assert renamed[0]["name"] == "ChatGPT"
    assert renamed[0]["offers"][0]["service_name"] == "ChatGPT"

    destination = site_admin_service.save_service({"name": "Google AI", "site_enabled": "1"})
    site_admin_service.save_offer({
        "offer_id": str(google),
        "service_id": str(destination["service_id"]),
        "name": "Google AI Pro",
        "tn_price": "60",
    })
    moved = {service["name"]: service for service in storefront_service.catalog()["services"]}
    assert "Google AI Pro" not in moved
    assert moved["Google AI"]["offers"][0]["id"] == google
    assert db.get_offer(google)["service_id"] == destination["service_id"]


def test_save_service_creates_and_renames(mock_mongodb):
    created = site_admin_service.save_service({"name": " Netflix ", "emoji": "🎬", "site_enabled": "0"})
    service = db.get_service(created["service_id"])
    assert created["created"] is True
    assert service["name"] == "Netflix"
    assert service["site_name"] == "Netflix"
    assert service["active"] == 0
    assert service["site_enabled"] is False

    site_admin_service.save_service({"service_id": str(created["service_id"]), "name": "Netflix TN", "site_enabled": "1"})
    service = db.get_service(created["service_id"])
    assert service["name"] == "Netflix"
    assert service["site_name"] == "Netflix TN"
    assert service["site_enabled"] is True

    with pytest.raises(site_admin_service.SiteAdminError, match="obligatoire"):
        site_admin_service.save_service({"name": " "})


_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _data_url(data: bytes, content_type: str = "image/png") -> str:
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def test_product_category_uploads_and_removes_its_own_logo(mock_mongodb):
    official_id = db.add_service("officiels subscribes", "⭐", sales_channels=["bot", "tn_site"])
    first = db.add_offer(
        official_id, "Manus 1 mois", 6.0, 4,
        sales_channels=["bot", "tn_site"], tn_price_millimes=25000,
    )
    second = db.add_offer(
        official_id, "Manus 12 mois", 18.0, 2,
        sales_channels=["bot", "tn_site"], tn_price_millimes=60000,
    )

    with pytest.raises(site_admin_service.SiteAdminError, match="PNG, JPEG ou WebP"):
        site_admin_service.rename_product_category({
            "name": "Autre",
            "offer_ids": str(first),
            "logo": "https://example.com/logo.png",
        })
    assert "site_category_name" not in db.get_offer(first)

    site_admin_service.rename_product_category({
        "name": "Manus",
        "offer_ids": f"{first},{second}",
        "logo": _data_url(_PNG),
    })
    grouped = {group["label"]: group for group in site_admin_service.catalog({})["groups"]}
    url = grouped["Manus"]["logo_url"]
    assert url.startswith(f"/api/storefront/category-logo?id={first}&v=")
    assert site_logo_service.load_category_logo(first) == (_PNG, "image/png")
    assert db.get_offer(second)["site_category_logo_id"] == first

    public = {service["name"]: service for service in storefront_service.catalog()["services"]}
    assert public["Manus"]["logo_url"] == url
    assert {offer["service_logo_url"] for offer in public["Manus"]["offers"]} == {url}

    site_admin_service.rename_product_category({
        "name": "Manus AI",
        "offer_ids": f"{first},{second}",
    })
    created = site_admin_service.save_offer({
        "service_id": str(official_id),
        "name": "Manus AI 3 mois",
        "tn_price": "30",
        "site_category_name": "Manus AI",
        "site_enabled": "1",
    })
    assert db.get_offer(created["offer_id"])["site_category_logo_id"] == first
    renamed = storefront_service.catalog()["services"][0]
    assert renamed["name"] == "Manus AI"
    assert renamed["logo_url"] == url

    site_admin_service.rename_product_category({
        "name": "Manus AI",
        "offer_ids": f"{first},{second},{created['offer_id']}",
        "remove_logo": "1",
    })
    assert site_logo_service.load_category_logo(first) is None
    assert db.get_offer(second).get("site_category_logo_id") is None
    assert storefront_service.catalog()["services"][0]["logo_url"] == ""


def test_save_service_uploads_replaces_and_removes_logo(mock_mongodb):
    service_id = site_admin_service.save_service({"name": "Netflix", "logo": _data_url(_PNG)})["service_id"]
    service = db.get_service(service_id)
    url = site_logo_service.logo_url(service)
    assert url.startswith(f"/api/storefront/service-logo?id={service_id}&v=")
    assert site_logo_service.load(service_id) == (_PNG, "image/png")
    (listed,) = site_admin_service.catalog({})["services"]
    assert listed["logo_url"] == url

    site_admin_service.save_service({"service_id": str(service_id), "name": "Netflix"})
    assert site_logo_service.load(service_id) is not None

    site_admin_service.save_service({"service_id": str(service_id), "name": "Netflix", "remove_logo": "1"})
    assert site_logo_service.load(service_id) is None
    assert site_logo_service.logo_url(db.get_service(service_id)) == ""


@pytest.mark.parametrize("logo, message", [
    ("https://example.com/logo.png", "PNG, JPEG ou WebP"),
    ("data:image/svg+xml;base64,PHN2Zz4=", "PNG, JPEG ou WebP"),
    (_data_url(b"GIF89a" + b"\x00" * 16), "illisible"),
    (_data_url(_PNG + b"\x00" * site_logo_service.MAX_LOGO_BYTES), "500 Ko"),
], ids=["url", "svg", "gif", "too_large"])
def test_save_service_rejects_invalid_logo_without_creating(mock_mongodb, logo, message):
    with pytest.raises(site_admin_service.SiteAdminError, match=message):
        site_admin_service.save_service({"name": "Canva", "logo": logo})
    assert site_admin_service.catalog({})["services"] == []


def test_save_offer_uploads_and_removes_a_product_video(mock_mongodb):
    service_id, offer_id = _offer()
    base = {"offer_id": str(offer_id), "service_id": str(service_id), "name": "Netflix 1 mois", "tn_price": "15"}
    payload = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8

    site_admin_service.save_offer({**base, "video": _data_url(payload, "video/mp4")})
    url = db.get_offer(offer_id)["site_video_url"]
    assert url.startswith(f"/api/storefront/offer-video?id={offer_id}&v=")
    assert site_logo_service.load_offer_video(offer_id) == (payload, "video/mp4")
    public = next(
        offer
        for service in storefront_service.catalog()["services"]
        for offer in service["offers"]
        if offer["id"] == offer_id
    )
    assert public["video_url"] == url
    assert public["image_url"] == ""

    site_admin_service.save_offer({**base, "site_video_url": "", "remove_video": "1"})
    assert site_logo_service.load_offer_video(offer_id) is None
    assert db.get_offer(offer_id)["site_video_url"] == ""

    with pytest.raises(site_admin_service.SiteAdminError, match="MP4 ou WebM"):
        site_admin_service.save_offer({**base, "video": _data_url(payload, "video/avi")})


def test_save_offer_uploads_and_removes_product_image(mock_mongodb):
    service_id, offer_id = _offer()
    base = {"offer_id": str(offer_id), "service_id": str(service_id), "name": "Netflix 1 mois", "tn_price": "15"}

    site_admin_service.save_offer({**base, "image": _data_url(_PNG)})
    url = db.get_offer(offer_id)["site_image_url"]
    assert url.startswith(f"/api/storefront/offer-image?id={offer_id}&v=")
    assert site_logo_service.load_offer_image(offer_id) == (_PNG, "image/png")
    assert storefront_service.catalog()["services"][0]["offers"][0]["image_url"] == url

    site_admin_service.save_offer({**base, "site_image_url": url})
    assert site_logo_service.load_offer_image(offer_id) is not None

    site_admin_service.save_offer({**base, "site_image_url": "https://cdn.example.com/netflix.png"})
    assert site_logo_service.load_offer_image(offer_id) is None
    assert db.get_offer(offer_id)["site_image_url"] == "https://cdn.example.com/netflix.png"

    site_admin_service.save_offer({**base, "image": _data_url(_PNG)})
    site_admin_service.save_offer({**base, "site_image_url": "", "remove_image": "1"})
    assert site_logo_service.load_offer_image(offer_id) is None
    assert db.get_offer(offer_id)["site_image_url"] == ""

    with pytest.raises(site_admin_service.SiteAdminError, match="1 Mo"):
        site_admin_service.save_offer({**base, "image": _data_url(_PNG + b"\x00" * site_logo_service.MAX_OFFER_IMAGE_BYTES)})


def test_save_offer_creates_a_sellable_product_with_stock(mock_mongodb):
    service_id = site_admin_service.save_service({"name": "Canva"})["service_id"]
    site_settings_service.save({"tnd_per_usdt": "3,2", "payment_d17": "1", "details_d17": "21 000 000"})

    result = site_admin_service.save_offer({
        "service_id": str(service_id),
        "name": "Canva Pro 1 an",
        "tn_price": "32",
        "site_description_fr": "Compte personnel",
        "site_badge": "Nouveau",
        "site_image_url": "https://cdn.example.com/canva.png",
        "period_value": "1", "period_unit": "years",
        "warranty_value": "3", "warranty_unit": "months",
        "initial_inventory": "###\nuser1:pass\n###\nuser2:pass",
    })
    offer = db.get_offer(result["offer_id"])
    assert result["created"] is True
    assert offer["price"] == 0
    assert offer["active"] == 0
    assert offer["description"] == ""
    assert offer["warranty_days"] == 0
    assert offer["site_period_days"] == 365
    assert offer["site_warranty_days"] == 90
    assert offer["tn_price_millimes"] == 32000
    assert offer["stock"] == 2
    assert offer["site_image_url"] == "https://cdn.example.com/canva.png"

    public = storefront_service.catalog()["services"][0]["offers"][0]
    assert public["name"] == "Canva Pro 1 an"
    assert public["price_millimes"] == 32000
    assert public["description"] == "Compte personnel"
    assert public["badge"] == "Nouveau"


def test_optional_remark_is_saved_on_the_product_by_the_admin(mock_mongodb):
    service_id, offer_id = _offer()
    site_admin_service.save_offer({
        "offer_id": str(offer_id),
        "service_id": str(service_id),
        "name": "Netflix 1 mois",
        "tn_price": "15",
        "site_remark": "  Préférence de profil  ",
        "site_requires_info": "1",
    })
    offer = db.get_offer(offer_id)
    assert offer["site_remark"] == "Préférence de profil"
    assert offer["site_requires_info"] is True
    assert offer.get("note") != "Préférence de profil"

    public = next(
        item
        for service in storefront_service.catalog()["services"]
        for item in service["offers"]
        if item["id"] == offer_id
    )
    assert public["remark"] == "Préférence de profil"
    assert public["requires_info"] is True


def test_save_offer_keeps_bot_copy_and_shares_stock_mode(mock_mongodb):
    service_id, offer_id = _offer()
    db.update_offer(offer_id, description="Texte bot", note="30 days", active=1)
    other_service = site_admin_service.save_service({"name": "Streaming"})["service_id"]

    site_admin_service.save_offer({
        "offer_id": str(offer_id), "service_id": str(other_service), "name": "Netflix 3 mois",
        "price": "12,5", "tn_price": "", "stock_mode": "unlimited", "site_enabled": "1",
        "site_description_fr": "Texte site", "warranty_value": "7", "warranty_unit": "days",
    })
    offer = db.get_offer(offer_id)
    assert offer["service_id"] == other_service
    assert offer["name"] == "Netflix 1 mois"
    assert offer["description"] == "Texte bot"
    assert offer["note"] == "30 days"
    assert offer["price"] == 5.0
    assert offer["active"] == 1
    assert offer["warranty_days"] == 0
    assert offer["site_name"] == "Netflix 3 mois"
    assert offer["site_description_fr"] == "Texte site"
    assert offer["site_warranty_days"] == 7
    assert offer["unlimited_stock"] is True
    assert offer["site_enabled"] is True
    assert "tn_price_millimes" not in mock_mongodb.offers.find_one({"id": offer_id})
    assert service_id != other_service

    db.update_offer(offer_id, description="Nouveau texte bot", note="NW", price=8.0, warranty_days=14, active=0)
    offer = db.get_offer(offer_id)
    assert offer["description"] == "Nouveau texte bot"
    assert offer["price"] == 8.0
    assert offer["active"] == 0
    assert offer["warranty_days"] == 14
    assert offer["site_description_fr"] == "Texte site"
    assert offer["site_name"] == "Netflix 3 mois"
    assert offer["site_enabled"] is True
    assert offer["site_warranty_days"] == 7
    assert "tn_price_millimes" not in mock_mongodb.offers.find_one({"id": offer_id})


@pytest.mark.parametrize("form, message", [
    ({"name": "X"}, "service"),
    ({"service_id": "SERVICE", "name": ""}, "obligatoire"),
    ({"service_id": "SERVICE", "name": "X", "tn_price": "5", "site_image_url": "http://x"}, "https"),
])
def test_save_offer_rejects_invalid_input(mock_mongodb, form, message):
    service_id = site_admin_service.save_service({"name": "Canva"})["service_id"]
    form = {key: str(service_id) if value == "SERVICE" else value for key, value in form.items()}
    with pytest.raises(site_admin_service.SiteAdminError, match=message):
        site_admin_service.save_offer(form)


def test_overview_counts_revenue_only_for_confirmed_carts(mock_mongodb, site_customer):
    sana, karim = site_customer(name="Sana", email="sana@example.com"), site_customer(name="Karim", email="karim@example.com")
    _, offer_id = _offer(millimes=15000)
    confirmed = _cart(sana, offer_id, quantity=2)
    _cart(karim, offer_id)
    site_orders_service.confirm_cart(confirmed["reference"])

    result = site_admin_service.overview()
    assert result["revenue_today_millimes"] == 30000
    assert result["revenue_month_millimes"] == 30000
    assert result["carts"]["to_verify"] == 1
    assert result["carts"]["confirmed"] == 1
    assert result["customers"] == 2
    assert result["deposits_pending"] == 0
    assert result["top_products"][0] == {
        "offer_name": "Netflix 1 mois", "service_name": "Netflix", "quantity": 2, "revenue_millimes": 30000,
    }
    assert len(result["recent_carts"]) == 2


def test_customers_are_accounts_with_wallet_and_history(mock_mongodb, site_customer):
    sana = site_customer(name="Sana", email="sana@example.com", phone="+21622333444")
    karim = site_customer(name="Karim", email="karim@example.com", phone="+21655111222")
    _, offer_id = _offer(millimes=10000)
    first = _cart(sana, offer_id)
    _cart(sana, offer_id, quantity=3)
    _cart(karim, offer_id)
    site_orders_service.confirm_cart(first["reference"])
    storefront_wallet_service.credit(sana["id"], 7000, kind="deposit")

    result = site_admin_service.customers({})
    assert result["total"] == 2
    row = next(item for item in result["items"] if item["id"] == sana["id"])
    assert row["email"] == "sana@example.com"
    assert row["balance_millimes"] == 7000
    assert row["carts_count"] == 2
    assert row["pending_count"] == 1
    assert row["total_spent_millimes"] == 10000
    assert [cart["payment_label"] for cart in row["carts"]] == ["D17", "D17"]

    assert [row["name"] for row in site_admin_service.customers({"search": ["karim@"]})["items"]] == ["Karim"]


def test_settings_validation(mock_mongodb):
    settings = site_settings_service.get()
    assert settings["payment_methods"] == ["d17", "flouci"]
    assert "whatsapp_number" not in settings
    assert [item["id"] for item in settings["available_payment_methods"]] == ["d17", "flouci", "izi", "wafacash"]
    with pytest.raises(site_settings_service.SiteSettingsError, match="taux"):
        site_settings_service.save({"tnd_per_usdt": "0", "payment_d17": "1", "details_d17": "21 000 000"})
    with pytest.raises(site_settings_service.SiteSettingsError, match="au moins un"):
        site_settings_service.save({"tnd_per_usdt": "3"})
    with pytest.raises(site_settings_service.SiteSettingsError, match="IZI"):
        site_settings_service.save({"tnd_per_usdt": "3", "payment_izi": "1", "details_izi": " "})

    saved = site_settings_service.save({
        "tnd_per_usdt": "3,25",
        "payment_d17": "1",
        "details_d17": "D17 : 21 000 000",
        "payment_izi": "1",
        "details_izi": "IZI : 55 000 000",
    })
    assert saved["tnd_per_usdt"] == 3.25
    assert saved["payment_methods"] == ["d17", "izi"]
    assert saved["payment_details"]["izi"] == "IZI : 55 000 000"


def test_site_requests_stay_out_of_the_bot_workspace(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _offer(millimes=10000)
    cart = _cart(customer, offer_id)
    line_id = cart["order_ids"][0]
    now = int(time.time())
    db.get_conn().orders.update_one(
        {"id": line_id},
        {"$set": {"status": "delivered", "delivered_at": now, "warranty_days": 30, "total_millimes": 10000}},
    )
    support_service.create_ticket(42, "Bot ticket", category="other")
    site_requests_service.create_ticket(customer, {"message": "Mon compte site ne marche pas", "category": "order"})
    site_requests_service.create_ticket(customer, {"message": "Ajoutez Canva annuel svp", "category": "catalog_request"})
    claim = site_requests_service.create_warranty(customer, {"order_id": line_id, "reason": "Le compte ne se connecte pas"})

    bot_tickets = dashboard_api.list_tickets({})
    assert [item["id"] for item in bot_tickets["items"]] != []
    assert all(item.get("channel") != "tn_site" for item in bot_tickets["items"])
    site_tickets = dashboard_api.list_tickets({"channel": ["tn_site"], "exclude_category": ["catalog_request"]})
    assert [item["category"] for item in site_tickets["items"]] == ["order"]
    site_requests = dashboard_api.list_tickets({"channel": ["tn_site"], "category": ["catalog_request"]})
    assert len(site_requests["items"]) == 1

    bot_orders = dashboard_api.list_orders({})
    assert line_id not in {item["id"] for item in bot_orders["items"]}

    request_id = claim["warranty"]["id"]
    db.accept_warranty_request(request_id)
    resolved = db.resolve_warranty_request(request_id, "refund")
    assert resolved["status"] == "refunded"
    assert storefront_wallet_service.balance(customer["id"]) == claim["warranty"]["refund_millimes"]
    assert db.get_conn().wallets.count_documents({}) == 0
    assert dashboard_api.list_warranties({})["total"] == 0
    assert dashboard_api.list_warranties({"channel": ["tn_site"]})["total"] == 1


def _delivered_line(customer, name="Netflix 1 mois", service="Netflix"):
    _, offer_id = _offer(name=name, service=service)
    cart = _cart(customer, offer_id)
    line_id = cart["order_ids"][0]
    db.get_conn().orders.update_one(
        {"id": line_id},
        {"$set": {"status": "delivered", "delivered_at": int(time.time()), "warranty_days": 30, "total_millimes": 10000}},
    )
    return line_id


def test_customer_reply_stays_on_their_open_thread(mock_mongodb, site_customer):
    owner = site_customer()
    other = site_customer(name="Sara Trabelsi", email="sara@example.com", phone="+21622222333")
    opened = site_requests_service.create_ticket(owner, {"message": "Mon compte site ne marche pas", "category": "order"})
    ticket_id = opened["ticket"]["id"]

    replied = site_requests_service.reply_ticket(owner, ticket_id, "Toujours bloqué après redémarrage")
    assert replied["ticket"]["status"] == "waiting_admin"
    assert replied["ticket"]["messages"][-1]["sender"] == "client"
    assert replied["ticket"]["messages"][-1]["content"] == "Toujours bloqué après redémarrage"

    with pytest.raises(site_requests_service.SiteRequestError, match="introuvable") as missing:
        site_requests_service.reply_ticket(other, ticket_id, "Je ne suis pas le client")
    assert missing.value.status == 404

    support_service.close_ticket(ticket_id)
    with pytest.raises(site_requests_service.SiteRequestError, match="fermée"):
        site_requests_service.reply_ticket(owner, ticket_id, "Une dernière question")

    resolved = site_requests_service.create_ticket(owner, {"message": "Le paiement est passé deux fois", "category": "payment"})
    db.get_conn().support_tickets.update_one({"id": resolved["ticket"]["id"]}, {"$set": {"status": "resolved"}})
    with pytest.raises(site_requests_service.SiteRequestError, match="fermée"):
        site_requests_service.reply_ticket(owner, resolved["ticket"]["id"], "C'est revenu")


def test_warranty_history_keeps_the_refusal_and_the_replacement(mock_mongodb, site_customer):
    customer = site_customer()
    refused_order = _delivered_line(customer)
    replaced_order = _delivered_line(customer, name="Spotify 1 mois", service="Spotify")
    refused = site_requests_service.create_warranty(customer, {"order_id": refused_order, "reason": "Le compte ne se connecte pas"})
    replaced = site_requests_service.create_warranty(customer, {"order_id": replaced_order, "reason": "Le mot de passe a changé"})

    refused_id = refused["warranty"]["id"]
    assert db.refuse_warranty_request(refused_id, "Hors délai d'usage")

    replaced_id = replaced["warranty"]["id"]
    assert db.accept_warranty_request(replaced_id)
    assert db.resolve_warranty_request(replaced_id, "replacement")
    db.get_conn().warranty_requests.update_one(
        {"id": replaced_id},
        {"$set": {"replacement_text": "login: new@mail.test"}},
    )
    assert db.complete_warranty_replacement(replaced_id)

    listed = {item["id"]: item for item in site_requests_service.list_warranties(customer["id"])["warranties"]}
    assert listed[refused_id]["status"] == "refused"
    assert listed[refused_id]["admin_note"] == "Hors délai d'usage"
    assert listed[replaced_id]["status"] == "replacement_delivered"
    assert listed[replaced_id]["replacement"] == "login: new@mail.test"

    flags = site_requests_service.warranty_flags([{"id": refused_order}, {"id": replaced_order}])
    assert flags[refused_order]["warranty_note"] == "Hors délai d'usage"
    assert flags[refused_order]["warranty_status"] == "refused"
    assert flags[replaced_order]["replacement"] == "login: new@mail.test"
    assert flags[replaced_order]["warranty_note"] == ""
