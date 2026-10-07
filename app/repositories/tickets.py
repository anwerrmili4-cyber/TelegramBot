"""Bot support tickets (``support_tickets``); site tickets are kept out of these lists."""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import DESCENDING

from app.repositories._mongo import audit_event, conn, next_id, public


def create_ticket(user_id, message):
    tid = next_id("tickets")
    conn().support_tickets.insert_one({"id": tid, "user_id": user_id, "message": message[:2000], "status": "open", "created_at": datetime.now(UTC)})
    audit_event("ticket.created", user_id, {"ticket_id": tid})
    return tid


def list_tickets(status="open", limit=50):
    return [public(x) for x in conn().support_tickets.find({
        "status": status,
        "channel": {"$ne": "tn_site"},
    }).sort("created_at", DESCENDING).limit(limit)]


def get_ticket(ticket_id):
    return public(conn().support_tickets.find_one({"id": ticket_id}))


def close_ticket(ticket_id):
    return bool(conn().support_tickets.update_one({"id": ticket_id}, {"$set": {"status": "closed", "closed_at": datetime.now(UTC)}}).matched_count)
