"""Public surface: Telegram webhook, landing page, buyer API. Dashboard routes are blocked."""

from __future__ import annotations

from fastapi import Request
from starlette.responses import Response

from app.web import common, legacy_bridge, surfaces
from app.web.routes import catalog, health, telegram

ROUTES: common.Routes = {
    ("GET", "/health"): health.health,
    ("GET", "/api/storefront/catalog"): catalog.storefront_catalog,
    ("POST", "/api/webhook"): telegram.webhook,
}


async def entry(request: Request) -> Response:
    from railway_server import PublicHandler

    target = common.raw_target(request)
    if not surfaces.is_admin_path(target):
        path = surfaces.normalized_request_path(target)
        handler = common.native_handler(ROUTES, request.method, path)
        if handler is not None:
            return await handler(request)
    return await legacy_bridge.dispatch(PublicHandler, request)


app = common.build_app(surface="public", headers=surfaces.PUBLIC_HEADERS, entry=entry)
