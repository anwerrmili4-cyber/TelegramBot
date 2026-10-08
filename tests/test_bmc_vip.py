"""BMC VIP bundle: launch price, method-value description, and one-time channel links."""

import time

import database as db
import keyboards as kb
from admin import offer_admin_keyboard
from app.constants import OrderStatus
from app.domain import payment_service
from bot import bmc_vip_channel_message, compact_offer_text


def _method(name, price):
    service_id = db.ensure_methods_service()
    offer_id = db.add_offer(
        service_id, name, price, 0,
        period_days=0, warranty_days=0, unlimited_stock=True, active=True,
    )
    db.update_offer(
        offer_id,
        method_media=[{"type": "text", "text": f"steps for {name}"}],
        active=1,
        unlimited_stock=True,
    )
    return offer_id


def test_vip_button_is_first_and_hides_other_method_prices(mock_mongodb):
    _method("Alpha method", 10)
    _method("Beta method", 7.5)
    service_id = db.ensure_methods_service()

    keyboard = kb.offers_keyboard("en", service_id)
    vip = db.get_offer(db.ensure_bmc_vip_offer())

    assert keyboard.inline_keyboard[0][0].callback_data == f"off:{vip['id']}"
    assert keyboard.inline_keyboard[0][0].text == "👑 BMC VIP | claim all methods | $15"
    assert all(
        row[0].callback_data != f"off:{vip['id']}"
        for row in keyboard.inline_keyboard[1:]
    )
    assert vip["price"] == 15
    assert vip["bmc_vip_claims"] == 1
    description = compact_offer_text(vip, "en")
    assert "Alpha method" not in description
    assert "7.5" not in description
    assert "17.5" not in description
    assert "4 places are still $15" in description
    assert "channel link" in description.casefold()


def test_admin_description_replaces_the_default_and_is_kept(mock_mongodb):
    vip_id = db.ensure_bmc_vip_offer()
    db.set_bmc_vip_custom_description(vip_id, "Private BMC access. New drops every day.")

    vip = db.get_offer(db.ensure_bmc_vip_offer())

    assert vip["description"] == "Private BMC access. New drops every day."
    assert "Alpha" not in vip["description"]
    card = compact_offer_text(vip, "ar")
    assert "Private BMC access" in card
    assert "أماكن" not in card


def test_admin_price_stays_after_the_launch_slots_fill(mock_mongodb):
    vip_id = db.ensure_bmc_vip_offer()
    db.set_bmc_vip_price(vip_id, 40)
    now = int(time.time())
    db.get_conn().orders.insert_many([
        {
            "id": index,
            "user_id": 100 + index,
            "offer_id": vip_id,
            "qty": 1,
            "status": "delivered",
            "created_at": now,
        }
        for index in range(1, 6)
    ])

    vip = db.get_offer(db.ensure_bmc_vip_offer())

    assert vip["price"] == 40
    assert vip["bmc_vip_price_custom"] is True
    assert vip["period_days"] == 0
    assert vip["warranty_days"] == 0
    assert vip["site_period_days"] == 0
    assert vip["site_warranty_days"] == 0
    assert "BMC VIP is $40." in vip["description"]
    assert "$15" not in vip["description"]
    assert "lancement" not in vip["description_fr"].casefold()


def test_launch_price_becomes_25_after_five_claims(mock_mongodb):
    vip_id = db.ensure_bmc_vip_offer()
    now = int(time.time())
    db.get_conn().orders.insert_many([
        {
            "id": index,
            "user_id": 100 + index,
            "offer_id": vip_id,
            "qty": 1,
            "status": "delivered",
            "created_at": now,
        }
        for index in range(1, 5)
    ])

    vip = db.get_offer(db.ensure_bmc_vip_offer())

    assert vip["price"] == 25
    assert vip["bmc_vip_claims"] == 5
    assert "now $25" in vip["description"]


def test_admin_channel_link_is_delivered_once_then_deleted(mock_mongodb, monkeypatch):
    monkeypatch.setattr(
        payment_service, "verify_payment",
        lambda *_args, **_kwargs: {"status": "confirmed", "reason": "test"},
    )
    _method("Alpha method", 4)
    vip_id = db.ensure_bmc_vip_offer()
    added, skipped = db.add_bmc_vip_links(
        "https://t.me/+FirstInvite\n"
        "not a link\n"
        "t.me/+SecondInvite\n"
        "https://t.me/+FirstInvite\n"
    )
    assert (added, skipped) == (2, 2)
    assert db.bmc_vip_link_count() == 2
    assert db.offer_has_stock(db.get_offer(vip_id)) is True
    callbacks = [
        button.callback_data
        for row in offer_admin_keyboard(vip_id).inline_keyboard
        for button in row
    ]
    assert f"adm_bmc_vip_links:{vip_id}" in callbacks
    assert all(not callback.startswith("adm_inventory:") for callback in callbacks)
    assert all(not callback.startswith("adm_method_media:") for callback in callbacks)

    now = int(time.time())
    db.get_conn().orders.insert_one({
        "id": 50,
        "user_id": 42,
        "offer_id": vip_id,
        "service_name": "Methods",
        "offer_name": "BMC VIP",
        "qty": 1,
        "total_price": 15,
        "status": OrderStatus.PENDING_PAYMENT,
        "txid": "",
        "created_at": now - 10,
        "expires_at": now + 1800,
    })

    result = payment_service.submit_payment(50, "VIP_CHANNEL_TXID", 42)

    assert result["status"] == "delivered"
    assert result["delivered_content"] == ["https://t.me/+FirstInvite"]
    assert db.get_order(50)["delivery_text"] == "https://t.me/+FirstInvite"
    assert db.bmc_vip_link_count() == 1
    remaining = db.get_conn().bmc_vip_links.find_one()
    assert remaining["link"] == "https://t.me/+SecondInvite"
    message = bmc_vip_channel_message("en", result["delivered_content"][0])
    assert "https://t.me/+FirstInvite" in message
    assert "private channel link" in message.casefold()

    assert db.offer_has_stock(db.get_offer(vip_id)) is True
    db.claim_bmc_vip_link()
    assert db.bmc_vip_link_count() == 0
    assert db.offer_has_stock(db.get_offer(vip_id)) is False
