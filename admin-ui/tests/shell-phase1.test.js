import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { SHELL_MESSAGES, shellErrorMessage } from "../src/ui/messages.js";
import { adminPageId, filterNavEntries, resolveAdminPage } from "../src/ui/route.js";

const root = new URL("../", import.meta.url);

test("unknown admin routes resolve to overview and known routes stay", () => {
  const known = ["overview", "orders", "site-orders"];
  assert.equal(adminPageId("/admin"), "overview");
  assert.equal(adminPageId("/admin/"), "overview");
  assert.equal(resolveAdminPage("/admin/orders", known), "orders");
  assert.equal(resolveAdminPage("/admin-v2/site-orders", known), "site-orders");
  assert.equal(resolveAdminPage("/admin/missing", known), "overview");
  assert.equal(resolveAdminPage("/admin/login", known), "overview");
});

test("command palette only returns existing navigation entries", () => {
  const groups = [
    { label: "Catalogue & finance", items: [{ id: "deposits", label: "Dépôts & paiements", icon: "wallet" }] },
    { label: "Espace de travail", items: [{ id: "orders", label: "Commandes", icon: "list" }] },
  ];
  assert.deepEqual(filterNavEntries(groups, "").map((item) => item.id), ["deposits", "orders"]);
  assert.deepEqual(filterNavEntries(groups, "depots").map((item) => item.id), ["deposits"]);
  assert.deepEqual(filterNavEntries(groups, "inconnu"), []);
});

test("shell errors use the shared French messages", () => {
  assert.equal(shellErrorMessage({ name: "AbortError" }), SHELL_MESSAGES.network);
  assert.equal(shellErrorMessage({ name: "TimeoutError" }), SHELL_MESSAGES.network);
  assert.equal(shellErrorMessage(new TypeError("Failed to fetch")), SHELL_MESSAGES.network);
  assert.equal(shellErrorMessage(new Error("")), SHELL_MESSAGES.unexpected);
  assert.equal(shellErrorMessage(new Error("Erreur serveur (500).")), "Erreur serveur (500).");
  assert.equal(SHELL_MESSAGES.sessionExpired, "Session expirée. Reconnecte-toi.");
  assert.equal(SHELL_MESSAGES.empty, "Aucun élément");
});

test("the shell keeps action payloads and drops smooth scrolling", async () => {
  const app = await readFile(new URL("src/App.jsx", root), "utf8");
  assert.match(app, /SHELL_MESSAGES/);
  assert.match(app, /resolveAdminPage/);
  assert.match(app, /buildAdminQuery/);
  assert.doesNotMatch(app, /startViewTransition/);
  assert.doesNotMatch(app, /ScrollTrigger/);
  assert.match(app, /complete_withdrawal/);
  assert.match(app, /site_cart_confirm/);
});
