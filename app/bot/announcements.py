"""Presentation and delivery helpers for Telegram announcements."""

from __future__ import annotations

from app.bot.presentation import _is_single_emoji


def announcement_service_emoji(service, fallback="📦"):
    """Render a service's Unicode or Premium emoji inside announcement text."""
    service = service or {}
    raw_emoji = str(service.get("emoji") or "").strip()
    emoji = raw_emoji if _is_single_emoji(raw_emoji) else fallback
    emoji_id = str(service.get("custom_emoji_id") or "").strip()
    if emoji_id and emoji_id.isascii():
        return f"[[TGEMOJI:{emoji_id}:{emoji.encode('utf-8').hex()}]]"
    return emoji


def announcement_plain(value):
    """Keep dynamic names from breaking the customizable Markdown template."""
    return str(value or "").replace("*", "").replace("_", " ").replace("`", "").strip()


__all__ = ["announcement_plain", "announcement_service_emoji"]
