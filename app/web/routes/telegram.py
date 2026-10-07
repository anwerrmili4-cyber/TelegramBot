"""Telegram webhook: acknowledge at once, process the update on the bot loop."""

from __future__ import annotations

import hmac
import logging

import orjson
from fastapi import Request
from starlette.responses import Response

from app.web.common import json_response, run_sync

log = logging.getLogger(__name__)

MAX_WEBHOOK_BODY_BYTES = 1_000_000


async def webhook(request: Request) -> Response:
    import database as db
    from app.bot import runtime as bot_runtime
    from config import env_value

    secret = env_value("HP_WEBHOOK_SECRET")
    if not secret:
        log.error("HP_WEBHOOK_SECRET is not configured; refusing webhook request")
        return json_response({"ok": False, "error": "webhook_not_configured"}, 503)
    supplied = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        return json_response({"ok": False, "error": "invalid webhook secret"}, 403)
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        return json_response({"ok": False, "error": "content_type_must_be_json"}, 415)
    declared = request.headers.get("content-length", "")
    if declared and (not declared.isdigit() or not 0 < int(declared) <= MAX_WEBHOOK_BODY_BYTES):
        return json_response({"ok": False, "error": "invalid_body_size"}, 413)
    body = await request.body()
    if not body or len(body) > MAX_WEBHOOK_BODY_BYTES:
        return json_response({"ok": False, "error": "invalid_body_size"}, 413)
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        return json_response({"ok": False, "error": "invalid_update"}, 400)
    if not isinstance(payload, dict):
        return json_response({"ok": False, "error": "invalid_update"}, 400)
    update_id = payload.get("update_id")
    if update_id is None or not await run_sync(db.claim_update, update_id):
        return json_response({"ok": True, "duplicate": True})
    try:
        await run_sync(bot_runtime.submit_update, payload)
    except Exception:
        await run_sync(db.release_update, update_id)
        log.exception("webhook_processing_failed update_id=%s", update_id)
        return json_response({"ok": False}, 500)
    return json_response({"ok": True})
