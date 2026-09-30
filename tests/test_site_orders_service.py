"""Admin handling of Tunisian storefront carts."""

import base64
import itertools

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import (
    inventory_service,
    site_orders_service,
    storefront_invoice_service,
    storefront_service,
    storefront_wallet_service,
)
from tests.conftest import RECEIPT

_references = itertools.count(1)


def _offer(name, stock=5, millimes=20000):
    service_id = db.add_service(f"Service {name}", "✦", sales_channels=["bot", "tn_site"])
    return db.add_offer(service_id, name, 6.0, stock, sales_channels=["bot", "tn_site"], tn_price_millimes=millimes)


@pytest.fixture
def customer(site_customer):
    return site_customer()


def _cart(customer, *lines, method="flouci"):
    return storefront_service.create_order({
        "payment_method": method,
        "transaction_reference": f"FL-{next(_references):05d}",
        "receipt": RECEIPT,
        "items": [{"offer_id": o, "quantity": q} for o, q in lines],
    }, customer)


def _statuses(reference):
    return {row["status"] for row in db.get_conn().orders.find({"cart_reference": reference})}


def _stock(offer_id):
    return db.get_offer(offer_id)["stock"]


def test_supplier_line_uses_the_shared_reseller_api(mock_mongodb, customer, monkeypatch):
    offer_id = _offer("API")
    db.get_conn().offers.update_one(
        {"id": offer_id},
        {"$set": {"supplier_provider": "vex", "supplier_product_id": "external-1"}},
    )
    calls = []

    def fake_purchase(order_id):
        calls.append(order_id)
        return ["login:secret"]

    monkeypatch.setattr(site_orders_service.reseller_service, "fulfill_paid_order", fake_purchase)
    cart = _cart(customer, (offer_id, 1))
    before = _stock(offer_id)
    site_orders_service.confirm_cart(cart["reference"])
    assert calls
    assert _stock(offer_id) == before - 1
    delivered = db.get_conn().orders.find_one({"id": calls[0]})
    assert delivered["sales_channel"] == "tn_site"


def test_list_groups_lines_into_one_cart_with_payment_details(mock_mongodb, customer):
    netflix, spotify = _offer("Netflix"), _offer("Spotify", millimes=5000)
    cart = _cart(customer, (netflix, 2), (spotify, 1))

    result = site_orders_service.list_carts({})

    assert result["total"] == 1
    assert result["counts"]["to_verify"] == 1
    item = result["items"][0]
    assert item["reference"] == cart["reference"]
    assert item["status"] == "to_verify"
    assert item["customer_id"] == customer["id"]
    assert item["customer_name"] == "Amine Ben Salah"
    assert item["payment_method"] == "flouci"
    assert item["payment_label"] == "Flouci"
    assert item["transaction_reference"].startswith("FL-")
    assert item["receipt_id"]
    assert item["total_millimes"] == 45000
    assert [(line["offer_name"], line["quantity"]) for line in item["items"]] == [("Netflix", 2), ("Spotify", 1)]


def test_list_filters_by_status_and_searches_reference_name_and_transaction(mock_mongodb, customer):
    offer = _offer("Canva")
    first, second = _cart(customer, (offer, 1)), _cart(customer, (offer, 1))
    site_orders_service.confirm_cart(second["reference"])

    assert [c["reference"] for c in site_orders_service.list_carts({"status": ["to_verify"]})["items"]] == [first["reference"]]
    assert [c["reference"] for c in site_orders_service.list_carts({"status": ["confirmed"]})["items"]] == [second["reference"]]
    assert site_orders_service.list_carts({"status": ["all"], "search": [first["reference"].lower()]})["total"] == 1
    assert site_orders_service.list_carts({"status": ["all"], "search": ["amine"]})["total"] == 2
    transaction = db.get_order(first["order_ids"][0])["payment_reference"]
    assert site_orders_service.list_carts({"status": ["all"], "search": [transaction]})["total"] == 1


def test_list_ignores_bot_orders(mock_mongodb):
    offer = _offer("Bot only")
    db.create_order(123, db.get_offer(offer), 1)
    assert site_orders_service.list_carts({"status": ["all"]})["total"] == 0


def test_confirm_marks_every_line_paid_and_reserves_stock(mock_mongodb, customer):
    netflix, spotify = _offer("Netflix", stock=5), _offer("Spotify", stock=3)
    cart = _cart(customer, (netflix, 2), (spotify, 1))

    result = site_orders_service.confirm_cart(cart["reference"])

    assert result["delivered"] == 0 and result["waiting"] == 2
    assert _statuses(cart["reference"]) == {str(OrderStatus.PAYMENT_CONFIRMED)}
    assert (_stock(netflix), _stock(spotify)) == (3, 2)
    with pytest.raises(site_orders_service.SiteOrderError, match="plus en attente"):
        site_orders_service.confirm_cart(cart["reference"])


