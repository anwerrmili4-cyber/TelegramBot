"""Process entrypoint: three uvicorn servers, the scheduler and the job runner.

Everything shares the main asyncio loop except the Telegram bot, which keeps
its own loop thread (see :mod:`app.bot.runtime`) because its handlers call
the synchronous database layer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import threading
from collections.abc import Callable

import uvicorn

from app.core.config import RuntimeSettings

log = logging.getLogger("railway")

SHUTDOWN_GRACE_SECONDS = 10


class _Server(uvicorn.Server):
    """uvicorn server whose signals are handled once for the whole process."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def _uvicorn_config(app, port: int) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        lifespan="off",
        log_config=None,
        access_log=False,
        server_header=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=30,
        timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
    )


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(stop.set))


async def run(settings: RuntimeSettings, register_webhook: Callable[[], dict]) -> None:
    from app.bot import runtime as bot_runtime
    from app.core import db as core_db
    from app.core.jobs import JobRunner
    from app.jobs import handlers as _job_handlers  # noqa: F401  (registers job kinds)
    from app.jobs.scheduler import Scheduler, default_jobs
    from app.web import admin_app, notification_service, public_app, storefront_app

    # Initialise MongoDB and Telegram before Railway marks the deployment healthy.
    await asyncio.to_thread(bot_runtime.application)
    result = await asyncio.to_thread(register_webhook)
    if not result.get("ok"):
        raise RuntimeError(result.get("message") or "Telegram webhook registration failed")

    stop = asyncio.Event()
    _install_signal_handlers(stop)
    servers = [
        _Server(_uvicorn_config(public_app.app, settings.port)),
        _Server(_uvicorn_config(admin_app.app, settings.admin_port)),
        _Server(_uvicorn_config(storefront_app.app, settings.storefront_port)),
    ]
    scheduler = Scheduler(default_jobs(settings.schedule))
    admin_app.attach_scheduler(scheduler)
    runner = JobRunner(concurrency=settings.job_concurrency)
    notifications_stop = threading.Event()

    log.info(
        "Public Telegram service listening on 0.0.0.0:%s (public URL: %s)",
        settings.port, settings.public_base_url,
    )
    log.info("Admin dashboard listening on 0.0.0.0:%s", settings.admin_port)
    log.info("Tunisian storefront listening on 0.0.0.0:%s", settings.storefront_port)

    tasks = [asyncio.create_task(server.serve(), name=f"http-{index}") for index, server in enumerate(servers)]
    background = [
        asyncio.create_task(scheduler.run(stop), name="scheduler"),
        asyncio.create_task(runner.run(stop), name="jobs"),
        asyncio.create_task(
            asyncio.to_thread(notification_service.worker_loop, notifications_stop),
            name="admin-notifications",
        ),
    ]

    async def stop_when_a_server_dies() -> None:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()

    watcher = asyncio.create_task(stop_when_a_server_dies())
    await stop.wait()
    log.info("Shutting down")
    for server in servers:
        server.should_exit = True
    notifications_stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    watcher.cancel()
    _done, pending = await asyncio.wait(background, timeout=SHUTDOWN_GRACE_SECONDS)
    for task in pending:
        task.cancel()
    await asyncio.to_thread(bot_runtime.shutdown)
    await core_db.close_async()
    failed = [task for task in tasks if task.done() and not task.cancelled() and task.exception()]
    if failed:
        raise failed[0].exception()


def serve(settings: RuntimeSettings, *, register_webhook: Callable[[], dict]) -> None:
    asyncio.run(run(settings, register_webhook))
