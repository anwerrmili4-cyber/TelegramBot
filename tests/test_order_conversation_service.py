"""Order conversations are durable and scoped to their order."""

from app.domain import order_conversation_service


def test_order_conversation_keeps_client_and_admin_messages_in_order(mock_mongodb):
    first = order_conversation_service.record_message(
        71, "admin", 999, "Please send the account email.", created_at=100,
    )
    second = order_conversation_service.record_message(
        71, "client", 42, "client@example.com", created_at=101,
    )
    order_conversation_service.record_message(
        72, "client", 43, "This belongs to another order.", created_at=99,
    )

    grouped = order_conversation_service.messages_by_order([71])

    assert first["id"] != second["id"]
    assert grouped == {
        71: [
            {
                "id": first["id"], "order_id": 71, "sender_type": "admin",
                "sender_id": 999, "content": "Please send the account email.",
                "kind": "message", "created_at": 100,
            },
            {
                "id": second["id"], "order_id": 71, "sender_type": "client",
                "sender_id": 42, "content": "client@example.com",
                "kind": "message", "created_at": 101,
            },
        ],
    }


def test_order_conversation_rejects_unknown_sender_and_empty_content(mock_mongodb):
    for sender, content in (("supplier", "Hello"), ("client", "   ")):
        try:
            order_conversation_service.record_message(71, sender, 42, content)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid order conversation input was accepted")

    assert mock_mongodb.order_messages.count_documents({}) == 0


def test_order_conversation_has_chronological_lookup_index(mock_mongodb):
    index = mock_mongodb.order_messages.index_information()["order_conversation_chronological"]
    assert index["key"] == [("order_id", 1), ("created_at", 1), ("id", 1)]
