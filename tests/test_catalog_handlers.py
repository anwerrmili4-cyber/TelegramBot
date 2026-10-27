"""Compatibility checks for catalog handlers extracted from ``bot``."""


def test_bot_facade_reexports_catalog_navigation_handlers():
    import bot
    from app.bot.handlers import catalog

    assert bot._load_offer_with_live_stock is catalog.load_offer_with_live_stock
    assert bot.show_deep_link_offer is catalog.show_deep_link_offer
    assert bot.show_service_offers is catalog.show_service_offers
    assert bot.catalog_reply_markup is catalog.catalog_reply_markup
    assert bot.show_catalog is catalog.show_catalog
