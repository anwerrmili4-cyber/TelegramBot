"""Site support replies go by email. Bot replies stay on Telegram."""

from api import webhook
from app.domain import support_service


def test_site_ticket_reply_emails_the_customer(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    ticket = support_service.create_ticket(
        0, "Ma commande est bloquée depuis hier", channel="tn_site", customer_id=customer["id"],
    )
    sent_emails.clear()

    webhook._email_site_ticket_reply(ticket, int(ticket["id"]), "Nous vérifions le reçu.")

    (message,) = sent_emails
    assert message["to"] == ["amine@example.com"]
    assert message["subject"] == f"Réponse du support — ticket #{ticket['id']}"
    assert f"ticket #{ticket['id']}" in message["text"]
    assert "Nous vérifions le reçu." in message["text"]
    assert message["text"].rstrip().endswith("/messagerie")


def test_bot_ticket_reply_is_not_emailed(mock_mongodb, site_customer, sent_emails):
    customer = site_customer()
    ticket = support_service.create_ticket(42, "Besoin d'aide sur le bot", customer_id=customer["id"])
    sent_emails.clear()

    webhook._email_site_ticket_reply(ticket, int(ticket["id"]), "Réponse bot")

    assert sent_emails == []
