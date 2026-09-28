import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.web.async_runtime import AsyncRuntime


@pytest.fixture
def runtime():
    instance = AsyncRuntime()
    yield instance
    instance.close()


def test_background_delivery_continues_between_requests(runtime):
    completed = threading.Event()

    async def watcher():
        await asyncio.sleep(0.02)
        completed.set()

    async def start():
        asyncio.create_task(watcher())

    runtime.run(start())
    assert completed.wait(2), "Delivery watcher stopped when the HTTP request returned"


def test_slow_request_does_not_block_other_requests(runtime):
    started = threading.Event()
    release = threading.Event()

    async def slow():
        started.set()
        await asyncio.to_thread(release.wait, 3)

    async def fast():
        return "ready"

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(runtime.run, slow())
        try:
            assert started.wait(2)
            assert pool.submit(runtime.run, fast()).result(timeout=2) == "ready"
            assert not pending.done()
        finally:
            release.set()
            pending.result(timeout=3)


def test_updates_serialize_per_user_and_release_locks_after_failure(runtime):
    async def scenario():
        release = asyncio.Event()
        started = asyncio.Event()
        calls = []

        async def process(update):
            calls.append(update.update_id)
            if update.update_id == 1:
                started.set()
                await release.wait()
                raise ValueError("failed update")

        application = SimpleNamespace(process_update=process)

        def update(uid, event):
            return SimpleNamespace(
                effective_user=SimpleNamespace(id=uid),
                effective_chat=SimpleNamespace(id=uid), update_id=event,
            )

        first = asyncio.create_task(runtime.process_update(application, update(10, 1)))
        await started.wait()
        second = asyncio.create_task(runtime.process_update(application, update(10, 2)))
        await runtime.process_update(application, update(20, 3))
        await asyncio.sleep(0)
        assert calls == [1, 3]
        release.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert isinstance(results[0], ValueError)
        assert calls == [1, 3, 2]
        assert runtime._keys == {}

    runtime.run(scenario())
