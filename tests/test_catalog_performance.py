import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import database as db
import keyboards as kb
from app.domain import reseller_service
from app.web import dashboard_api


def test_services_with_stock_returns_totals_without_n_plus_one(mock_mongodb):
    first = db.add_service("First", "1")
    second = db.add_service("Second", "2")
    db.add_offer(first, "A", 1.0, 2)
    db.add_offer(first, "B", 1.0, 3)
    db.add_offer(second, "C", 1.0, 1)

    services = db.list_services_with_stock()
    totals = {service["id"]: service["total_stock"] for service in services}

    assert totals[first] == 5
    assert totals[second] == 1


def test_flat_catalog_returns_offers_from_active_services_only(mock_mongodb):
    active = db.add_service("Active", "A")
    inactive = db.add_service("Inactive", "I")
    visible = db.add_offer(active, "Visible offer", 2.0, 4)
    hidden = db.add_offer(inactive, "Hidden offer", 3.0, 5)
    db.update_service(inactive, active=0)

    offers = db.list_catalog_offers()

    assert [offer["id"] for offer in offers] == [visible]
    assert offers[0]["service_name"] == "Active"
    assert hidden not in {offer["id"] for offer in offers}


def test_catalog_propagates_service_button_suffix(mock_mongodb):
    service_id = db.add_service(
        "officiels subscribes", "⭐", suffix_emoji="✅",
    )
    db.add_offer(service_id, "Premium", 5.0, 4)

    service = db.get_service(service_id)
    offer = db.list_catalog_offers()[0]

    assert service["suffix_emoji"] == "✅"
    assert offer["service_suffix_emoji"] == "✅"


def test_dashboard_catalog_query_count_does_not_grow_with_services(mock_mongodb, monkeypatch):
    collections = (mock_mongodb.services, mock_mongodb.offers, mock_mongodb.orders)
    queries = []
    for collection in collections:
        for method in ("find", "aggregate", "count_documents"):
            spy = Mock(wraps=getattr(collection, method))
            monkeypatch.setattr(collection, method, spy)
            queries.append(spy)

    service_id = db.add_service("First", "1")
    db.add_offer(service_id, "Offer", 5, 3)
    for spy in queries:
        spy.reset_mock()
    db.dashboard_data()
    baseline = sum(spy.call_count for spy in queries)

    for index in range(20):
        service_id = db.add_service(f"Extra {index}", "2")
        db.add_offer(service_id, "Offer", 5, 3)
    for spy in queries:
        spy.reset_mock()
    data = db.dashboard_data()

    assert len(data["services"]) == 21
    assert sum(spy.call_count for spy in queries) == baseline


def test_inventory_summary_fetches_offer_names_in_one_query(mock_mongodb, monkeypatch):
    mock_mongodb.offers.insert_many([{"id": i, "name": f"Offer {i}"} for i in range(20)])
    mock_mongodb.inventory.insert_many([
        {"id": i, "offer_id": i, "status": "available"} for i in range(20)
    ])
    find = Mock(wraps=mock_mongodb.offers.find)
    monkeypatch.setattr(mock_mongodb.offers, "find", find)

    rows = dashboard_api.inventory_summary()

    assert len(rows) == 20
    assert all(row["offer_name"] == f"Offer {row['offer_id']}" for row in rows)
    assert find.call_count == 1


def test_flat_catalog_buttons_do_not_load_each_service(mock_mongodb, monkeypatch):
    service_id = db.add_service("officiels subscribes", "⭐")
    for index in range(8):
        db.add_offer(service_id, f"Product {index}", 5.0, 2)
    find_one = Mock(wraps=mock_mongodb.services.find_one)
    monkeypatch.setattr(mock_mongodb.services, "find_one", find_one)

    keyboard = kb.catalog_offers_keyboard("en")
    product_rows = [
        row for row in keyboard.inline_keyboard
        if row and str(getattr(row[0], "callback_data", "") or "").startswith("off:")
    ]

    assert len(product_rows) == 8
    assert find_one.call_count == 0


def test_catalog_keyboard_is_reused_until_it_expires(mock_mongodb, monkeypatch):
    monkeypatch.setattr(kb, "BOT_CATALOG_CACHE_SECONDS", 30)
    service_id = db.add_service("Netflix", "N")
    db.add_offer(service_id, "Premium", 4.0, 2)
    listed = Mock(wraps=kb.db.list_catalog_offers)
    monkeypatch.setattr(kb.db, "list_catalog_offers", listed)

    first = kb.catalog_offers_keyboard("en")
    second = kb.catalog_offers_keyboard("en")

    assert second is first
    assert listed.call_count == 1


