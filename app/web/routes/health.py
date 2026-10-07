"""Liveness for Railway and an authenticated operational view for admins."""

from __future__ import annotations

import hmac
import time
from typing import Any

from fastapi import Request
from starlette.responses import Response

from app.web.common import json_response, run_sync

_scheduler = None


def attach_scheduler(scheduler) -> None:
    """Expose the running scheduler's job state on the details endpoint."""
    global _scheduler
    _scheduler = scheduler


def cron_authorized(request: Request) -> bool:
    from config import env_value

    expected = env_value("CRON_SECRET")
    supplied = request.headers.get("authorization", "")
    return bool(expected) and hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


async def health(_request: Request) -> Response:
    from api.webhook import health_payload

    return json_response(health_payload())


async def details(request: Request) -> Response:
    """MongoDB latency, bot, job queue, cache and scheduler state."""
    if not cron_authorized(request):
        return json_response({"ok": False, "error": "Unauthorized"}, 401)
    from app.bot import runtime as bot_runtime
    from app.core import db as core_db
    from app.core import jobs
    from app.core.cache import cache

    checks: dict[str, Any] = {"timestamp": int(time.time())}
    healthy = True
    try:
        checks["mongo_ping_ms"] = await core_db.ping_ms()
    except Exception as exc:
        healthy = False
        checks["mongo_error"] = type(exc).__name__
    try:
        checks["jobs"] = await run_sync(jobs.backlog)
        checks["alerts"] = jobs.queue_alerts(checks["jobs"])
        healthy = healthy and not checks["alerts"]
    except Exception as exc:
        healthy = False
        checks["jobs_error"] = type(exc).__name__
    checks["bot_started"] = bot_runtime.is_started()
    checks["cache"] = cache.stats()
    checks["scheduler"] = _scheduler.snapshot() if _scheduler is not None else []
    if request.query_params.get("telegram") == "1":
        from api.webhook import telegram_webhook_health

        checks["telegram"] = await run_sync(telegram_webhook_health)
        healthy = healthy and bool(checks["telegram"].get("healthy"))
    return json_response(
        {"ok": healthy, **checks}, 200 if healthy else 503, {"Cache-Control": "no-store"},
    )
