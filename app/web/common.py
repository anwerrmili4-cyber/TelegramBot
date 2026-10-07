"""Pieces shared by the three FastAPI surfaces."""

from __future__ import annotations

import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import orjson
from fastapi import FastAPI, Request
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

log = logging.getLogger("http")

SLOW_REQUEST_MS = 1000
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return str(value)


def json_response(payload: Any, status_code: int = 200, headers: dict[str, str] | None = None) -> Response:
    body = orjson.dumps(payload, default=_json_default, option=orjson.OPT_NON_STR_KEYS)
    return Response(body, status_code=status_code, media_type="application/json", headers=headers)


class RequestContextMiddleware:
    """Tag every request with an id, add surface headers, log slow and failed calls."""

    def __init__(self, app: ASGIApp, *, surface: str, headers: dict[str, str]):
        self.app = app
        self.surface = surface
        self.headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                supplied = value.decode("latin-1")
                break
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else secrets.token_hex(8)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(name, value) for name, value in self.headers if name not in present]
                message["headers"] = [*message.get("headers", []), *extra, (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            status = status_holder["status"]
            if status >= 500 or elapsed_ms >= SLOW_REQUEST_MS:
                log.log(
                    logging.ERROR if status >= 500 else logging.WARNING,
                    "http_request surface=%s method=%s path=%s status=%s duration_ms=%s",
                    self.surface, scope.get("method"), scope.get("path"), status, elapsed_ms,
                    extra={"surface": self.surface, "status": status, "duration_ms": elapsed_ms},
                )
            request_id_var.reset(token)


def build_app(*, surface: str, headers: dict[str, str], entry: Callable) -> FastAPI:
    """One catch-all route: ``entry`` dispatches natively or to the legacy handler."""
    app = FastAPI(
        title=f"BlackMarket {surface}",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_api_route(
        "/{full_path:path}",
        entry,
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    app.add_middleware(RequestContextMiddleware, surface=surface, headers=headers)
    return app


def raw_target(request: Request) -> str:
    raw = request.scope.get("raw_path", b"").decode("latin-1") or request.url.path
    return raw + (f"?{request.url.query}" if request.url.query else "")


async def run_sync(function: Callable[..., Any], *args: Any) -> Any:
    return await anyio.to_thread.run_sync(function, *args)


Routes = dict[tuple[str, str], Callable[[Request], Awaitable[Response]]]


def native_handler(routes: Routes, method: str, path: str):
    """HEAD is answered by the GET handler."""
    handler = routes.get((method, path))
    if handler is None and method == "HEAD":
        handler = routes.get(("GET", path))
    return handler
