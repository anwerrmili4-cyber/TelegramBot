"""Storefront visit and interaction statistics for the site admin."""

from __future__ import annotations

import base64
import http.client
import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import api.webhook as webhook_module
import database as db
import railway_server
from app.domain import site_stats_service


def _visitor(number: int) -> str:
    return f"{number:032x}"


def _visit(path: str = "/", visitor: int = 1, **extra):
    return site_stats_service.record({
        "kind": "visit",
        "path": path,
        "visitor_id": _visitor(visitor),
        **extra,
    })


def _interaction(action: str, visitor: int = 1, **extra):
    return site_stats_service.record({
        "kind": "interaction",
        "action": action,
        "visitor_id": _visitor(visitor),
        **extra,
    })


def test_visit_and_interaction_counts_are_real_events(mock_mongodb):
    _visit("/")
    _visit("/boutique", visitor=2)
    _visit("/produit/12", visitor=1)
    _interaction("cart_add", visitor=2, offer_id=12, label="Netflix 1 mois", path="/produit/12")
    _interaction("search", label="netflix")
    _interaction("favorite", offer_id=12)

    result = site_stats_service.stats({})
    summary = result["summary"]
    assert summary["visits_today"] == 3
    assert summary["visits"] == 3
    assert summary["unique_today"] == 2
    assert summary["unique"] == 2
    assert summary["interactions_today"] == 3
    assert summary["interactions"] == 3
    assert summary["live_visitors"] == 2
    assert result["daily"][-1]["visits"] == 3
    assert result["daily"][-1]["visitors"] == 2
    assert result["daily"][-1]["interactions"] == 3
    assert len(result["daily"]) == 30
    assert {page["path"]: page["visits"] for page in result["popular_pages"]}["/"] == 1
    assert {page["path"]: page["visits"] for page in result["popular_pages"]}["/produit"] == 1
    product = result["popular_products"][0]
    assert product["offer_id"] == 12
    assert product["views"] == 1
    assert product["cart_adds"] == 1
    assert result["searches"] == [{"label": "netflix", "count": 1}]
    assert {item["action"]: item["count"] for item in result["actions"]}["cart_add"] == 1
    assert "visitor_id" not in result["recent"][0]
    assert result["recent"][0]["action_label"]


def test_funnel_sources_devices_and_heatmap(mock_mongodb):
    _visit("/", visitor=1, device="mobile", source="social")
    _visit("/produit/12", visitor=1, device="mobile")
    _visit("/", visitor=2, device="desktop", source="search")
    _visit("/boutique", visitor=3, device="mobile", source="direct")
    _interaction("cart_add", visitor=1, offer_id=12)
    _interaction("checkout", visitor=1)
    _interaction("order", visitor=1)
    _interaction("search", visitor=2, label="spotify")

    result = site_stats_service.stats({"days": ["7"]})

    assert [(step["key"], step["visitors"]) for step in result["funnel"]] == [
        ("visitors", 3), ("product", 1), ("cart_add", 1), ("checkout", 1), ("order", 1),
    ]
    sources = {row["key"]: row["count"] for row in result["sources"]}
    assert sources == {"social": 1, "search": 1, "direct": 1, "referral": 0}
    devices = {row["key"]: row["count"] for row in result["devices"]}
    assert devices == {"mobile": 2, "desktop": 1, "tablet": 0}
    assert len(result["heatmap"]) == 7
    assert all(len(row["hours"]) == 24 for row in result["heatmap"])
    assert sum(sum(row["hours"]) for row in result["heatmap"]) == 4
    summary = result["summary"]
    assert summary["entries"] == 3
    assert summary["engaged"] == 2
    assert summary["orders"] == 1
    assert summary["returning"] == 0
    assert result["previous"] == {"visits": 0, "unique": 0, "interactions": 0, "orders": 0}


def test_unknown_device_and_source_are_not_stored(mock_mongodb):
    _visit("/", device="smart-fridge", source="https://example.com/page")
    _interaction("search", label="netflix", source="social")
    rows = list(mock_mongodb.storefront_events.find({}, {"_id": 0, "device": 1, "source": 1}))
    assert rows == [{"device": "", "source": ""}, {"device": "", "source": ""}]


def test_previous_period_and_returning_visitors(mock_mongodb):
    now = int(datetime.now(UTC).timestamp())
    base = {"action": "page", "path": "/", "label": "", "offer_id": 0, "customer_id": None,
            "device": "", "source": ""}
    mock_mongodb.storefront_events.insert_many([
        {**base, "kind": "visit", "visitor_id": _visitor(5), "day": "2000-01-01",
         "created_at": now - 9 * 86400},
        {**base, "kind": "visit", "visitor_id": _visitor(6), "day": "2000-01-02",
         "created_at": now - 10 * 86400},
    ])
    _visit("/", visitor=7)
    mock_mongodb.storefront_events.insert_one({
        **base, "kind": "visit", "visitor_id": _visitor(7), "day": "2000-01-03", "created_at": now - 86400,
        "path": "/prix",
    })

    week = site_stats_service.stats({"days": ["7"]})
    assert week["previous"]["visits"] == 2
    assert week["previous"]["unique"] == 2
    assert week["summary"]["returning"] == 1
    assert site_stats_service.stats({"days": ["90"]})["previous"] is None


