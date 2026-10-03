"""Verified site clients see nouveautés, admin messages, and news. Read state stays private."""

import database as db
from app.domain import storefront_notification_service


def _offer():
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(
        service_id,
        "ChatGPT Plus",
        6.0,
        4,
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=25000,
    )


def _publish_three(offer_id: int) -> None:
    storefront_notification_service.publish({
        "kind": "novelty",
        "title": "Nouveau ChatGPT",
        "body": "ChatGPT Plus vient d'arriver sur la boutique.",
        "offer_id": offer_id,
        "email": "stranger@example.com",
    })
    storefront_notification_service.publish({
        "kind": "admin",
        "title": "Message du shop",
        "body": "Le support répond plus vite le soir.",
    })
    storefront_notification_service.publish({
        "kind": "news",
        "title": "Horaires du support",
        "body": "Le support est ouvert tous les jours.",
    })


def test_a_verified_client_sees_three_kinds_and_read_state_stays_private(mock_mongodb, site_customer):
    owner = site_customer()
    other = site_customer(name="Sana", email="sana@example.com")
    unverified = {
        "id": db._next_id("storefront_customers"),
        "name": "Inconnu",
        "email": "pending@example.com",
        "email_verified": False,
        "created_at": 1,
    }
    mock_mongodb.storefront_customers.insert_one(unverified)
    offer_id = _offer()
    _publish_three(offer_id)

    stored = list(mock_mongodb.storefront_notifications.find())
    assert len(stored) == 3
    assert all("email" not in row and row.get("to") is None for row in stored)
    assert all(row["audience"] == "verified" for row in stored)

    feed = storefront_notification_service.for_customer(owner)
    labels = [item["kind_label"] for item in feed["items"]]
    assert labels == ["Actualité", "Message", "Nouveauté"]
    assert feed["unread"] == 3
    novelty = next(item for item in feed["items"] if item["kind"] == "novelty")
    assert novelty["href"] == f"/produit/{offer_id}"
    assert "stranger@example.com" not in str(feed)

    hidden = storefront_notification_service.for_customer(unverified)
    assert hidden["items"] == []
    assert hidden["unread"] == 0

    opened = storefront_notification_service.mark_read(owner, novelty["id"])
    assert opened["unread"] == 2
    assert next(item["read"] for item in opened["items"] if item["id"] == novelty["id"])
    other_feed = storefront_notification_service.for_customer(other)
    assert other_feed["unread"] == 3
    assert all(item["read"] is False for item in other_feed["items"])

    cleared = storefront_notification_service.mark_all_read(other)
    assert cleared["unread"] == 0
    assert storefront_notification_service.for_customer(owner)["unread"] == 2


def test_a_client_does_not_see_a_notification_from_before_the_account(mock_mongodb, site_customer):
    site_customer()
    storefront_notification_service.publish({
        "kind": "news",
        "title": "Ancienne actu",
        "body": "Cette actu existait avant le compte.",
    })
    late = site_customer(name="Tardif", email="tardif@example.com")
    late["created_at"] = 9_999_999_999
    mock_mongodb.storefront_customers.update_one({"id": late["id"]}, {"$set": {"created_at": late["created_at"]}})
    assert storefront_notification_service.for_customer(late)["items"] == []


def test_an_unknown_notification_cannot_be_marked_read(mock_mongodb, site_customer):
    customer = site_customer()
    try:
        storefront_notification_service.mark_read(customer, 404)
    except storefront_notification_service.NotificationError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("an unknown notification was marked read")
