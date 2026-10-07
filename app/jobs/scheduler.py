"""In-process scheduler for the singleton Railway service.

Each periodic job has its own loop, so a slow supplier sync can never delay
the payment monitor or the Codex acceptance deadlines. Jobs call the domain
functions directly instead of going through the cron HTTP endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import ScheduleSettings
from app.jobs import scheduled

log = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: float
    function: Callable[[], tuple[int, dict[str, Any]]]
    runs: int = 0
    failures: int = 0
    last_status: int | None = None
    last_run_at: float | None = None
    last_duration_ms: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "runs": self.runs,
            "failures": self.failures,
            "last_status": self.last_status,
            "last_run_at": self.last_run_at,
            "last_duration_ms": self.last_duration_ms,
        }


def default_jobs(schedule: ScheduleSettings) -> list[ScheduledJob]:
    return [
        ScheduledJob("restock", schedule.restock_seconds, scheduled.run_restock_check),
        ScheduledJob("prices", schedule.prices_seconds, scheduled.run_price_check),
        ScheduledJob("pending-payments", schedule.pending_payments_seconds, scheduled.run_pending_payments),
        ScheduledJob("codex-deadlines", schedule.codex_deadlines_seconds, scheduled.run_codex_deadlines),
        ScheduledJob("queue-monitor", 60, scheduled.run_queue_monitor),
    ]


class Scheduler:
    def __init__(self, jobs: list[ScheduledJob]):
        self.jobs = jobs

    async def run_once(self, job: ScheduledJob) -> None:
        if job._lock.locked():
            return
        async with job._lock:
            started = time.perf_counter()
            job.last_run_at = time.time()
            try:
                status, _result = await asyncio.to_thread(job.function)
            except Exception:
                status = 500
                log.exception("scheduled_job_crashed job=%s", job.name)
            job.runs += 1
            job.last_status = status
            job.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            if status >= 500:
                job.failures += 1
                log.error("scheduled_job_failed job=%s status=%s", job.name, status)
            else:
                log.info(
                    "scheduled_job_done job=%s status=%s duration_ms=%s",
                    job.name, status, job.last_duration_ms,
                )

    async def _loop(self, job: ScheduledJob, stop: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=job.interval_seconds)
                return
            except TimeoutError:
                pass
            await self.run_once(job)

    async def run(self, stop: asyncio.Event) -> None:
        await asyncio.gather(*(self._loop(job, stop) for job in self.jobs))

    def snapshot(self) -> list[dict[str, Any]]:
        return [job.snapshot() for job in self.jobs]
