"""Run the complete BlackMarket Telegram service on Railway.

The three surfaces (public + Telegram webhook, admin, Tunisian storefront) are
FastAPI apps served by uvicorn on one event loop; see :mod:`app.web.server`.
The handler classes below hold the routing rules for routes that still run
through the original request handler.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

from api import storefront_site, webhook
from app.core import config as core_config
from app.web import surfaces

log = logging.getLogger("railway")

_MAX_DISCARDED_BODY_BYTES = 1_000_000
TERMS_PAGE = Path(__file__).resolve().parent / "assets" / "terms.html"
TERMS_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "font-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
_normalized_request_path = surfaces.normalized_request_path
_is_admin_path = surfaces.is_admin_path


class PublicHandler(webhook.handler):
    """Public Telegram and landing-page surface with dashboard routes blocked."""

    def _block_admin(self) -> None:
        # Never disclose the private dashboard hostname from a public response.
        self._reply(404, {"ok": False, "error": "NOT_FOUND"}, headers={
            "Cache-Control": "no-store",
        })

    def end_headers(self) -> None:
        for name, value in surfaces.PUBLIC_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def do_GET(self) -> None:
        path = _normalized_request_path(self.path)
        if path == "/terms":
            body = TERMS_PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Content-Security-Policy", TERMS_CSP)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if _is_admin_path(self.path):
            self._block_admin()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if _is_admin_path(self.path):
            self._block_admin()
            return
        super().do_POST()

    def do_OPTIONS(self) -> None:
        if _is_admin_path(self.path):
            self._block_admin()
            return
        super().do_OPTIONS()


class StorefrontHandler(webhook.handler):
    """Tunisian customer site: the built SPA plus its own storefront API.

    This surface gets its own Railway domain, so it deliberately exposes
    nothing but the storefront. The Telegram webhook, the buyer API, the cron
    endpoints and the dashboard all stay on the other two ports.
    """

    _ALLOWED_API = (
        "/api/storefront/catalog",
        "/api/storefront/order",
        "/api/storefront/cart",
        "/api/storefront/service-logo",
        "/api/storefront/category-logo",
        "/api/storefront/offer-image",
        "/api/storefront/offer-video",
        "/api/storefront/reviews",
        "/api/storefront/reviews/email",
        *webhook.STOREFRONT_AUTH_GET_PATHS,
    )
    _ALLOWED_POST = frozenset({
        "/api/storefront/orders",
        "/api/storefront/reviews/email",
        *webhook.STOREFRONT_AUTH_POST_PATHS,
    })

    def end_headers(self) -> None:
        for name, value in surfaces.STOREFRONT_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def _not_found(self) -> None:
        # Discard any request body first: closing the socket with bytes still
        # unread makes the client see a reset instead of this response.
        length = self.headers.get("Content-Length", "")
        if length.isdigit():
            self.rfile.read(min(int(length), _MAX_DISCARDED_BODY_BYTES))
        self._reply(404, {"ok": False, "error": "NOT_FOUND"}, headers={"Cache-Control": "no-store"})

    def _serve_app(self, path: str) -> None:
        target = storefront_site.resolve(path)
        if target is None:
            self._reply(503, {
                "ok": False,
                "error": "storefront_not_built",
                "message": storefront_site.BUILD_MISSING_MESSAGE,
            })
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", storefront_site.content_type(target))
        self.send_header("Cache-Control", storefront_site.cache_control(target))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = _normalized_request_path(self.path)
        if path == "/health" or path in self._ALLOWED_API:
            super().do_GET()
            return
        if path.startswith("/api/") or _is_admin_path(self.path):
            self._not_found()
            return
        self._serve_app(path)

    def do_POST(self) -> None:
        if _normalized_request_path(self.path) not in self._ALLOWED_POST:
            self._not_found()
            return
        super().do_POST()

    def do_OPTIONS(self) -> None:
        path = _normalized_request_path(self.path)
        if path not in self._ALLOWED_POST and path not in webhook.STOREFRONT_AUTH_PATHS:
            self._not_found()
            return
        super().do_OPTIONS()


class AdminHandler(webhook.handler):
    """Administration, Telegram webhook and operational API surface."""

    def end_headers(self) -> None:
        for name, value in surfaces.ADMIN_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        super().do_GET()


def deployment_issues() -> list[str]:
    """Return safe configuration errors for the all-in-one Railway service."""
    return core_config.deployment_issues()


def register_telegram_webhook(*, attempts: int = 3, retry_seconds: float = 2) -> dict:
    """Register the Railway URL with Telegram, retrying transient failures."""
    result: dict = {"ok": False, "message": "Telegram webhook was not registered."}
    for attempt in range(1, attempts + 1):
        result = webhook.repair_telegram_webhook()
        if result.get("ok"):
            log.info("Telegram webhook registered at %s", result.get("url"))
            return result
        log.warning(
            "Telegram webhook registration attempt %s/%s failed: %s",
            attempt,
            attempts,
            result.get("message", "unknown error"),
        )
        if attempt < attempts:
            time.sleep(retry_seconds)
    return result


def main() -> None:
    from app.core.logging import configure_logging
    from app.web import server

    issues = deployment_issues()
    if issues:
        raise RuntimeError("Incomplete Railway configuration: " + ", ".join(issues))
    settings = core_config.RuntimeSettings.from_env()
    configure_logging()
    server.serve(settings, register_webhook=register_telegram_webhook)


if __name__ == "__main__":
    main()
