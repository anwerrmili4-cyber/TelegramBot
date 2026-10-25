"""Pure Telegram text and Premium emoji presentation helpers."""

from __future__ import annotations

import contextlib
import html
import re


def custom_emojis_from_message(message):
    """Extract every unique Premium custom emoji from entities or a sticker."""
    found = []
    entities = list(getattr(message, "entities", None) or [])
    entities.extend(getattr(message, "caption_entities", None) or [])
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        emoji_id = getattr(entity, "custom_emoji_id", None)
        if str(entity_type) == "custom_emoji" and emoji_id and emoji_id not in found:
            found.append(emoji_id)
    sticker = getattr(message, "sticker", None)
    sticker_emoji_id = getattr(sticker, "custom_emoji_id", None)
    if sticker_emoji_id and sticker_emoji_id not in found:
        found.append(sticker_emoji_id)
    return found


def custom_emoji_from_message(message):
    """Return the first Premium emoji, the only one Telegram allows as a button icon."""
    emojis = custom_emojis_from_message(message)
    return emojis[0] if emojis else ""


def text_without_custom_emojis(message):
    """Remove Premium emoji placeholders using Telegram's UTF-16 entity offsets."""
    value = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    entities = list(getattr(message, "entities", None) or [])
    entities.extend(getattr(message, "caption_entities", None) or [])
    encoded = bytearray(value.encode("utf-16-le"))
    ranges = []
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        if str(entity_type) == "custom_emoji":
            ranges.append((int(entity.offset) * 2, (int(entity.offset) + int(entity.length)) * 2))
    for start, end in sorted(ranges, reverse=True):
        del encoded[start:end]
    return encoded.decode("utf-16-le").strip()


def text_with_custom_emoji_tokens(message):
    """Preserve every Premium emoji ID and its exact UTF-16 text position."""
    value = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    entities = list(
        (getattr(message, "entities", None) if getattr(message, "text", None) else
         getattr(message, "caption_entities", None)) or []
    )
    encoded = bytearray(value.encode("utf-16-le"))
    replacements = []
    for entity in entities:
        entity_type = getattr(getattr(entity, "type", None), "value", getattr(entity, "type", None))
        emoji_id = getattr(entity, "custom_emoji_id", None)
        if str(entity_type) != "custom_emoji" or not emoji_id:
            continue
        start = int(entity.offset) * 2
        end = (int(entity.offset) + int(entity.length)) * 2
        fallback = bytes(encoded[start:end]).decode("utf-16-le")
        token = f"[[TGEMOJI:{emoji_id}:{fallback.encode('utf-8').hex()}]]"
        replacements.append((start, end, token.encode("utf-16-le")))
    for start, end, token in sorted(replacements, reverse=True):
        encoded[start:end] = token
    return encoded.decode("utf-16-le").strip()


def rich_text_from_message(message):
    """Capture Telegram's exact entity-aware HTML from an admin message."""
    html_value = (
        getattr(message, "text_html", None)
        or getattr(message, "caption_html", None)
    )
    if html_value:
        return f"[[HTML]]{html_value}"
    return text_with_custom_emoji_tokens(message)


def _is_single_emoji(value):
    """Check if a string contains an emoji character rather than text or digits."""
    if not value or not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    if any(
        char.isascii()
        and (char.isalnum() or char in "_-/:;=+,.<>?[]{}()!@#$%^&*`~|\\\"'")
        for char in candidate
    ):
        return False
    return len(candidate) <= 8


def render_stored_rich_text(value, *, parse_legacy_markdown=True):
    """Render trusted admin HTML or legacy Markdown/token text as Telegram HTML."""
    raw_value = str(value or "")

    def close_unfinished_tags(rendered):
        """Close formatting tags left open when dashboard fields truncate HTML."""
        rendered = re.sub(r"<[^>]*\Z", "", rendered)
        supported = {
            "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
            "span", "tg-spoiler", "a", "code", "pre", "blockquote", "tg-emoji",
        }
        opened = []
        for match in re.finditer(r"<\s*(/?)\s*([a-zA-Z][\w-]*)(?:\s[^<>]*)?>", rendered):
            closing, tag = match.group(1), match.group(2).lower()
            if tag not in supported:
                continue
            if not closing:
                opened.append(tag)
            elif opened and opened[-1] == tag:
                opened.pop()
        return rendered + "".join(f"</{tag}>" for tag in reversed(opened))

    def render_custom_emoji(match):
        emoji_id, fallback_hex = match.groups()
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            fallback = bytes.fromhex(fallback_hex).decode("utf-8")
            if not _is_single_emoji(fallback):
                fallback = "📦"
            return f'<tg-emoji emoji-id="{emoji_id}">{html.escape(fallback)}</tg-emoji>'
        return ""

    def render_custom_emoji_tokens(rendered):
        return re.sub(
            r"\[\[TGEMOJI:([0-9A-Za-z_-]+):([0-9a-fA-F]+)\]\]",
            render_custom_emoji,
            rendered,
        )

    html_prefix = next(
        (prefix for prefix in ("[[HTML]]", "[HTML]") if raw_value.startswith(prefix)),
        None,
    )
    if html_prefix:
        rendered = raw_value.removeprefix(html_prefix)
        if parse_legacy_markdown:
            rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
            rendered = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", rendered)
            rendered = re.sub(r"_([^_]+)_", r"<i>\1</i>", rendered)
        return close_unfinished_tags(render_custom_emoji_tokens(rendered))
    rendered = html.escape(raw_value)
    if parse_legacy_markdown:
        rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
        rendered = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", rendered)
        rendered = re.sub(r"_([^_]+)_", r"<i>\1</i>", rendered)

    return render_custom_emoji_tokens(rendered)


__all__ = [
    "_is_single_emoji",
    "custom_emoji_from_message",
    "custom_emojis_from_message",
    "render_stored_rich_text",
    "rich_text_from_message",
    "text_with_custom_emoji_tokens",
    "text_without_custom_emojis",
]
