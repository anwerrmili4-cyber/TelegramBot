"""Advanced search shared by the Telegram admin panel."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.constants import ParseMode

import admin
import database as db
from app.domain import admin_search_service
from bot import PENDING, cb_admin, handle_pending_input


def _seed(mock_mongodb):
    service_id = db.add_service("Courses", "C")
    offer_id = db.add_offer(service_id, "Coursera Premium", 3.1, 10)
    mock_mongodb.users.insert_one({
        "telegram_id": 77,
        "username": "coursemax",
        "first_name": "Max",
        "full_name": "Coursera Buyer",
    })
    mock_mongodb.wallets.insert_one({"user_id": 77, "balance_cents": 250})
    mock_mongodb.orders.insert_many([
        {
            "id": 11, "user_id": 77, "offer_id": offer_id,
            "offer_name": "Coursera Premium", "service_name": "Courses",
            "status": "delivered", "txid": "0xabcbulk", "created_at": 1_700_000_000,
        },
        {
            "id": 12, "user_id": 77, "offer_id": offer_id,
            "offer_name": "Coursera Premium", "service_name": "Courses",
            "status": "pending_payment", "txid": "0xother", "created_at": 1_800_000_000,
        },
    ])
    mock_mongodb.support_tickets.insert_one({
        "id": 5, "user_id": 77, "status": "open",
        "message": "The Coursera code did not arrive", "updated_at": 10,
    })
    return offer_id


def test_admin_search_groups_orders_customers_products_and_tickets(mock_mongodb):
    offer_id = _seed(mock_mongodb)

    found = admin_search_service.search("coursera")

    groups = {group["key"]: group["items"] for group in found["groups"]}
    assert [item["id"] for item in groups["orders"]] == [12, 11]
    assert groups["customers"][0]["telegram_id"] == 77
    assert any(item["kind"] == "offer" and item["id"] == offer_id for item in groups["products"])
    assert groups["tickets"][0]["id"] == 5


def test_admin_search_respects_field_status_and_dates(mock_mongodb):
    _seed(mock_mongodb)

    by_txid = admin_search_service.search("0xabcbulk", field="txid")
    assert [group["key"] for group in by_txid["groups"]] == ["orders"]
    assert by_txid["groups"][0]["items"][0]["id"] == 11

    delivered = admin_search_service.search(
        "coursera du:2023-11-14 au:2023-11-14", status="delivered",
    )
    assert [item["id"] for item in delivered["groups"][0]["items"]] == [11]
    assert delivered["dates"] == {"date_from": "2023-11-14", "date_to": "2023-11-14"}

    assert admin_search_service.search("   ") is None


def test_admin_search_opens_the_customization_section(mock_mongodb):
    found = admin_search_service.search("fiche produit")
    customize = next(group for group in found["groups"] if group["key"] == "customize")
    assert customize["items"][0]["callback"] == "adm_text_key:offer_card_template"

    screens = admin_search_service.search("design des tickets", scope="customize")
    assert [item["callback"] for item in screens["groups"][0]["items"]] == ["adm_ticket_style"]

    welcome = admin_search_service.search("bienvenue sur black market")
    callbacks = [
        item["callback"]
        for group in welcome["groups"] if group["key"] == "customize"
        for item in group["items"]
    ]
    assert "adm_text_key:welcome" in callbacks

    text, markup = admin.admin_search_results(found)
    assert "Personnalisation" in text
    assert "adm_text_key:offer_card_template" in [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


def test_admin_panel_search_opens_filters_and_returns_a_result(monkeypatch, mock_mongodb):
    admin_id = 9001
    monkeypatch.setattr("bot.ADMIN_ID", admin_id)
    _seed(mock_mongodb)
    query = SimpleNamespace(
        data="adm_search",
        from_user=SimpleNamespace(id=admin_id),
        message=SimpleNamespace(text="panel", reply_text=AsyncMock()),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )

    asyncio.run(cb_admin(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert PENDING.get(admin_id)[0] == "adm_search"
    opened = query.edit_message_text.await_args
    assert "Recherche avancée" in opened.args[0]
    assert opened.kwargs["parse_mode"] == ParseMode.HTML

    query.data = "adm_sset:f:txid"
    query.edit_message_text.reset_mock()
    asyncio.run(cb_admin(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert PENDING.get(admin_id)[1]["field"] == "txid"

    message = SimpleNamespace(text="0xabcbulk", reply_text=AsyncMock())
    asyncio.run(handle_pending_input(
        SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), message=message),
        SimpleNamespace(),
        "en",
    ))

    sent = message.reply_text.await_args
    assert "Commandes" in sent.args[0]
    callbacks = [
        button.callback_data
        for row in sent.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "adm_order:11" in callbacks
    assert "adm_search" in {
        button.callback_data
        for row in admin.admin_panel_keyboard().inline_keyboard
        for button in row
    }
