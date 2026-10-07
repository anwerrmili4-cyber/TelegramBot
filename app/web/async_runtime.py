"""Keep Telegram I/O and background tasks running between HTTP requests."""

import asyncio
import threading


class AsyncRuntime:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._start_lock = threading.Lock()
        self._thread = None
        self._keys = {}

    def _serve(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._serve, name="telegram-asyncio", daemon=True,
                )
                self._thread.start()

    def submit(self, awaitable):
        self.start()
        return asyncio.run_coroutine_threadsafe(awaitable, self.loop)

    def run(self, awaitable):
        # Only startup is locked; network waits must not serialize all callers.
        return self.submit(awaitable).result()

    async def process_update(self, application, update):
        """Preserve each user's input order while other users can make progress."""
        user = update.effective_user
        chat = update.effective_chat
        key = ("user", user.id) if user else ("chat", chat.id if chat else None)
        entry = self._keys.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                await application.process_update(update)
        finally:
            entry[1] -= 1
            if not entry[1]:
                del self._keys[key]

    def close(self):
        """Drain cancelled tasks before closing the event loop at shutdown."""
        if self._thread is not None:
            async def cancel_tasks():
                tasks = asyncio.all_tasks() - {asyncio.current_task()}
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            self.run(cancel_tasks())
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)
        self.loop.close()
