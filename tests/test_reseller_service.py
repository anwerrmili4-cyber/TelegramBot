"""MailReader catalog integration and local resale configuration."""

from __future__ import annotations

import json
import uuid
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

import database as db
from app.domain import reseller_service


def _supplier_payload():
    return {
        "ok": True,
        "reseller": {"name": "Demo Reseller", "balance": "42.50"},
        "products": [
            {
                "id": "mail_100",
                "name": "Mailbox 100",
                "wholesale_price": "2.25",
                "currency": "USDT",
                "description": "Automatic mailbox delivery",
                "delivery_instruction": "Use the supplied credentials",
                "stock": 12,
            },
            {
                "id": "mail_empty",
                "name": "Mailbox Empty",
                "wholesale_price": "1.00",
                "currency": "USDT",
                "stock": 0,
            },
        ],
    }


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"delivery": ["mail:user:pass:https://mail.test/read#code"]}, ["mail:user:pass:https://mail.test/read#code"]),
        ({"result": {"items": ["shamekh:user:pass"]}}, ["shamekh:user:pass"]),
        ({"data": {"credentials": "kakao:user:pass"}}, ["kakao:user:pass"]),
        ({"data": "vex:user:pass"}, ["vex:user:pass"]),
        ({"deliveredAccounts": [{
            "user": "canboso@example.com",
            "password": "secret#1",
            "recoveryUrl": "https://canboso.test/recover?a=1&b=#code",
        }]}, [
            "canboso@example.com:secret#1:https://canboso.test/recover?a=1&b=#code",
        ]),
        ({"response": {"payload": {"delivered_accounts": ["nested:user:pass"]}}}, ["nested:user:pass"]),
        ({"delivered_codes": ["CGPT-CODE-1"]}, ["CGPT-CODE-1"]),
        ({"delivered_keys": ["UPIBOT-KEY-1"]}, ["UPIBOT-KEY-1"]),
        ({"delivery": {"accounts": [{
            "user": "canboso-current@example.com",
            "password": "current-secret",
            "verifyEmail": "verify@example.com",
            "expiryText": "30 days",
            "otherInfo": "keep this",
        }]}}, [
            "canboso-current@example.com:current-secret:verify@example.com:30 days:keep this",
        ]),
        ({"data": {"items": [{
            "productName": "SLOT CANVA EDU 1 NĂM",
            "accounts": ["account|password|2fa...."],
        }]}}, [
            "account|password|2fa....",
        ]),
    ],
)
def test_delivery_extractor_supports_every_supplier_response_shape(payload, expected):
    assert reseller_service._delivery_items(payload) == expected


def test_catalog_overlays_admin_selection(monkeypatch, mock_mongodb):
    monkeypatch.setattr(reseller_service, "_request_json", lambda _path: _supplier_payload())
    db.save_reseller_product_config(
        "mailreader",
        "mail_100",
        name="Mailbox 100",
        wholesale_price=2.25,
        currency="USDT",
        retail_price=4.5,
        enabled=True,
    )

    result = reseller_service.catalog()

    assert result["supplier_name"] == "Demo Reseller"
    assert result["balance"] == 42.5
    assert result["selected_count"] == 1
    assert result["used_count"] == 1
    assert result["unused_count"] == 1
    assert result["products"][0]["enabled"] is True
    assert result["products"][0]["retail_price"] == 4.5
    assert result["products"][0]["profit"] == 2.25
    assert result["products"][1]["enabled"] is False


def test_enabled_product_requires_profitable_retail_price(mock_mongodb):
    with pytest.raises(ValueError, match="supérieur"):
        reseller_service.save_product(
            "mail_100",
            name="Mailbox 100",
            wholesale_price=2.25,
            currency="USDT",
            retail_price=2.25,
            enabled=True,
        )


def test_api_key_is_required_without_exposing_a_secret(monkeypatch):
    monkeypatch.setattr(reseller_service, "MAILREADER_API_KEY", "")

    with pytest.raises(reseller_service.ResellerApiError, match="HP_MAILREADER_API_KEY"):
        reseller_service._request_json("/api/reseller/products")


def test_mailreader_preflight_refreshes_balance_and_rejects_stale_stock(monkeypatch):
    payloads = [{
        "ok": True,
        "reseller": {"balance": "42.50"},
        "products": [{"id": "coursera-premium-12m", "stock": 0}],
    }]
    monkeypatch.setattr(reseller_service, "_request_json", lambda path: payloads.pop(0))

    with pytest.raises(reseller_service.ResellerOrderNotCreatedError, match="Stock MailReader insuffisant"):
        reseller_service._mailreader_preflight_purchase(
            {"supplier_product_id": "coursera-premium-12m", "wholesale_price": 3},
            1,
        )


