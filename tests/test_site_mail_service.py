"""Admin mail goes only to existing site customers, from the configured address."""

import time

import database as db
from app.domain import email_service, site_mail_service


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
