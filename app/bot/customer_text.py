"""Render customizable customer-facing Telegram text."""

from __future__ import annotations

import html

import database as db
from app.bot.presentation import render_stored_rich_text
from i18n import format_customer_template, t


def premium_customer_text(lang: str, key: str, **kwargs) -> str:
    """Render customer text as HTML with its configured Premium emoji."""
    protected_values = {}
    if key == "welcome" and "first_name" in kwargs:
        token = "WELCOMEFIRSTNAMEPLACEHOLDER8A6C"
        protected_values[token] = html.escape(str(kwargs["first_name"]))
        kwargs = dict(kwargs)
        kwargs["first_name"] = token
    if key == "delivery_received" and "content" in kwargs:
        token = "DELIVERYCONTENTPLACEHOLDER9F4A"
        protected_values[token] = html.escape(str(kwargs["content"]))
        kwargs = dict(kwargs)
        kwargs["content"] = token
    raw_override = db.get_text_override(key, lang)
    if raw_override is not None and str(raw_override).strip():
        raw_value = str(raw_override)
        if kwargs:
            format_kwargs = kwargs
            is_stored_html = raw_value.startswith(("[[HTML]]", "[HTML]"))
            if is_stored_html:
                format_kwargs = {
                    name: html.escape(str(value))
                    for name, value in kwargs.items()
                }
                if key == "order_created":
                    for name in ("total", "binance_id"):
                        if name in format_kwargs:
                            format_kwargs[name] = f"<code>{format_kwargs[name]}</code>"
            raw_value = format_customer_template(raw_value, **format_kwargs)
    else:
        raw_value = t(lang, key, **kwargs)
    if key == "order_created" and not raw_value.startswith(("[[HTML]]", "[HTML]")):
        copyable_values = {
            name: str(kwargs[name])
            for name in ("total", "binance_id")
            if name in kwargs
        }
        if copyable_values:
            raw_template = str(raw_override) if raw_override is not None else ""
            for name, plain_value in copyable_values.items():
                if f"`{{{name}}}`" not in raw_template:
                    raw_value = raw_value.replace(
                        plain_value, f"`{plain_value}`", 1,
                    )
    value = render_stored_rich_text(raw_value)
    for token, protected_value in protected_values.items():
        value = value.replace(token, protected_value)
    inline_emojis = "<tg-emoji " in value
    emoji_id = db.get_text_override_icon(key, lang)
    if emoji_id and not inline_emojis:
        value = (
            f'<tg-emoji emoji-id="{html.escape(emoji_id)}">⭐</tg-emoji> {value}'
        )
    return value


__all__ = ["premium_customer_text"]