def test_mailreader_http_error_keeps_provider_reason(monkeypatch):
    error = HTTPError(
        "https://api.mailreader.tech/api/reseller?action=order",
        409,
        "Conflict",
        {},
        BytesIO(b'{"error":"insufficient stock"}'),
    )
    monkeypatch.setattr(reseller_service, "MAILREADER_API_KEY", "test-key")
    monkeypatch.setattr(reseller_service, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(reseller_service.ResellerOrderNotCreatedError, match="insufficient stock"):
        reseller_service._request_json(
            "/api/reseller?action=order",
            method="POST",
            body={"product_id": "coursera-premium-12m", "quantity": 1},
        )


def test_cgpt_active_client_sends_bearer_auth_and_idempotency(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"order_id": 42, "delivered_codes": ["CODE"]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(reseller_service, "CGPT_ACTIVE_API_KEY", "rsk_test")
    monkeypatch.setattr(reseller_service, "CGPT_ACTIVE_API_BASE", "https://supplier.example/api")
    monkeypatch.setattr(reseller_service, "urlopen", fake_urlopen)

    result = reseller_service._cgpt_active_request_json(
        "/v1/orders",
        method="POST",
        body={"product_id": 7, "quantity": 2},
        idempotency_key="550e8400-e29b-41d4-a716-446655440000",
    )

    assert result["delivered_codes"] == ["CODE"]
    request, timeout = requests[0]
    assert timeout == 20
    assert request.full_url == "https://supplier.example/api/v1/orders"
    assert request.get_header("Authorization") == "Bearer rsk_test"
    assert request.get_header("Idempotency-key") == "550e8400-e29b-41d4-a716-446655440000"
    assert json.loads(request.data) == {"product_id": 7, "quantity": 2}


def test_canboso_key_and_idempotency_are_sent_in_documented_fields(monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({"success": True})

    monkeypatch.setattr(reseller_service, "CANBOSO_API_KEY", "test-buyer-key")
    monkeypatch.setattr(reseller_service, "GPT_CHEAP_API_KEY", "test-gpt-cheap-key")
    monkeypatch.setattr(reseller_service, "SHOP_CRON_API_KEY", "test-shop-cron-key")
    monkeypatch.setattr(
        reseller_service,
        "CANBOSO_API_BASE",
        "https://supplier.example/api/v2/telegram-buyer",
    )
    monkeypatch.setattr(reseller_service, "urlopen", fake_urlopen)

    reseller_service._canboso_request_json("/products")
    reseller_service._canboso_request_json(
        "/purchase",
        method="POST",
        body={"product_id": "sku-1", "quantity": 2},
        idempotency_key="BM-123",
    )
    reseller_service._canboso_request_json(
        "/products",
        provider=reseller_service.GPT_CHEAP_PROVIDER,
    )
    reseller_service._canboso_request_json(
        "/products",
        provider=reseller_service.SHOP_CRON_PROVIDER,
    )

    get_request, get_timeout = requests[0]
    assert get_timeout == 20
    assert parse_qs(urlsplit(get_request.full_url).query) == {"key": ["test-buyer-key"]}
    assert get_request.data is None

    post_request, post_timeout = requests[1]
    assert post_timeout == 20
    assert urlsplit(post_request.full_url).query == ""
    assert post_request.get_header("Idempotency-key") == "BM-123"
    assert json.loads(post_request.data) == {
        "key": "test-buyer-key",
        "product_id": "sku-1",
        "quantity": 2,
    }

    gpt_cheap_request, gpt_cheap_timeout = requests[2]
    assert gpt_cheap_timeout == 20
    assert parse_qs(urlsplit(gpt_cheap_request.full_url).query) == {
        "key": ["test-gpt-cheap-key"]
    }

    shop_cron_request, shop_cron_timeout = requests[3]
    assert shop_cron_timeout == 20
    assert parse_qs(urlsplit(shop_cron_request.full_url).query) == {
        "key": ["test-shop-cron-key"]
    }


def test_publish_product_creates_native_bot_service_and_offer(monkeypatch, mock_mongodb):
    monkeypatch.setattr(reseller_service, "_request_json", lambda _path: _supplier_payload())

    saved = reseller_service.save_catalog_product(
        "mail_100",
        retail_price=4.5,
        enabled=True,
        new_service_name="Boîtes mail",
        service_emoji="📧",
        display_name="Mailbox Premium",
        description="Livraison automatique",
        warranty="Remplacement sous 24 heures",
        delivery_delay="Instantané",
        sort_order=7,
        low_stock_threshold=3,
    )

    service = db.get_service(saved["service_id"])
    offer = db.get_offer(saved["local_offer_id"])
    assert service["name"] == "Boîtes mail"
    assert service["emoji"] == "📧"
    assert offer["name"] == "Mailbox Premium"
    assert offer["note"] == "Remplacement sous 24 heures"
    assert offer["service_id"] == service["id"]
    assert offer["supplier_provider"] == "mailreader"
    assert offer["supplier_product_id"] == "mail_100"
    assert offer["stock"] == 12
    assert offer["price"] == 4.5
    assert offer["active"] == 1
    assert offer["sort_order"] == 7
    assert offer["custom_emoji_id"] == ""
    assert saved["warranty"] == "Remplacement sous 24 heures"


def test_republishing_updates_same_native_offer(monkeypatch, mock_mongodb):
    monkeypatch.setattr(reseller_service, "_request_json", lambda _path: _supplier_payload())
    service_id = db.add_service("Emails", "📧")
    first = reseller_service.save_catalog_product(
        "mail_100", retail_price=4.5, enabled=True, service_id=service_id
    )
    second = reseller_service.save_catalog_product(
        "mail_100",
        retail_price=5.25,
        enabled=True,
        service_id=service_id,
        display_name="Mailbox Pro",
    )

    assert second["local_offer_id"] == first["local_offer_id"]
    assert mock_mongodb.offers.count_documents(
        {"supplier_provider": "mailreader", "supplier_product_id": "mail_100"}
    ) == 1
    assert db.get_offer(first["local_offer_id"])["price"] == 5.25


def test_paid_supplier_order_is_delivered_idempotently(monkeypatch, mock_mongodb):
    service_id = db.add_service("Emails", "📧")
    offer_id = db.add_offer(
        service_id,
        "Mailbox",
        4.5,
        10,
        supplier_provider="mailreader",
        supplier_product_id="mail_100",
    )
    mock_mongodb.orders.insert_one({
        "id": 91,
        "user_id": 123,
        "offer_id": offer_id,
        "qty": 2,
        "status": "payment_confirmed",
    })
    calls = []

    def fake_request(path, *, method="GET", body=None):
        calls.append((path, method, body))
        return {"order": {"id": "supplier-1"}, "delivery_items": ["user:a", "user:b"]}

    monkeypatch.setattr(reseller_service, "_request_json", fake_request)

    assert reseller_service.fulfill_paid_order(91) == ["user:a", "user:b"]
    assert reseller_service.fulfill_paid_order(91) == ["user:a", "user:b"]
    assert [call[0] for call in calls] == [
        "/api/reseller/products",
        "/api/reseller?action=order",
    ]
    assert calls[1][1] == "POST"
    assert calls[1][2]["external_order_id"] == "BM-91"
    assert db.get_order(91)["status"] == "delivered"
    assert mock_mongodb.inventory.count_documents({"delivered_order_id": 91}) == 2
    assert "user:a" not in str(mock_mongodb.reseller_fulfillments.find_one({"order_id": 91}))


def test_mailreader_delivery_array_is_forwarded_without_manual_fallback(
    monkeypatch, mock_mongodb,
):
    service_id = db.add_service("Coursera", "🎓")
    offer_id = db.add_offer(
        service_id,
        "Coursera account",
        2.0,
        10,
        supplier_provider="mailreader",
        supplier_product_id="coursera-1",
    )
    mock_mongodb.orders.insert_one({
        "id": 222,
        "user_id": 123,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })
    account = (
        "65. EloiseQuattrocchi101261@outlook.com:pasqq74516:"
        "https://www.mailreader.tech/read_code?uuid=e538cdf9-b01b-0ef4-6982-fd42c96cf98a"
    )
    monkeypatch.setattr(
        reseller_service,
        "_request_json",
        lambda *_args, **_kwargs: {
            "success": True,
            "order": {"id": "supplier-BM-222"},
            "delivery": [account],
        },
    )

    assert reseller_service.fulfill_paid_order(222) == [account]
    assert db.get_order(222)["status"] == "delivered"
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 222})
    assert fulfillment["status"] == "completed"
    assert fulfillment["supplier_order_id"] == "supplier-BM-222"


def test_created_supplier_order_without_delivery_is_never_purchased_twice(
    monkeypatch, mock_mongodb,
):
    service_id = db.add_service("API", "🔌")
    offer_id = db.add_offer(
        service_id,
        "API account",
        2.0,
        10,
        supplier_provider="mailreader",
        supplier_product_id="api-1",
    )
    mock_mongodb.orders.insert_one({
        "id": 223,
        "user_id": 123,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })
    calls = []

    def fake_request(*_args, **_kwargs):
        calls.append(True)
        return {"success": True, "order": {"id": "supplier-223"}, "delivery": []}

    monkeypatch.setattr(reseller_service, "_request_json", fake_request)

    with pytest.raises(reseller_service.ResellerApiError, match="pas encore disponible"):
        reseller_service.fulfill_paid_order(223)
    with pytest.raises(reseller_service.ResellerApiError, match="Aucun second achat"):
        reseller_service.fulfill_paid_order(223)

    assert len(calls) == 2  # fresh balance/stock read, then the single purchase POST
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 223})
    assert fulfillment["status"] == "delivery_pending"
    assert fulfillment["supplier_order_id"] == "supplier-223"


