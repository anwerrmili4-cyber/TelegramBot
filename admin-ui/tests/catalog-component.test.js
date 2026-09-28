import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

test("CatalogPage renders combined URL filters and a persisted view preference", async () => {
  const previousWindow = globalThis.window;
  const previousStorage = globalThis.localStorage;
  globalThis.window = {
    location: { search: "?status=inactive&stock=empty", pathname: "/admin/catalog", hash: "" },
    history: { state: null, replaceState() {} },
  };
  globalThis.localStorage = { getItem: (key) => key === "catalog-view" ? '"list"' : null, setItem() {} };
  const vite = await createServer({ configFile: false, root: fileURLToPath(new URL("../", import.meta.url)), appType: "custom", logLevel: "silent", server: { middlewareMode: true } });
  try {
    const { CatalogPage } = await vite.ssrLoadModule("/src/AdminPages.jsx");
    const markup = renderToStaticMarkup(React.createElement(CatalogPage, {
      data: {
        currency: "USDT",
        services: [{ id: 1, name: "Accounts", active: 1, total_stock: 4, offers: [
          { id: 10, name: "Active product", active: 1, stock: 4, sales_channels: ["bot"] },
          { id: 11, name: "Paused product", active: 0, stock: 0, sales_channels: ["bot"] },
        ] }],
      },
      onAction: async () => true,
    }));
    assert.match(markup, /catalog-list-view/);
    assert.match(markup, /Paused product/);
    assert.doesNotMatch(markup, /Active product/);
    assert.match(markup, /Page 1 sur 1/);
    assert.doesNotMatch(markup, /Emoji droit/);
  } finally {
    await vite.close();
    if (previousWindow === undefined) delete globalThis.window; else globalThis.window = previousWindow;
    if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage;
  }
});


test("catalog renders all formats and safe advanced product controls", async () => {
  const vite = await createServer({ configFile: false, root: fileURLToPath(new URL("../", import.meta.url)), appType: "custom", logLevel: "silent", server: { middlewareMode: true } });
  try {
    const { CatalogPage, OfferForm } = await vite.ssrLoadModule("/src/AdminPages.jsx");
    const offers = [
      { id: 1, name: "Manual", manual_stock: true, auto_delivery: false },
      { id: 2, name: "Unlimited", unlimited_stock: true, stock: -1 },
      { id: 3, name: "Media", method_media: [{ type: "document", file_id: "file" }] },
      { id: 4, name: "Bot package", feature_key: "bot_like_mine" },
      { id: 5, name: "Supplier", supplier_provider: "vex" },
    ].map((offer) => ({ ...offer, service_id: 1, sales_channels: ["bot"], active: 1 }));
    const services = [{ id: 1, name: "Products", offers }];
    const markup = renderToStaticMarkup(React.createElement(CatalogPage, { data: { services }, onAction: async () => true }));
    for (const label of ["Livraison manuelle", "Stock illimité", "Méthode / médias", "Pack bot", "API fournisseur", "Prix à venir"]) assert.ok(markup.includes(label), label);
    assert.match(markup, /aria-hidden="true" inert=""/);
    assert.doesNotMatch(markup, /Stock -1/);
    const form = renderToStaticMarkup(React.createElement(OfferForm, { services, offer: offers[0], onAction: async () => true, onClose() {} }));
    assert.match(form, /Réglages avancés/);
    assert.match(form, /Livraison manuelle/);
    assert.doesNotMatch(form, /Emoji|Icône|Canal de vente/);
  } finally { await vite.close(); }
});
