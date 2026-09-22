"""Service métier pour le support client.

Gère les tickets sous forme de conversations avec messages multiples,
catégories, priorités et liaison aux commandes.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import database as db
from app.constants import TicketCategory, TicketPriority, TicketStatus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Création de ticket
# ---------------------------------------------------------------------------

def create_ticket(
    user_id: int,
    message: str,
    category: str = TicketCategory.OTHER,
    order_id: int | None = None,
    priority: str = TicketPriority.NORMAL,
    media: dict | None = None,
) -> dict:
    """Crée un ticket support avec un premier message.

    Returns:
        Le ticket créé avec son ID.
    """
    conn = db.get_conn()
    ticket_id = db._next_id("tickets")
    now = datetime.now(UTC)

    ticket = {
        "id": ticket_id,
        "user_id": user_id,
        "order_id": order_id,
        "category": category,
        "priority": priority,
        "status": TicketStatus.WAITING_ADMIN,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
    }
    conn.support_tickets.insert_one(ticket)

    # Premier message du client
    add_message(ticket_id, user_id, message, sender_type="client", media=media)

    db.audit_event(
        "ticket.created",
        actor_id=user_id,
        details={"ticket_id": ticket_id, "category": category, "order_id": order_id},
    )
    log.info("Ticket #%d créé par user %d (catégorie: %s)", ticket_id, user_id, category)

    return db._public(conn.support_tickets.find_one({"id": ticket_id}))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def add_message(
    ticket_id: int,
    sender_id: int,
    content: str,
    sender_type: str = "client",
    media: dict | None = None,
) -> dict:
    """Ajoute un message à un ticket.

    Args:
        ticket_id: ID du ticket.
        sender_id: Telegram ID de l'expéditeur.
        content: Contenu du message.
        sender_type: "client" ou "admin".

    Returns:
        Le message créé.
    """
    conn = db.get_conn()
    msg_id = db._next_id("ticket_messages")
    now = datetime.now(UTC)

    msg = {
        "id": msg_id,
        "ticket_id": ticket_id,
        "sender_id": sender_id,
        "sender_type": sender_type,
        "content": content[:2000],
        "created_at": now,
    }
    if media:
        allowed = {
            "type", "file_id", "file_unique_id", "file_name", "mime_type",
            "width", "height", "duration", "file_size", "custom_emoji_id",
        }
        clean_media = {
            key: value for key, value in media.items()
            if key in allowed and value not in (None, "")
        }
        if clean_media.get("file_id"):
            msg["media"] = clean_media
    conn.ticket_messages.insert_one(msg)

    # Mettre à jour le statut du ticket
    new_status = TicketStatus.WAITING_ADMIN if sender_type == "client" else TicketStatus.WAITING_CUSTOMER
    conn.support_tickets.update_one(
        {"id": ticket_id},
        {"$set": {"status": new_status, "updated_at": now}},
    )

    return db._public(msg)


def get_messages(ticket_id: int, limit: int = 50) -> list[dict]:
    """Récupère les messages d'un ticket, du plus ancien au plus récent."""
    conn = db.get_conn()
    from pymongo import ASCENDING
    return [
        db._public(m)
        for m in conn.ticket_messages.find(
            {"ticket_id": ticket_id}
        ).sort("created_at", ASCENDING).limit(limit)
    ]


def admin_reply(ticket_id: int, admin_id: int, content: str) -> dict | None:
    """Réponse admin à un ticket.

    Returns:
        Le message créé, ou None si le ticket n'existe pas.
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        return None

    msg = add_message(ticket_id, admin_id, content, sender_type="admin")
    log.info("Admin a répondu au ticket #%d", ticket_id)
    return msg


# ---------------------------------------------------------------------------
# Gestion des tickets
# ---------------------------------------------------------------------------

def get_ticket(ticket_id: int) -> dict | None:
    """Récupère un ticket par son ID."""
    return db._public(db.get_conn().support_tickets.find_one({"id": ticket_id}))



def link_channel_message(ticket_id: int, channel_message_id: int) -> bool:
    """Associate a support-channel post with its ticket for reply routing."""
    result = db.get_conn().support_tickets.update_one(
        {"id": int(ticket_id)},
        {"$addToSet": {"channel_message_ids": int(channel_message_id)}},
    )
    return bool(result.matched_count)


def get_ticket_by_channel_message(channel_message_id: int) -> dict | None:
    """Resolve the ticket linked to a support-channel post."""
    return db._public(db.get_conn().support_tickets.find_one({
        "channel_message_ids": int(channel_message_id),
    }))

def list_tickets(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Liste les tickets avec filtres optionnels."""
    query: dict = {}
    if status:
        query["status"] = status
    if user_id:
        query["user_id"] = user_id

    from pymongo import DESCENDING
    return [
        db._public(t)
        for t in db.get_conn().support_tickets.find(query).sort(
            "updated_at", DESCENDING
        ).limit(limit)
    ]