def test_shamekh_catalog_maps_products_balance_and_stock(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/api/me":
            return {"ok": True, "user": {"balance": 18.75}}
        return {
            "ok": True,
            "products": [{
                "id": 7,
                "name_en": "Premium Account",
                "price": 0.71,
                "stock_count": 97,
            }],
        }

    monkeypatch.setattr(reseller_service, "_shamekh_request_json", fake_request)

    result = reseller_service.catalog("shamekh")

    assert result["provider"] == "shamekh"
    assert result["supplier_name"] == "Shamekh’s bot"
    assert result["balance"] == 18.75
    assert result["products"][0]["id"] == "7"
    assert result["products"][0]["wholesale_price"] == 0.71
    assert result["products"][0]["stock"] == 97


def test_shamekh_product_publishes_and_delivers(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/api/me":
            return {"ok": True, "user": {"balance": 18.75}}
        if path == "/api/buy":
            return {
                "ok": True,
                "transaction_id": "tx_supplier_1",
                "items": ["delivered-account"],
            }
        return {
            "ok": True,
            "products": [{
                "id": 7,
                "name_en": "Premium Account",
                "price": 0.71,
                "stock_count": 97,
            }],
        }

    monkeypatch.setattr(reseller_service, "_shamekh_request_json", fake_request)
    service_id = db.add_service("Premium", "⭐")
    saved = reseller_service.save_catalog_product(
        "7",
        provider="shamekh",
        retail_price=1.5,
        enabled=True,
        service_id=service_id,
        warranty="24 hours",
    )
    offer = db.get_offer(saved["local_offer_id"])
    mock_mongodb.orders.insert_one({
        "id": 92,
        "user_id": 123,
        "offer_id": offer["id"],
        "qty": 1,
        "status": "payment_confirmed",
    })

    assert offer["supplier_provider"] == "shamekh"
    assert reseller_service.fulfill_paid_order(92) == ["delivered-account"]
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 92})
    assert fulfillment["supplier_order_id"] == "tx_supplier_1"
    assert fulfillment["status"] == "completed"
    assert db.get_order(92)["status"] == "delivered"


