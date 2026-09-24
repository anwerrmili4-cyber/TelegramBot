import test from "node:test";
import assert from "node:assert/strict";
import { catalogQueryString, filterCatalogServices, paginateCatalogServices, readCatalogQuery, reorderIds } from "../src/catalog-utils.js";

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
  const query = catalogQueryString({ ...defaults, search: "pro", category: "1", searchField: "product", status: "active", stock: "available", source: "api", sort: "name", view: "list", page: 3, pageSize: 25 });
  assert.deepEqual(readCatalogQuery(query), { search: "pro", category: "1", searchField: "product", status: "active", stock: "available", source: "api", sort: "name", view: "list", page: 3, pageSize: 25 });
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
