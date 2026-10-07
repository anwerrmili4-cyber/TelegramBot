"""Shared infrastructure: cache, write listener, job queue, logging, settings."""

import asyncio
import json
import logging
import threading
import time
from types import SimpleNamespace

import pytest

import database as db
from app.core import cache as cache_module
from app.core import config as core_config
from app.core import jobs
from app.core.cache import TTLCache
from app.core.db import CatalogWriteListener
from app.core.logging import JsonFormatter, RequestIdFilter, request_id_var
from app.domain import reseller_service, storefront_service


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_cache_returns_the_stored_value_until_it_expires():
    clock = FakeClock()
    store = TTLCache(clock=clock)
    calls = []

    def load():
        calls.append(1)
        return len(calls)

    assert store.get_or_set("k", 5, load) == 1
    assert store.get_or_set("k", 5, load) == 1
    clock.now += 6
    assert store.get_or_set("k", 5, load) == 2
    assert store.stats()["misses"] == 2


def test_cache_invalidation_by_prefix_keeps_other_keys():
    store = TTLCache()
    store.set("catalog:a", 1, 60)
    store.set("other", 2, 60)
    store.invalidate("catalog:")
    assert store.get("catalog:a") == (False, None)
    assert store.get("other") == (True, 2)


def test_concurrent_misses_load_once():
    store = TTLCache()
    started = threading.Event()
    release = threading.Event()
    calls = []

    def load():
        calls.append(1)
        started.set()
        release.wait(2)
        return "value"

    results = []
    threads = [threading.Thread(target=lambda: results.append(store.get_or_set("k", 60, load))) for _ in range(5)]
    for thread in threads:
        thread.start()
    started.wait(2)
    release.set()
    for thread in threads:
        thread.join(2)

    assert results == ["value"] * 5
    assert len(calls) == 1


def test_a_value_loaded_during_an_invalidation_is_not_stored():
    store = TTLCache()

    def load():
        store.invalidate("catalog:")
        return "stale"

    assert store.get_or_set("catalog:x", 60, load) == "stale"
    assert store.get("catalog:x") == (False, None)


def _event(name, command, request_id=1):
    return SimpleNamespace(command_name=name, command=command, connection_id=("h", 1), request_id=request_id)


def test_catalog_writes_invalidate_and_other_writes_do_not(monkeypatch):
    invalidations = []
    monkeypatch.setattr("app.core.db.invalidate_catalog", lambda: invalidations.append(1))
    listener = CatalogWriteListener()

    listener.started(_event("update", {"update": "offers"}, 1))
    listener.started(_event("insert", {"insert": "orders"}, 2))
    listener.started(_event("find", {"find": "offers"}, 3))
    listener.succeeded(_event("insert", {}, 2))
    listener.succeeded(_event("find", {}, 3))
    assert invalidations == []
    listener.succeeded(_event("update", {}, 1))
    assert invalidations == [1]

    listener.started(_event("findAndModify", {"findAndModify": "services"}, 4))
    listener.failed(_event("findAndModify", {}, 4))
    assert invalidations == [1]


def test_catalog_is_served_from_cache_until_invalidated(mock_mongodb, monkeypatch):
    monkeypatch.setattr(storefront_service, "CATALOG_CACHE_SECONDS", 60)
    service_id = db.add_service("Netflix", "🎬", sales_channels=["bot", "tn_site"])
    db.add_offer(service_id, "Premium", 5.0, 3, sales_channels=["bot", "tn_site"], tn_price_millimes=15000)
    first = storefront_service.catalog()
    db.add_offer(service_id, "Basic", 3.0, 3, sales_channels=["bot", "tn_site"], tn_price_millimes=9000)

    assert storefront_service.catalog() is first
    cache_module.invalidate_catalog()
    names = [offer["name"] for offer in storefront_service.catalog()["services"][0]["offers"]]
    assert sorted(names) == ["Basic", "Premium"]


