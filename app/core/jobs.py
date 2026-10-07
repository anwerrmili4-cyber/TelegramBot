"""Durable background jobs stored in MongoDB.

Request handlers enqueue work and return at once; :class:`JobRunner` executes
it on the server's event loop. A job is claimed atomically with a lease, so a
crash mid-run only delays it until the lease expires, and failures retry with
exponential backoff up to ``max_attempts``.

Handlers are plain functions (run in a worker thread, since the domain layer
is synchronous) or coroutines (awaited on the loop).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

import database as db

log = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 300
MAX_BACKOFF_SECONDS = 3600
DONE_RETENTION_SECONDS = 7 * 86400

_handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
_wakeup = threading.Event()
_runner_active = threading.Event()


def runner_active() -> bool:
    return _runner_active.is_set()


def dispatch(kind: str, payload: dict[str, Any], *, fallback: Callable[[], Any], **options: Any) -> int | None:
    """Queue a job when a runner is consuming the queue; otherwise run ``fallback`` now.

    The fallback keeps standalone tools (polling bot, scripts) working, and
    covers a database outage at enqueue time. It runs on a daemon thread so
    the caller never waits on the network.
    """
    if runner_active():
        try:
            return enqueue(kind, payload, **options)
        except Exception:
            log.exception("job_enqueue_failed kind=%s; running inline", kind)

    def run_fallback() -> None:
        try:
            fallback()
        except Exception:
            log.exception("job_fallback_failed kind=%s", kind)

    threading.Thread(target=run_fallback, name=f"job-{kind}", daemon=True).start()
    return None


def handler(kind: str):
    """Register the function that executes jobs of ``kind``."""
    def register(function):
        _handlers[kind] = function
        return function
    return register


def registered_kinds() -> list[str]:
    return sorted(_handlers)


def ensure_indexes(conn=None) -> None:
    conn = conn if conn is not None else db.get_conn()
    conn.jobs.create_index("id", unique=True)
    conn.jobs.create_index([("status", ASCENDING), ("run_at", ASCENDING)])
    conn.jobs.create_index([("status", ASCENDING), ("lease_until", ASCENDING)])
    conn.jobs.create_index(
        "dedupe_key", unique=True, partialFilterExpression={"dedupe_key": {"$type": "string"}},
    )
    conn.jobs.create_index("finished_at_date", expireAfterSeconds=DONE_RETENTION_SECONDS)


def enqueue(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    delay_seconds: float = 0,
    dedupe_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> int | None:
    """Store a job and wake the runner. Returns ``None`` for a duplicate key."""
    now = time.time()
    job = {
        "id": db._next_id("jobs"),
        "kind": kind,
        "payload": dict(payload or {}),
        "status": QUEUED,
        "attempts": 0,
        "max_attempts": max(1, int(max_attempts)),
        "run_at": now + max(0.0, float(delay_seconds)),
        "created_at": now,
        "lease_until": None,
        "last_error": "",
    }
    if dedupe_key:
        job["dedupe_key"] = str(dedupe_key)
    try:
        db.get_conn().jobs.insert_one(job)
    except DuplicateKeyError:
        return None
    _wakeup.set()
    return job["id"]


def claim(worker: str, *, lease_seconds: float = DEFAULT_LEASE_SECONDS, now: float | None = None):
    """Take the oldest due job, or one whose previous lease expired."""
    now = time.time() if now is None else now
    row = db.get_conn().jobs.find_one_and_update(
        {"$or": [
            {"status": QUEUED, "run_at": {"$lte": now}},
            {"status": RUNNING, "lease_until": {"$lte": now}},
        ]},
        {
            "$set": {"status": RUNNING, "worker": worker, "lease_until": now + lease_seconds, "started_at": now},
            "$inc": {"attempts": 1},
        },
        sort=[("run_at", ASCENDING), ("id", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )
    return db._public(row)


def complete(job: dict[str, Any]) -> None:
    now = time.time()
    db.get_conn().jobs.update_one(
        {"id": job["id"], "status": RUNNING},
        {"$set": {
            "status": DONE,
            "finished_at": now,
            "finished_at_date": _utc(now),
            "lease_until": None,
        }},
    )


def backoff_seconds(attempts: int) -> float:
    return float(min(MAX_BACKOFF_SECONDS, 10 * 2 ** max(0, attempts - 1)))


def fail(job: dict[str, Any], error: str, *, now: float | None = None) -> str:
    """Schedule a retry, or mark the job failed once its attempts are spent."""
    now = time.time() if now is None else now
    attempts = int(job.get("attempts") or 1)
    final = attempts >= int(job.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
    update: dict[str, Any] = {"last_error": str(error)[:2000], "lease_until": None}
    if final:
        update.update({"status": FAILED, "finished_at": now, "finished_at_date": _utc(now)})
    else:
        update.update({"status": QUEUED, "run_at": now + backoff_seconds(attempts)})
    db.get_conn().jobs.update_one({"id": job["id"], "status": RUNNING}, {"$set": update})
    return FAILED if final else QUEUED


def backlog(now: float | None = None) -> dict[str, int]:
    """Counts used by the health endpoint to spot a stuck or failing queue."""
    now = time.time() if now is None else now
    jobs = db.get_conn().jobs
    return {
        "due": jobs.count_documents({"status": QUEUED, "run_at": {"$lte": now}}),
        "scheduled": jobs.count_documents({"status": QUEUED, "run_at": {"$gt": now}}),
        "running": jobs.count_documents({"status": RUNNING}),
        "failed": jobs.count_documents({"status": FAILED}),
        "failed_last_hour": jobs.count_documents({"status": FAILED, "finished_at": {"$gte": now - 3600}}),
    }


BACKLOG_ALERT_THRESHOLD = max(1, int(os.environ.get("HP_JOB_BACKLOG_ALERT", "50") or 50))


def queue_alerts(counts: dict[str, int]) -> list[str]:
    """Conditions an operator should hear about: a growing backlog or jobs that gave up."""
    alerts = []
    if counts.get("due", 0) >= BACKLOG_ALERT_THRESHOLD:
        alerts.append(f"{counts['due']} jobs are waiting (alert at {BACKLOG_ALERT_THRESHOLD})")
    if counts.get("failed_last_hour", 0):
        alerts.append(f"{counts['failed_last_hour']} jobs failed permanently in the last hour")
    return alerts


def run_one(job: dict[str, Any]) -> Any:
    """Execute a claimed job synchronously (used by tests and the runner)."""
    function = _handlers.get(job["kind"])
    if function is None:
        raise LookupError(f"No handler registered for job kind {job['kind']!r}")
    return function(dict(job.get("payload") or {}))


def _utc(timestamp: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, UTC)


class JobRunner:
    """Pull due jobs and run up to ``concurrency`` of them at a time."""

    def __init__(self, *, concurrency: int | None = None, poll_seconds: float = 2.0):
        self.concurrency = max(1, int(concurrency or os.environ.get("HP_JOB_CONCURRENCY", "4")))
        self.poll_seconds = poll_seconds
        self.worker = f"{os.getpid()}-{id(self):x}"

    async def _execute(self, job: dict[str, Any]) -> None:
        function = _handlers.get(job["kind"])
        try:
            if function is None:
                raise LookupError(f"No handler registered for job kind {job['kind']!r}")
            payload = dict(job.get("payload") or {})
            if inspect.iscoroutinefunction(function):
                await function(payload)
            else:
                await asyncio.to_thread(function, payload)
        except Exception as exc:
            outcome = await asyncio.to_thread(fail, job, repr(exc))
            log.exception("job_failed id=%s kind=%s outcome=%s", job["id"], job["kind"], outcome)
            return
        await asyncio.to_thread(complete, job)

    async def run(self, stop: asyncio.Event) -> None:
        _runner_active.set()
        try:
            await self._run(stop)
        finally:
            _runner_active.clear()

    async def _run(self, stop: asyncio.Event) -> None:
        running: set[asyncio.Task] = set()
        while not stop.is_set():
            claimed = False
            while len(running) < self.concurrency:
                try:
                    job = await asyncio.to_thread(claim, self.worker)
                except Exception:
                    log.exception("job_claim_failed")
                    break
                if job is None:
                    break
                claimed = True
                task = asyncio.create_task(self._execute(job))
                running.add(task)
                task.add_done_callback(running.discard)
                task.add_done_callback(lambda _task: _wakeup.set())
            if claimed:
                continue
            _wakeup.clear()
            await _wait_for_wakeup(stop, self.poll_seconds)
        if running:
            await asyncio.gather(*running, return_exceptions=True)


async def _wait_for_wakeup(stop: asyncio.Event, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not stop.is_set() and not _wakeup.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
