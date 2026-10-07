"""Process-wide TTL cache for data that is read often and edited rarely.

The service runs as a single Railway replica, so an in-memory cache is
coherent: every write path that changes cached data calls ``invalidate``.
Concurrent misses on one key are coalesced so a burst of storefront visits
rebuilds the catalog once instead of once per request.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._entries: dict[str, tuple[float, int, Any]] = {}
        self._loading: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        self._generation = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry[0] > self._clock():
                self.hits += 1
                return True, entry[2]
            return False, None

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._entries[key] = (self._clock() + ttl, self._generation, value)

    def get_or_set(self, key: str, ttl: float, loader: Callable[[], T]) -> T:
        """Return the cached value, loading it once even under concurrent misses.

        A value loaded while an ``invalidate`` happened is returned to its
        caller but not stored, so an edit is never hidden by a slow rebuild.
        """
        if ttl <= 0:
            return loader()
        found, value = self.get(key)
        if found:
            return value
        with self._lock:
            key_lock = self._loading.setdefault(key, threading.Lock())
        with key_lock:
            found, value = self.get(key)
            if found:
                return value
            with self._lock:
                self.misses += 1
                generation = self._generation
            value = loader()
            with self._lock:
                if generation == self._generation:
                    self._entries[key] = (self._clock() + ttl, generation, value)
                self._loading.pop(key, None)
            return value

    def invalidate(self, prefix: str = "") -> None:
        """Drop every key starting with ``prefix`` (everything when empty)."""
        with self._lock:
            self._generation += 1
            if not prefix:
                self._entries.clear()
                return
            for key in [key for key in self._entries if key.startswith(prefix)]:
                del self._entries[key]

    def clear(self) -> None:
        self.invalidate("")
        with self._lock:
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._entries), "hits": self.hits, "misses": self.misses}


cache = TTLCache()

CATALOG_PREFIX = "catalog:"


def invalidate_catalog() -> None:
    """Forget every cached view of services, offers, logos and site settings."""
    cache.invalidate(CATALOG_PREFIX)
