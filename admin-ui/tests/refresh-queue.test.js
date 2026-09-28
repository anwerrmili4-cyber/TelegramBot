import test from "node:test";
import assert from "node:assert/strict";
import { createRefreshQueue } from "../src/refresh-queue.js";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("polls do not restart or overlap a slow delivery request", async () => {
  const pending = deferred();
  let calls = 0;
  const queue = createRefreshQueue(async () => { calls++; await pending.promise; });
  const first = queue.refresh();
  await Promise.resolve();
  assert.equal(queue.refresh(), first);
  assert.equal(queue.refresh(), first);
  assert.equal(calls, 1);
  pending.resolve();
  await first;
  await queue.refresh();
  assert.equal(calls, 2);
});

test("mutations during a request trigger one fresh read afterwards", async () => {
  const pending = deferred();
  let calls = 0;
  const queue = createRefreshQueue(async () => { calls++; await pending.promise; });
  const first = queue.refresh();
  await Promise.resolve();
  queue.refresh(true);
  queue.refresh(true);
  pending.resolve();
  await first;
  assert.equal(calls, 2);
});

test("leaving a page drops its queued refresh", async () => {
  const pending = deferred();
  let calls = 0;
  const queue = createRefreshQueue(async () => { calls++; await pending.promise; });
  const first = queue.refresh();
  await Promise.resolve();
  queue.refresh(true);
  queue.dispose();
  pending.resolve();
  await first;
  await queue.refresh();
  assert.equal(calls, 1);
});

test("a failed read does not prevent retry", async () => {
  let calls = 0;
  const queue = createRefreshQueue(async () => { if (++calls === 1) throw new Error("offline"); });
  await assert.rejects(queue.refresh(), /offline/);
  await queue.refresh();
  assert.equal(calls, 2);
});
