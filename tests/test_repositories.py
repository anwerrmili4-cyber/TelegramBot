"""Repository modules extracted from ``database`` and the guards moved out of ``bot``."""

from __future__ import annotations

import database as db
from app.repositories import bot_state, broadcasts, payment_references, tickets


def test_database_re_exports_the_repository_functions():
    assert db.create_ticket is tickets.create_ticket
    assert db.claim_update is bot_state.claim_update
    assert db.create_broadcast_job is broadcasts.create_broadcast_job
    assert db.claim_payment_reference is payment_references.claim_payment_reference
    assert db.CATALOG_UPDATE_BROADCAST_KINDS is broadcasts.CATALOG_UPDATE_BROADCAST_KINDS


def test_bot_tickets_exclude_site_tickets(mock_mongodb):
    ticket_id = tickets.create_ticket(42, "Mon compte ne marche pas")
    mock_mongodb.support_tickets.insert_one({"id": 999, "status": "open", "channel": "tn_site"})

    assert [row["id"] for row in tickets.list_tickets()] == [ticket_id]
    assert mock_mongodb.audit_events.find_one({"action": "ticket.created"})["details"] == {"ticket_id": ticket_id}
    assert tickets.close_ticket(ticket_id) is True
    assert tickets.get_ticket(ticket_id)["status"] == "closed"
    assert tickets.list_tickets() == []


def test_updates_are_claimed_once_and_can_be_released(mock_mongodb):
    assert bot_state.claim_update(5) is True
    assert bot_state.claim_update(5) is False
    bot_state.release_update(5)
    assert bot_state.claim_update(5) is True


def test_pending_state_round_trip(mock_mongodb):
    assert bot_state.get_pending_state(7) is None
    bot_state.set_pending_state(7, ("await_txid", 12))
    assert bot_state.get_pending_state(7) == ("await_txid", 12)
    assert bot_state.pop_pending_state(7) == ("await_txid", 12)
    assert bot_state.pop_pending_state(7, "none") == "none"


def test_catalog_broadcasts_skip_opted_out_and_blocked_users(mock_mongodb):
    mock_mongodb.users.insert_many([
        {"telegram_id": 1},
        {"telegram_id": 2, "catalog_notifications_enabled": False},
        {"telegram_id": 3, "catalog_notification_disabled_offer_ids": [9]},
        {"telegram_id": 4, "broadcast_blocked": True},
        {"telegram_id": 5, "banned": True},
    ])

    job, created = broadcasts.create_broadcast_job("stock", {"offer_id": 9}, dedupe_key="stock:9")
    again, created_again = broadcasts.create_broadcast_job("stock", {"offer_id": 9}, dedupe_key="stock:9")
    admin_job, _ = broadcasts.create_broadcast_job("admin_message", {})

    assert created and not created_again and again["id"] == job["id"]
    assert job["recipient_count"] == 1
    assert admin_job["recipient_count"] == 3
    assert broadcasts.claim_broadcast_job(job["id"])["status"] == "running"
    assert broadcasts.fail_broadcast_job(job["id"], "network") == "retry"


def test_membership_cache_is_shared_with_the_bot_module():
    import bot
    from app.bot import middlewares

    assert bot._membership_cache is middlewares._membership_cache
    assert bot.block_banned_users is middlewares.block_banned_users
