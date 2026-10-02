"""Run the complete BlackMarket Telegram service on Railway."""

from __future__ import annotations

import logging
import os
import posixpath
import re
import signal
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

import config
from api import storefront_site, webhook

log = logging.getLogger("railway")
_TELEGRAM_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class RailwayHTTPServer(ThreadingHTTPServer):
    """Concurrent HTTP server whose request threads cannot block shutdown."""

    allow_reuse_address = True
    daemon_threads = True


_ADMIN_PREFIXES = ("/admin", "/admin-v2", "/admin-legacy")
_MAX_DISCARDED_BODY_BYTES = 1_000_000
_TERMS_PAGE = Path(__file__).resolve().parent / "assets" / "terms.html"


def _normalized_request_path(raw_target: str) -> str:
    """Decode and normalize a request path before applying route boundaries."""
    decoded = unquote(urlsplit(raw_target).path).replace("\\", "/")
    normalized = posixpath.normpath("/" + decoded.lstrip("/"))
    return normalized.rstrip("/") or "/"


def _is_admin_path(raw_target: str) -> bool:
    path = _normalized_request_path(raw_target)
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _ADMIN_PREFIXES)


class PublicHandler(webhook.handler):
    """Public Telegram and landing-page surface with dashboard routes blocked."""

    def _block_admin(self) -> None:
        # Never disclose the private dashboard hostname from a public response.
        self._reply(404, {"ok": False, "error": "NOT_FOUND"}, headers={
            "Cache-Control": "no-store",
        })

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        super().end_headers()

    def do_GET(self) -> None:
        path = _normalized_request_path(self.path)
        if path == "/terms":
            body = _TERMS_PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src 'none'; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'none'",
            )
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
        "/api/storefront/offer-image",
        "/api/storefront/offer-video",
        *webhook.STOREFRONT_AUTH_GET_PATHS,
    )
    _ALLOWED_POST = frozenset({"/api/storefront/orders", *webhook.STOREFRONT_AUTH_POST_PATHS})

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            # Catalog artwork may be any https URL; fonts come from Google and
            # inline styles carry the per-card animation offsets. The
            # accounts.google.com/gsi sources serve the "Sign in with Google" button.
            "default-src 'self'; img-src 'self' data: https:; media-src 'self' https:; "
            "script-src 'self' https://accounts.google.com/gsi/client; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://accounts.google.com/gsi/; "
            "frame-src https://accounts.google.com/gsi/; "
            "base-uri 'none'; object-src 'none'; frame-ancestors 'none'",
        )
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
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
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
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
    issues = config.configuration_issues(webhook=True)
    webhook_secret = config.env_value("HP_WEBHOOK_SECRET")
    cron_secret = config.env_value("CRON_SECRET")
    if webhook_secret and (
        len(webhook_secret) < 24
        or not _TELEGRAM_SECRET_RE.fullmatch(webhook_secret)
    ):
        issues.append(
            "HP_WEBHOOK_SECRET (at least 24 characters using A-Z, a-z, 0-9, _ or -)"
        )
    if cron_secret and len(cron_secret) < 24:
        issues.append("CRON_SECRET (must contain at least 24 characters)")
    if (
        config.env_value("RAILWAY_ENVIRONMENT_ID")
        and not config.env_value("HP_PUBLIC_BASE_URL")
        and not config.env_value("RAILWAY_PUBLIC_DOMAIN")
    ):
        issues.append("Railway public domain (generate one under Networking)")
    return list(dict.fromkeys(issues))


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


def _call_scheduled_endpoint(port: int, path: str, secret: str) -> None:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    try:
        with urlopen(request, timeout=240) as response:
            log.info("Scheduled job %s completed with HTTP %s", path, response.status)
    except HTTPError as exc:
        log.error("Scheduled job %s returned HTTP %s", path, exc.code)
    except (URLError, TimeoutError) as exc:
        log.error("Scheduled job %s could not run: %s", path, exc)