def test_background_supplier_refresh_never_blocks_and_runs_one_at_a_time(monkeypatch):
    monkeypatch.setattr(reseller_service, "SUPPLIER_REFRESH_IN_BACKGROUND", True)
    monkeypatch.setattr(reseller_service, "_background_refresh_started_at", 0.0)
    release = threading.Event()
    calls = []

    def slow_refresh():
        calls.append(1)
        release.wait(2)

    monkeypatch.setattr(reseller_service, "refresh_supplier_stock", slow_refresh)
    started = time.perf_counter()
    reseller_service.refresh_supplier_stock_in_background()
    monkeypatch.setattr(reseller_service, "_background_refresh_started_at", 0.0)
    reseller_service.refresh_supplier_stock_in_background()
    elapsed = time.perf_counter() - started
    release.set()
    deadline = time.time() + 2
    while reseller_service._background_refresh_running.locked() and time.time() < deadline:
        time.sleep(0.01)

    assert elapsed < 0.5
    assert calls == [1]


def test_jobs_run_retry_with_backoff_and_fail_after_max_attempts(mock_mongodb):
    attempts = []

    @jobs.handler("test.flaky")
    def flaky(payload):
        attempts.append(payload["n"])
        raise RuntimeError("boom")

    job_id = jobs.enqueue("test.flaky", {"n": 1}, max_attempts=2)
    job = jobs.claim("w")
    assert job["id"] == job_id and job["attempts"] == 1
    with pytest.raises(RuntimeError):
        jobs.run_one(job)
    assert jobs.fail(job, "boom", now=1000.0) == jobs.QUEUED
    row = mock_mongodb.jobs.find_one({"id": job_id})
    assert row["run_at"] == 1000.0 + jobs.backoff_seconds(1)

    job = jobs.claim("w", now=row["run_at"])
    assert job["attempts"] == 2
    assert jobs.fail(job, "boom") == jobs.FAILED
    assert jobs.backlog()["failed"] == 1


def test_jobs_dedupe_and_expired_leases(mock_mongodb):
    assert jobs.enqueue("test.noop", dedupe_key="once")
    assert jobs.enqueue("test.noop", dedupe_key="once") is None
    job = jobs.claim("crashed", lease_seconds=10, now=time.time())
    assert jobs.claim("other", now=time.time()) is None
    retaken = jobs.claim("other", now=time.time() + 11)
    assert retaken["id"] == job["id"] and retaken["worker"] == "other"


def test_job_runner_executes_sync_and_async_handlers(mock_mongodb):
    seen = []

    @jobs.handler("test.sync")
    def sync_job(payload):
        seen.append(("sync", payload["v"]))

    @jobs.handler("test.async")
    async def async_job(payload):
        seen.append(("async", payload["v"]))

    jobs.enqueue("test.sync", {"v": 1})
    jobs.enqueue("test.async", {"v": 2})

    async def main():
        stop = asyncio.Event()
        runner = jobs.JobRunner(concurrency=2, poll_seconds=0.2)
        task = asyncio.create_task(runner.run(stop))
        for _ in range(50):
            if mock_mongodb.jobs.count_documents({"status": jobs.DONE}) == 2:
                break
            await asyncio.sleep(0.05)
        stop.set()
        await task

    asyncio.run(main())
    assert sorted(seen) == [("async", 2), ("sync", 1)]
    assert mock_mongodb.jobs.count_documents({"status": jobs.DONE}) == 2


def test_json_logs_carry_the_request_id():
    record = logging.LogRecord("svc", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.order_id = 7
    token = request_id_var.set("req-123")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "hello world"
    assert entry["request_id"] == "req-123"
    assert entry["order_id"] == 7


def test_runtime_settings_reject_duplicate_ports(monkeypatch):
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("ADMIN_PORT", "9000")
    with pytest.raises(RuntimeError, match="different"):
        core_config.RuntimeSettings.from_env()
    monkeypatch.setenv("ADMIN_PORT", "9001")
    monkeypatch.setenv("HP_PENDING_PAYMENT_MONITOR_INTERVAL_SECONDS", "1")
    settings = core_config.RuntimeSettings.from_env()
    assert settings.admin_port == 9001
    assert settings.schedule.pending_payments_seconds == 10