def test_kakao_catalog_maps_balance_source_and_products(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/api/balance":
            return {"success": True, "balance": 62.77}
        return {
            "success": True,
            "products": [{
                "id": "kakao-1",
                "name": "Digital Account",
                "price": 1.23,
                "stock": 14,
                "source": "Kakao inventory",
            }],
        }

    monkeypatch.setattr(reseller_service, "_kakao_request_json", fake_request)

    result = reseller_service.catalog("kakao")

    assert result["provider"] == "kakao"
    assert result["supplier_name"] == "Kakao Shop"
    assert result["balance"] == 62.77
    assert result["products"][0]["id"] == "kakao-1"
    assert result["products"][0]["wholesale_price"] == 1.23
    assert result["products"][0]["stock"] == 14
    assert result["products"][0]["description"] == "Source : Kakao inventory"


def test_kakao_purchase_uses_external_id_and_is_idempotent(monkeypatch, mock_mongodb):
    calls = []

    def fake_request(path, **kwargs):
        if path == "/api/balance":
            return {"success": True, "balance": 62.77}
        if path == "/api/purchase":
            calls.append(kwargs["body"])
            return {
                "success": True,
                "order_id": 555,
                "credentials": "user:pass",
                "external_order_id": kwargs["body"]["external_order_id"],
            }
        return {
            "success": True,
            "products": [{
                "id": "kakao-1",
                "name": "Digital Account",
                "price": 1.23,
                "stock": 14,
                "source": "Kakao inventory",
            }],
        }

    monkeypatch.setattr(reseller_service, "_kakao_request_json", fake_request)
    service_id = db.add_service("Kakao", "🛍️")
    saved = reseller_service.save_catalog_product(
        "kakao-1",
        provider="kakao",
        retail_price=2.5,
        enabled=True,
        service_id=service_id,
    )
    offer = db.get_offer(saved["local_offer_id"])
    mock_mongodb.orders.insert_one({
        "id": 93,
        "user_id": 123,
        "offer_id": offer["id"],
        "qty": 1,
        "status": "payment_confirmed",
    })

    assert reseller_service.fulfill_paid_order(93) == ["user:pass"]
    assert reseller_service.fulfill_paid_order(93) == ["user:pass"]
    assert calls == [{
        "product_id": "kakao-1",
        "quantity": 1,
        "external_order_id": "BM-93",
    }]
    assert db.get_order(93)["status"] == "delivered"


def test_vex_catalog_maps_balance_stock_and_manual_delivery(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "?action=balance":
            return {"ok": True, "balance": 25.4}
        return {
            "ok": True,
            "products": [{
                "id": "5a7576cb-941f-4fb6-b56d-0a2946574650",
                "name": "VEX Account",
                "price": 0.85,
                "stock": 11,
                "manual_delivery": True,
            }],
        }

    monkeypatch.setattr(reseller_service, "_vex_request_json", fake_request)

    result = reseller_service.catalog("vex")

    assert result["provider"] == "vex"
    assert result["supplier_name"] == "VEX Reseller"
    assert result["balance"] == 25.4
    assert result["products"][0]["wholesale_price"] == 0.85
    assert result["products"][0]["stock"] == 11
    assert result["products"][0]["manual_delivery"] is True


def test_vex_order_is_delivered_and_replayed_without_double_charge(monkeypatch, mock_mongodb):
    calls = []
    product_id = "5a7576cb-941f-4fb6-b56d-0a2946574650"

    def fake_request(path, **kwargs):
        if path == "?action=balance":
            return {"ok": True, "balance": 25.4}
        if path == "?action=order":
            calls.append(kwargs["body"])
            return {
                "status": "delivered",
                "order_id": "VEX-12345678",
                "data": "vex-user:vex-pass",
                "amount": 0.85,
            }
        return {
            "ok": True,
            "products": [{
                "id": product_id,
                "name": "VEX Account",
                "price": 0.85,
                "stock": 11,
                "manual_delivery": False,
            }],
        }

    monkeypatch.setattr(reseller_service, "_vex_request_json", fake_request)
    service_id = db.add_service("VEX", "📦")
    saved = reseller_service.save_catalog_product(
        product_id,
        provider="vex",
        retail_price=1.75,
        enabled=True,
        service_id=service_id,
    )
    offer = db.get_offer(saved["local_offer_id"])
    mock_mongodb.orders.insert_one({
        "id": 94,
        "user_id": 123,
        "offer_id": offer["id"],
        "qty": 1,
        "status": "payment_confirmed",
    })

    assert offer["supplier_provider"] == "vex"
    assert reseller_service.fulfill_paid_order(94) == ["vex-user:vex-pass"]
    assert reseller_service.fulfill_paid_order(94) == ["vex-user:vex-pass"]
    assert calls == [{
        "product_id": product_id,
        "quantity": 1,
        "external_order_id": "BM-94",
    }]
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 94})
    assert fulfillment["supplier_order_id"] == "VEX-12345678"


def test_canboso_catalog_maps_wallet_products_and_slot_delivery(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/balance":
            return {
                "success": True,
                "walletCurrency": "VND",
                "balance": 250000,
                "usdtBalance": 0,
            }
        return {
            "success": True,
            "products": [{
                "_id": "canboso-1",
                "product_name": "ChatGPT Plus",
                "description": "Instant account",
                "usdPricing": 1.85,
                "requiresCustomerEmail": False,
                "stats": {"available": 60},
            }, {
                "_id": "canboso-slot",
                "product_name": "Business Slot",
                "usdPricing": 3.5,
                "requiresCustomerEmail": True,
                "stats": {"available": 10},
            }],
        }

    monkeypatch.setattr(reseller_service, "_canboso_request_json", fake_request)

    result = reseller_service.catalog("canboso")

    assert result["provider"] == "canboso"
    assert result["supplier_name"] == "Piggy AI"
    assert result["balance"] == 250000
    assert result["currency"] == "VND"
    assert result["products"][0]["id"] == "canboso-1"
    assert result["products"][0]["name"] == "ChatGPT Plus"
    assert result["products"][0]["wholesale_price"] == 1.85
    assert result["products"][0]["currency"] == "USDT"
    assert result["products"][0]["stock"] == 60
    assert result["products"][0]["manual_delivery"] is False
    assert result["products"][1]["manual_delivery"] is True


def test_canboso_catalog_maps_current_live_product_schema(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/balance":
            return {
                "success": True,
                "walletCurrency": "USD",
                "balance": 12.5,
            }
        return {
            "success": True,
            "walletCurrency": "USD",
            "products": [{
                "productId": "live-account-1",
                "name": "Premium account",
                "description": "Instant account",
                "productType": "account",
                "price": {"amount": 0.05, "currency": "USD", "text": "$0.05"},
                "availability": {"available": 41, "sold": 513},
            }, {
                "productId": "live-slot-1",
                "name": "Business slot",
                "productType": "slot",
                "price": {"amount": 3.5, "currency": "USD", "text": "$3.50"},
                "availability": {"available": 10, "sold": 2},
                "purchaseRequirements": {"customerEmail": True, "quantityFixed": 1},
            }],
        }

    monkeypatch.setattr(reseller_service, "_canboso_request_json", fake_request)

    result = reseller_service.catalog("canboso")

    assert len(result["products"]) == 2
    assert result["products"][0]["id"] == "live-account-1"
    assert result["products"][0]["wholesale_price"] == 0.05
    assert result["products"][0]["currency"] == "USDT"
    assert result["products"][0]["stock"] == 41
    assert result["products"][0]["manual_delivery"] is False
    assert result["products"][1]["manual_delivery"] is True


def test_canboso_shops_use_separate_wallet_keys(monkeypatch, mock_mongodb):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs.get("provider", "canboso")))
        if path == "/balance":
            return {"success": True, "walletCurrency": "USD", "balance": 12.5}
        return {
            "success": True,
            "products": [{
                "productId": "account-1",
                "name": "Premium account",
                "productType": "account",
                "price": {"amount": 1.0, "currency": "USD"},
                "availability": {"available": 5},
            }],
        }

    monkeypatch.setattr(reseller_service, "CANBOSO_API_KEY", "piggy-key")
    monkeypatch.setattr(reseller_service, "GPT_CHEAP_API_KEY", "gpt-cheap-key")
    monkeypatch.setattr(reseller_service, "SHOP_CRON_API_KEY", "shop-cron-key")
    monkeypatch.setattr(reseller_service, "_canboso_request_json", fake_request)

    piggy = reseller_service.catalog("canboso")
    cheap = reseller_service.catalog("gpt_cheap")
    shop_cron = reseller_service.catalog("shop_cron")

    assert piggy["supplier_name"] == "Piggy AI"
    assert cheap["supplier_name"] == "GPT Cheap"
    assert shop_cron["supplier_name"] == "Shop Cron"
    assert calls == [
        ("/products", "canboso"),
        ("/balance", "canboso"),
        ("/products", "gpt_cheap"),
        ("/balance", "gpt_cheap"),
        ("/products", "shop_cron"),
        ("/balance", "shop_cron"),
    ]


