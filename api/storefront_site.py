"""Static hosting for the Tunisian storefront single-page app.

The built Vite bundle lives in ``storefront/dist``. It is served on its own
domain so the customer site shares an origin with ``/api/storefront/*``: no CORS
preflight, and the relative image URLs the catalog returns resolve as-is.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "storefront" / "dist"
INDEX = "index.html"

BUILD_MISSING_MESSAGE = "Run `npm install && npm run build` in storefront."

# Everything else is a hashed Vite bundle and may be cached indefinitely.
_NEVER_CACHE = {".html", ".webmanifest"}


def resolve(relative_path: str) -> Path | None:
    """Return the file for a request path, or ``None`` if it escapes the build.

    An unknown path falls back to ``index.html`` so the app still boots when a
    customer opens a bookmarked or mistyped URL.
    """
    candidate = DIST / relative_path.lstrip("/")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(DIST.resolve())
    except (OSError, ValueError):
        return None
    if resolved.is_file():
        return resolved
    fallback = DIST / INDEX
    return fallback if fallback.is_file() else None


def content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix in {".js", ".css", ".svg", ".json"}:
        return f"{guessed}; charset=utf-8"
    return guessed


def cache_control(path: Path) -> str:
    if path.suffix in _NEVER_CACHE:
        return "no-store, max-age=0"
    return "public, max-age=31536000, immutable"
