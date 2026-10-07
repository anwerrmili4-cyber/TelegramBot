"""Send media by URL once, then by the ``file_id`` Telegram returned."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from telegram.error import BadRequest

from app.repositories import telegram_files

log = logging.getLogger(__name__)


async def send_cached_photo(send: Callable[..., Awaitable[Any]], url: str, **kwargs: Any) -> Any:
    """``send`` is e.g. ``message.reply_photo``; it receives ``photo=`` plus ``kwargs``."""
    file_id = await asyncio.to_thread(telegram_files.get_file_id, url)
    if file_id:
        try:
            return await send(photo=file_id, **kwargs)
        except BadRequest as exc:
            log.info("cached_file_id_rejected url=%s reason=%s", url, exc)
            await asyncio.to_thread(telegram_files.forget_file_id, url)
    message = await send(photo=url, **kwargs)
    photos = getattr(message, "photo", None)
    new_file_id = getattr(photos[-1], "file_id", None) if isinstance(photos, (list, tuple)) and photos else None
    if isinstance(new_file_id, str) and new_file_id:
        await asyncio.to_thread(telegram_files.remember_file_id, url, new_file_id)
    return message
