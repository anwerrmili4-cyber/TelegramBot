"""Opening products must not wait for a slow supplier stock API."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot
import database as db
from app.domain import order_service, reseller_service


@pytest.mark.parametrize("route,offer_count", [
    ("service_button", 2), ("service_button", 1), ("offer_button", 1),
    ("service_link", 2), ("service_link", 1), ("offer_link", 1),
])
def test_product_navigation_does_not_wait_for_supplier(monkeypatch, route, offer_count):
    service_id = db.add_service("Canva", "C")
    offer_ids = [
        db.add_offer(service_id, f"Premium {index}", 4.0, 2)
        for index in range(offer_count)
    ]
    release = threading.Event()
    entered = threading.Event()
    finished = threading.Event()
    refresh_lock = threading.Lock()

    def slow_refresh(offers=None):
        entered.set()
        release.wait(0.4)
        finished.set()

    monkeypatch.setattr(reseller_service, "SUPPLIER_REFRESH_IN_BACKGROUND", True)
    monkeypatch.setattr(reseller_service, "_background_refresh_started_at", 0.0)
    monkeypatch.setattr(reseller_service, "_background_refresh_running", refresh_lock)
    monkeypatch.setattr(reseller_service, "refresh_supplier_stock", slow_refresh)
    message = SimpleNamespace(text="Catalog", reply_text=AsyncMock())
    query = SimpleNamespace(
        data=f"svc:{service_id}" if route == "service_button" else f"off:{offer_ids[0]}",
        from_user=SimpleNamespace(id=7), message=message, answer=AsyncMock(),
        edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message, callback_query=query, effective_user=query.from_user,
    )
    started = time.perf_counter()
    try:
        if route == "service_link":
            asyncio.run(bot.show_service_offers(update, SimpleNamespace(), "en", service_id))
        elif route == "offer_link":
            asyncio.run(bot.show_deep_link_offer(update, "en", offer_ids[0]))
        else:
            asyncio.run(bot.cb_navigation(update, SimpleNamespace()))
        elapsed = time.perf_counter() - started
        print(f"{route}/{offer_count}: {elapsed:.3f}s")
        assert message.reply_text.await_count + query.edit_message_text.await_count == 1
        assert entered.wait(1), "Browsing should still trigger a stock refresh"
        assert not finished.is_set(), "Screen waited for the supplier API"
        assert elapsed < 0.3
        screen = (message.reply_text.await_args or query.edit_message_text.await_args)
        assert "Canva" in screen.args[0] or "Premium" in screen.args[0]
    finally:
        release.set()
        if entered.is_set():
            assert finished.wait(2)
        # Join the refresh's final lock release before restoring test globals.
        assert refresh_lock.acquire(timeout=2)
        refresh_lock.release()


@pytest.mark.parametrize("route", ["stepper", "buy_now", "open_quantity"])
def test_purchase_buttons_do_not_wait_for_supplier(monkeypatch, route):
    """Quantity and Buy now must redraw before any supplier catalog request."""
    service_id = db.add_service("Canva", "C")
    offer_id = db.add_offer(service_id, "Premium", 4.0, 7)
    release = threading.Event()
    entered = threading.Event()

    def slow_refresh(offers=None):
        entered.set()
        release.wait(0.4)

    monkeypatch.setattr(reseller_service, "refresh_supplier_stock", slow_refresh)
    monkeypatch.setattr(bot, "lang_of", lambda _user_id: "en")
    data = {
        "stepper": f"qty_adjust:{offer_id}:3",
        "buy_now": f"buyq:{offer_id}:3",
        "open_quantity": f"buy:{offer_id}",
    }[route]
    message = SimpleNamespace(text="Choose quantity", photo=None, reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=7),
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    started = time.perf_counter()
    try:
        asyncio.run(bot.cb_navigation(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        ))
        elapsed = time.perf_counter() - started
        print(f"{route}: {elapsed:.3f}s")
        assert elapsed < 0.3, f"{route} waited {elapsed:.3f}s for the supplier"
        assert not entered.is_set(), f"{route} called the supplier stock API"
        query.answer.assert_awaited()
        if route == "stepper":
            query.edit_message_reply_markup.assert_not_awaited()
            query.edit_message_text.assert_awaited()
            rendered = query.edit_message_text.await_args.args[0]
            assert "Premium" in rendered
            assert "12.00" in rendered
            markup = query.edit_message_text.await_args.kwargs["reply_markup"]
            stepper = markup.inline_keyboard
            assert stepper[0][1].text == "3"
            assert stepper[1][0].callback_data == f"qty_custom:{offer_id}"
            assert stepper[2][0].callback_data == f"buyq:{offer_id}:3"
        else:
            rendered = query.edit_message_text.await_args.args[0]
            assert "Premium" in rendered
            if route == "buy_now":
                assert "*3*" in rendered or "3" in rendered
    finally:
        release.set()


def test_checkout_rechecks_supplier_stock_before_creating_order(monkeypatch):
    service_id = db.add_service("Canva", "C")
    offer_id = db.add_offer(
        service_id, "Premium", 4.0, 2,
        supplier_provider="vex", supplier_product_id="sku",
    )
    saved_offer = db.get_offer(offer_id)

    def sold_out(offers):
        assert offers[0]["id"] == offer_id
        db.get_conn().offers.update_one({"id": offer_id}, {"$set": {"stock": 0}})

    monkeypatch.setattr(reseller_service, "refresh_supplier_stock", sold_out)
    with pytest.raises(ValueError, match="rupture de stock"):
        order_service.create_order(7, saved_offer)
    assert db.get_conn().orders.count_documents({}) == 0