def close_ticket(ticket_id: int) -> bool:
    """Ferme un ticket."""
    conn = db.get_conn()
    result = conn.support_tickets.update_one(
        {"id": ticket_id, "status": {"$ne": TicketStatus.CLOSED}},
        {
            "$set": {
                "status": TicketStatus.CLOSED,
                "closed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        },
    )
    if result.modified_count:
        db.audit_event("ticket.closed", details={"ticket_id": ticket_id})
        return True
    return False


def close_all_tickets() -> int:
    """Close every active, non-archived support conversation."""
    now = datetime.now(UTC)
    result = db.get_conn().support_tickets.update_many(
        {
            "status": {"$nin": [TicketStatus.CLOSED, TicketStatus.RESOLVED]},
            "archived_at": {"$exists": False},
        },
        {"$set": {"status": TicketStatus.CLOSED, "closed_at": now, "updated_at": now}},
    )
    if result.modified_count:
        db.audit_event("ticket.closed_all", details={"count": result.modified_count})
    return int(result.modified_count)


def archive_ticket(ticket_id: int) -> bool:
    """Hide a closed ticket from the active inbox while preserving its history."""
    now = datetime.now(UTC)
    result = db.get_conn().support_tickets.update_one(
        {
            "id": int(ticket_id),
            "status": {"$in": [TicketStatus.CLOSED, TicketStatus.RESOLVED]},
            "archived_at": {"$exists": False},
        },
        {"$set": {"archived_at": now, "updated_at": now}},
    )
    if result.modified_count:
        db.audit_event("ticket.archived", details={"ticket_id": int(ticket_id)})
        return True
    return False


def archive_closed_tickets() -> int:
    """Archive all closed or resolved tickets that are still in the inbox."""
    now = datetime.now(UTC)
    result = db.get_conn().support_tickets.update_many(
        {
            "status": {"$in": [TicketStatus.CLOSED, TicketStatus.RESOLVED]},
            "archived_at": {"$exists": False},
        },
        {"$set": {"archived_at": now, "updated_at": now}},
    )
    if result.modified_count:
        db.audit_event("ticket.archived_closed", details={"count": result.modified_count})
    return int(result.modified_count)


def unarchive_ticket(ticket_id: int) -> bool:
    """Return an archived ticket to the regular support inbox."""
    result = db.get_conn().support_tickets.update_one(
        {"id": int(ticket_id), "archived_at": {"$exists": True}},
        {"$unset": {"archived_at": ""}, "$set": {"updated_at": datetime.now(UTC)}},
    )
    if result.modified_count:
        db.audit_event("ticket.unarchived", details={"ticket_id": int(ticket_id)})
        return True
    return False


def reopen_ticket(ticket_id: int) -> bool:
    """Rouvre un ticket fermé."""
    conn = db.get_conn()
    result = conn.support_tickets.update_one(
        {"id": ticket_id, "status": TicketStatus.CLOSED},
        {
            "$set": {
                "status": TicketStatus.OPEN,
                "closed_at": None,
                "updated_at": datetime.now(UTC),
            }
        },
    )
    if result.modified_count:
        db.audit_event("ticket.reopened", details={"ticket_id": ticket_id})
        return True
    return False


def count_open_tickets() -> int:
    """Compte les tickets non fermés."""
    conn = db.get_conn()
    return conn.support_tickets.count_documents(
        {"status": {"$nin": [TicketStatus.CLOSED, TicketStatus.RESOLVED]}}
    )
