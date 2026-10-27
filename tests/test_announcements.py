"""Compatibility checks for announcement behavior extracted from ``bot``."""


def test_bot_facade_reexports_announcement_formatters():
    import bot
    from app.bot import announcements

    assert bot._announcement_service_emoji is announcements.announcement_service_emoji
    assert bot._announcement_plain is announcements.announcement_plain
    assert announcements.announcement_plain("Pro_*`Plan`") == "Pro Plan"
    assert announcements.announcement_service_emoji(
        {"emoji": "not-an-emoji"}, fallback="📦",
    ) == "📦"


def test_bot_facade_reexports_announcement_delivery_helpers():
    import bot
    from app.bot import announcements

    assert bot._track_broadcast_message is announcements.track_broadcast_message
    assert bot._send_broadcast_message_safe is announcements.send_broadcast_message_safe


def test_bot_facade_reexports_broadcast_batching():
    import bot
    from app.bot import announcements

    assert bot._is_blocked_broadcast_error is announcements.is_blocked_broadcast_error
    assert bot._broadcast_in_batches is announcements.broadcast_in_batches
    assert bot.BROADCAST_BATCH_SIZE == announcements.BROADCAST_BATCH_SIZE
    assert bot.BROADCAST_BATCH_DELAY == announcements.BROADCAST_BATCH_DELAY


def test_bot_facade_reexports_stock_announcements():
    import bot
    from app.bot import announcements

    assert bot.announce_channel_restock is announcements.announce_channel_restock
    assert bot.send_new_stock_broadcast is announcements.send_new_stock_broadcast


def test_bot_facade_reexports_flash_sale_announcements():
    import bot
    from app.bot import announcements

    assert bot.announce_flash_sale is announcements.announce_flash_sale


def test_bot_facade_reexports_admin_supplier_announcements():
    import bot
    from app.bot import announcements

    assert (
        bot.announce_supplier_change_admin
        is announcements.announce_supplier_change_admin
    )


def test_bot_facade_reexports_supplier_price_announcements():
    import bot
    from app.bot import announcements

    assert bot.announce_api_flash_sale is announcements.announce_api_flash_sale
    assert (
        bot.announce_supplier_price_update
        is announcements.announce_supplier_price_update
    )


def test_bot_facade_reexports_general_customer_announcements():
    import bot
    from app.bot import announcements

    assert bot.broadcast_admin_message is announcements.broadcast_admin_message
    assert bot.announce_restock_digest is announcements.announce_restock_digest


def test_bot_facade_reexports_broadcast_deletion():
    import bot
    from app.bot import announcements

    assert bot.delete_broadcast_messages is announcements.delete_broadcast_messages


def test_bot_facade_reexports_program_notices():
    import bot
    from app.bot import announcements

    assert bot.broadcast_maintenance_notice is announcements.broadcast_maintenance_notice
    assert (
        bot.broadcast_affiliate_program_update
        is announcements.broadcast_affiliate_program_update
    )


def test_bot_facade_reexports_broadcast_job_dispatch():
    import bot
    from app.bot import announcements

    assert bot._execute_broadcast_job is announcements.execute_broadcast_job
