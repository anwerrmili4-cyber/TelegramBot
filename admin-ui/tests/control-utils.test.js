import test from "node:test";
import assert from "node:assert/strict";
import { csvCell, csvDocument, getAdminJson, normalizeSearchValue, readPreference, savePreference, searchableText } from "../src/control-utils.js";

test("catalog search reads mixed values and ignores accents", () => {
  const product = { id: 42, active: true, price: 7.5, names: ["Édition Pro", "احترافي"], metadata: { provider: "API-One" } };
  const text = searchableText(product);
  for (const query of ["42", "true", "7.5", "edition pro", "احترافي", "api-one"]) {
    assert.equal(text.includes(normalizeSearchValue(query)), true);
  }
  const circular = { name: "safe" };
  circular.self = circular;
  assert.match(searchableText(circular), /safe/);
});

test("catalog view preferences persist and recover safely", () => {
  const storage = new Map();
  const previous = globalThis.localStorage;
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
  try {
    assert.equal(savePreference("catalog-view", "list"), true);
    assert.equal(readPreference("catalog-view", "grid"), "list");
  } finally {
    if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous;
  }
});

test("CSV neutralizes spreadsheet formulas including leading whitespace", () => {
  for (const value of ["=1+2", "+SUM(A1)", "@SUM(A1)", "-1+2", " \t=HYPERLINK(1)"]) {
    assert.equal(csvCell(value).startsWith('"\''), true);
  }
  assert.equal(csvCell('Client "A",\nB'), '"Client ""A"",\nB"');
});

test("export only includes explicitly selected fields", () => {
  const csv = csvDocument([["id", "ID"], ["status", "Statut"]], [{ id: 1, status: "paid", secret: "must-not-leak" }]);
  assert.equal(csv, '\ufeff"ID","Statut"\r\n"1","paid"');
  assert.equal(csv.includes("must-not-leak"), false);
});

test("expired admin session triggers sign-in without accepting the payload", async () => {
  const oldFetch = globalThis.fetch;
  const oldWindow = globalThis.window;
  let eventType;
  try {
    globalThis.fetch = async () => ({ status: 401, ok: false });
    globalThis.window = { dispatchEvent: (event) => { eventType = event.type; } };
    await assert.rejects(getAdminJson("/admin/api/orders"), /Session expirée/);
    assert.equal(eventType, "admin:session-expired");
  } finally { globalThis.fetch = oldFetch; globalThis.window = oldWindow; }
});

test("server failures never become empty successful data", async () => {
  const oldFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ status: 503, ok: false });
    await assert.rejects(getAdminJson("/admin/api/orders"), /503/);
    globalThis.fetch = async () => ({ status: 200, ok: true, json: async () => ({ ok: false, message: "Connexion indisponible" }) });
    await assert.rejects(getAdminJson("/admin/api/orders"), /Connexion indisponible/);
  } finally { globalThis.fetch = oldFetch; }
});