def test_confirm_delivers_inventory_lines_automatically(mock_mongodb, customer, sent_emails):
    stocked, manual = _offer("Netflix", stock=0), _offer("Spotify", stock=3)
    inventory_service.add_items(stocked, ["netflix@mail.tn:secret"])
    cart = _cart(customer, (stocked, 1), (manual, 1))
    sent_emails.clear()

    result = site_orders_service.confirm_cart(cart["reference"])

    assert (result["delivered"], result["waiting"]) == (1, 1)
    listed = site_orders_service.list_carts({"status": ["all"]})["items"][0]
    assert listed["status"] == "partial"
    assert [item["automatic"] for item in listed["items"]] == [True, False]
    delivered, waiting, invoice = sent_emails
    assert "netflix@mail.tn:secret" in delivered["text"]
    assert waiting["subject"] == f"Paiement confirmé — {cart['reference']}"
    assert invoice["subject"].startswith("Ta facture FAC-")

    site_orders_service.deliver_cart(cart["reference"], "spotify@mail.tn:autre")
    assert _statuses(cart["reference"]) == {str(OrderStatus.DELIVERED)}
    (history,) = storefront_service.customer_carts(customer["id"])
    assert [item["delivery"] for item in history["items"]] == ["netflix@mail.tn:secret", "spotify@mail.tn:autre"]


def test_confirm_rolls_back_the_whole_cart_when_one_line_is_out_of_stock(mock_mongodb, customer):
    netflix, spotify = _offer("Netflix", stock=5), _offer("Spotify", stock=3)
    cart = _cart(customer, (netflix, 2), (spotify, 1))
    mock_mongodb.offers.update_one({"id": spotify}, {"$set": {"stock": 0}})

    with pytest.raises(site_orders_service.SiteOrderError, match="Stock insuffisant pour « Spotify »"):
        site_orders_service.confirm_cart(cart["reference"])

    assert _statuses(cart["reference"]) == {str(OrderStatus.MANUAL_REVIEW)}
    assert _stock(netflix) == 5


def test_deliver_requires_confirmation_and_the_access_details(mock_mongodb, customer):
    offer = _offer("ChatGPT")
    cart = _cart(customer, (offer, 1))

    with pytest.raises(site_orders_service.SiteOrderError, match="Confirme d'abord"):
        site_orders_service.deliver_cart(cart["reference"], "Accès")

    site_orders_service.confirm_cart(cart["reference"])
    with pytest.raises(site_orders_service.SiteOrderError, match="Saisis les accès"):
        site_orders_service.deliver_cart(cart["reference"], "  ")
    site_orders_service.deliver_cart(cart["reference"], "Email : a@b.tn")

    listed = site_orders_service.list_carts({"status": ["delivered"]})["items"][0]
    assert listed["status"] == "delivered"
    assert listed["delivery_note"] == "Email : a@b.tn"
    assert listed["delivered_at"]
    with pytest.raises(site_orders_service.SiteOrderError, match="plus rien à livrer"):
        site_orders_service.deliver_cart(cart["reference"], "Encore")


def test_cancel_paid_cart_returns_stock_refunds_the_wallet_and_blocks_delivered_carts(mock_mongodb, customer):
    offer = _offer("Adobe", stock=4, millimes=10000)
    confirmed, delivered = _cart(customer, (offer, 2)), _cart(customer, (offer, 1))
    site_orders_service.confirm_cart(confirmed["reference"])
    site_orders_service.confirm_cart(delivered["reference"])
    site_orders_service.deliver_cart(delivered["reference"], "Accès")
    assert _stock(offer) == 1

    result = site_orders_service.cancel_cart(confirmed["reference"], "Client injoignable")

    assert result["refunded_millimes"] == 20000
    assert storefront_wallet_service.balance(customer["id"]) == 20000
    assert _statuses(confirmed["reference"]) == {str(OrderStatus.CANCELLED)}
    assert _stock(offer) == 3
    with pytest.raises(site_orders_service.SiteOrderError, match="ne peut plus être annulé"):
        site_orders_service.cancel_cart(delivered["reference"], "Trop tard")


