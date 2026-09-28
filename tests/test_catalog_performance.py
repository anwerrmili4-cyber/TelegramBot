from unittest.mock import Mock

import database as db
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
