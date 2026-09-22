"""Tests unitaires pour le service de support client."""

from __future__ import annotations

from app.constants import TicketCategory, TicketPriority, TicketStatus
from app.domain import support_service


def test_create_ticket_success(mock_mongodb):
    """Vérifie la création d'un ticket support."""
    ticket = support_service.create_ticket(
        user_id=12345,
        message="Bonjour, j'ai un problème avec ma commande.",
        category=TicketCategory.PAYMENT,
        order_id=5,
        priority=TicketPriority.HIGH,
    )

    assert ticket["id"] == 1
    assert ticket["user_id"] == 12345
    assert ticket["category"] == TicketCategory.PAYMENT
    assert ticket["priority"] == TicketPriority.HIGH
    assert ticket["status"] == TicketStatus.WAITING_ADMIN

    # Vérifier que le message a été ajouté au ticket
    msgs = support_service.get_messages(ticket_id=1)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Bonjour, j'ai un problème avec ma commande."
    assert msgs[0]["sender_type"] == "client"


def test_conversation_flow(mock_mongodb):
    """Vérifie les échanges de messages et l'évolution des statuts."""
    support_service.create_ticket(user_id=12345, message="Hello")

    # Réponse admin
    support_service.admin_reply(ticket_id=1, admin_id=999, content="Hello client, how can I help you?")

    # Le statut doit être WAITING_CUSTOMER
    ticket = support_service.get_ticket(ticket_id=1)
    assert ticket["status"] == TicketStatus.WAITING_CUSTOMER

    # Réponse client
    support_service.add_message(ticket_id=1, sender_id=12345, content="I need a refund", sender_type="client")

    # Le statut repasse en WAITING_ADMIN
    ticket = support_service.get_ticket(ticket_id=1)
    assert ticket["status"] == TicketStatus.WAITING_ADMIN

    # Vérifier l'historique complet
    msgs = support_service.get_messages(ticket_id=1)
    assert len(msgs) == 3
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["content"] == "Hello client, how can I help you?"
    assert msgs[2]["content"] == "I need a refund"


def test_close_and_reopen_ticket(mock_mongodb):
    """Vérifie la fermeture et la réouverture de tickets."""
    support_service.create_ticket(user_id=12345, message="Problem")

    # Fermer le ticket
    assert support_service.close_ticket(ticket_id=1) is True
    ticket = support_service.get_ticket(ticket_id=1)
    assert ticket["status"] == TicketStatus.CLOSED

    # Compter les tickets ouverts
    assert support_service.count_open_tickets() == 0

    # Réouvrir
    assert support_service.reopen_ticket(ticket_id=1) is True
    ticket = support_service.get_ticket(ticket_id=1)
    assert ticket["status"] == TicketStatus.OPEN
    assert support_service.count_open_tickets() == 1


def test_guided_ticket_keeps_category_and_order(mock_mongodb):
    ticket = support_service.create_ticket(
        user_id=321,
        message="Payment issue",
        category=TicketCategory.PAYMENT,
        order_id=77,
        priority=TicketPriority.HIGH,
    )

    assert ticket["category"] == TicketCategory.PAYMENT
    assert ticket["order_id"] == 77
    assert ticket["priority"] == TicketPriority.HIGH


def test_ticket_message_keeps_safe_telegram_media_metadata(mock_mongodb):
    ticket = support_service.create_ticket(
        user_id=321,
        message="[Photo] Screenshot",
        media={
            "type": "image",
            "file_id": "telegram-file-id",
            "mime_type": "image/jpeg",
            "width": 1280,
            "height": 720,
            "private_internal_value": "must-not-leak",
        },
    )

    message = support_service.get_messages(ticket["id"])[0]
    assert message["media"] == {
        "type": "image",
        "file_id": "telegram-file-id",
        "mime_type": "image/jpeg",
        "width": 1280,
        "height": 720,
    }


def test_bulk_close_archive_and_restore_tickets(mock_mongodb):
    first = support_service.create_ticket(user_id=101, message="First")
    second = support_service.create_ticket(user_id=202, message="Second")

    assert support_service.close_all_tickets() == 2
    assert support_service.get_ticket(first["id"])["status"] == TicketStatus.CLOSED
    assert support_service.get_ticket(second["id"])["status"] == TicketStatus.CLOSED
    assert support_service.archive_ticket(first["id"]) is True
    assert support_service.get_ticket(first["id"])["archived_at"]
    assert support_service.archive_closed_tickets() == 1
    assert support_service.get_ticket(second["id"])["archived_at"]
    assert support_service.unarchive_ticket(first["id"]) is True
    assert "archived_at" not in support_service.get_ticket(first["id"])


def test_open_ticket_must_be_closed_before_archive(mock_mongodb):
    ticket = support_service.create_ticket(user_id=303, message="Still open")

    assert support_service.archive_ticket(ticket["id"]) is False
