"""Public storefront catalog, served from the in-memory cache."""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.responses import Response

from app.web.common import json_response, run_sync

log = logging.getLogger(__name__)


async def storefront_catalog(_request: Request) -> Response:
    from app.domain import storefront_service

    try:
        payload = await run_sync(storefront_service.catalog)
    except Exception:
        log.exception("Storefront catalog request failed")
        return json_response(
            {"ok": False, "error": "Catalogue temporairement indisponible."},
            503,
            {"Access-Control-Allow-Origin": "*"},
        )
    return json_response(payload, headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60",
    })