def test_canboso_purchase_uses_stable_idempotency_key(monkeypatch, mock_mongodb):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs))
        return {
            "success": True,
            "order": {
                "orderCode": "ORDER1A2B3C4D5E",
                "status": "completed",
            },
            "delivery": {
                "accounts": [{
                    "user": "account@example.com",
                    "password": "supplier-secret",
                    "verifyEmail": "verify@example.com",
                }],
            },
        }

    monkeypatch.setattr(reseller_service, "_canboso_request_json", fake_request)
    service_id = db.add_service("Canboso", "📦")
    offer_id = db.add_offer(
        service_id,
        "Canboso Account",
        3.0,
        5,
        supplier_provider="canboso",
        supplier_product_id="canboso-1",
    )
    mock_mongodb.orders.insert_one({
        "id": 95,
        "user_id": 123,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })

    first = reseller_service.fulfill_paid_order(95)
    second = reseller_service.fulfill_paid_order(95)

    assert first == second
    assert len(first) == 1
    assert "supplier-secret" in first[0]
    assert calls == [(
        "/purchase",
        {
            "method": "POST",
            "body": {"product_id": "canboso-1", "quantity": 1},
            "idempotency_key": "BM-95",
        },
    )]
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 95})
    assert fulfillment["supplier_order_id"] == "ORDER1A2B3C4D5E"
    assert "supplier-secret" not in str(fulfillment)


def test_upibot_client_uses_shop_key_header(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true,"products":[]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(reseller_service, "UPIBOT_API_KEY", "sk_shop_test")
    monkeypatch.setattr(reseller_service, "UPIBOT_API_BASE", "https://supplier.example/shop-api/v1")
    monkeypatch.setattr(reseller_service, "urlopen", fake_urlopen)

    reseller_service._upibot_request_json("/products")

    request, timeout = requests[0]
    assert timeout == 20
    assert request.full_url == "https://supplier.example/shop-api/v1/products"
    assert request.get_header("X-shop-api-key") == "sk_shop_test"
    assert request.get_header("Authorization") is None


def test_upibot_catalog_maps_deposit_balance_and_products(monkeypatch, mock_mongodb):
    def fake_request(path, **_kwargs):
        if path == "/me":
            return {"ok": True, "deposit_balance": 12.5}
        return {
            "ok": True,
            "products": [{
                "id": 18,
                "product_id": 18,
                "name": "Email Outlook/Hotmail Account",
                "sell_price": 0.04,
                "in_stock": True,
                "stock_count": 94,
            }],
        }

    monkeypatch.setattr(reseller_service, "_upibot_request_json", fake_request)

    result = reseller_service.catalog("upibot")

    assert result["provider"] == "upibot"
    assert result["supplier_name"] == "UPIBot Shop"
    assert result["balance"] == 12.5
    assert result["currency"] == "USDT"
    assert result["products"][0]["id"] == "18"
    assert result["products"][0]["wholesale_price"] == 0.04
    assert result["products"][0]["stock"] == 94


def test_upibot_purchase_is_idempotent_and_extracts_delivered_keys(
    monkeypatch, mock_mongodb,
):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs))
        return {
            "ok": True,
            "order": {"id": 123, "status": "delivered"},
            "delivered_keys": [
                "email1@example.com|password|token",
                "email2@example.com|password|token",
            ],
        }

    monkeypatch.setattr(reseller_service, "_upibot_request_json", fake_request)
    offer_id = db.add_offer(
        db.add_service("UPIBot", "📦"),
        "Outlook account",
        0.08,
        2,
        supplier_provider="upibot",
        supplier_product_id="18",
    )
    mock_mongodb.orders.insert_one({
        "id": 98,
        "user_id": 456,
        "offer_id": offer_id,
        "qty": 2,
        "status": "payment_confirmed",
    })

    first = reseller_service.fulfill_paid_order(98)
    second = reseller_service.fulfill_paid_order(98)

    assert first == second == [
        "email1@example.com|password|token",
        "email2@example.com|password|token",
    ]
    assert calls == [("/orders", {
        "method": "POST",
        "body": {
            "product_id": 18,
            "quantity": 2,
            "customer_name": "telegram_user_456",
            "idempotency_key": "BM-98",
        },
    })]


