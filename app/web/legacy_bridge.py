"""Serve not-yet-ported routes through the original ``BaseHTTPRequestHandler`` classes.

Each request runs the handler against an in-memory socket on a bounded thread
pool, so every route keeps its exact behaviour (auth, CSRF checks, security
headers, port isolation) while uvicorn handles HTTP parsing, keep-alive and
concurrency. Routes move to native FastAPI handlers one group at a time.
"""

from __future__ import annotations

import contextvars
import http.client
import io
import logging
from http.server import BaseHTTPRequestHandler

import anyio
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 32 * 1024 * 1024
_HOP_BY_HOP = frozenset({"content-length", "connection", "keep-alive", "transfer-encoding", "server", "date"})
_limiter: anyio.CapacityLimiter | None = None


def _capacity() -> anyio.CapacityLimiter:
    global _limiter
    if _limiter is None:
        # One worker can hold a request for a logged-in member (account, order,
        # page view). A hundred members at once need a slot each, with room
        # for the requests that overlap.
        _limiter = anyio.CapacityLimiter(160)
    return _limiter


class _NullServer:
    server_name = "blackmarket"
    server_port = 0


class _InMemoryRequest:
    """The parts of a socket ``BaseHTTPRequestHandler`` touches."""

    def __init__(self, handler_class: type[BaseHTTPRequestHandler]):
        self.handler_class = handler_class

    def run(
        self,
        method: str,
        target: str,
        headers: list[tuple[str, str]],
        body: bytes,
        client: tuple[str, int],
    ) -> bytes:
        handler = self.handler_class.__new__(self.handler_class)
        raw_headers = "".join(f"{name}: {value}\r\n" for name, value in headers) + "\r\n"
        handler.headers = http.client.parse_headers(io.BytesIO(raw_headers.encode("latin-1", "replace")))
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.client_address = client
        handler.server = _NullServer()
        handler.command = method
        handler.path = target
        handler.request_version = "HTTP/1.1"
        handler.requestline = f"{method} {target} HTTP/1.1"
        handler.close_connection = True
        handler.raw_requestline = handler.requestline.encode("latin-1", "replace") + b"\r\n"
        operation = getattr(handler, "do_" + method, None)
        if operation is None:
            handler.send_error(501, f"Unsupported method ({method!r})")
        else:
            operation()
        if hasattr(handler, "_headers_buffer") and handler._headers_buffer:
            handler.flush_headers()
        return handler.wfile.getvalue()


def parse_raw_response(raw: bytes) -> tuple[int, list[tuple[str, str]], bytes]:
    head, separator, body = raw.partition(b"\r\n\r\n")
    if not separator:
        return 502, [("content-type", "application/json")], b'{"ok":false,"error":"empty_response"}'
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ", 2)[1])
    headers = []
    for line in lines[1:]:
        name, _, value = line.partition(":")
        if name and name.strip().lower() not in _HOP_BY_HOP:
            headers.append((name.strip().lower(), value.strip()))
    return status, headers, body


def _client(request: Request) -> tuple[str, int]:
    if request.client:
        return request.client.host, request.client.port
    return "127.0.0.1", 0


async def dispatch(handler_class: type[BaseHTTPRequestHandler], request: Request) -> Response:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return Response(b'{"ok":false,"error":"payload_too_large"}', 413, media_type="application/json")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            return Response(b'{"ok":false,"error":"payload_too_large"}', 413, media_type="application/json")
    headers = [(name.decode("latin-1"), value.decode("latin-1")) for name, value in request.scope["headers"]]
    if body and not any(name.lower() == "content-length" for name, _ in headers):
        headers.append(("Content-Length", str(len(body))))
    target = request.scope.get("raw_path", b"").decode("latin-1") or request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    runner = _InMemoryRequest(handler_class)
    context = contextvars.copy_context()
    raw = await anyio.to_thread.run_sync(
        context.run,
        runner.run,
        request.method,
        target,
        headers,
        bytes(body),
        _client(request),
        limiter=_capacity(),
    )
    status, response_headers, payload = parse_raw_response(raw)
    response = Response(payload if request.method != "HEAD" else b"", status_code=status)
    del response.headers["content-length"]
    for name, value in response_headers:
        response.headers.append(name, value)
    response.headers["content-length"] = str(len(payload))
    return response
