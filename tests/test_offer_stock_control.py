"""One in-stock offer stays listed when suppliers sell the same product."""

import database as db
import keyboards as kb
from app.domain import offer_stock_control, storefront_service
from app.domain.order_service import create_order


def _offer(service_id, provider, price, stock, **extra):
    period_days = extra.pop("period_days", 30)
    warranty_days = extra.pop("warranty_days", 7)
    return db.add_offer(
        service_id,
        extra.pop("name", "ChatGPT Plus"),
        price,
        stock,
        supplier_provider=provider,
        supplier_product_id=extra.pop("supplier_product_id", f"{provider}-sku"),
        period_days=period_days,
        period_value=extra.pop("period_value", period_days),
        period_unit=extra.pop("period_unit", "days"),
        warranty_days=warranty_days,
        warranty_value=extra.pop("warranty_value", warranty_days),
        warranty_unit=extra.pop("warranty_unit", "days"),
        **extra,
    )


def test_group_key_is_name_duration_and_warranty_not_the_supplier():
    month = {
        "name": "  Canva   PRO ",
        "period_value": 1,
        "period_unit": "months",
        "warranty_value": 7,
        "warranty_unit": "days",
        "supplier_provider": "vex",
    }
    days = {
        "name": "canva pro",
        "period_days": 30,
        "warranty_days": 7,
        "supplier_provider": "upibot",
    }

    assert offer_stock_control.same_product_group_key(month) == ("canva pro", 30, 7)
    assert offer_stock_control.same_product_group_key(month) == offer_stock_control.same_product_group_key(days)


