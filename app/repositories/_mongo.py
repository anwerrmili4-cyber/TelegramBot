"""Access to the shared connection and helpers that still live in ``database``.

``database`` is imported lazily: it re-exports the repositories, so a
module-level import would be circular. Looking names up on the module at call
time also keeps test patches such as ``database.get_conn`` effective.
"""

from __future__ import annotations

from typing import Any


def legacy():
    import database

    return database


def conn():
    return legacy().get_conn()


def public(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    result = dict(document)
    result.pop("_id", None)
    return result


def next_id(sequence: str) -> int:
    return legacy()._next_id(sequence)


def audit_event(action: str, actor_id: Any = None, details: dict | None = None) -> None:
    legacy().audit_event(action, actor_id, details)