def test_cgpt_active_catalog_maps_cdk_products_and_skips_input_products(
    monkeypatch, mock_mongodb,
):
    def fake_request(path, **_kwargs):
        if path == "/v1/me":
            return {"name": "Demo reseller", "balance": "12.500000"}
        return {
            "products": [{
                "id": 1,
                "name": "Perplexity PRO",
                "description": "Instant activation code",
                "product_type": "cdk",
                "your_unit_price": "19.000000",
                "stock": None,
                "inputs": [],
                "delivery_instructions": "Redeem on the vendor website",
            }, {
                "id": 22,
                "name": "Adobe Team",
                "product_type": "team_invite",
                "your_unit_price": "5.000000",
                "stock": None,
                "inputs": [{"name": "email", "required": True}],
            }]
        }

    monkeypatch.setattr(reseller_service, "_cgpt_active_request_json", fake_request)

    result = reseller_service.catalog("cgpt_active")

    assert result["provider"] == "cgpt_active"
    assert result["supplier_name"] == "Rich AI Store"
    assert result["balance"] == 12.5
    assert len(result["products"]) == 1
    product = result["products"][0]
    assert product["id"] == "1"
    assert product["wholesale_price"] == 19.0
    assert product["stock"] == 0
    assert product["unlimited_stock"] is True
    assert product["delivery_instruction"] == "Redeem on the vendor website"


def test_cgpt_active_purchase_uses_uuid_and_delivers_instructions(
    monkeypatch, mock_mongodb,
):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs))
        return {
            "order_id": 812,
            "status": "delivered",
            "delivered_codes": ["CGPT-CODE"],
            "delivery_instructions": "Redeem at example.test",
        }

    monkeypatch.setattr(reseller_service, "_cgpt_active_request_json", fake_request)
    offer_id = db.add_offer(
        db.add_service("Rich AI Store", "📦"),
        "Instant code",
        25.0,
        1,
        supplier_provider="cgpt_active",
        supplier_product_id="1",
    )
    mock_mongodb.orders.insert_one({
        "id": 97,
        "user_id": 123,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })

    first = reseller_service.fulfill_paid_order(97)
    second = reseller_service.fulfill_paid_order(97)

    assert first == second == ["CGPT-CODE\n\nHow to redeem:\nRedeem at example.test"]
    assert len(calls) == 1
    path, kwargs = calls[0]
    assert path == "/v1/orders"
    assert kwargs["method"] == "POST"
    assert kwargs["body"] == {"product_id": 1, "quantity": 1}
    assert uuid.UUID(kwargs["idempotency_key"]).version == 4
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 97})
    assert fulfillment["supplier_order_id"] == "812"
    assert fulfillment["idempotency_key"] == kwargs["idempotency_key"]


def test_ventebot_request_uses_reseller_header_without_exposing_key(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success":true,"products":[]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(reseller_service, "VENTEBOT_API_KEY", "vbr_test_secret")
    monkeypatch.setattr(reseller_service, "VENTEBOT_API_BASE", "https://vente.example")
    monkeypatch.setattr(reseller_service, "urlopen", fake_urlopen)

    reseller_service._ventebot_request_json("/api/reseller/products?lang=en")

    request, timeout = requests[0]
    assert timeout == 20
    assert request.full_url == "https://vente.example/api/reseller/products?lang=en"
    assert request.get_header("X-reseller-key") == "vbr_test_secret"
    assert request.get_header("Authorization") is None


def test_ventebot_catalog_maps_immediate_products_and_skips_activation(
    monkeypatch, mock_mongodb,
):
    def fake_request(path, **_kwargs):
        if path == "/api/reseller/me":
            return {"success": True, "wallet_balance": 12.5}
        return {
            "success": True,
            "products": [{
                "id": 16,
                "name": "Gemini 18 months",
                "description": "Instant account",
                "price_usd": 0.55,
                "warranty_days": 7,
                "delivery_type": "stock",
                "stock": 101,
            }, {
                "id": 17,
                "name": "Manual activation",
                "price_usd": 2.0,
                "delivery_type": "activation",
                "stock": None,
            }, {
                "id": 999,
                "name": "Synthetic API test",
                "price_usd": 0.01,
                "delivery_type": "api_test",
                "api_test": True,
                "stock": 1,
            }],
        }

    monkeypatch.setattr(reseller_service, "_ventebot_request_json", fake_request)

    result = reseller_service.catalog("ventebot")

    assert result["provider"] == "ventebot"
    assert result["supplier_name"] == "VenteBot"
    assert result["balance"] == 12.5
    assert len(result["products"]) == 1
    assert result["products"][0]["id"] == "16"
    assert result["products"][0]["wholesale_price"] == 0.55
    assert result["products"][0]["stock"] == 101
    assert result["products"][0]["warranty"] == "7 day warranty"
    assert reseller_service.provider_bot_username("ventebot") == "storeBatmanBot"


def test_ventebot_purchase_is_idempotent_and_delivers_order_items(
    monkeypatch, mock_mongodb,
):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs))
        return {
            "success": True,
            "order": {
                "id": 712,
                "status": "COMPLETED",
                "items": [{"id": 1, "account_data": "user@example.com:password"}],
            },
        }

    monkeypatch.setattr(reseller_service, "_ventebot_request_json", fake_request)
    offer_id = db.add_offer(
        db.add_service("VenteBot", "📦"),
        "Gemini account",
        1.0,
        1,
        supplier_provider="ventebot",
        supplier_product_id="16",
    )
    mock_mongodb.orders.insert_one({
        "id": 101,
        "user_id": 456,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })

    first = reseller_service.fulfill_paid_order(101)
    second = reseller_service.fulfill_paid_order(101)

    assert first == second == ["user@example.com:password"]
    assert calls == [("/api/reseller/orders", {
        "method": "POST",
        "body": {
            "product_id": 16,
            "quantity": 1,
            "customer_reference": "telegram_user_456",
            "idempotency_key": "BM-101",
        },
    })]
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 101})
    assert fulfillment["supplier_order_id"] == "712"