def test_client_price_ignores_a_lower_supplier_cost(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    dear_cost_cheap_client = _offer(service_id, "vex", 3.5, 4)
    cheap_cost_dear_client = _offer(service_id, "upibot", 8, 9)
    mock_mongodb.offers.update_one({"id": dear_cost_cheap_client}, {"$set": {"wholesale_price": 7}})
    mock_mongodb.offers.update_one({"id": cheap_cost_dear_client}, {"$set": {"wholesale_price": 1}})
    offer_stock_control.reconcile_same_product_offers()

    assert db.get_offer(dear_cost_cheap_client)["active"] == 1
    parked = db.get_offer(cheap_cost_dear_client)
    assert parked["active"] == 0
    assert parked["stock_control_hold"] is True
    assert mock_mongodb.offers.count_documents({"service_id": service_id}) == 2


def test_out_of_stock_offer_is_replaced_by_the_next_in_stock_price(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    cheap = _offer(service_id, "vex", 3, 2)
    mid = _offer(service_id, "upibot", 5, 6)
    dear = _offer(service_id, "kakao", 9, 8)

    assert db.get_offer(cheap)["active"] == 1
    assert db.get_offer(mid)["active"] == 0
    assert db.get_offer(dear)["active"] == 0
    assert [offer["id"] for offer in db.list_offers(service_id)] == [cheap]
    assert {offer["id"] for offer in db.list_catalog_offers()} >= {cheap}
    assert mid not in {offer["id"] for offer in db.list_catalog_offers()}

    db.update_offer(cheap, stock=0)

    assert db.get_offer(cheap)["active"] == 0
    assert db.get_offer(mid)["active"] == 1
    assert db.get_offer(dear)["active"] == 0
    assert [offer["id"] for offer in db.list_offers(service_id)] == [mid]

    db.update_offer(mid, stock=0)
    assert db.get_offer(dear)["active"] == 1
    db.update_offer(dear, stock=0)
    assert [offer["id"] for offer in db.list_offers(service_id)] == []
    assert db.get_offer(cheap)["active"] == 0
    assert mock_mongodb.offers.count_documents({"name": "ChatGPT Plus"}) == 3


def test_same_supplier_or_different_warranty_is_left_alone(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    first = _offer(service_id, "vex", 3, 2, supplier_product_id="a")
    second = _offer(service_id, "vex", 9, 2, supplier_product_id="b")
    other_warranty = _offer(service_id, "upibot", 1, 4, warranty_days=30, name="ChatGPT Plus")

    assert db.get_offer(first)["active"] == 1
    assert db.get_offer(second)["active"] == 1
    assert db.get_offer(other_warranty)["active"] == 1


def test_a_single_out_of_stock_offer_is_not_deactivated(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    offer_id = _offer(service_id, "vex", 4, 0)

    offer = db.get_offer(offer_id)
    assert offer["active"] == 1
    assert offer.get("stock_control_hold") is not True


def test_equal_client_prices_keep_the_offer_already_listed(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    listed = _offer(service_id, "vex", 4, 1)
    _offer(service_id, "upibot", 4, 20)

    assert db.get_offer(listed)["active"] == 1
    assert db.list_offers(service_id)[0]["id"] == listed


def test_unlimited_stock_counts_as_available_and_stock_tracking_off_does_not(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    limited = _offer(service_id, "vex", 2, 5)
    unlimited = _offer(service_id, "upibot", 6, 0, unlimited_stock=True)

    assert db.get_offer(limited)["active"] == 1
    assert db.get_offer(unlimited)["active"] == 0

    db.update_offer(limited, stock_enabled=False)
    assert db.get_offer(unlimited)["active"] == 1
    assert db.get_offer(limited)["active"] == 0


def test_local_copy_is_not_treated_as_another_supplier(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    supplier = _offer(service_id, "vex", 5, 3)
    copy_id = db.copy_supplier_offers_to_local()["offer_ids"][0]
    other = _offer(service_id, "upibot", 4, 3)

    copy = db.get_offer(copy_id)
    assert copy["active"] == 0
    assert copy.get("stock_control_hold") is not True
    assert db.get_offer(other)["active"] == 1
    assert db.get_offer(supplier)["active"] == 0


def test_purchase_that_empties_stock_activates_the_sibling(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    cheap = _offer(service_id, "vex", 3, 1)
    dear = _offer(service_id, "upibot", 8, 4)
    mock_mongodb.orders.insert_one({
        "id": 77,
        "offer_id": cheap,
        "qty": 1,
        "status": "pending_payment",
    })

    assert db.mark_order_paid(77, "manual") is True
    assert db.get_offer(cheap)["stock"] == 0
    assert db.get_offer(cheap)["active"] == 0
    assert db.get_offer(dear)["active"] == 1


def test_flash_sale_price_is_the_client_price(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    cheap = _offer(service_id, "vex", 5, 3)
    dear = _offer(service_id, "upibot", 9, 3)

    db.start_flash_sale(dear, 2, 30)

    assert db.get_offer(dear)["active"] == 1
    assert db.get_offer(dear)["price"] == 2
    assert db.get_offer(cheap)["active"] == 0


def test_site_and_bot_list_only_the_active_offer_while_admin_keeps_both(mock_mongodb, monkeypatch):
    monkeypatch.setattr(
        "app.domain.reseller_service.refresh_supplier_stock",
        lambda *_args, **_kwargs: None,
    )
    service_id = db.add_service("Design", "✦", sales_channels=["bot", "tn_site"])
    cheap = _offer(
        service_id, "vex", 3, 4,
        tn_price_millimes=9000, site_enabled=True,
    )
    dear = _offer(
        service_id, "upibot", 8, 4,
        tn_price_millimes=15000, site_enabled=True,
    )

    listed = [
        offer["id"]
        for service in storefront_service.catalog()["services"]
        for offer in service["offers"]
    ]
    assert listed == [cheap]
    assert [offer["id"] for offer in db.list_offers(service_id)] == [cheap]
    panel = [
        offer["id"]
        for service in db.dashboard_data(include_history=False)["services"]
        if service["id"] == service_id
        for offer in service["offers"]
    ]
    assert set(panel) == {cheap, dear}

    try:
        storefront_service._resolved_line(dear, 1)
    except storefront_service.StorefrontError as exc:
        assert "plus disponible" in str(exc)
    else:
        raise AssertionError("the dearer supplier offer was still sold on the site")

    user_id = db.get_conn().users.insert_one({"telegram_id": 4242, "lang": "en"}).inserted_id
    # create_order reads the offer, not the user document id.
    db.get_conn().users.update_one({"telegram_id": 4242}, {"$set": {"id": 4242}})
    try:
        create_order(4242, db.get_offer(dear), 1)
    except ValueError as exc:
        assert "pas disponible" in str(exc)
    else:
        raise AssertionError("the bot accepted the parked offer")
    assert user_id


def test_unpublishing_the_winner_returns_the_other_offer(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    cheap = _offer(service_id, "vex", 3, 4, supplier_product_id="cheap")
    dear = _offer(service_id, "upibot", 8, 4, supplier_product_id="dear")
    db.save_reseller_product_config(
        "vex", "cheap",
        name="ChatGPT Plus",
        wholesale_price=1,
        currency="USDT",
        retail_price=3,
        enabled=False,
        service_id=service_id,
        local_offer_id=cheap,
    )

    assert db.get_offer(cheap)["active"] == 0
    assert db.get_offer(cheap).get("stock_control_hold") is not True
    assert db.get_offer(dear)["active"] == 1


def test_archiving_the_winner_restores_the_sibling(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    cheap = _offer(service_id, "vex", 3, 4)
    dear = _offer(service_id, "upibot", 8, 4)

    assert db.archive_offer(cheap) is True
    assert db.get_offer(dear)["active"] == 1
    assert db.get_offer(dear).get("stock_control_hold") is not True


def test_an_inactive_service_cannot_hide_the_live_offer(mock_mongodb):
    hidden = db.add_service("Old", "✦")
    live = db.add_service("Live", "✦")
    parked = _offer(hidden, "vex", 2, 5)
    shown = _offer(live, "upibot", 6, 5)
    db.update_service(hidden, active=0)

    assert db.get_offer(shown)["active"] == 1
    assert db.get_offer(parked)["active"] in (0, 1)
    assert [offer["id"] for offer in db.list_offers(live)] == [shown]


def test_startup_sweep_corrects_offers_already_stored(mock_mongodb):
    service_id = db.add_service("Design", "✦")
    mock_mongodb.offers.insert_many([
        {
            "id": 901, "service_id": service_id, "name": "Canva Pro", "price": 9, "stock": 4,
            "supplier_provider": "vex", "supplier_product_id": "a",
            "period_days": 30, "warranty_days": 7, "active": 1,
        },
        {
            "id": 902, "service_id": service_id, "name": "canva   pro", "price": 4, "stock": 2,
            "supplier_provider": "upibot", "supplier_product_id": "b",
            "period_days": 30, "warranty_days": 7, "active": 1,
        },
    ])

    offer_stock_control.reconcile_same_product_offers()

    assert db.get_offer(902)["active"] == 1
    parked = db.get_offer(901)
    assert parked["active"] == 0
    assert parked["stock_control_hold"] is True
    assert mock_mongodb.offers.count_documents({"id": {"$in": [901, 902]}}) == 2


def test_database_startup_runs_the_sweep(mock_mongodb, monkeypatch):
    calls = []
    monkeypatch.setattr(
        offer_stock_control,
        "reconcile_same_product_offers",
        lambda: calls.append("sweep") or {"groups": 0, "updated": 0, "activated": [], "deactivated": []},
    )
    db._schema_initialized = False
    db.init_db()
    assert calls == ["sweep"]


def test_bot_lists_the_lower_price_and_leaves_the_site_unchanged(mock_mongodb):
    service_id = db.add_service("Capcut", "🎬", sales_channels=["bot", "tn_site"], site_enabled=True)
    dear = _offer(
        service_id, "vex", 4, 5,
        name="Capcut pro", supplier_product_id="dear",
        warranty_days=0,
        tn_price_millimes=12000, site_enabled=True,
    )
    cheap = _offer(
        service_id, "vex", 3.9, 2,
        name="Capcut Pro", supplier_product_id="cheap",
        tn_price_millimes=11000, site_enabled=True,
    )

    assert db.get_offer(dear)["active"] == 1
    assert db.get_offer(cheap)["active"] == 1
    assert db.get_offer(dear).get("stock_control_hold") is not True
    assert [offer["id"] for offer in db.list_offers(service_id)] == [cheap]
    assert {offer["id"] for offer in db.list_offers(service_id, active_only=False)} == {cheap, dear}
    assert db.offer_is_listed_in_bot(db.get_offer(cheap)) is True
    assert db.offer_is_listed_in_bot(db.get_offer(dear)) is False

    callbacks = [
        button.callback_data
        for row in kb.offers_keyboard("en", service_id).inline_keyboard
        for button in row
    ]
    assert f"off:{cheap}" in callbacks
    assert f"off:{dear}" not in callbacks

    listed = [
        offer["id"]
        for service in storefront_service._build_catalog()["services"]
        for offer in service["offers"]
    ]
    assert set(listed) == {cheap, dear}


def test_bot_hides_a_higher_price_even_when_the_cheaper_offer_is_out_of_stock(mock_mongodb):
    service_id = db.add_service("Capcut", "🎬")
    cheap = _offer(service_id, "vex", 3.9, 0, name="Capcut pro", supplier_product_id="cheap")
    dear = _offer(service_id, "vex", 4, 8, name="Capcut pro", supplier_product_id="dear")

    assert [offer["id"] for offer in db.list_offers(service_id)] == [cheap]
    assert db.get_offer(dear)["active"] == 1


def test_bot_catalog_hides_the_higher_price_from_another_service(mock_mongodb):
    first = db.add_service("Capcut", "🎬")
    second = db.add_service("Video", "🎬")
    dear = _offer(first, "vex", 4, 3, name="Capcut pro", supplier_product_id="dear")
    cheap = _offer(second, "vex", 3.9, 3, name="Capcut pro", supplier_product_id="cheap")

    assert db.list_offers(first) == []
    assert [offer["id"] for offer in db.list_offers(second)] == [cheap]
    assert {offer["id"] for offer in db.list_catalog_offers()} == {dear, cheap}

    callbacks = [
        button.callback_data
        for row in kb._catalog_offers_keyboard("en").inline_keyboard
        for button in row
    ]
    assert f"off:{cheap}" in callbacks
    assert f"off:{dear}" not in callbacks


def test_bot_keeps_the_same_name_when_the_period_is_different(mock_mongodb):
    service_id = db.add_service("Capcut", "🎬")
    month = _offer(service_id, "vex", 3.9, 2, name="Capcut pro", supplier_product_id="month")
    year = _offer(
        service_id, "vex", 9, 2,
        name="Capcut pro", supplier_product_id="year", period_days=365,
    )

    assert {offer["id"] for offer in db.list_offers(service_id)} == {month, year}
