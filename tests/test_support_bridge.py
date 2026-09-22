import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import support_bridge
from app.domain import support_service


def _user(user_id=42):
    return SimpleNamespace(
        id=user_id,
        full_name="Support Client",
        first_name="Support",
        username="client42",
    )


def test_client_ticket_message_is_posted_and_linked(mock_mongodb):
    ticket = support_service.create_ticket(42, "Initial issue", category="other")
    sent = SimpleNamespace(message_id=701)
    bot_client = SimpleNamespace(send_message=AsyncMock(return_value=sent))

    asyncio.run(
        support_bridge.send_client_text(
            SimpleNamespace(bot=bot_client),
            ticket,
            _user(),
            "Initial issue",
        )
    )

    call = bot_client.send_message.await_args
    assert call.args[0] == -1004326329551
    assert "TKT-000001" in call.args[1]
    assert "Initial issue" in call.args[1]
    assert "BLACKMARKET SUPPORT CENTER" in call.args[1]
    assert "NEW TICKET" in call.args[1]
    assert "CUSTOMER DETAILS" in call.args[1]
    assert "CUSTOMER MESSAGE" in call.args[1]
    assert "Priority:" in call.args[1]
    linked = support_service.get_ticket_by_channel_message(701)
    assert linked["id"] == ticket["id"]


def test_ticket_card_style_is_editable_and_keeps_html_safe(mock_mongodb):
    support_bridge.save_ticket_style("title", "VIP <Support>")
    support_bridge.save_ticket_style(
        "reply_hint", "Answer ticket {ticket_ref} with /reply {ticket_id}",
    )
    support_bridge.save_ticket_style("footer", "Always by your side")

    preview = support_bridge.ticket_card_preview()

    assert "VIP &lt;Support&gt;" in preview
    assert "Answer ticket TKT-000062 with /reply 62" in preview
    assert "Always by your side" in preview
    assert "{ticket_id}" not in preview
    assert "{ticket_ref}" not in preview


def test_ticket_card_style_can_be_restored(mock_mongodb):
    support_bridge.save_ticket_style("title", "Temporary title")

    support_bridge.reset_ticket_style()

    assert support_bridge.ticket_style() == support_bridge.TICKET_STYLE_DEFAULTS


def test_admin_channel_reply_is_delivered_to_linked_customer(mock_mongodb):
    ticket = support_service.create_ticket(42, "Please help", category="other")
    support_service.link_channel_message(ticket["id"], 701)
    channel_message = SimpleNamespace(
        message_id=702,
        chat=SimpleNamespace(id=-1004326329551),
        from_user=None,
        reply_to_message=SimpleNamespace(message_id=701),
        text="Hello, I can help you.",
        caption=None,
        photo=None,
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        sticker=None,
    )
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=900)),
        copy_message=AsyncMock(),
    )

    delivered = asyncio.run(
        support_bridge.handle_admin_channel_post(
            SimpleNamespace(channel_post=channel_message),
            SimpleNamespace(bot=bot_client),
        )
    )

    assert delivered is True
    call = bot_client.send_message.await_args
    assert call.args[0] == 42
    assert "Hello, I can help you." in call.args[1]
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "ticket_close:1"
    messages = support_service.get_messages(ticket["id"])
    assert messages[-1]["sender_type"] == "admin"
    assert messages[-1]["content"] == "Hello, I can help you."
    assert support_service.get_ticket(ticket["id"])["status"] == "waiting_customer"


def test_customer_attachment_is_copied_to_support_channel(mock_mongodb):
    ticket = support_service.create_ticket(42, "Initial issue", category="other")
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=710)),
        copy_message=AsyncMock(return_value=SimpleNamespace(message_id=711)),
    )
    message = SimpleNamespace(
        message_id=55,
        chat_id=42,
        chat=SimpleNamespace(id=42),
        caption="Screenshot",
        photo=[SimpleNamespace(file_id="photo")],
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        sticker=None,
    )

    asyncio.run(
        support_bridge.send_client_media(
            SimpleNamespace(bot=bot_client),
            ticket,
            _user(),
            message,
        )
    )

    bot_client.copy_message.assert_awaited_once_with(
        chat_id=-1004326329551,
        from_chat_id=42,
        message_id=55,
    )
    assert support_service.get_ticket_by_channel_message(710)["id"] == ticket["id"]
    assert support_service.get_ticket_by_channel_message(711)["id"] == ticket["id"]


def test_message_media_uses_largest_photo_and_preserves_dimensions():
    message = SimpleNamespace(
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="one", width=90, height=90, file_size=200),
            SimpleNamespace(file_id="large", file_unique_id="two", width=1280, height=720, file_size=4000),
        ],
        document=None,
        video=None,
        animation=None,
        video_note=None,
        sticker=None,
    )

    assert support_bridge.message_media(message) == {
        "type": "image",
        "file_id": "large",
        "file_unique_id": "two",
        "file_name": None,
        "mime_type": None,
        "width": 1280,
        "height": 720,
        "duration": None,
        "file_size": 4000,
        "custom_emoji_id": None,
    }


def test_admin_can_reply_with_channel_command(mock_mongodb):
    ticket = support_service.create_ticket(42, "Please help", category="other")
    channel_message = SimpleNamespace(
        message_id=703,
        chat=SimpleNamespace(id=-1004326329551),
        from_user=None,
        reply_to_message=None,
        text=f"/reply {ticket['id']} Command response",
        caption=None,
        photo=None,
        document=None,
        video=None,
        animation=None,
        audio=None,
        voice=None,
        video_note=None,
        sticker=None,
    )
    bot_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=901)),
        copy_message=AsyncMock(),
    )

    delivered = asyncio.run(
        support_bridge.handle_admin_channel_post(
            SimpleNamespace(channel_post=channel_message),
            SimpleNamespace(bot=bot_client),
        )
    )

    assert delivered is True
    assert bot_client.send_message.await_args.args[0] == 42
    assert "Command response" in bot_client.send_message.await_args.args[1]
    assert support_service.get_messages(ticket["id"])[-1]["content"] == "Command response"
