"""Security headers and path rules for the three public surfaces.

The legacy handler classes and the native FastAPI routes both read these, so a
response carries the same headers whichever implementation produced it.
"""

from __future__ import annotations

import posixpath
from urllib.parse import unquote, urlsplit

_PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=()"

PUBLIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": _PERMISSIONS,
}

ADMIN_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": _PERMISSIONS,
}

STOREFRONT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Catalog artwork may be any https URL; fonts come from Google and
    # inline styles carry the per-card animation offsets. The
    # accounts.google.com/gsi sources serve the "Sign in with Google" button.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; media-src 'self' https:; "
        "script-src 'self' https://accounts.google.com/gsi/client; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "frame-src https://accounts.google.com/gsi/; "
        "base-uri 'none'; object-src 'none'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": _PERMISSIONS,
}

ADMIN_PREFIXES = ("/admin", "/admin-v2", "/admin-legacy")


def normalized_request_path(raw_target: str) -> str:
    """Decode and normalize a request path before applying route boundaries."""
    decoded = unquote(urlsplit(raw_target).path).replace("\\", "/")
    normalized = posixpath.normpath("/" + decoded.lstrip("/"))
    return normalized.rstrip("/") or "/"


def is_admin_path(raw_target: str) -> bool:
    path = normalized_request_path(raw_target)
    return any(path == prefix or path.startswith(prefix + "/") for prefix in ADMIN_PREFIXES)
