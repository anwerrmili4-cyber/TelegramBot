"""Product news stays quiet while that offer is off the customer bot."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import database as db
from app.domain import offer_stock_control, reseller_service
from app.jobs.scheduled import run_price_check, run_restock_check
from bot import _run_broadcast_job, announce_channel_restock, queue_broadcast


def _offer(service_id, provider, name, price, stock, product_id):
    return db.add_offer(
        service_id,
        name,
        price,
        stock,
        supplier_provider=provider,
        supplier_product_id=product_id,
        period_days=30,
        period_value=30,
        period_unit="days",
        warranty_days=7,
        warranty_value=7,
        warranty_unit="days",
    )


def _record_submit(monkeypatch):
    submitted = []

    def _submit(job_id):
        submitted.append(int(job_id))
        return True

    monkeypatch.setattr("bot._submit_broadcast_job", _submit)
    return submitted


def test_parked_supplier_news_is_kept_and_returns_when_the_offer_is_listed(
    monkeypatch, mock_mongodb,
):
    submitted = _record_submit(monkeypatch)
    service_id = db.add_service("CapCut", "🎬")
    cheap = _offer(service_id, "vex", "CapCut Pro", 3, 4, "cheap")
    dear = _offer(service_id, "upibot", "CapCut Pro", 8, 4, "dear")
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})

    assert db.get_offer(cheap)["active"] == 1
    parked = db.get_offer(dear)
    assert parked["active"] == 0
    assert parked["stock_control_hold"] is True
    assert {row["id"] for row in db.list_offers(service_id, active_only=False)} == {cheap, dear}
    assert [row["id"] for row in db.list_offers(service_id)] == [cheap]

    bot_client = SimpleNamespace(send_message=AsyncMock())
    sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client),
        dear,
        5,
        9,
        {"provider": "upibot", "offer_id": dear, "added": 5, "stock": 9},
    ))
    assert sent == 0
    bot_client.send_message.assert_not_awaited()

    live = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client), cheap, 1, 4,
    ))
    assert live == 1
    assert bot_client.send_message.await_args.kwargs["chat_id"] == 101
    bot_client.send_message.reset_mock()

    first = queue_broadcast(
        "stock",
        offer_id=dear,
        added=5,
        stock=9,
        supplier_event={"provider": "upibot", "offer_id": dear, "added": 5, "stock": 9, "previous_stock": 4},
        dedupe_key="restock-dear-1",
    )
    second = queue_broadcast(
        "stock",
        offer_id=dear,
        added=2,
        stock=11,
        supplier_event={
            "provider": "upibot", "offer_id": dear, "added": 2, "stock": 11, "previous_stock": 9,
        },
        dedupe_key="restock-dear-2",
    )
    repeat = queue_broadcast(
        "stock",
        offer_id=dear,
        added=2,
        stock=11,
        supplier_event={
            "provider": "upibot", "offer_id": dear, "added": 2, "stock": 11, "previous_stock": 9,
        },
        dedupe_key="restock-dear-2",
    )
    price = queue_broadcast(
        "api_flash_sale",
        event={"offer_id": dear, "previous_price": 8.0, "price": 7.0, "decreased": True},
        dedupe_key="price-dear-1",
    )

    assert first["held"] is True and first["queued"] is False
    assert second["job_id"] == first["job_id"]
    assert repeat["job_id"] == first["job_id"]
    assert price["held"] is True
    assert price["job_id"] != first["job_id"]
    assert submitted == []
    stock_job = db.get_broadcast_job(first["job_id"])
    assert stock_job["status"] == "held"
    assert stock_job["payload"]["added"] == 7
    assert stock_job["payload"]["supplier_event"]["previous_stock"] == 4
    assert db.get_offer(dear)["active"] == 0
    assert mock_mongodb.offers.count_documents({"service_id": service_id}) == 2
    assert mock_mongodb.broadcast_messages.count_documents({}) == 0

    db.update_offer(dear, stock=11)
    assert db.get_broadcast_job(first["job_id"])["status"] == "held"
    assert submitted == []

    db.update_offer(cheap, stock=0)

    assert db.get_offer(dear)["active"] == 1
    assert db.get_offer(dear).get("stock_control_hold") is not True
    assert db.get_offer(cheap)["active"] == 0
    assert {row["id"] for row in db.list_offers(service_id, active_only=False)} == {cheap, dear}
    released = db.get_broadcast_job(first["job_id"])
    assert released["status"] == "queued"
    assert db.get_broadcast_job(price["job_id"])["status"] == "queued"
    assert set(submitted) == {first["job_id"], price["job_id"]}

    sent = asyncio.run(announce_channel_restock(
        SimpleNamespace(bot=bot_client),
        dear,
        released["payload"]["added"],
        released["payload"]["stock"],
    ))
    assert sent == 1
    call = bot_client.send_message.await_args.kwargs
    assert call["chat_id"] == 101
    assert "NEW DROP AVAILABLE" in call["text"]
    assert "CapCut Pro" in call["text"]
    assert "Stock: <b>11</b>" in call["text"]
    assert call["reply_markup"].inline_keyboard[0][0].callback_data == f"buy:{dear}"


def test_higher_priced_duplicate_keeps_its_news_until_it_is_the_bot_price(
    monkeypatch, mock_mongodb,
):
    submitted = _record_submit(monkeypatch)
    service_id = db.add_service("Capcut", "🎬")
    cheap = _offer(service_id, "vex", "Capcut pro", 3.9, 5, "cheap")
    dear = _offer(service_id, "vex", "Capcut Pro", 4, 8, "dear")
    assert db.get_offer(cheap)["active"] == 1
    assert db.get_offer(dear)["active"] == 1
    assert db.get_offer(dear).get("stock_control_hold") is not True
    assert db.offer_is_listed_in_bot(db.get_offer(dear)) is False
    assert {row["id"] for row in db.list_offers(service_id, active_only=False)} == {cheap, dear}

    parked = queue_broadcast(
        "stock", offer_id=dear, added=3, stock=8, dedupe_key="capcut-dear",
    )
    assert parked["held"] is True
    assert submitted == []
    assert db.get_broadcast_job(parked["job_id"])["status"] == "held"

    db.update_offer(dear, price=3)
    assert db.offer_is_listed_in_bot(db.get_offer(dear)) is True
    assert db.get_broadcast_job(parked["job_id"])["status"] == "queued"
    assert submitted == [parked["job_id"]]
    assert db.get_offer(cheap)["active"] == 1
    assert db.get_offer(dear)["active"] == 1


def test_disabling_a_product_holds_its_news_until_it_is_enabled_again(
    monkeypatch, mock_mongodb,
):
    submitted = _record_submit(monkeypatch)
    service_id = db.add_service("Design", "✦")
    offer_id = db.add_offer(service_id, "Canva Pro", 4, 6)
    mock_mongodb.users.insert_one({"telegram_id": 101, "lang": "en"})

    db.update_offer(offer_id, product_enabled=False)
    assert db.list_offers(service_id) == []
    assert db.get_offer(offer_id)["id"] == offer_id
    assert [row["id"] for row in db.list_offers(service_id, active_only=False)] == [offer_id]

    parked = queue_broadcast("stock", offer_id=offer_id, added=2, stock=6)
    assert parked["held"] is True
    assert submitted == []

    db.update_offer(offer_id, product_enabled=True)
    assert db.get_broadcast_job(parked["job_id"])["status"] == "queued"
    assert submitted == [parked["job_id"]]
    assert [row["id"] for row in db.list_offers(service_id)] == [offer_id]


def test_a_queued_job_is_held_instead_of_sent_when_the_offer_is_already_parked(
    monkeypatch, mock_mongodb,
):
    _record_submit(monkeypatch)
    service_id = db.add_service("CapCut", "🎬")
    _offer(service_id, "vex", "CapCut Pro", 3, 4, "cheap")
    dear = _offer(service_id, "upibot", "CapCut Pro", 8, 4, "dear")
    job, created = db.create_broadcast_job(
        "stock",
        {"offer_id": dear, "added": 4, "stock": 8},
        dedupe_key="already-queued",
    )

    assert created is True
    _run_broadcast_job(job["id"])

    saved = db.get_broadcast_job(job["id"])
    assert saved["status"] == "held"
    assert saved["attempts"] == 0
    assert saved["offer_id"] == dear
    assert mock_mongodb.broadcast_messages.count_documents({}) == 0


def test_restock_and_price_crons_hold_the_parked_offer_and_send_the_live_one(
    monkeypatch, mock_mongodb,
):
    submitted = _record_submit(monkeypatch)
    service_id = db.add_service("CapCut", "🎬")
    cheap = _offer(service_id, "vex", "CapCut Pro", 3, 4, "cheap")
    dear = _offer(service_id, "upibot", "CapCut Pro", 8, 4, "dear")

    monkeypatch.setattr(reseller_service, "detect_restock_events", lambda: {
        "ok": True,
        "checked": 2,
        "errors": [],
        "events": [
            {
                "provider": "vex",
                "product_id": "cheap",
                "offer_id": cheap,
                "previous_stock": 4,
                "stock": 6,
                "added": 2,
            },
            {
                "provider": "upibot",
                "product_id": "dear",
                "offer_id": dear,
                "previous_stock": 4,
                "stock": 9,
                "added": 5,
            },
        ],
    })
    status, result = run_restock_check()
    assert status == 200
    assert result["queued_broadcasts"] == 1
    assert result["held_broadcasts"] == 1
    held = db.get_conn().broadcast_jobs.find_one({"status": "held"})
    queued = db.get_conn().broadcast_jobs.find_one({"status": "queued"})
    assert held["offer_id"] == dear
    assert queued["payload"]["offer_id"] == cheap
    assert submitted == [queued["id"]]

    monkeypatch.setattr(reseller_service, "detect_supplier_price_changes", lambda: {
        "ok": True,
        "checked": 2,
        "errors": [],
        "changes": [
            {"offer_id": dear, "decreased": True, "previous_price": 8, "price": 7},
        ],
        "flash_sales": [],
    })
    status, result = run_price_check()
    assert status == 200
    assert result["queued_broadcasts"] == 0
    assert result["held_broadcasts"] == 1
    assert offer_stock_control.offer_reaches_bot_customers(db.get_offer(dear)) is False
    assert db.get_conn().broadcast_jobs.count_documents({"status": "held", "offer_id": dear}) == 2
