// Coalesce refreshes without cancelling slow requests or losing a saved change.
export function createRefreshQueue(load) {
  let running = null;
  let queued = false;
  let disposed = false;

  function refresh(afterChange = false) {
    if (disposed) return Promise.resolve();
    if (running) {
      queued ||= afterChange;
      return running;
    }
    running = Promise.resolve().then(async () => {
      if (disposed) return;
      do {
        queued = false;
        await load();
      } while (queued && !disposed);
    }).finally(() => { running = null; });
    return running;
  }

  return {
    refresh,
    dispose() { disposed = true; queued = false; },
  };
}
