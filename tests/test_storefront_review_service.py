"""Moderated reviews for delivered Tunisian site orders."""

import database as db
from app.domain import inventory_service, storefront_review_service, storefront_service, storefront_wallet_service
from tests.test_storefront_service import _catalog_offer


def _delivered(customer, offer_id, reference="TN-REVIEW1", name="ChatGPT"):
    order_id = db._next_id("orders")
    db.get_conn().orders.insert_one({
        "id": order_id,
        "sales_channel": "tn_site",
        "customer_id": customer["id"],
        "customer_name": customer["name"],
        "customer_email": customer["email"],
        "offer_id": offer_id,
        "offer_name": name,
        "status": "delivered",
        "cart_reference": reference,
    })
    return order_id


def test_submit_once_stays_hidden_until_approved(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    payload = {"order_id": order_id, "score": 5, "comment": "Livraison rapide et accès correct."}

    first = storefront_review_service.submit(customer, payload)
    second = storefront_review_service.submit(customer, {**payload, "comment": "Un autre commentaire assez long."})

    assert second["review"]["comment"] == first["review"]["comment"]
    assert storefront_review_service.public_for_offer(offer_id)["count"] == 0
    assert storefront_review_service.public_latest()["reviews"] == []

    review_id = db.get_conn().storefront_reviews.find_one({"order_id": order_id})["id"]
    storefront_review_service.approve(review_id)
    published = storefront_review_service.public_for_offer(offer_id)
    item = published["reviews"][0]
    assert item["name"] == "Amine Ben Salah"
    assert item["email"] == "amine@example.com"
    assert item["service_name"] == "ChatGPT"
    assert item["service_logo_url"] == ""
    assert item["comment"] == "Livraison rapide et accès correct."
    assert set(item) == {
        "name", "email", "score", "comment", "offer_name",
        "service_name", "service_logo_url", "created_at",
    }
    assert "phone" not in item
    assert published["count"] == 1


def test_rejected_review_stays_off_the_public_page(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    storefront_review_service.submit(customer, {"order_id": order_id, "score": 2, "comment": "L'accès ne fonctionnait pas."})
    review_id = db.get_conn().storefront_reviews.find_one({"order_id": order_id})["id"]
    storefront_review_service.reject(review_id, "Hors sujet")
    assert storefront_review_service.public_for_offer(offer_id)["reviews"] == []


def test_one_review_email_per_cart_and_backfill_does_not_send_unless_asked(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    _, offer_id = _catalog_offer(stock=0)
    inventory_service.add_items(offer_id, ["user@mail.tn:secret"])
    storefront_wallet_service.credit(customer["id"], 50000, kind="deposit")
    sent_emails.clear()
    result = storefront_service.create_order(
        {"payment_method": "wallet", "items": [{"offer_id": offer_id, "quantity": 1}]},
        customer,
    )
    subjects = [message["subject"] for message in sent_emails]
    assert subjects.count(f"Ton avis sur {result['reference']}") == 1

    sent_emails.clear()
    assert storefront_review_service.notify_cart(result["reference"]) is False
    assert sent_emails == []

    _delivered(customer, offer_id, reference="TN-DEJA1")
    counted = storefront_review_service.backfill(send=False)
    assert counted == {"ok": True, "count": 1, "sent": 0}
    assert sent_emails == []
    sent = storefront_review_service.backfill(send=True)
    assert sent["sent"] == 1
    assert sent_emails[0]["subject"] == "Ton avis sur TN-DEJA1"
    assert storefront_review_service.backfill(send=True)["sent"] == 0
