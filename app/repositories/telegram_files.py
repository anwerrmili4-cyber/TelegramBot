"""Telegram ``file_id``s of media the bot sends by URL (``telegram_file_ids``)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.repositories._mongo import conn


def get_file_id(source: str) -> str | None:
    row = conn().telegram_file_ids.find_one({"_id": source}, {"file_id": 1})
    return (row or {}).get("file_id") or None


def remember_file_id(source: str, file_id: str) -> None:
    conn().telegram_file_ids.update_one(
        {"_id": source},
        {"$set": {"file_id": file_id, "updated_at": datetime.now(UTC)}},
        upsert=True,
    )


def forget_file_id(source: str) -> None:
    conn().telegram_file_ids.delete_one({"_id": source})
