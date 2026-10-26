import test from "node:test";
import assert from "node:assert/strict";
import { FW_FILTERS, buyerDateRange, buyerOrderTarget, fwStatusText } from "../src/product-buyers-utils.js";

test("preset periods use local calendar days and an exclusive next-day boundary", () => {
  const now = new Date(2026, 9, 25, 15, 30);
  const seconds = (day) => new Date(2026, 9, day).getTime() / 1000;
  assert.deepEqual(buyerDateRange("all", "", "", now), { from_ts: "", to_ts: "" });
  for (const [period, day] of [["today", 25], ["7d", 19], ["30d", -4], ["month", 1]]) {
    assert.deepEqual(buyerDateRange(period, "", "", now), { from_ts: seconds(day), to_ts: seconds(26) });
  }
});

test("custom periods include the entire last day and reject invalid or reversed dates", () => {
  const result = buyerDateRange("custom", "2026-10-25", "2026-10-25");
  assert.equal(result.from_ts, new Date(2026, 9, 25).getTime() / 1000);
  assert.equal(result.to_ts, new Date(2026, 9, 26).getTime() / 1000);
  for (const [from, to] of [["", ""], ["2026-02-30", "2026-03-02"], ["2026-10-26", "2026-10-25"]]) {
    assert.ok(buyerDateRange("custom", from, to).error);
  }
});

test("order links keep bot and site destinations separate", () => {
  assert.deepEqual(buyerOrderTarget("bot", { order_id: 5 }), { page: "orders", id: 5 });
  assert.deepEqual(buyerOrderTarget("site", { order_id: 5, cart_reference: "TN-1" }), { page: "site-orders", id: "TN-1" });
  assert.equal(buyerOrderTarget("site", { order_id: 5 }), null);
  assert.equal(buyerOrderTarget("bot", {}), null);
});

test("full warranty filters and statuses have explicit non-color labels", () => {
  assert.deepEqual(FW_FILTERS.map(([id]) => id), ["all", "fw", "fw_active", "fw_finished"]);
  assert.equal(fwStatusText({ fw_status: "active", remaining_days: 12 }), "En cours · 12 j restants");
  assert.equal(fwStatusText({ fw_status: "active", remaining_days: 1 }), "En cours · 1 j restant");
  assert.equal(fwStatusText({ fw_status: "active", remaining_days: null }), "En cours · fin inconnue");
  assert.equal(fwStatusText({ fw_status: "finished" }), "Terminé");
  assert.equal(fwStatusText({ fw_status: "" }), "");
});
