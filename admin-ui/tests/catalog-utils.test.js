import test from "node:test";
import assert from "node:assert/strict";
import { catalogOfferPayload, catalogItemFormat, catalogStockLabel, catalogQueryString, filterCatalogServices, paginateCatalogServices, readCatalogQuery, reorderIds } from "../src/catalog-utils.js";

const services = [{
  id: 1,
  name: "Premium",
  total_stock: 3,
  offers: [
    { id: 10, name: "Édition Pro", active: 1, stock: 3, supplier_provider: "vex", sales_channels: ["bot"] },
    { id: 11, name: "Lifetime", active: 1, stock: 0, unlimited_stock: true, sales_channels: ["bot"] },
    { id: 12, name: "Paused", active: 0, stock: 0, sales_channels: ["bot"] },
  ],
}, {
  id: 2,
  name: "Hidden channel",
  total_stock: 8,
  offers: [{ id: 20, name: "Web only", active: 1, stock: 8, sales_channels: ["api"] }],
}];

const defaults = { search: "", category: "", searchField: "all", status: "all", stock: "all", source: "all", sort: "default" };

test("catalog filters combine status, stock, source and accent-insensitive search", () => {
  assert.deepEqual(filterCatalogServices(services, { ...defaults, search: "edition", source: "api", stock: "available", status: "active" }).flatMap((service) => service.offers.map((offer) => offer.id)), [10]);
  assert.deepEqual(filterCatalogServices(services, { ...defaults, stock: "unlimited" }).flatMap((service) => service.offers.map((offer) => offer.id)), [11]);
  assert.deepEqual(filterCatalogServices(services, { ...defaults, status: "inactive", stock: "empty", source: "internal" }).flatMap((service) => service.offers.map((offer) => offer.id)), [12]);
});

test("catalog query state round-trips into a bookmarkable URL", () => {
  const query = catalogQueryString({ ...defaults, search: "pro", category: "1", searchField: "product", status: "active", stock: "available", source: "api", format: "supplier", sort: "name", view: "list", page: 3, pageSize: 25 });
  assert.deepEqual(readCatalogQuery(query), { search: "pro", category: "1", searchField: "product", status: "active", stock: "available", source: "api", format: "supplier", sort: "name", view: "list", page: 3, pageSize: 25 });
});

test("catalog pagination preserves groups and clamps invalid pages", () => {
  const result = paginateCatalogServices([{ ...services[0], offers: Array.from({ length: 55 }, (_, index) => ({ id: index + 1 })) }], 2, 25);
  assert.equal(result.items[0].offers.length, 25);
  assert.equal(result.items[0].offers[0].id, 26);
  assert.equal(result.pages, 3);
  assert.equal(paginateCatalogServices(services, 99, 25).page, 1);
  assert.equal(paginateCatalogServices([{ id: 9, name: "Empty", offers: [] }], 1, 25).items[0].name, "Empty");
});

test("drag ordering moves an id without dropping siblings", () => {
  assert.deepEqual(reorderIds([1, 2, 3, 4], 4, 2), [1, 4, 2, 3]);
});


test("catalog identifies existing delivery formats without changing their data", () => {
  const cases = [
    [{ supplier_provider: "vex", unlimited_stock: true }, {}, "supplier"],
    [{ feature_key: "bot_like_mine", unlimited_stock: true }, {}, "bot"],
    [{ method_media: [{ type: "document", file_id: "file" }] }, {}, "method"],
    [{}, { name: "Methods" }, "method"],
    [{ manual_stock: true, unlimited_stock: true }, {}, "manual"],
    [{ unlimited_stock: true }, {}, "unlimited"],
    [{ stock: 2 }, {}, "inventory"],
  ];
  for (const [item, service, expected] of cases) assert.equal(catalogItemFormat(item, service), expected);
  assert.equal(catalogStockLabel({ stock: -1, unlimited_stock: true }), "Illimité");
  assert.equal(catalogStockLabel({ stock: -1 }), "0");
  assert.deepEqual(filterCatalogServices(services, { ...defaults, format: "supplier" })[0].offers.map((item) => item.id), [10]);
});

test("search matches each product, not text from a sibling or a hidden channel", () => {
  assert.deepEqual(filterCatalogServices(services, { ...defaults, search: "edition" })[0].offers.map((item) => item.id), [10]);
  assert.deepEqual(filterCatalogServices(services, { ...defaults, search: "Premium", searchField: "product" }), []);
  assert.deepEqual(filterCatalogServices(services, { ...defaults, search: "Web only" }), []);
  assert.equal(readCatalogQuery("?format=unknown").format, "all");
});


test("editing a legacy product preserves untouched advanced settings", () => {
  const initial = { name: "Legacy", price: 2, service_id: 1, auto_delivery: false, period_value: 30, period_unit: "days", warranty_value: 6, warranty_unit: "days", note: "6 months", bulk_quantity: 10, bulk_unit_price: 1, initial_inventory: "" };
  const payload = catalogOfferPayload({ ...initial, name: "Renamed" }, initial, { id: 42 });
  assert.equal(payload.name, "Renamed");
  assert.equal(payload.action, "update_offer");
  assert.equal(payload.offer_id, 42);
  for (const field of ["note", "warranty_days", "period_days", "auto_delivery", "bulk_unit_price", "custom_emoji_id", "sales_channels", "initial_inventory"]) assert.equal(field in payload, false, field);
  const changed = catalogOfferPayload({ ...initial, warranty_value: 1, warranty_unit: "years", auto_delivery: true }, initial, { id: 42 });
  assert.equal(changed.warranty_days, 365);
  assert.equal(changed.note, "1 years");
  assert.equal(changed.auto_delivery, "on");
});
