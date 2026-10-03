"""Admin mail goes only to existing site customers, from the configured address."""

import time

import pytest

import database as db
from app.domain import email_service, site_mail_service


@pytest.fixture(autouse=True)
def no_live_resend_history(monkeypatch):
    monkeypatch.setattr(email_service, "list_provider_messages", lambda limit=50: [])


def test_a_message_reaches_one_client_from_the_shop_address(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    sent_emails.clear()

    result = site_mail_service.send_message({
        "audience": "one",
        "customer_id": customer["id"],
        "subject": "Votre accès",
        "message": "Ton accès est prêt dans ton compte.",
    })

    assert result["sent"] == 1
    (message,) = sent_emails
    assert message["to"] == ["amine@example.com"]
    assert message["subject"] == "Votre accès"
    assert "Ton accès est prêt" in message["text"]
    logged = site_mail_service.mailbox()["messages"][0]
    assert logged["kind"] == "send_client_message"
    assert logged["to"] == "amine@example.com"
    assert logged["subject"] == "Votre accès"
    assert logged["status"] == "queued"
    detail = site_mail_service.message_detail(logged["id"])
    assert detail["text"] == message["text"]
    assert site_mail_service.mailbox()["from"] == "BLACKMARKET <noreply@ourblackmarket.com>"


def test_all_clients_skips_an_unverified_account_and_an_unknown_id_is_refused(mock_mongodb, site_customer, sent_emails):
    site_customer(name="Sana", email="sana@example.com")
    pending = {
        "id": db._next_id("storefront_customers"),
        "name": "Inconnu",
        "email": "pending@example.com",
        "email_verified": False,
    }
    mock_mongodb.storefront_customers.insert_one(pending)
    sent_emails.clear()

    result = site_mail_service.send_message({
        "audience": "all",
        "subject": "Nouveauté",
        "message": "Un nouveau produit est en ligne sur la boutique.",
    })

    assert result["sent"] == 1
    assert sent_emails[0]["to"] == ["sana@example.com"]
    try:
        site_mail_service.send_message({
            "audience": "one",
            "customer_id": pending["id"],
            "subject": "Privé",
            "message": "Ce message ne doit pas partir.",
        })
    except site_mail_service.SiteMailError as exc:
        assert "client" in str(exc).lower()
    else:
        raise AssertionError("an unverified address was accepted")
    assert len(sent_emails) == 1


def test_an_automatic_email_is_listed_and_a_stranger_row_stays_hidden(mock_mongodb, site_customer):
    customer = site_customer()
    email_service.send_welcome(customer["email"], customer["name"], "https://www.ourblackmarket.com")
    row = site_mail_service.mailbox()["messages"][0]
    assert row["kind"] == "send_welcome"
    assert row["to"] == customer["email"]
    assert row["status"] == "queued"
    detail = site_mail_service.message_detail(row["id"])
    assert detail["subject"] == row["subject"]
    assert customer["name"] in detail["text"]

    db.get_conn().storefront_mail_log.insert_one({
        "id": 9001,
        "created_at": int(time.time()) + 10,
        "kind": "send",
        "to": "stranger@example.com",
        "name": "",
        "subject": "Secret",
        "text": "ne pas montrer",
        "html": "<p>ne pas montrer</p>",
        "status": "queued",
    })
    assert site_mail_service.message_detail(9001) is None
    assert all(item["to"] != "stranger@example.com" for item in site_mail_service.mailbox()["messages"])


def test_resend_history_is_listed_only_for_site_clients(mock_mongodb, site_customer, monkeypatch):
    customer = site_customer()
    monkeypatch.setattr(email_service, "list_provider_messages", lambda limit=50: [
        {
            "id": "rs-11111111-1111-1111-1111-111111111111",
            "created_at": 1_700_000_000,
            "kind": "resend",
            "kind_label": "Déjà envoyé",
            "to": customer["email"],
            "subject": "Ancien accès",
            "status": "delivered",
        },
        {
            "id": "rs-22222222-2222-2222-2222-222222222222",
            "created_at": 1_700_000_100,
            "kind": "resend",
            "kind_label": "Déjà envoyé",
            "to": "stranger@example.com",
            "subject": "Pas un client",
            "status": "delivered",
        },
    ])

    subjects = [item["subject"] for item in site_mail_service.mailbox()["messages"]]
    assert "Ancien accès" in subjects
    assert "Pas un client" not in subjects


def test_past_orders_and_deposits_rebuild_the_sent_mail(mock_mongodb, site_customer):
    customer = site_customer()
    db.get_conn().orders.insert_one({
        "id": 50,
        "sales_channel": "tn_site",
        "cart_reference": "TN-HIST1",
        "customer_id": customer["id"],
        "customer_email": customer["email"],
        "customer_name": customer["name"],
        "offer_name": "ChatGPT",
        "qty": 1,
        "status": "cancelled",
        "payment_method": "d17",
        "cart_total_millimes": 25000,
        "total_millimes": 25000,
        "created_at": 100,
        "cancelled_at": 200,
        "admin_note": "Reçu illisible",
    })
    db.get_conn().storefront_deposits.insert_one({
        "id": 7,
        "customer_id": customer["id"],
        "customer_email": customer["email"],
        "customer_name": customer["name"],
        "amount_millimes": 10000,
        "credited_millimes": 10000,
        "status": "approved",
        "created_at": 300,
        "reviewed_at": 400,
    })

    subjects = [item["subject"] for item in site_mail_service.mailbox()["messages"]]
    assert "Commande TN-HIST1 reçue" in subjects
    assert "Commande TN-HIST1 annulée" in subjects
    assert "Recharge créditée #7" in subjects
    detail = site_mail_service.message_detail("db-cancelled-TN-HIST1")
    assert detail["to"] == customer["email"]
    assert "Reçu illisible" in detail["text"]
