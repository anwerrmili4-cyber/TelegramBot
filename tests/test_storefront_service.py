import database as db
from app.constants import OrderStatus
from app.domain import storefront_service


def _catalog_offer():
    service_id = db.add_service("ChatGPT", "✦", sales_channels=["bot", "tn_site"])
    offer_id = db.add_offer(
        service_id,
        "ChatGPT Plus 1 mois",
        6.0,
        5,
        description="Compte premium prêt à utiliser",
        sales_channels=["bot", "tn_site"],
        tn_price_millimes=25000,
    )
    return service_id, offer_id


def test_catalog_uses_live_mongo_offers_and_tnd(mock_mongodb):
    _, offer_id = _catalog_offer()
    result = storefront_service.catalog()
    offer = result["services"][0]["offers"][0]
    assert offer["id"] == offer_id
    assert offer["price_millimes"] == 25000
    assert result["currency"] == "TND"
    assert {item["id"] for item in result["payment_methods"]} == {"d17", "flouci"}


def test_create_order_waits_for_manual_whatsapp_verification(mock_mongodb):
    _, offer_id = _catalog_offer()
    result = storefront_service.create_order({
        "name": "Amine Ben Salah",
        "phone": "21 111 222",
        "offer_id": offer_id,
        "quantity": 1,
        "payment_method": "d17",
    })
    order = db.get_order(result["order_id"])
    assert order["status"] == OrderStatus.MANUAL_REVIEW
    assert order["currency"] == "TND"
    assert order["paid_at"] is None
    assert order["verification_channel"] == "whatsapp"
    assert "wa.me/21621994132" in result["whatsapp_url"]


def test_tracking_token_is_required(mock_mongodb):
    _, offer_id = _catalog_offer()
    result = storefront_service.create_order({
        "name": "Amine Ben Salah",
        "phone": "21111222",
        "offer_id": offer_id,
        "quantity": 1,
        "payment_method": "flouci",
    })
    status = storefront_service.order_status(result["order_id"], result["tracking_token"])
    assert status["order"]["status"] == OrderStatus.MANUAL_REVIEW
