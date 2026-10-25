"""Search the saved Telegram catalog without contacting suppliers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

import database as db

SEARCH_FIELDS = (
    "service_name",
    "name",
    "description",
    "note",
    "duration",
    "warranty",
)


def _normalized(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", plain.casefold()).split())


def search(
    offers: Iterable[Mapping[str, Any]],
    query: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return offers containing every normalized search word, in catalog order."""
    words = _normalized(query).split()
    if not words or limit <= 0:
        return []

    matches = []
    for offer in offers:
        haystack = _normalized(" ".join(str(offer.get(field) or "") for field in SEARCH_FIELDS))
        if all(word in haystack for word in words):
            matches.append(dict(offer))
            if len(matches) >= limit:
                break
    return matches


def search_saved_catalog(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Search the same deduplicated saved offers displayed in the bot catalog."""
    from app.domain.offer_stock_control import keep_best_bot_price

    offers = keep_best_bot_price(list(db.list_catalog_offers()))
    return search(offers, query, limit=limit)
