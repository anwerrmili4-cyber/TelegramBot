"""Periodic maintenance jobs.

Each job returns ``(http_status, result)`` so the authenticated ``/api/cron/*``
endpoints and the in-process scheduler share one implementation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import database as db
from app.domain import order_service, reseller_service

log = logging.getLogger(__name__)


def _dedupe_key(prefix: str, event: dict[str, Any]) -> str:
    source = {"window": int(time.time() // 300), "event": event}
    return prefix + hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:32]


def run_restock_check() -> tuple[int, dict[str, Any]]:
    """Detect supplier restocks and queue the stock announcements."""
    from bot import queue_broadcast

    try:
        result = reseller_service.detect_restock_events()
        queued_jobs = [
            queue_broadcast(
                "stock",
                offer_id=int(event["offer_id"]),
                added=max(0, int(event.get("added") or 0)),
                stock=max(0, int(event.get("stock") or 0)),
                supplier_event=event,
                dedupe_key=_dedupe_key("restock:", event),
            )
            for event in result["events"]
        ]
        result["queued_broadcasts"] = sum(1 for job in queued_jobs if job["queued"])
        result["queued_recipients"] = sum(
            job.get("recipient_count", 0) for job in queued_jobs if job["queued"]
        )
        result["announced_messages"] = 0
        db.set_setting("stock_cron_last_run_at", int(time.time()))
        db.set_setting("stock_cron_last_status", "ok" if result["ok"] else "partial")
        db.set_setting("stock_cron_last_checked", int(result["checked"]))
        db.set_setting("stock_cron_last_events", len(result["events"]))
        db.set_setting("stock_cron_last_announced", 0)
        db.set_setting("stock_cron_last_queued", result["queued_broadcasts"])
        return (200 if result["ok"] else 207), result
    except Exception as exc:
        log.exception("Automatic reseller stock check failed")
        db.set_setting("stock_cron_last_run_at", int(time.time()))
        db.set_setting("stock_cron_last_status", "failed")
        return 500, {"ok": False, "error": str(exc)}


def run_price_check() -> tuple[int, dict[str, Any]]:
    """Detect supplier price changes and queue flash-sale announcements."""
    from bot import queue_broadcast

    try:
        result = reseller_service.detect_supplier_price_changes()
        db.set_setting("price_cron_last_run_at", int(time.time()))
        db.set_setting("price_cron_last_status", "queueing")
        db.set_setting("price_cron_last_checked", int(result["checked"]))
        db.set_setting("price_cron_last_changes", len(result["changes"]))
        db.set_setting("price_cron_last_flash_sales", len(result["flash_sales"]))
        queued = 0
        queued_recipients = 0
        for event in result["changes"]:
            job = queue_broadcast(
                "api_flash_sale" if event.get("decreased") else "supplier_price_update",
                event=event,
                dedupe_key=_dedupe_key("api-price:", event),
            )
            queued += int(job["queued"])
            queued_recipients = max(queued_recipients, job["recipient_count"])
        result["queued_broadcasts"] = queued
        result["queued_recipients"] = queued_recipients
        result["announced_messages"] = 0
        db.set_setting("price_cron_last_status", "ok" if result["ok"] else "partial")
        db.set_setting("price_cron_last_announced", 0)
        db.set_setting("price_cron_last_queued", queued)
        return (200 if result["ok"] else 207), result
    except Exception as exc:
        log.exception("Automatic reseller price check failed")
        db.set_setting("price_cron_last_run_at", int(time.time()))
        db.set_setting("price_cron_last_status", "failed")
        return 500, {"ok": False, "error": str(exc)}


def run_pending_payments() -> tuple[int, dict[str, Any]]:
    """Cancel bot orders whose payment window elapsed."""
    try:
        cancelled_ids = order_service.cancel_stale_pending_orders()
        return 200, {"ok": True, "cancelled": len(cancelled_ids), "order_ids": cancelled_ids}
    except Exception as exc:
        log.exception("Pending-payment cancellation monitor failed")
        return 500, {"ok": False, "error": str(exc)}


def run_codex_deadlines() -> tuple[int, dict[str, Any]]:
    """Expire Codex-number orders whose acceptance window elapsed."""
    from app.bot import runtime as bot_runtime
    from bot import monitor_codex_number_deadlines

    try:
        expired = bot_runtime.run(monitor_codex_number_deadlines(bot_runtime.application().bot))
        return 200, {
            "ok": True,
            "expired": len(expired),
            "order_ids": [int(order["id"]) for order in expired],
        }
    except Exception as exc:
        log.exception("Codex acceptance deadline monitor failed")
        return 500, {"ok": False, "error": str(exc)}


def run_queue_monitor() -> tuple[int, dict[str, Any]]:
    """Log an error Railway can alert on when background jobs pile up or give up."""
    from app.core import jobs

    counts = jobs.backlog()
    alerts = jobs.queue_alerts(counts)
    for alert in alerts:
        log.error("job_queue_alert %s", alert, extra={"jobs": counts})
    return 200, {"ok": not alerts, "jobs": counts, "alerts": alerts}


JOBS = {
    "/api/cron/restock": run_restock_check,
    "/api/cron/prices": run_price_check,
    "/api/cron/pending-payments": run_pending_payments,
    "/api/cron/codex-deadlines": run_codex_deadlines,
}
