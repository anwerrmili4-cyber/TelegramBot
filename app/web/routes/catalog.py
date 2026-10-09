"""Public storefront catalog, served from the in-memory cache."""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.responses import Response

from app.web.common import json_response, run_sync

log = logging.getLogger(__name__)


async def storefront_catalog(_request: Request) -> Response:
    from app.core.cache import cache
    from app.domain import storefront_service

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60",
    }
    found, body = cache.get(storefront_service.CATALOG_BODY_KEY)
    try:
        if found:
            # The bytes are already built. Stay on the event loop so a burst
            # of visitors is not queued behind the thread pool.
            storefront_service.note_catalog_view()
        else:
            body = await run_sync(storefront_service.catalog_body)
    except Exception:
        log.exception("Storefront catalog request failed")
        return json_response(
            {"ok": False, "error": "Catalogue temporairement indisponible."},
            503,
            {"Access-Control-Allow-Origin": "*"},
        )
    return Response(body, media_type="application/json", headers=headers)
