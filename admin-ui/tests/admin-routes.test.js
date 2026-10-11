import test from "node:test";
import assert from "node:assert/strict";
import { buildAdminQuery, isLinkedValue, linkTarget } from "../src/admin-routes.js";

test("existing admin routes keep their query keys", () => {
  assert.equal(buildAdminQuery("orders", 12).toString(), "order=12");
  assert.equal(buildAdminQuery("customers", 7).toString(), "user=7");
  assert.equal(buildAdminQuery("support", 3).toString(), "ticket=3");
  assert.equal(buildAdminQuery("site-support", 3).toString(), "ticket=3");
  assert.equal(buildAdminQuery("product-requests", 4).toString(), "request=4");
  assert.equal(buildAdminQuery("withdrawals", 4).toString(), "withdrawal=4");
  assert.equal(buildAdminQuery("warranties", 9).toString(), "warranty=9");
  assert.equal(buildAdminQuery("site-warranties", 9).toString(), "warranty=9");
  assert.equal(buildAdminQuery("site-orders", "C1", { status: "paid", search: "a@b.c" }).toString(), "cart=C1&status=paid&search=a%40b.c");
  assert.equal(buildAdminQuery("site-orders", null, { status: "to_verify" }).toString(), "status=to_verify");
  assert.equal(buildAdminQuery("site-customers", 8, { search: "amina" }).toString(), "customer=8&search=amina");
  assert.equal(buildAdminQuery("site-deposits", 5, { status: "pending", search: "x" }).toString(), "deposit=5&status=pending&search=x");
});

test("supplier, product and collection names map to their pages", () => {
  assert.equal(linkTarget("catalog", "supplier_provider").target, "api-products");
  assert.equal(linkTarget("catalog", "supplier_provider").query, "provider");
  assert.equal(linkTarget("provider-history", "provider").target, "api-products");
  assert.equal(linkTarget("catalog", "offer").query, "offer");
  assert.equal(linkTarget("catalog", "service").query, "category");
  assert.equal(buildAdminQuery("api-products", "gpt_cheap").toString(), "provider=gpt_cheap");
  assert.equal(buildAdminQuery("catalog", null, { offer: 10, category: 2 }).toString(), "offer=10&category=2");
  assert.equal(buildAdminQuery("deposits", 15).toString(), "deposit=15&search=15");
  assert.equal(isLinkedValue(""), false);
  assert.equal(isLinkedValue("Stock interne"), false);
  assert.equal(isLinkedValue("gpt_cheap"), true);
});
