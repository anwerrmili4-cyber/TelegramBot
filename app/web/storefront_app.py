"""Tunisian storefront surface: the built SPA and the storefront API only."""

from __future__ import annotations

from fastapi import Request
from starlette.responses import Response

from app.web import common, legacy_bridge, surfaces
from app.web.routes import catalog, health
from app.web.routes.storefront_spa import spa_response

ROUTES: common.Routes = {
    ("GET", "/health"): health.health,
    ("GET", "/api/storefront/catalog"): catalog.storefront_catalog,
}


async def entry(request: Request) -> Response:
    from railway_server import StorefrontHandler

    target = common.raw_target(request)
    path = surfaces.normalized_request_path(target)
    handler = common.native_handler(ROUTES, request.method, path)
    if handler is not None:
        return await handler(request)
    if request.method in {"GET", "HEAD"} and not path.startswith("/api/") and not surfaces.is_admin_path(target):
        return spa_response(path)
    return await legacy_bridge.dispatch(StorefrontHandler, request)


app = common.build_app(surface="storefront", headers=surfaces.STOREFRONT_HEADERS, entry=entry)