def test_phagia_request_uses_bearer_authentication(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success":true,"data":[]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(reseller_service, "PHAGIA_API_KEY", "private-test-key")
    monkeypatch.setattr(reseller_service, "PHAGIA_API_BASE", "https://phagia.example")
    monkeypatch.setattr(reseller_service, "urlopen", fake_urlopen)

    reseller_service._phagia_request_json("/api/v2/client/products")

    request, timeout = requests[0]
    assert timeout == 20
    assert request.full_url == "https://phagia.example/api/v2/client/products"
    assert request.get_header("Authorization") == "Bearer private-test-key"


def test_phagia_catalog_maps_wallet_and_common_product_fields(
    monkeypatch, mock_mongodb,
):
    def fake_request(path, **_kwargs):
        if path == "/api/v2/client/wallet":
            return {"success": True, "data": {"balance": 25.75}}
        return {
            "success": True,
            "data": {
                "products": [{
                    "id": 81,
                    "title": "Premium account",
                    "description": "Instant delivery",
                    "reseller_price": 1.25,
                    "stock": 9,
                    "currency": "USDT",
                }],
            },
        }

    monkeypatch.setattr(reseller_service, "_phagia_request_json", fake_request)

    result = reseller_service.catalog("phagia")

    assert result["provider"] == "phagia"
    assert result["supplier_name"] == "Shop Phá Giá"
    assert result["balance"] == 25.75
    assert result["products"][0]["id"] == "81"
    assert result["products"][0]["name"] == "Premium account"
    assert result["products"][0]["wholesale_price"] == 1.25
    assert result["products"][0]["stock"] == 9
    assert reseller_service.provider_bot_username("phagia") == "tailieudenphagiabot"


def test_phagia_purchase_uses_only_documented_order_fields(
    monkeypatch, mock_mongodb,
):
    calls = []

    def fake_request(path, **kwargs):
        calls.append((path, kwargs))
        return {
            "success": True,
            "data": {
                "id": 991,
                "items": [{"account_data": "login:password"}],
            },
        }

    monkeypatch.setattr(reseller_service, "_phagia_request_json", fake_request)
    offer_id = db.add_offer(
        db.add_service("Shop Phá Giá", "📦"),
        "Premium account",
        2.0,
        1,
        supplier_provider="phagia",
        supplier_product_id="81",
    )
    mock_mongodb.orders.insert_one({
        "id": 102,
        "user_id": 456,
        "offer_id": offer_id,
        "qty": 1,
        "status": "payment_confirmed",
    })

    assert reseller_service.fulfill_paid_order(102) == ["login:password"]
    assert calls == [("/api/v2/client/orders", {
        "method": "POST",
        "body": {"product_id": 81, "quantity": 1},
    })]
    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 102})
    assert fulfillment["supplier_order_id"] == "991"


def test_restock_detection_baselines_then_reports_only_increases(monkeypatch, mock_mongodb):
    offer_id = db.add_offer(
        service_id=db.add_service("API stock", "📦"),
        name="API plan",
        price=9.0,
        stock=0,
        supplier_provider="mailreader",
        supplier_product_id="sku-1",
    )
    db.save_reseller_product_config(
        "mailreader",
        "sku-1",
        name="API plan",
        wholesale_price=5.0,
        currency="USDT",
        retail_price=9.0,
        enabled=True,
        service_id=1,
        local_offer_id=offer_id,
    )
    stock = {"value": 2}

    def fake_catalog(provider):
        assert provider == "mailreader"
        db.update_offer(offer_id, stock=stock["value"])
        return {
            "products": [{
                "id": "sku-1",
                "enabled": True,
                "local_offer_id": offer_id,
                "stock": stock["value"],
            }]
        }

    monkeypatch.setattr(reseller_service, "MAILREADER_API_KEY", "configured")
    monkeypatch.setattr(reseller_service, "SHAMEKH_API_KEY", "")
    monkeypatch.setattr(reseller_service, "KAKAO_API_KEY", "")
    monkeypatch.setattr(reseller_service, "VEX_API_KEY", "")
    monkeypatch.setattr(reseller_service, "NASTELE_API_KEY", "")
    monkeypatch.setattr(reseller_service, "CANBOSO_API_KEY", "")
    monkeypatch.setattr(reseller_service, "GPT_CHEAP_API_KEY", "")
    monkeypatch.setattr(reseller_service, "SHOP_CRON_API_KEY", "")
    monkeypatch.setattr(reseller_service, "UPIBOT_API_KEY", "")
    monkeypatch.setattr(reseller_service, "TOOLORAX_API_KEY", "")
    monkeypatch.setattr(reseller_service, "CGPT_ACTIVE_API_KEY", "")
    monkeypatch.setattr(reseller_service, "VENTEBOT_API_KEY", "")
    monkeypatch.setattr(reseller_service, "catalog", fake_catalog)

    assert reseller_service.detect_restock_events()["events"] == []
    stock["value"] = 6
    result = reseller_service.detect_restock_events()
    assert result["events"] == [{
        "provider": "mailreader",
        "product_id": "sku-1",
        "offer_id": offer_id,
        "previous_stock": 2,
        "stock": 6,
        "added": 4,
    }]
    assert reseller_service.detect_restock_events()["events"] == []


