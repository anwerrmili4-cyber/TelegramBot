"""MongoDB clients shared by the whole process.

``database.get_conn()`` keeps the synchronous client used by the bot handlers
and the domain services. Native async routes use :func:`async_db`, which is
bound to the event loop that first awaits it (the uvicorn loop).

Both clients carry :data:`catalog_write_listener`, so any successful write to
a collection the storefront catalog reads drops the cached catalog, whichever
code path made the change.
"""

from __future__ import annotations

import threading
import time

from pymongo import AsyncMongoClient, monitoring

from app.core.cache import invalidate_catalog
from config import MONGODB_DB, MONGODB_URI

APP_NAME = "blackmarket"
SERVER_SELECTION_TIMEOUT_MS = 10_000
CATALOG_COLLECTIONS = frozenset({"services", "offers", "settings"})
_WRITE_COMMANDS = frozenset({"insert", "update", "delete", "findAndModify", "findandmodify"})


class CatalogWriteListener(monitoring.CommandListener):
    """Invalidate the catalog cache after a write to a catalog collection succeeds."""

    def __init__(self) -> None:
        self._pending: set[tuple[object, int]] = set()
        self._lock = threading.Lock()

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        if event.command_name not in _WRITE_COMMANDS:
            return
        if event.command.get(event.command_name) in CATALOG_COLLECTIONS:
            with self._lock:
                self._pending.add((event.connection_id, event.request_id))

    def succeeded(self, event: monitoring.CommandSucceededEvent) -> None:
        with self._lock:
            key = (event.connection_id, event.request_id)
            if key not in self._pending:
                return
            self._pending.discard(key)
        invalidate_catalog()

    def failed(self, event: monitoring.CommandFailedEvent) -> None:
        with self._lock:
            self._pending.discard((event.connection_id, event.request_id))


catalog_write_listener = CatalogWriteListener()


def client_options() -> dict:
    return {
        "serverSelectionTimeoutMS": SERVER_SELECTION_TIMEOUT_MS,
        "appname": APP_NAME,
        "event_listeners": [catalog_write_listener],
    }


_async_client: AsyncMongoClient | None = None


def async_client() -> AsyncMongoClient:
    global _async_client
    if _async_client is None:
        if not MONGODB_URI:
            raise RuntimeError("HP_MONGODB_URI is required")
        _async_client = AsyncMongoClient(MONGODB_URI, **client_options())
    return _async_client


def async_db():
    return async_client()[MONGODB_DB]


async def ping_ms() -> float:
    """Round trip to the primary in milliseconds, for health checks."""
    started = time.perf_counter()
    await async_db().command("ping")
    return round((time.perf_counter() - started) * 1000, 1)


async def close_async() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.close()
        _async_client = None
