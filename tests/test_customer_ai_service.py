import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.domain import customer_ai_service as service


def seed_customer_context(mock_mongodb):
    mock_mongodb.services.insert_one({"id": 1, "name": "AI", "active": 1})
    mock_mongodb.offers.insert_one({
        "id": 11,
        "service_id": 1,
        "name": "ChatGPT K12",
        "description": "Private ChatGPT workspace with managed access.",
        "price": 8,
        "stock": 2,
        "active": 1,
        "currency": "USDT",
        "period_value": 30,
        "period_unit": "days",
        "warranty_value": 7,
        "warranty_unit": "days",
        "delivery_delay": "Within one hour",
        "bulk_quantity": 5,
        "bulk_unit_price": 6.5,
        "inventory": ["catalog-secret"],
    })
    mock_mongodb.orders.insert_many([
        {
            "id": 21,
            "user_id": 42,
            "offer_name": "ChatGPT K12",
            "service_name": "AI",
            "status": "paid",
            "qty": 1,
            "total_price": 8,
            "delivery_text": "customer-delivery-secret",
            "txid": "private-txid",
        },
        {
            "id": 22,
            "user_id": 99,
            "offer_name": "Other customer plan",
            "service_name": "AI",
            "status": "delivered",
            "delivery_text": "other-customer-secret",
        },
    ])


def test_safe_context_contains_only_requesting_customers_sanitized_orders(mock_mongodb):
    seed_customer_context(mock_mongodb)

    encoded = json.dumps(service.safe_customer_context(42), default=str)

    assert '"id": 21' in encoded
    assert '"id": 22' not in encoded
    assert "customer-delivery-secret" not in encoded
    assert "other-customer-secret" not in encoded
    assert "private-txid" not in encoded
    assert "catalog-secret" not in encoded
    assert "Private ChatGPT workspace" in encoded
    assert '"delivery_delay": "Within one hour"' in encoded


def test_chat_uses_short_memory_and_returns_sanitized_handoff(monkeypatch, mock_mongodb):
    seed_customer_context(mock_mongodb)
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://ai.example/chat")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODEL", "model-a")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            result = {
                "reply": "Order #21 is paid. Human support can check delivery.",
                "needs_human": True,
                "category": "delivery",
            }
            return json.dumps({
                "choices": [{"message": {"content": json.dumps(result)}}]
            }).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(service, "urlopen", fake_urlopen)
    result = service.chat(42, "Where is my delivery?", "en")

    assert result == {
        "reply": "Order #21 is paid. Human support can check delivery.",
        "needs_human": True,
        "category": "delivery",
    }
    sent = json.dumps(captured["body"])
    assert "customer-delivery-secret" not in sent
    assert "other-customer-secret" not in sent
    assert captured["timeout"] == 45
    history = list(mock_mongodb.customer_ai_messages.find({"user_id": 42}))
    assert [item["role"] for item in history] == ["user", "assistant"]


def test_chat_rejects_unknown_handoff_category(monkeypatch, mock_mongodb):
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://ai.example/chat")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODEL", "model-a")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            content = json.dumps({
                "reply": "I cannot do that.",
                "needs_human": "false",
                "category": "delete_everything",
            })
            return json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    monkeypatch.setattr(service, "urlopen", lambda request, timeout: Response())

    result = service.chat(42, "Do something unsafe", "en")

    assert result["needs_human"] is False
    assert result["category"] == "other"


def test_chat_falls_back_locally_when_provider_rejects_client(monkeypatch, mock_mongodb):
    seed_customer_context(mock_mongodb)
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://ai.example/chat")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODEL", "model-a")
    error_body = BytesIO(json.dumps({
        "error": {"message": "unauthorized client detected"},
    }).encode())

    def reject(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, error_body)

    monkeypatch.setattr(service, "urlopen", reject)

    result = service.chat(42, "hello", "en")

    assert result["needs_human"] is False
    assert "Hello" in result["reply"]


def test_chat_falls_back_to_private_order_summary_without_api_key(monkeypatch, mock_mongodb):
    seed_customer_context(mock_mongodb)
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "")

    result = service.chat(42, "What is my order status?", "en")

    assert result["needs_human"] is False
    assert "#21" in result["reply"]
    assert "#22" not in result["reply"]
    assert "private-txid" not in result["reply"]


def test_local_fallback_returns_complete_named_product_information(monkeypatch, mock_mongodb):
    seed_customer_context(mock_mongodb)
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "")

    result = service.chat(42, "whats the description of chatgpt k12", "en")

    assert result["needs_human"] is False
    assert "ChatGPT K12" in result["reply"]
    assert "Private ChatGPT workspace with managed access." in result["reply"]
    assert "8 USDT" in result["reply"]
    assert "Stock: 2" in result["reply"]
    assert "Duration: 30 days" in result["reply"]
    assert "Warranty: 7 days" in result["reply"]
    assert "Delivery: Within one hour" in result["reply"]
    assert "6.5 USDT × 5+" in result["reply"]
    assert "catalog-secret" not in result["reply"]


@pytest.mark.parametrize(("message", "preferred", "expected"), [
    ("Hello, show me the products", "en", "en"),
    ("Bonjour, montrez-moi les produits", "en", "fr"),
    ("مرحبا، أريد رؤية المنتجات", "en", "ar"),
    ("你好，我想查看产品", "en", "zh"),
    ("Xin chào, tôi muốn xem sản phẩm", "en", "vi"),
    ("नमस्ते, मुझे उत्पाद देखना है", "en", "hi"),
    ("السلام علیکم، مجھے مصنوعات دیکھنی ہیں", "en", "ur"),
])
def test_detects_supported_customer_language(message, preferred, expected):
    assert service.detect_language(message, preferred) == expected


def test_chinese_order_question_gets_chinese_local_answer(monkeypatch, mock_mongodb):
    seed_customer_context(mock_mongodb)
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "")

    result = service.chat(42, "我的订单状态", "en")

    assert result["needs_human"] is False
    assert "您最近的订单" in result["reply"]
    assert "#21" in result["reply"]
