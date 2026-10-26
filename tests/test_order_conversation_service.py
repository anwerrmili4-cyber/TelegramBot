"""Order conversations are durable and scoped to their order."""

from datetime import UTC, datetime

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
                "kind": "message", "created_at": 100, "source": "order",
            },
            {
                "id": second["id"], "order_id": 71, "sender_type": "client",
                "sender_id": 42, "content": "client@example.com",
                "kind": "message", "created_at": 101, "source": "order",
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


def test_order_conversation_includes_historical_support_tickets(mock_mongodb):
    mock_mongodb.support_tickets.insert_many([
        {"id": 301, "order_id": 71, "user_id": 42},
        {"id": 302, "order_id": 72, "user_id": 43},
    ])
    mock_mongodb.ticket_messages.insert_many([
        {
            "id": 801, "ticket_id": 301, "sender_type": "client", "sender_id": 42,
            "content": "My account email is client@example.com.",
            "created_at": datetime.fromtimestamp(100, UTC),
        },
        {
            "id": 802, "ticket_id": 301, "sender_type": "admin", "sender_id": 999,
            "content": "Thank you, I will prepare it.",
            "created_at": datetime.fromtimestamp(101, UTC),
        },
        {
            "id": 803, "ticket_id": 302, "sender_type": "client", "sender_id": 43,
            "content": "Another order.", "created_at": datetime.fromtimestamp(99, UTC),
        },
    ])

    grouped = order_conversation_service.messages_by_order([71])

    assert [message["content"] for message in grouped[71]] == [
        "My account email is client@example.com.",
        "Thank you, I will prepare it.",
    ]
    assert [message["sender_type"] for message in grouped[71]] == ["client", "admin"]
    assert [message["created_at"] for message in grouped[71]] == [100, 101]