def test_cancel_unverified_cart_leaves_stock_and_wallet_untouched(mock_mongodb, customer):
    offer = _offer("Figma", stock=4)
    cart = _cart(customer, (offer, 2))
    result = site_orders_service.cancel_cart(cart["reference"], "Reçu illisible")
    assert result["refunded_millimes"] == 0
    assert _statuses(cart["reference"]) == {str(OrderStatus.CANCELLED)}
    assert _stock(offer) == 4
    assert storefront_wallet_service.balance(customer["id"]) == 0


def test_each_admin_step_emails_the_customer(mock_mongodb, customer, sent_emails):
    netflix = _offer("Netflix", millimes=15000)
    reference = _cart(customer, (netflix, 2))["reference"]
    sent_emails.clear()

    site_orders_service.confirm_cart(reference)
    site_orders_service.deliver_cart(reference, "Email : compte@netflix.tn\nMot de passe : <secret>")

    confirmed, invoice, delivered = sent_emails
    assert confirmed["to"] == invoice["to"] == delivered["to"] == ["amine@example.com"]
    assert confirmed["subject"] == f"Paiement confirmé — {reference}"
    assert "Total : 30,000 DT" in confirmed["text"]
    assert delivered["subject"] == f"Ta commande {reference} est livrée"
    assert "Mot de passe : <secret>" in delivered["text"]
    assert "Mot de passe : &lt;secret&gt;" in delivered["html"]

    other = _cart(customer, (netflix, 1))["reference"]
    site_orders_service.cancel_cart(other, "Reçu illisible")
    assert sent_emails[-1]["subject"] == f"Commande {other} annulée"
    assert "Motif : Reçu illisible" in sent_emails[-1]["text"]


def test_carts_without_an_email_are_processed_silently(mock_mongodb, customer, sent_emails):
    cart = _cart(customer, (_offer("Figma"), 1))
    mock_mongodb.orders.update_many({}, {"$unset": {"customer_email": ""}})
    sent_emails.clear()

    site_orders_service.confirm_cart(cart["reference"])
    site_orders_service.deliver_cart(cart["reference"], "Accès")

    assert sent_emails == []
    assert _statuses(cart["reference"]) == {str(OrderStatus.DELIVERED)}


def test_payment_issues_one_invoice_with_its_pdf_attached(mock_mongodb, customer, sent_emails):
    netflix, spotify = _offer("Netflix", millimes=15000), _offer("Spotify", millimes=5000)
    reference = _cart(customer, (netflix, 2), (spotify, 1))["reference"]
    sent_emails.clear()

    site_orders_service.confirm_cart(reference)
    site_orders_service.deliver_cart(reference, "Accès")
    storefront_invoice_service.issue(reference)

    invoices = list(mock_mongodb.storefront_invoices.find({"cart_reference": reference}))
    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice["number"].startswith("FAC-") and invoice["total_millimes"] == 35000
    assert [(item["offer_name"], item["quantity"]) for item in invoice["items"]] == [("Netflix", 2), ("Spotify", 1)]

    (mail,) = [message for message in sent_emails if message["subject"].startswith("Ta facture")]
    (attachment,) = mail["attachments"]
    assert attachment["filename"] == f"{invoice['number']}.pdf"
    assert base64.b64decode(attachment["content"]).startswith(b"%PDF")
    assert storefront_invoice_service.render_pdf(invoice).startswith(b"%PDF")

    listed = site_orders_service.list_carts({"status": ["all"]})["items"][0]
    assert listed["invoice_number"] == invoice["number"]
    (history,) = storefront_service.customer_carts(customer["id"])
    assert history["invoice_number"] == invoice["number"]


def test_unpaid_cart_has_no_invoice_and_refunds_are_recorded(mock_mongodb, customer):
    offer = _offer("Adobe", millimes=10000)
    pending, paid = _cart(customer, (offer, 1)), _cart(customer, (offer, 2))
    site_orders_service.cancel_cart(pending["reference"], "Reçu illisible")
    assert storefront_invoice_service.find(pending["reference"]) is None

    site_orders_service.confirm_cart(paid["reference"])
    site_orders_service.cancel_cart(paid["reference"], "Client injoignable")

    invoice = storefront_invoice_service.find(paid["reference"])
    assert invoice["refunded_millimes"] == 20000
    assert storefront_invoice_service.render_pdf(invoice).startswith(b"%PDF")


def test_unknown_reference_is_reported(mock_mongodb):
    with pytest.raises(site_orders_service.SiteOrderError, match="introuvable"):
        site_orders_service.confirm_cart("TN-ZZZZZZ")
