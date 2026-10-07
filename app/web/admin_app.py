"""Admin surface: dashboard, admin API, cron endpoints and operational health."""

from __future__ import annotations

from fastapi import Request
from starlette.responses import Response

from app.web import common, legacy_bridge, surfaces
from app.web.routes import catalog, health, telegram

attach_scheduler = health.attach_scheduler

ROUTES: common.Routes = {
    ("GET", "/health"): health.health,
    ("GET", "/api/health/details"): health.details,
    ("GET", "/api/storefront/catalog"): catalog.storefront_catalog,
    ("POST", "/api/webhook"): telegram.webhook,
}


async def entry(request: Request) -> Response:
    from railway_server import AdminHandler

    path = surfaces.normalized_request_path(common.raw_target(request))
    handler = common.native_handler(ROUTES, request.method, path)
    if handler is not None:
        return await handler(request)
    return await legacy_bridge.dispatch(AdminHandler, request)


app = common.build_app(surface="admin", headers=surfaces.ADMIN_HEADERS, entry=entry)
