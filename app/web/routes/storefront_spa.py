"""The built storefront single-page app; hashed assets are cached immutably."""

from __future__ import annotations

from starlette.responses import FileResponse, Response

from api import storefront_site
from app.web.common import json_response


def spa_response(path: str) -> Response:
    target = storefront_site.resolve(path)
    if target is None:
        return json_response({
            "ok": False,
            "error": "storefront_not_built",
            "message": storefront_site.BUILD_MISSING_MESSAGE,
        }, 503)
    return FileResponse(
        target,
        media_type=storefront_site.content_type(target),
        headers={"Cache-Control": storefront_site.cache_control(target)},
    )
