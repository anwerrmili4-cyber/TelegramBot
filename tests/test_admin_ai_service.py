import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.domain import admin_ai_service as service
from config import normalized_http_url


def dashboard_data():
    return {
        "summary": {"orders": 9, "revenue_today": 12.5},
        "alerts": [{"type": "stock_low", "message": "Stock faible", "severity": "warning"}],
        "services": [{
            "id": 1,
            "name": "Canva",
            "active": 1,
            "offers": [{
                "id": 11,
                "name": "Canva 1m",
                "price": 2,
                "stock": 3,
                "active": 1,
                "delivery": ["secret-account"],
                "api_key": "secret-key",
            }],
        }],
        "orders": [{
            "id": 21,
            "status": "paid",
            "offer_name": "Canva 1m",
            "user_id": 999,
            "delivery": ["secret-delivery"],
        }],
        "tickets": [{"id": 31, "status": "waiting_admin", "message": "private text"}],
        "users": [{"telegram_id": 41, "username": "private_user", "banned": False}],
        "dashboard_write_token": "never-send-this",
    }


def test_safe_snapshot_excludes_secrets_and_customer_content():
    snapshot = service.safe_dashboard_snapshot(dashboard_data())
    encoded = json.dumps(snapshot)

    assert "secret-account" not in encoded
    assert "secret-delivery" not in encoded
    assert "secret-key" not in encoded
    assert "private text" not in encoded
    assert "private_user" not in encoded
    assert "never-send-this" not in encoded
    assert snapshot["services"][0]["offers"][0]["id"] == 11


def test_sanitize_actions_allows_only_known_entities_and_actions():
    snapshot = service.safe_dashboard_snapshot(dashboard_data())
    actions = service.sanitize_actions([
        {"action": "toggle_offer", "label": "Désactiver", "parameters": {"offer_id": 11}},
        {"action": "toggle_offer", "parameters": {"offer_id": 999}},
        {"action": "reveal_inventory", "parameters": {"inventory_id": 1}},
        {"action": "toggle_ban", "parameters": {"user_id": 41, "banned": True}},
    ], snapshot)

    assert [item["action"] for item in actions] == ["toggle_offer", "toggle_ban"]
    assert actions[1]["parameters"]["banned"] == 1


def test_chat_rejects_model_outside_configured_list(monkeypatch):
    monkeypatch.setattr(service, "AI_COMPARISON_MODELS", ("allowed-model",))

    with pytest.raises(service.AdminAIError, match="Model not allowed"):
        service.chat([{"role": "user", "content": "Résumé"}], "other-model", dashboard_data())


def test_markdown_url_copied_from_chat_is_repaired():
    assert normalized_http_url(
        "[https://co.agentrouter.org/v1/chat/completions](https://agentrouter.org/v1/chat/completions)"
    ) == "https://agentrouter.org/v1/chat/completions"


def test_agentrouter_unauthorized_client_error_is_explicit():
    body = BytesIO(json.dumps({
        "error": {"message": "unauthorized client detected, contact support"}
    }).encode())
    error = HTTPError("https://agentrouter.org", 401, "Unauthorized", {}, body)

    message = service._provider_error_message(error)

    assert "unauthorized client" in message
    assert "Railway" in message


def test_public_config_identifies_openai(monkeypatch):
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://api.openai.com/v1/chat/completions")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "test-token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODELS", ("gpt-5.6-terra",))

    config = service.public_config()

    assert config["configured"] is True
    assert config["provider"] == "OpenAI"
    assert config["models"] == ["gpt-5.6-terra"]


def test_chat_returns_sanitized_suggestions(monkeypatch, mock_mongodb):
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://ai.example/v1/chat/completions")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "test-token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODELS", ("model-a",))
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            result = {
                "reply": "Canva stock is low.",
                "suggested_actions": [
                    {"action": "toggle_offer", "label": "Désactiver Canva", "parameters": {"offer_id": 11}},
                    {"action": "delete_everything", "parameters": {}},
                ],
            }
            return json.dumps({"choices": [{"message": {"content": json.dumps(result)}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(service, "urlopen", fake_urlopen)
    result = service.chat([{"role": "user", "content": "Analyze stock"}], "model-a", dashboard_data())

    assert result["reply"] == "Canva stock is low."
    assert [item["action"] for item in result["suggested_actions"]] == ["toggle_offer"]
    sent = json.dumps(captured["body"])
    assert "secret-delivery" not in sent
    assert "never-send-this" not in sent
    assert "Always answer in English" in sent


def test_database_context_covers_operational_records_but_redacts_credentials(mock_mongodb):
    mock_mongodb.users.insert_one({
        "telegram_id": 41, "username": "customer_41", "banned": False,
    })
    mock_mongodb.support_tickets.insert_one({
        "id": 31, "user_id": 41, "status": "waiting_admin", "category": "delivery",
    })
    mock_mongodb.ticket_messages.insert_one({
        "id": 32, "ticket_id": 31, "sender_type": "client",
        "content": "My delivery has not arrived.",
    })
    mock_mongodb.orders.insert_one({
        "id": 21, "user_id": 41, "status": "paid", "offer_name": "Canva 1m",
        "delivery_text": "login@example.com:secret-password",
    })
    mock_mongodb.external_api_connectors.insert_one({
        "id": 7, "name": "Partner", "encrypted_secret": "ciphertext-value",
    })

    context = service.admin_database_context("Tell me about ticket 31 and customer 41")
    encoded = json.dumps(context)

    assert context["collection_counts"]["users"] == 1
    assert context["collection_counts"]["orders"] == 1
    assert "customer_41" in encoded
    assert "My delivery has not arrived." in encoded
    assert "login@example.com:secret-password" not in encoded
    assert "ciphertext-value" not in encoded
    assert "[REDACTED]" in encoded


def test_chat_uses_english_database_fallback_when_provider_is_blocked(
    monkeypatch, mock_mongodb,
):
    mock_mongodb.orders.insert_one({
        "id": 88, "user_id": 41, "status": "paid", "offer_name": "ChatGPT K12",
        "total_price": 9,
    })
    monkeypatch.setattr(service, "AI_COMPARISON_API_URL", "https://ai.example/chat")
    monkeypatch.setattr(service, "AI_COMPARISON_API_KEY", "test-token")
    monkeypatch.setattr(service, "AI_COMPARISON_MODELS", ("model-a",))

    def reject(request, timeout):
        body = BytesIO(json.dumps({
            "error": {"message": "unauthorized client detected"},
        }).encode())
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, body)

    monkeypatch.setattr(service, "urlopen", reject)

    result = service.chat(
        [{"role": "user", "content": "Tell me about order 88"}],
        "model-a",
        dashboard_data(),
    )

    assert result["ok"] is True
    assert result["model"] == "database-fallback"
    assert "direct read-only database lookup" in result["reply"]
    assert '"id": 88' in result["reply"]
    assert result["suggested_actions"] == []
