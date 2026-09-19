import json

from app.domain import customer_ai_service as service


def seed_customer_context(mock_mongodb):
    mock_mongodb.services.insert_one({"id": 1, "name": "AI", "active": 1})
    mock_mongodb.offers.insert_one({
        "id": 11,
        "service_id": 1,
        "name": "Pro plan",
        "price": 8,
        "stock": 2,
        "active": 1,
        "inventory": ["catalog-secret"],
    })
    mock_mongodb.orders.insert_many([
        {
            "id": 21,
            "user_id": 42,
            "offer_name": "Pro plan",
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