def test_supplier_price_drop_preserves_profit_amount_and_creates_flash_event(
    monkeypatch, mock_mongodb,
):
    service_id = db.add_service("API prices", "🔥")
    offer_id = db.add_offer(
        service_id, "API plan", 15.0, 8,
        supplier_provider="mailreader", supplier_product_id="sku-price",
    )
    db.save_reseller_product_config(
        "mailreader",
        "sku-price",
        name="API plan",
        wholesale_price=10.0,
        currency="USDT",
        retail_price=15.0,
        enabled=True,
        service_id=service_id,
        local_offer_id=offer_id,
    )
    # Simulate a product configured before fixed profit amounts were stored.
    mock_mongodb.reseller_products.update_one(
        {"provider": "mailreader", "product_id": "sku-price"},
        {"$unset": {"profit_amount": ""}},
    )
    wholesale = {"value": 10.0}

    monkeypatch.setattr(reseller_service, "MAILREADER_API_KEY", "configured")
    monkeypatch.setattr(reseller_service, "SHAMEKH_API_KEY", "")
    monkeypatch.setattr(reseller_service, "KAKAO_API_KEY", "")
    monkeypatch.setattr(reseller_service, "VEX_API_KEY", "")
    monkeypatch.setattr(reseller_service, "NASTELE_API_KEY", "")
    monkeypatch.setattr(reseller_service, "CANBOSO_API_KEY", "")
    monkeypatch.setattr(reseller_service, "GPT_CHEAP_API_KEY", "")
    monkeypatch.setattr(reseller_service, "SHOP_CRON_API_KEY", "")
    monkeypatch.setattr(reseller_service, "UPIBOT_API_KEY", "")
    monkeypatch.setattr(reseller_service, "TOOLORAX_API_KEY", "")
    monkeypatch.setattr(reseller_service, "CGPT_ACTIVE_API_KEY", "")
    monkeypatch.setattr(reseller_service, "VENTEBOT_API_KEY", "")
    monkeypatch.setattr(
        reseller_service,
        "catalog",
        lambda _provider: {
            "products": [{
                "id": "sku-price",
                "enabled": True,
                "local_offer_id": offer_id,
                "wholesale_price": wholesale["value"],
            }]
        },
    )

    assert reseller_service.detect_supplier_price_changes()["changes"] == []
    wholesale["value"] = 8.0
    result = reseller_service.detect_supplier_price_changes()

    assert len(result["flash_sales"]) == 1
    assert result["flash_sales"][0]["profit_amount"] == 5.0
    assert result["flash_sales"][0]["previous_price"] == 15.0
    assert result["flash_sales"][0]["price"] == 13.0
    assert db.get_offer(offer_id)["price"] == 13.0

    config = db.list_reseller_product_configs("mailreader")[0]
    assert config["profit_amount"] == 5.0

    wholesale["value"] = 9.0
    increase = reseller_service.detect_supplier_price_changes()

    assert increase["changes"][0]["profit_amount"] == 5.0
    assert increase["changes"][0]["price"] == 14.0
    assert db.get_offer(offer_id)["price"] == 14.0


def test_all_supplier_bot_usernames_are_registered():
    assert reseller_service.PROVIDER_BOT_USERNAMES == {
        "mailreader": "dodistore_bot",
        "shamekh": "Shamekhstock_bot",
        "kakao": "Shop_KOKORO_BOT",
        "vex": "VexoranShoppieBot",
        "nastele": "BolemT",
        "canboso": "PiggyAi799_Bot",
        "gpt_cheap": "GPTCheapChat_bot",
        "shop_cron": "shop_cron191_en_bot",
        "upibot": "scanupigptbot",
        "toolorax": "TooloraXbot",
        "cgpt_active": "RichAIStoreBot",
        "ventebot": "storeBatmanBot",
        "phagia": "tailieudenphagiabot",
    }


def test_nastele_catalog_and_fulfillment(monkeypatch, mock_mongodb):
    def fake_request(path, *, method="GET", body=None):
        if path == "/api/partner/products":
            return {
                "success": True,
                "data": [
                    {
                        "id": 43,
                        "name": "SLOT CANVA EDU 1 NĂM",
                        "price": 30000,
                        "description": "Canva Edu slot",
                        "stock": 40,
                    }
                ],
            }
        if path == "/api/partner/balance":
            return {
                "success": True,
                "data": {
                    "balance": 78992,
                    "currency": "VND",
                },
            }
        if path == "/api/partner/orders":
            assert method == "POST"
            assert body == {"productId": 43, "qty": 1}
            return {
                "success": True,
                "data": {
                    "orderId": 2244,
                    "totalAmount": 30000,
                    "items": [
                        {
                            "productName": "SLOT CANVA EDU 1 NĂM",
                            "quantity": 1,
                            "unitPrice": 30000,
                            "accounts": ["canva_user:canva_pass"],
                        }
                    ],
                },
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(reseller_service, "_nastele_request_json", fake_request)
    monkeypatch.setattr(reseller_service, "get_nastele_vnd_rate", lambda: 25000.0)

    cat = reseller_service.catalog("nastele")
    assert cat["ok"] is True
    assert cat["supplier_name"] == "NasTele"
    assert cat["balance"] == 3.16
    assert cat["currency"] == "USDT"
    assert len(cat["products"]) == 1
    assert cat["products"][0]["id"] == "43"
    assert cat["products"][0]["wholesale_price"] == 1.2
    assert cat["products"][0]["currency"] == "USDT"
    assert cat["products"][0]["stock"] == 40

    service_id = db.add_service("Canva", "🎨")
    saved = reseller_service.save_catalog_product(
        "43",
        provider="nastele",
        retail_price=2.5,
        enabled=True,
        service_id=service_id,
        display_name="Canva Edu 1 An",
    )

    offer = db.get_offer(saved["local_offer_id"])
    assert offer is not None
    assert offer["supplier_provider"] == "nastele"
    assert offer["supplier_product_id"] == "43"

    mock_mongodb.orders.insert_one({
        "id": 99,
        "user_id": 12345,
        "offer_id": offer["id"],
        "qty": 1,
        "status": "payment_confirmed",
    })

    delivered = reseller_service.fulfill_paid_order(99)
    assert delivered == ["canva_user:canva_pass"]

    order = db.get_order(99)
    assert order["status"] == "delivered"
    assert order["supplier_external_order_id"] == "BM-99"

    fulfillment = mock_mongodb.reseller_fulfillments.find_one({"order_id": 99})
    assert fulfillment["supplier_order_id"] == "2244"

