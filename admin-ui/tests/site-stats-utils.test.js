import test from "node:test";
import assert from "node:assert/strict";
import { delta, formatDelta, insights, niceMax, peakSlot, percent, relativeTime } from "../src/site-stats-utils.js";

test("period comparison handles growth, decline, flat and a new metric", () => {
  assert.deepEqual(delta(15, 10), { kind: "up", value: 50 });
  assert.equal(delta(5, 10).kind, "down");
  assert.equal(delta(0, 0).kind, "flat");
  assert.equal(delta(3, 0).kind, "new");
  assert.equal(delta(3, null), null);
  assert.equal(formatDelta(delta(15, 10)), "+50 %");
  assert.equal(formatDelta(delta(5, 10)), "−50 %");
  assert.equal(formatDelta(delta(3, 0)), "Nouveau");
});

test("axis maximum rounds up to a readable value", () => {
  assert.equal(niceMax(0), 4);
  assert.equal(niceMax(7), 10);
  assert.equal(niceMax(23), 25);
  assert.equal(niceMax(41), 50);
  assert.equal(niceMax(180), 200);
});

test("percent refuses an empty base", () => {
  assert.equal(percent(1, 0), null);
  assert.equal(percent(1, 4), 25);
});

test("peak slot and insights come from the real series", () => {
  const heatmap = [{ day: "Lun", hours: Array(24).fill(0) }, { day: "Mar", hours: Array(24).fill(0) }];
  heatmap[1].hours[21] = 9;
  assert.deepEqual(peakSlot(heatmap), { day: "Mar", hour: 21, count: 9 });
  const items = insights({
    summary: { unique: 20, orders: 2 },
    daily: [{ date: "2026-10-06", visits: 4 }, { date: "2026-10-07", visits: 12 }],
    heatmap,
    sources: [{ key: "social", label: "Réseaux sociaux", count: 3 }, { key: "direct", label: "Accès direct", count: 1 }],
    devices: [{ key: "mobile", label: "Mobile", count: 8 }, { key: "desktop", label: "Ordinateur", count: 2 }],
  });
  const text = Object.fromEntries(items.map((item) => [item.key, item.text]));
  assert.match(text["best-day"], /7 octobre avec 12 visite/);
  assert.equal(text.peak, "le mardi entre 21 h et 22 h.");
  assert.match(text.source, /^Réseaux sociaux : 75 %/);
  assert.match(text.conversion, /^10 %/);
  assert.match(text.device, /^Mobile pour 80 %/);
  assert.deepEqual(insights({ summary: {}, daily: [{ date: "2026-10-07", visits: 0 }] }), []);
});

test("relative time reads naturally in French", () => {
  const now = 1_800_000_000_000;
  assert.equal(relativeTime(now / 1000 - 120, now), "il y a 2 minutes");
  assert.equal(relativeTime(now / 1000 - 3 * 3600, now), "il y a 3 heures");
});