def test_identical_page_view_is_not_counted_twice(mock_mongodb):
    assert _visit("/boutique")["stored"] is True
    assert _visit("/boutique")["stored"] is False
    assert site_stats_service.stats({})["summary"]["visits"] == 1


def test_bot_interactions_are_not_site_visits(mock_mongodb):
    db.log_interaction(7, interaction_type="button", action="catalog")
    assert site_stats_service.stats({})["summary"]["visits"] == 0
    assert site_stats_service.stats({})["summary"]["interactions"] == 0


def test_old_events_stay_outside_the_window(mock_mongodb):
    _visit("/")
    old = datetime.now(UTC) - timedelta(days=40)
    mock_mongodb.storefront_events.insert_one({
        "kind": "visit",
        "action": "page",
        "path": "/prix",
        "label": "",
        "offer_id": 0,
        "visitor_id": _visitor(9),
        "customer_id": None,
        "day": "2000-01-01",
        "created_at": int(old.timestamp()),
        "created_at_date": old,
    })
    result = site_stats_service.stats({"days": ["7"]})
    assert result["summary"]["days"] == 7
    assert result["summary"]["visits"] == 1
    assert len(result["daily"]) == 7
    assert all(point["date"] != "2000-01-01" for point in result["daily"])


def test_email_like_labels_and_unknown_pages_are_rejected(mock_mongodb):
    _interaction("search", label="amine@example.com")
    stored = mock_mongodb.storefront_events.find_one({"action": "search"})
    assert stored["label"] == ""
    assert site_stats_service.stats({})["searches"] == []

    with pytest.raises(site_stats_service.SiteStatsError, match="Page inconnue"):
        _visit("/admin")
    with pytest.raises(site_stats_service.SiteStatsError, match="Interaction inconnue"):
        _interaction("message")
    with pytest.raises(site_stats_service.SiteStatsError, match="Visiteur invalide"):
        site_stats_service.record({"kind": "visit", "path": "/", "visitor_id": "nope"})


def test_customer_id_comes_from_the_session_not_the_payload(mock_mongodb, site_customer):
    customer = site_customer(name="Sana", email="sana@example.com")
    site_stats_service.record(
        {
            "kind": "visit",
            "path": "/mon-compte",
            "visitor_id": _visitor(3),
            "customer_id": 999,
        },
        customer_id=customer["id"],
    )
    stored = mock_mongodb.storefront_events.find_one({"visitor_id": _visitor(3)})
    assert stored["customer_id"] == customer["id"]
    assert site_stats_service.stats({})["recent"][0]["customer_name"] == "Sana"


def test_a_visitor_cannot_flood_events(mock_mongodb, monkeypatch):
    monkeypatch.setattr(site_stats_service, "MAX_EVENTS_PER_MINUTE", 1)
    _interaction("checkout")
    with pytest.raises(site_stats_service.SiteStatsError, match="Trop d'événements") as raised:
        _interaction("order")
    assert raised.value.status == 429


def test_product_name_prefers_the_site_title(mock_mongodb):
    service_id = db.add_service("Netflix", "🎬")
    offer_id = db.add_offer(service_id, "Netflix bot", 5, 1)
    db.get_conn().offers.update_one({"id": offer_id}, {"$set": {"site_name": "Netflix site"}})
    _visit(f"/produit/{offer_id}")
    assert site_stats_service.stats({})["popular_products"][0]["name"] == "Netflix site"


@contextmanager
def _running(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _post_event(port: int, payload: dict, headers: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", "/api/storefront/events", body=body, headers={
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        **(headers or {}),
    })
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw)


def test_storefront_records_events_and_admin_stats_require_a_session(monkeypatch, mock_mongodb):
    monkeypatch.setattr(webhook_module, "DASHBOARD_PASSWORD", "site-test")
    payload = {"kind": "visit", "path": "/", "visitor_id": _visitor(4)}

    with _running(railway_server.StorefrontHandler) as port:
        status, body = _post_event(port, payload)
        assert status == 200
        assert body["stored"] is True
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("OPTIONS", "/api/storefront/events")
        options = connection.getresponse()
        options.read()
        connection.close()
        assert options.status == 204
        assert options.headers["Access-Control-Allow-Origin"] == "*"
        blocked = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        blocked.request("GET", "/admin/api/site-stats")
        hidden = blocked.getresponse()
        hidden.read()
        blocked.close()
        assert hidden.status == 404

    token = base64.b64encode(b"admin:site-test").decode()
    with _running(webhook_module.handler) as port:
        base = f"http://127.0.0.1:{port}"
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(f"{base}/admin/api/site-stats", timeout=5)
        assert unauthorized.value.code == 401
        with urlopen(Request(f"{base}/admin/api/site-stats", headers={"Authorization": f"Basic {token}"}), timeout=5) as response:
            stats = json.load(response)
        assert stats["summary"]["visits_today"] == 1
        with urlopen(f"{base}/admin/site-stats", timeout=5) as page:
            assert b'id="root"' in page.read()

        status, rejected = _post_event(port, {"kind": "visit", "path": "/nope", "visitor_id": _visitor(4)})
        assert status == 400
        assert "Page inconnue" in rejected["error"]
