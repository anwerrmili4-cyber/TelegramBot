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
    const { default: CatalogPage } = await vite.ssrLoadModule("/src/pages/CatalogPage.jsx");
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

test("offline products stay in one Hors ligne row and bulk options reopen", async () => {
  const previousWindow = globalThis.window;
  const previousStorage = globalThis.localStorage;
  globalThis.window = {
    location: { search: "", pathname: "/admin/catalog", hash: "" },
    history: { state: null, replaceState() {} },
  };
  globalThis.localStorage = { getItem: () => null, setItem() {} };
  const vite = await createServer({ configFile: false, root: fileURLToPath(new URL("../", import.meta.url)), appType: "custom", logLevel: "silent", server: { middlewareMode: true } });
  try {
    const page = await vite.ssrLoadModule("/src/pages/CatalogPage.jsx");
    const markup = renderToStaticMarkup(React.createElement(page.default, {
      data: {
        currency: "USDT",
        services: [{ id: 1, name: "Figma", active: 1, total_stock: 18, offers: [
          { id: 10, name: "Live Pro", active: 1, stock: 4, price: 6, sales_channels: ["bot"] },
          { id: 11, name: "Closed stock", active: 1, stock: 9, price: 6, sales_channels: ["bot"], stock_enabled: false },
          { id: 12, name: "Hidden product", active: 1, stock: 3, price: 6, sales_channels: ["bot"], product_enabled: false },
          { id: 13, name: "Paused duo", active: 0, stock: 2, price: 6, sales_channels: ["bot"], product_enabled: false, stock_enabled: false },
        ] }],
      },
      onAction: async () => true,
    }));
    const offlineAt = markup.indexOf('aria-label="Hors ligne"');
    const onlineMarkup = markup.slice(0, offlineAt);
    const offlineMarkup = markup.slice(offlineAt);
    assert.match(onlineMarkup, /Live Pro/);
    assert.match(onlineMarkup, /Visible/);
    assert.doesNotMatch(onlineMarkup, /Closed stock|Hidden product|Paused duo/);
    assert.match(offlineMarkup, /Closed stock/);
    assert.match(offlineMarkup, /Hidden product/);
    assert.equal(offlineMarkup.split("<strong>Paused duo</strong>").length - 1, 1);
    assert.match(offlineMarkup, /Produit off <small>2<\/small>/);
    assert.match(offlineMarkup, /Stock off <small>2<\/small>/);
    assert.match(offlineMarkup, /Désactivés <small>1<\/small>/);
    assert.match(offlineMarkup, /Produit OFF/);
    assert.match(offlineMarkup, /Stock OFF/);
    assert.match(offlineMarkup, /Désactivé/);
    const saved = renderToStaticMarkup(React.createElement(page.OfferForm, {
      services: [{ id: 1, name: "Figma" }],
      offer: { id: 4, service_id: 1, name: "Pack", price: 12, bulk_options: [
        { name: "Lot 5", min_quantity: 5, unit_price: 8 },
        { name: "Lot 10", min_quantity: 10, unit_price: 6 },
      ] },
      onAction: async () => true,
      onClose() {},
    }));
    assert.match(saved, /value="Lot 5"/);
    assert.match(saved, /value="Lot 10"/);
    assert.match(saved, /value="5"/);
    assert.match(saved, /value="8"/);
    assert.match(saved, /value="10"/);
    assert.match(saved, /value="6"/);
    const legacy = renderToStaticMarkup(React.createElement(page.OfferForm, {
      services: [{ id: 1, name: "Figma" }],
      offer: { id: 5, service_id: 1, name: "Ancien", price: 10, bulk_quantity: 5, bulk_unit_price: 2.5 },
      onAction: async () => true,
      onClose() {},
    }));
    const named = renderToStaticMarkup(React.createElement(page.OfferForm, {
      services: [
        { id: 2, name: "Zoom", offers: [{ id: 3, name: "Teams" }] },
        { id: 1, name: "Canva", offers: [{ id: 9, name: "Éducation" }, { id: 8, name: "Pro 1 mois" }, { id: 11, name: "Archivé", archived: 1 }] },
      ],
      offer: { id: 4, service_id: 1, name: "Pack", price: 12 },
      onAction: async () => true,
      onClose() {},
    }));
    const canvaAt = named.indexOf(">Canva<");
    const zoomAt = named.indexOf(">Zoom<");
    assert.ok(canvaAt > 0 && canvaAt < zoomAt);
    assert.match(named, /Produits déjà dans Canva/);
    assert.match(named, />Éducation</);
    assert.match(named, />Pro 1 mois</);
    assert.doesNotMatch(named, />Teams<|>Archivé</);
    assert.match(legacy, /value="Gros"/);
    assert.match(legacy, /value="5"/);
    assert.match(legacy, /value="2.5"/);
    const fresh = renderToStaticMarkup(React.createElement(page.OfferForm, {
      services: [{ id: 1, name: "Figma" }],
      onAction: async () => true,
      onClose() {},
    }));
    assert.match(fresh, /Période \(optionnelle\)/);
    assert.match(fresh, /Garantie \(optionnelle\)/);
    assert.match(fresh, /aria-label="Durée du produit \(optionnelle\)"[^>]*value=""/);
    assert.match(fresh, /aria-label="Garantie du produit \(optionnelle\)"[^>]*value=""/);
    assert.doesNotMatch(fresh, /aria-label="(?:Durée|Garantie) du produit \(optionnelle\)"[^>]*required/);
    const listed = renderToStaticMarkup(React.createElement(page.ExistingCatalogNames, {
      service: { id: 4, name: "Cursor", offers: [{ name: "Gamma Pro" }, { name: "Alpha" }] },
    }));
    const alphaAt = listed.indexOf(">Alpha<");
    const gammaAt = listed.indexOf(">Gamma Pro<");
    assert.match(listed, /Produits déjà dans Cursor/);
    assert.ok(alphaAt > 0 && alphaAt < gammaAt);
    assert.doesNotMatch(listed, /<button|réutiliser/);
    assert.match(listed, /Classés de A à Z\./);
  } finally {
    await vite.close();
    if (previousWindow === undefined) delete globalThis.window; else globalThis.window = previousWindow;
    if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage;
  }
});
