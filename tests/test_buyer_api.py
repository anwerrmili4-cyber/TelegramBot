"""Security, wallet, delivery, and HTTP tests for the public buyer API."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import database as db
from api.webhook import handler
from app.domain import buyer_api_service


@contextmanager
def running_server():
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _buyer_with_product(mock_mongodb, *, balance_cents=1000):
    db.upsert_user(42, "buyer", "Buyer")
    service_id = db.add_service("Accounts", "📦")
    offer_id = db.add_offer(service_id, "Premium Account", 5.0, 0)
    db.add_inventory_items(offer_id, ["user1:pass1", "user2:pass2"])
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": balance_cents})
    issued = buyer_api_service.create_key(42, label="Test buyer")
    key = buyer_api_service.authenticate(issued["key"], "127.0.0.1", "balance")
    return issued, key, offer_id


def test_key_is_returned_once_but_only_hash_is_stored(mock_mongodb):
    db.upsert_user(42, "buyer", "Buyer")

    issued = buyer_api_service.create_key(42, label="Partner")
    stored = mock_mongodb.buyer_api_keys.find_one({"id": issued["id"]})

    assert issued["key"].startswith("tgb_")
    assert len(issued["key"]) == 52
    assert stored["key_hash"]
    assert "key" not in stored
    assert issued["key"] not in str(stored)
    assert issued["key"] not in str(buyer_api_service.list_keys())


def test_user_can_self_issue_and_regenerate_a_single_active_key(mock_mongodb):
    db.upsert_user(42, "buyer", "Buyer")

    first = buyer_api_service.issue_user_key(42)
    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.issue_user_key(42)
    second = buyer_api_service.issue_user_key(42, regenerate=True)

    assert error.value.code == "API_KEY_ALREADY_EXISTS"
    assert first["key"] != second["key"]
    assert mock_mongodb.buyer_api_keys.count_documents({
        "user_id": 42, "active": True,
    }) == 1
    with pytest.raises(buyer_api_service.BuyerApiError):
        buyer_api_service.authenticate(first["key"], "127.0.0.1", "balance")
    assert buyer_api_service.authenticate(
        second["key"], "127.0.0.2", "balance"
    )["user_id"] == 42


def test_reseller_dashboard_is_scoped_and_sums_only_recent_successes(mock_mongodb):
    db.upsert_user(42, "buyer", "Buyer")
    db.upsert_user(99, "other", "Other")
    mock_mongodb.wallets.insert_one({"user_id": 42, "balance_cents": 1234})
    issued = buyer_api_service.issue_user_key(42)
    now = int(time.time())
    mock_mongodb.buyer_api_purchases.insert_many([
        {
            "buyer_key_id": issued["id"], "idempotency_key": "recent-order",
            "user_id": 42, "created_at": now, "response": {"success": True, "amount": 2.2},
        },
        {
            "buyer_key_id": issued["id"], "idempotency_key": "old-order",
            "user_id": 42, "created_at": now - (31 * 86400),
            "response": {"success": True, "amount": 9.0},
        },
        {
            "buyer_key_id": issued["id"], "idempotency_key": "failed-order",
            "user_id": 42, "created_at": now, "response": {"success": False, "amount": 7.0},
        },
        {
            "buyer_key_id": 999, "idempotency_key": "other-user",
            "user_id": 99, "created_at": now, "response": {"success": True, "amount": 50.0},
        },
    ])

    result = buyer_api_service.dashboard(42)

    assert result["active"] is True
    assert result["balance"] == 12.34
    assert result["total_orders"] == 2
    assert result["spend_30d"] == 2.2
    assert result["key"]["prefix"] == issued["prefix"]
    assert "key_hash" not in result["key"]
    assert issued["key"] not in str(result)


def test_catalog_and_balance_are_scoped_to_key_owner(mock_mongodb):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb)

    catalog = buyer_api_service.products(key)
    wallet = buyer_api_service.balance(key)

    assert catalog["success"] is True
    assert catalog["requester"]["chatId"] == 42
    assert catalog["products"][0]["_id"] == str(offer_id)
    assert catalog["products"][0]["walletPricing"] == 5.0
    assert catalog["products"][0]["stats"]["available"] == 2
    assert wallet["balance"] == 10.0
    assert wallet["walletCurrency"] == "USDT"


def test_purchase_charges_and_delivers_exactly_once(mock_mongodb):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb)

    status, first, replayed = buyer_api_service.purchase(
        key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-001",
    )
    replay_status, second, second_replayed = buyer_api_service.purchase(
        key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-001",
    )

    assert status == replay_status == 200
    assert replayed is False
    assert second_replayed is True
    assert first == second
    assert first["status"] == "delivered"
    assert first["deliveredAccounts"] == ["user1:pass1"]
    assert first["balance"] == 5.0
    assert mock_mongodb.orders.count_documents({"source": "buyer_api"}) == 1
    assert mock_mongodb.inventory.count_documents({"status": "delivered"}) == 1


def test_processing_purchase_becomes_available_through_status_and_replay(
    monkeypatch, mock_mongodb,
):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb)

    def defer_delivery(order_id, _user_id):
        mock_mongodb.orders.update_one(
            {"id": order_id},
            {"$set": {"status": "payment_confirmed", "updated_at": int(time.time())}},
        )
        return {"status": "confirmed_no_delivery", "delivered_content": None}

    monkeypatch.setattr(
        buyer_api_service.payment_service, "confirm_wallet_order", defer_delivery
    )
    status, pending, replayed = buyer_api_service.purchase(
        key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-pending-001",
    )

    assert status == 202
    assert replayed is False
    assert pending["status"] == "processing"
    assert pending["terminal"] is False

    order_id = int(pending["orderCode"].removeprefix("BM-"))
    delivered = buyer_api_service.order_service.manual_deliver_order(
        order_id, "ready-user:ready-pass"
    )
    current = buyer_api_service.order_status(key, pending["orderCode"])
    replay_status, replay, replayed = buyer_api_service.purchase(
        key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-pending-001",
    )

    assert delivered["status"] == "delivered"
    assert current["status"] == "delivered"
    assert current["terminal"] is True
    assert current["deliveredAccounts"] == ["ready-user:ready-pass"]
    assert replay_status == 200
    assert replayed is True
    assert replay == current


def test_order_status_is_scoped_to_the_key_that_created_it(mock_mongodb):
    _issued, owner_key, offer_id = _buyer_with_product(mock_mongodb)
    _status, purchase, _replayed = buyer_api_service.purchase(
        owner_key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-private-001",
    )
    db.upsert_user(99, "other", "Other")
    other_issued = buyer_api_service.create_key(99, label="Other buyer")
    other_key = buyer_api_service.authenticate(
        other_issued["key"], "127.0.0.99", "status"
    )

    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.order_status(other_key, purchase["orderCode"])

    assert error.value.status == 404
    assert error.value.code == "ORDER_NOT_FOUND"


def test_idempotency_key_cannot_be_reused_for_another_request(mock_mongodb):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb)
    buyer_api_service.purchase(
        key,
        product_id=str(offer_id),
        quantity=1,
        idempotency_key="partner-order-002",
    )

    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.purchase(
            key,
            product_id=str(offer_id),
            quantity=2,
            idempotency_key="partner-order-002",
        )

    assert error.value.status == 409
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_insufficient_wallet_never_consumes_inventory(mock_mongodb):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb, balance_cents=100)

    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.purchase(
            key,
            product_id=str(offer_id),
            quantity=1,
            idempotency_key="partner-order-003",
        )

    assert error.value.code == "INSUFFICIENT_BALANCE"
    assert mock_mongodb.orders.count_documents({}) == 0
    assert mock_mongodb.inventory.count_documents({"status": "available"}) == 2
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 100


def test_stock_race_refunds_wallet(monkeypatch, mock_mongodb):
    _issued, key, offer_id = _buyer_with_product(mock_mongodb)
    monkeypatch.setattr(
        "app.domain.buyer_api_service.payment_service.confirm_wallet_order",
        lambda *_args: {"status": "failed", "delivered_content": None},
    )

    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.purchase(
            key,
            product_id=str(offer_id),
            quantity=1,
            idempotency_key="partner-order-race-001",
        )

    assert error.value.code == "INSUFFICIENT_STOCK"
    assert mock_mongodb.wallets.find_one({"user_id": 42})["balance_cents"] == 1000
    assert mock_mongodb.orders.find_one({"source": "buyer_api"})["status"] == "cancelled"


def test_revoked_key_is_immediately_rejected(mock_mongodb):
    issued, _key, _offer_id = _buyer_with_product(mock_mongodb)

    assert buyer_api_service.revoke_key(issued["id"]) is True
    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.authenticate(issued["key"], "10.0.0.1", "products")

    assert error.value.status == 401
    assert error.value.code == "INVALID_API_KEY"


def test_endpoint_rate_limit_returns_retry_after(monkeypatch, mock_mongodb):
    issued, _key, _offer_id = _buyer_with_product(mock_mongodb)
    monkeypatch.setitem(buyer_api_service.RATE_LIMITS, "products_key", 1)

    buyer_api_service.authenticate(issued["key"], "10.0.0.2", "products")
    with pytest.raises(buyer_api_service.BuyerApiError) as error:
        buyer_api_service.authenticate(issued["key"], "10.0.0.2", "products")

    assert error.value.status == 429
    assert 1 <= error.value.retry_after <= 60


def test_swagger_and_openapi_are_public():
    with running_server() as base_url:
        with urlopen(f"{base_url}/api/swagger", timeout=5) as response:
            swagger = response.read().decode()
        with urlopen(f"{base_url}/api/openapi.json", timeout=5) as response:
            spec = json.load(response)

    assert "SwaggerUIBundle" in swagger
    assert spec["info"]["title"] == "BlackMarket Buyer API"
    assert "/api/v2/telegram-buyer/purchase" in spec["paths"]
    assert "/api/v2/telegram-buyer/orders/{orderCode}" in spec["paths"]
    assert spec["components"]["securitySchemes"]["BuyerKeyAuth"]["scheme"] == "bearer"
    purchase_schema = spec["components"]["schemas"]["PurchaseRequest"]
    assert "key" not in purchase_schema["properties"]


def test_http_catalog_balance_and_idempotent_purchase(mock_mongodb):
    issued, _key, offer_id = _buyer_with_product(mock_mongodb)
    authorization = {"Authorization": f"Bearer {issued['key']}"}

    with running_server() as base_url:
        with urlopen(
            Request(
                f"{base_url}/api/v2/telegram-buyer/products",
                headers=authorization,
            ),
            timeout=5,
        ) as response:
            catalog = json.load(response)
        with urlopen(
            Request(
                f"{base_url}/api/v2/telegram-buyer/balance",
                headers=authorization,
            ),
            timeout=5,
        ) as response:
            wallet = json.load(response)

        body = json.dumps({
            "product_id": str(offer_id),
            "quantity": 1,
        }).encode()
        request = Request(
            f"{base_url}/api/v2/telegram-buyer/purchase",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "http-partner-order-001",
                **authorization,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            purchase = json.load(response)
            replay_header = response.headers["Idempotent-Replayed"]
        with urlopen(request, timeout=5) as response:
            replay = json.load(response)
            second_replay_header = response.headers["Idempotent-Replayed"]

    assert catalog["products"][0]["_id"] == str(offer_id)
    assert wallet["balance"] == 10.0
    assert purchase == replay
    assert replay_header == "false"
    assert second_replay_header == "true"


def test_http_order_status_returns_delivery_for_authenticated_owner(mock_mongodb):
    issued, _key, offer_id = _buyer_with_product(mock_mongodb)
    body = json.dumps({
        "product_id": str(offer_id),
        "quantity": 1,
    }).encode()

    with running_server() as base_url:
        request = Request(
            f"{base_url}/api/v2/telegram-buyer/purchase",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "http-order-status-001",
                "Authorization": f"Bearer {issued['key']}",
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            purchase = json.load(response)
        with urlopen(
            Request(
                f"{base_url}/api/v2/telegram-buyer/orders/{purchase['orderCode']}",
                headers={"Authorization": f"Bearer {issued['key']}"},
            ),
            timeout=5,
        ) as response:
            status = json.load(response)
            cache_control = response.headers["Cache-Control"]

    assert status["status"] == "delivered"
    assert status["terminal"] is True
    assert status["deliveredAccounts"] == ["user1:pass1"]
    assert cache_control == "no-store"


def test_http_invalid_key_is_safe(mock_mongodb):
    with running_server() as base_url:
        try:
            urlopen(
                Request(
                    f"{base_url}/api/v2/telegram-buyer/balance",
                    headers={"Authorization": f"Bearer tgb_{'0' * 48}"},
                ),
                timeout=5,
            )
        except HTTPError as exc:
            payload = json.load(exc)
            assert exc.code == 401
        else:
            raise AssertionError("Invalid buyer key was accepted")

    assert payload == {
        "success": False,
        "code": "INVALID_API_KEY",
        "message": "Invalid API key.",
    }


def test_http_rejects_legacy_query_and_body_credentials(mock_mongodb):
    issued, _key, offer_id = _buyer_with_product(mock_mongodb)

    with running_server() as base_url:
        legacy_urls = [
            f"{base_url}/api/v2/telegram-buyer/balance?key={issued['key']}",
        ]
        purchase = Request(
            f"{base_url}/api/v2/telegram-buyer/purchase",
            data=json.dumps({
                "key": issued["key"],
                "product_id": str(offer_id),
                "quantity": 1,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "legacy-body-key-001",
            },
            method="POST",
        )
        for request in [*legacy_urls, purchase]:
            with pytest.raises(HTTPError) as error:
                urlopen(request, timeout=5)
            payload = json.load(error.value)
            assert error.value.code == 400
            assert payload["code"] == "API_KEY_LOCATION_NOT_ALLOWED"

    assert mock_mongodb.orders.count_documents({"source": "buyer_api"}) == 0
