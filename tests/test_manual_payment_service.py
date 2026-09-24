from urllib.parse import parse_qs, urlsplit

import pytest

import database as db
from app.constants import OrderStatus
from app.domain import manual_payment_service


def _insert_order(order_id=91):
    db.get_conn().orders.insert_one({
        "id": order_id,
        "user_id": 123,
        "status": OrderStatus.PENDING_PAYMENT,
        "total_millimes": 25000,
        "payment_method": "",
        "created_at": 1,
        "updated_at": 1,
    })


@pytest.mark.parametrize("method", ["d17", "D17", "flouci", " Flouci "])
def test_manual_payment_uses_whatsapp_without_confirming_payment(mock_mongodb, method):
    _insert_order()

    result = manual_payment_service.request_manual_review(91, method)

    order = db.get_order(91)
    assert order["status"] == OrderStatus.MANUAL_REVIEW
    assert order.get("verify_method", "") == ""
    assert order.get("paid_at") is None
    assert result["automatic_confirmation"] is False
    assert result["whatsapp_number"] == "21621994132"
    parsed = urlsplit(result["whatsapp_url"])
    assert parsed.netloc == "wa.me"
    assert parsed.path == "/21621994132"
    assert "commande #91" in parse_qs(parsed.query)["text"][0]
    assert "25,000 DT" in parse_qs(parsed.query)["text"][0]


def test_manual_payment_rejects_unknown_method(mock_mongodb):
    _insert_order()
    with pytest.raises(ValueError, match="D17 ou Flouci"):
        manual_payment_service.request_manual_review(91, "card")


def test_manual_payment_does_not_reopen_terminal_order(mock_mongodb):
    _insert_order()
    db.get_conn().orders.update_one(
        {"id": 91}, {"$set": {"status": OrderStatus.DELIVERED}}
    )
    with pytest.raises(ValueError, match="ne peut plus"):
        manual_payment_service.request_manual_review(91, "d17")
