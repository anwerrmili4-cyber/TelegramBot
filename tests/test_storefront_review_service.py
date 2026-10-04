"""Moderated reviews for delivered Tunisian site orders."""

import http.client
from urllib.parse import urlencode

import pytest

import database as db
import railway_server
from app.domain import inventory_service, storefront_review_service, storefront_service, storefront_wallet_service
from app.web import dashboard_api
from tests.test_railway_server import _get, running_surface
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
    assert subjects.count(f"Ton avis sur {result['reference']}") == 0
    delivered = next(item for item in sent_emails if item["subject"] == f"Ta commande {result['reference']} est livrée")
    assert 'name="score"' in delivered["html"]
    assert "Envoyer" in delivered["html"]
    assert "/api/storefront/reviews/email" in delivered["html"]

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
    assert "Envoyer" in sent_emails[0]["html"]
    assert storefront_review_service.backfill(send=True)["sent"] == 0


def test_email_form_saves_a_pending_review_and_admin_sees_the_client(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    db.get_conn().orders.update_one({"id": order_id}, {"$set": {
        "payment_method": "wallet",
        "total_millimes": 20000,
        "cart_total_millimes": 20000,
        "service_name": "ChatGPT",
        "delivered_at": 1_700_000_000,
    }})
    token = storefront_review_service.issue_token(order_id)
    page = storefront_review_service.email_review_page(token=token, score=4)
    assert "<textarea" in page
    assert 'value="4"' in page
    assert "checked" in page
    assert "background-color:#ffffff" in page
    assert 'class="bm-stars"' in page
    assert "<a " not in page
    assert 'type="submit"' in page

    first = storefront_review_service.submit_from_email(token, 5, "Livraison rapide et accès correct.")
    assert first["already"] is False
    again = storefront_review_service.submit_from_email(token, 4, "Un autre commentaire assez long.")
    assert again["already"] is True

    item = storefront_review_service.admin_list()["items"][0]
    assert item["phone"] == "+21621111222"
    assert item["email"] == "amine@example.com"
    assert item["name"] == "Amine Ben Salah"
    assert item["customer_id"] == customer["id"]
    assert item["order_id"] == order_id
    assert item["cart_reference"] == "TN-REVIEW1"
    assert item["source"] == "email"
    assert item["payment_label"] == "Portefeuille"
    assert item["status"] == "pending"
    assert storefront_review_service.public_latest()["reviews"] == []
    received = dashboard_api.list_admin_notifications(complete=True)["items"]
    assert any(
        note["title"] == "Avis à valider" and note["target"]["entity_id"] == item["id"]
        for note in received
    )

    storefront_review_service.approve(item["id"])
    published = storefront_review_service.public_for_offer(offer_id)["reviews"][0]
    assert "phone" not in published
    storefront_review_service.delete(item["id"])
    assert storefront_review_service.admin_list()["items"] == []
    assert storefront_review_service.public_for_offer(offer_id)["reviews"] == []


def test_email_review_rejects_a_forged_token():
    with pytest.raises(storefront_review_service.ReviewError):
        storefront_review_service.submit_from_email("1.9999999999.not-a-signature", 5, "Commentaire assez long.")


def test_storefront_port_accepts_the_review_posted_from_the_email(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    token = storefront_review_service.issue_token(order_id)
    body = urlencode({"token": token, "score": "5", "comment": "Livraison rapide et accès correct."})
    with running_surface(railway_server.StorefrontHandler) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST",
            "/api/storefront/reviews/email",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        payload = response.read()
        connection.close()
    assert response.status == 200
    assert response.getheader("Location") is None
    assert "envoyé".encode() in payload
    row = db.get_conn().storefront_reviews.find_one({"order_id": order_id})
    assert row["status"] == "pending"
    assert row["phone"] == customer["phone"]
    assert row["source"] == "email"


def test_published_reviews_are_served_on_the_storefront(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    storefront_review_service.submit(
        customer,
        {"order_id": order_id, "score": 5, "comment": "Livraison rapide et accès correct."},
    )
    with running_surface(railway_server.StorefrontHandler) as port:
        hidden, hidden_body = _get(port, "/api/storefront/reviews")
        review_id = db.get_conn().storefront_reviews.find_one({"order_id": order_id})["id"]
        storefront_review_service.approve(review_id)
        listed, listed_body = _get(port, "/api/storefront/reviews")
        offered, offered_body = _get(port, f"/api/storefront/reviews?offer_id={offer_id}")
    assert hidden.status == 200
    assert b'"reviews": []' in hidden_body or b'"reviews":[]' in hidden_body
    assert listed.status == 200 and b"NOT_FOUND" not in listed_body
    assert b"Livraison rapide" in listed_body
    assert offered.status == 200
    assert b"Livraison rapide" in offered_body


def test_opening_the_review_link_waits_for_the_button(mock_mongodb, site_customer):
    customer = site_customer()
    _, offer_id = _catalog_offer()
    order_id = _delivered(customer, offer_id)
    token = storefront_review_service.issue_token(order_id)
    with running_surface(railway_server.StorefrontHandler) as port:
        opened = _review_request(port, "GET", f"/api/storefront/reviews/email?token={token}&score=4")
        untouched = _review_request(port, "GET", "/api/storefront/reviews/email")
        saved = _review_request(
            port,
            "GET",
            "/api/storefront/reviews/email?" + urlencode({
                "token": token,
                "score": "5",
                "comment": "Livraison rapide et accès correct.",
                "send": "1",
            }),
        )
    assert opened.status == 200 and opened.getheader("Location") is None
    assert b"Envoyer" in opened.body
    assert b"plus valable" not in opened.body
    assert untouched.status == 200
    assert b"plus valable" in untouched.body
    assert saved.status == 200 and saved.getheader("Location") is None
    assert "envoyé".encode() in saved.body
    assert db.get_conn().storefront_reviews.find_one({"order_id": order_id})["score"] == 5


def _review_request(port: int, method: str, path: str):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path)
    response = connection.getresponse()
    payload = response.read()
    status = response.status
    location = response.getheader("Location")
    connection.close()

    class _Answer:
        pass

    answer = _Answer()
    answer.status = status
    answer.body = payload
    answer.getheader = lambda name: location if name == "Location" else None
    return answer