def test_catalog_button_returns_before_supplier_refresh(mock_mongodb, monkeypatch):
    from bot import cb_navigation, show_catalog

    service_id = db.add_service("Netflix", "N")
    db.add_offer(service_id, "Premium", 4.0, 2)
    release = threading.Event()
    entered = threading.Event()

    def slow_refresh(offers=None):
        entered.set()
        release.wait(3)

    monkeypatch.setattr(reseller_service, "SUPPLIER_REFRESH_IN_BACKGROUND", True)
    monkeypatch.setattr(reseller_service, "_background_refresh_started_at", 0.0)
    monkeypatch.setattr(reseller_service, "_background_refresh_running", threading.Lock())
    monkeypatch.setattr(reseller_service, "refresh_supplier_stock", slow_refresh)

    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=7),
        message=message,
        callback_query=None,
    )
    started = time.perf_counter()
    try:
        asyncio.run(show_catalog(update, SimpleNamespace(), "en"))
        elapsed = time.perf_counter() - started
        assert elapsed < 1
        message.reply_text.assert_awaited()
        assert entered.wait(1)

        entered.clear()
        query_message = SimpleNamespace(text="menu", reply_text=AsyncMock())
        query = SimpleNamespace(
            data="catalog",
            from_user=SimpleNamespace(id=7),
            answer=AsyncMock(),
            message=query_message,
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        callback_update = SimpleNamespace(callback_query=query, effective_user=query.from_user)
        started = time.perf_counter()
        asyncio.run(cb_navigation(callback_update, SimpleNamespace()))
        assert time.perf_counter() - started < 1
        query.edit_message_text.assert_awaited()
    finally:
        release.set()


def test_supplier_offers_are_copied_as_inactive_local_twins(mock_mongodb):
    service_id = db.add_service("ChatGPT", "🤖")
    other_service = db.add_service("Spotify", "🎵")
    supplier_id = db.add_offer(
        service_id,
        "Plus - Apple pay",
        12.5,
        4,
        note="30 days",
        description="Compte ChatGPT Plus",
        currency="USDT",
        delivery_delay="Instantané après confirmation",
        photo_file_id="photo-1",
        supplier_provider="upibot",
        supplier_product_id="18",
        period_days=30,
        warranty_days=7,
        name_ar="بلس",
        description_ar="وصف",
    )
    db.update_offer(
        supplier_id,
        period_value=1,
        period_unit="months",
        warranty_value=7,
        warranty_unit="days",
        site_name="ChatGPT Plus",
        site_description_fr="Le même texte",
    )
    local_id = db.add_offer(service_id, "Already local", 3.0, 1)
    archived_service_offer = db.add_offer(
        other_service, "Old API", 2.0, 1,
        supplier_provider="mailreader", supplier_product_id="old",
    )
    db.archive_offer(archived_service_offer)
    mock_mongodb.inventory.insert_one({
        "id": 1, "offer_id": supplier_id, "status": "available", "payload": "secret",
    })
    mock_mongodb.reseller_products.insert_one({
        "provider": "upibot", "product_id": "18", "local_offer_id": supplier_id,
    })

    first = db.copy_supplier_offers_to_local()
    second = db.copy_supplier_offers_to_local()

    copy = db.get_offer(first["offer_ids"][0])
    original = db.get_offer(supplier_id)
    panel = next(
        item for item in db.dashboard_data(include_history=False)["services"]
        if item["id"] == service_id
    )
    panel_ids = {offer["id"] for offer in panel["offers"]}

    assert first["offers_copied"] == 1
    assert first["services"] == 1
    assert first["service_ids"] == [service_id]
    assert second["offers_copied"] == 0
    assert copy["name"] == original["name"] == "Plus - Apple pay"
    assert copy["description"] == "Compte ChatGPT Plus"
    assert copy["description_ar"] == "وصف"
    assert copy["price"] == original["price"] == 12.5
    assert copy["note"] == "30 days"
    assert copy["period_days"] == 30
    assert copy["period_value"] == 1
    assert copy["period_unit"] == "months"
    assert copy["warranty_days"] == 7
    assert copy["site_description_fr"] == "Le même texte"
    assert copy["photo_file_id"] == "photo-1"
    assert copy["service_id"] == service_id
    assert copy["active"] == 0
    assert copy["supplier_provider"] == ""
    assert copy["supplier_product_id"] == ""
    assert copy["local_copy_of_offer_id"] == supplier_id
    assert original["active"] == 1
    assert original["supplier_provider"] == "upibot"
    assert original["supplier_product_id"] == "18"
    assert copy["id"] not in {offer["id"] for offer in db.list_catalog_offers()}
    assert db.is_bot_visible(copy) is False
    assert {supplier_id, local_id, copy["id"]} <= panel_ids
    assert mock_mongodb.offers.count_documents({"local_copy_of_offer_id": {"$exists": True}}) == 1
    assert mock_mongodb.inventory.count_documents({"offer_id": copy["id"]}) == 0
    assert mock_mongodb.reseller_products.find_one({"product_id": "18"})["local_offer_id"] == supplier_id


def test_startup_copies_supplier_offers_once_when_the_schema_is_older(mock_mongodb):
    service_id = db.add_service("Netflix", "🎬")
    supplier_id = db.add_offer(
        service_id, "Premium", 6.0, 2,
        description="Exact description",
        supplier_provider="vex", supplier_product_id="sku",
    )
    mock_mongodb.schema_meta.update_one({"_id": "schema"}, {"$set": {"version": 31}})
    db._schema_initialized = False

    db.init_db()

    copies = list(mock_mongodb.offers.find({"local_copy_of_offer_id": supplier_id}))
    assert len(copies) == 1
    assert copies[0]["name"] == "Premium"
    assert copies[0]["description"] == "Exact description"
    assert copies[0]["price"] == 6.0
    assert copies[0]["active"] == 0
    assert copies[0]["supplier_provider"] == ""
    assert mock_mongodb.offers.find_one({"id": supplier_id})["supplier_provider"] == "vex"
    assert mock_mongodb.schema_meta.find_one({"_id": "schema"})["version"] == 32
    audit = mock_mongodb.audit_events.find_one({"action": "catalog.supplier_offers_copied_local"})
    assert audit["details"]["offers_copied"] == 1
    assert audit["details"]["services"] == 1
