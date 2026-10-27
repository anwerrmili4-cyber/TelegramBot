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