def scheduler_loop(stop_event: threading.Event, port: int) -> None:
    """Replace Vercel cron schedules inside the singleton Railway process."""
    secret = config.env_value("CRON_SECRET")
    intervals = {
        "/api/cron/restock": max(
            60, int(os.environ.get("HP_RESTOCK_INTERVAL_SECONDS", "300"))
        ),
        "/api/cron/prices": max(
            60, int(os.environ.get("HP_PRICE_INTERVAL_SECONDS", "600"))
        ),
        "/api/cron/pending-payments": max(
            10,
            int(os.environ.get(
                "HP_PENDING_PAYMENT_MONITOR_INTERVAL_SECONDS", "30"
            )),
        ),
        "/api/cron/codex-deadlines": max(
            10, int(os.environ.get("HP_CODEX_MONITOR_INTERVAL_SECONDS", "15"))
        ),
    }
    workers = []
    for path, interval in intervals.items():
        worker = threading.Thread(
            target=_scheduled_job_loop,
            args=(stop_event, port, path, secret, interval),
            name="scheduler-" + path.rsplit("/", 1)[-1],
            daemon=True,
        )
        worker.start()
        workers.append(worker)
    stop_event.wait()
    for worker in workers:
        worker.join(timeout=1)


def _scheduled_job_loop(stop_event, port, path, secret, interval):
    """A slow supplier must not delay payment checks or acceptance deadlines."""
    while not stop_event.wait(interval):
        try:
            _call_scheduled_endpoint(port, path, secret)
        except Exception:
            log.exception("Scheduled job %s failed", path)


def main() -> None:
    issues = deployment_issues()
    if issues:
        raise RuntimeError("Incomplete Railway configuration: " + ", ".join(issues))

    try:
        port = int(os.environ.get("PORT", "8080"))
        admin_port = int(os.environ.get("ADMIN_PORT", "8081"))
        storefront_port = int(os.environ.get("STOREFRONT_PORT", "8082"))
    except ValueError as exc:
        raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must be integers") from exc
    ports = {"PORT": port, "ADMIN_PORT": admin_port, "STOREFRONT_PORT": storefront_port}
    if any(not 1 <= value <= 65535 for value in ports.values()):
        raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must be between 1 and 65535")
    if len(set(ports.values())) != len(ports):
        raise RuntimeError("PORT, ADMIN_PORT and STOREFRONT_PORT must all be different")

    public_server = RailwayHTTPServer(("0.0.0.0", port), PublicHandler)
    admin_server = RailwayHTTPServer(("0.0.0.0", admin_port), AdminHandler)
    storefront_server = RailwayHTTPServer(("0.0.0.0", storefront_port), StorefrontHandler)
    try:
        # Initialize MongoDB and Telegram before Railway marks the deployment healthy.
        webhook._application()
        result = register_telegram_webhook()
        if not result.get("ok"):
            raise RuntimeError(
                result.get("message") or "Telegram webhook registration failed"
            )
    except Exception:
        public_server.server_close()
        admin_server.server_close()
        storefront_server.server_close()
        raise

    stop_event = threading.Event()
    scheduler = threading.Thread(
        target=scheduler_loop,
        args=(stop_event, admin_port),
        name="railway-scheduler",
        daemon=True,
    )
    scheduler.start()
    notification_worker = threading.Thread(
        target=webhook.notification_service.worker_loop,
        args=(stop_event,),
        name="admin-notifications",
        daemon=True,
    )
    notification_worker.start()

    def request_shutdown(_signum, _frame) -> None:
        stop_event.set()
        threading.Thread(target=public_server.shutdown, daemon=True).start()
        threading.Thread(target=admin_server.shutdown, daemon=True).start()
        threading.Thread(target=storefront_server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    log.info(
        "Public Telegram service listening on 0.0.0.0:%s (public URL: %s)",
        port,
        config.public_base_url_from_environment(),
    )
    log.info("Admin dashboard listening on 0.0.0.0:%s", admin_port)
    log.info("Tunisian storefront listening on 0.0.0.0:%s", storefront_port)
    admin_thread = threading.Thread(
        target=admin_server.serve_forever,
        kwargs={"poll_interval": 0.5},
        name="railway-admin-http",
        daemon=True,
    )
    admin_thread.start()
    storefront_thread = threading.Thread(
        target=storefront_server.serve_forever,
        kwargs={"poll_interval": 0.5},
        name="railway-storefront-http",
        daemon=True,
    )
    storefront_thread.start()
    try:
        public_server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        admin_server.shutdown()
        storefront_server.shutdown()
        admin_thread.join(timeout=5)
        storefront_thread.join(timeout=5)
        scheduler.join(timeout=5)
        notification_worker.join(timeout=5)
        public_server.server_close()
        admin_server.server_close()
        storefront_server.server_close()


if __name__ == "__main__":
    main()
