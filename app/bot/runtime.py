"""The Telegram ``Application`` and the event loop it lives on.

The bot handlers call the synchronous MongoDB layer, so they run on their own
persistent loop thread instead of the uvicorn loop: a slow query delays other
Telegram updates for a moment but never stalls HTTP. Updates from different
users run concurrently; one user's updates keep their arrival order.

Code on any other thread reaches the bot with :func:`run` (blocking) or
:func:`submit` (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Awaitable
from typing import Any

from app.web.async_runtime import AsyncRuntime

log = logging.getLogger(__name__)

runtime = AsyncRuntime()
_application = None
_application_lock = threading.Lock()


def _on_bot_loop() -> bool:
    try:
        return asyncio.get_running_loop() is runtime.loop
    except RuntimeError:
        return False


def run(awaitable: Awaitable[Any]) -> Any:
    """Run a coroutine on the bot loop and wait for its result."""
    if _on_bot_loop():
        raise RuntimeError("bot_runtime.run() would deadlock on the bot loop; await instead")
    return runtime.run(awaitable)


def submit(awaitable: Awaitable[Any]) -> concurrent.futures.Future:
    """Schedule a coroutine on the bot loop without waiting for it."""
    return runtime.submit(awaitable)


def application():
    """Build and initialise the bot once, on the bot loop."""
    global _application
    if _application is not None:
        return _application
    with _application_lock:
        if _application is None:
            from bot import build_app

            candidate = build_app()
            run(candidate.initialize())
            _application = candidate
    return _application


def is_started() -> bool:
    return _application is not None


def submit_update(payload: dict[str, Any]) -> concurrent.futures.Future:
    """Decode a webhook payload and process it in the background."""
    from telegram import Update

    app = application()
    update = Update.de_json(payload, app.bot)
    future = submit(runtime.process_update(app, update))
    update_id = payload.get("update_id")

    def report(done: concurrent.futures.Future) -> None:
        if done.cancelled():
            return
        error = done.exception()
        if error is not None:
            log.error("update_processing_failed update_id=%s", update_id, exc_info=error)

    future.add_done_callback(report)
    return future


def shutdown() -> None:
    global _application
    app = _application
    _application = None
    if app is not None:
        try:
            run(app.shutdown())
        except Exception:
            log.exception("Bot application shutdown failed")
    runtime.close()
