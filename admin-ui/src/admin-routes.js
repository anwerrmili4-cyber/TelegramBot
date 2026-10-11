import React from "react";

/** One row: a readable field on a source page, and the page that owns it. */
export const ADMIN_LINKS = Object.freeze([
  { source: "catalog", field: "supplier_provider", target: "api-products", query: "provider" },
  { source: "catalog", field: "offer", target: "catalog", query: "offer" },
  { source: "catalog", field: "service", target: "catalog", query: "category" },
  { source: "provider-history", field: "provider", target: "api-products", query: "provider" },
  { source: "provider-history", field: "order", target: "orders", query: "order" },
  { source: "provider-history", field: "product", target: "catalog", query: "offer" },
  { source: "orders", field: "customer", target: "customers", query: "user" },
  { source: "orders", field: "product", target: "catalog", query: "offer" },
  { source: "overview", field: "order", target: "orders", query: "order" },
  { source: "overview", field: "customer", target: "customers", query: "user" },
  { source: "deposits", field: "deposit", target: "deposits", query: "deposit" },
  { source: "deposits", field: "customer", target: "customers", query: "user" },
  { source: "withdrawals", field: "withdrawal", target: "withdrawals", query: "withdrawal" },
  { source: "withdrawals", field: "customer", target: "customers", query: "user" },
  { source: "warranties", field: "warranty", target: "warranties", query: "warranty" },
  { source: "warranties", field: "order", target: "orders", query: "order" },
  { source: "warranties", field: "customer", target: "customers", query: "user" },
  { source: "warranties", field: "product", target: "catalog", query: "offer" },
  { source: "inventory", field: "offer", target: "catalog", query: "offer" },
  { source: "inventory", field: "order", target: "orders", query: "order" },
  { source: "customers", field: "order", target: "orders", query: "order" },
  { source: "customers", field: "deposit", target: "deposits", query: "deposit" },
  { source: "customers", field: "withdrawal", target: "withdrawals", query: "withdrawal" },
  { source: "customers", field: "referral", target: "customers", query: "user" },
  { source: "customers", field: "warranty", target: "warranties", query: "warranty" },
  { source: "support", field: "customer", target: "customers", query: "user" },
  { source: "site-orders", field: "customer", target: "site-customers", query: "customer" },
  { source: "site-customers", field: "order", target: "site-orders", query: "cart" },
  { source: "site-customers", field: "deposit", target: "site-deposits", query: "deposit" },
  { source: "site-customers", field: "ticket", target: "site-support", query: "ticket" },
  { source: "site-customers", field: "request", target: "site-product-requests", query: "request" },
  { source: "site-customers", field: "warranty", target: "site-warranties", query: "warranty" },
  { source: "site-reviews", field: "customer", target: "site-customers", query: "customer" },
  { source: "site-reviews", field: "order", target: "site-orders", query: "cart" },
]);

/** Query key written when navigate(page, entityId) is called. Site carts keep their extra keys. */
export const PAGE_ENTITY_KEYS = Object.freeze({
  orders: "order",
  support: "ticket",
  "site-support": "ticket",
  "product-requests": "request",
  "site-product-requests": "request",
  customers: "user",
  withdrawals: "withdrawal",
  warranties: "warranty",
  "site-warranties": "warranty",
  "api-products": "provider",
  deposits: "deposit",
});

const INTERNAL_LABEL = "Stock interne";

export function linkTarget(source, field) {
  return ADMIN_LINKS.find((item) => item.source === source && item.field === field) || null;
}

export function isLinkedValue(value) {
  if (value == null) return false;
  const text = String(value).trim();
  return text !== "" && text !== INTERNAL_LABEL;
}

export function offerIdByName(services, name) {
  const needle = String(name || "").trim().toLocaleLowerCase("fr");
  if (!needle) return "";
  for (const service of services || []) {
    for (const offer of service.offers || []) {
      if (String(offer.name || "").trim().toLocaleLowerCase("fr") === needle) return offer.id;
    }
  }
  return "";
}

export function buildAdminQuery(page, entityId = null, extra = null) {
  const params = new URLSearchParams();
  const put = (key, value) => {
    if (value != null && value !== "") params.set(key, String(value));
  };
  if (page === "site-orders" && entityId != null) {
    put("cart", entityId);
    put("status", extra?.status || "all");
    put("search", extra?.search ?? entityId);
    return params;
  }
  if (page === "site-orders" && extra?.status) {
    put("status", extra.status);
    return params;
  }
  if (page === "site-customers" && entityId != null) {
    put("customer", entityId);
    put("search", extra?.search || "");
    return params;
  }
  if (page === "site-deposits" && entityId != null) {
    put("deposit", entityId);
    put("status", extra?.status || "all");
    put("search", extra?.search || "");
    return params;
  }
  if (page === "site-deposits" && extra?.status) {
    put("status", extra.status);
    return params;
  }
  if (page === "catalog") {
    put("offer", extra?.offer ?? (extra?.query === "offer" ? entityId : null));
    put("category", extra?.category ?? (extra?.query === "category" ? entityId : null));
    return params;
  }
  if (page === "deposits" && entityId != null) {
    put("deposit", entityId);
    put("search", extra?.search ?? entityId);
    return params;
  }
  const key = PAGE_ENTITY_KEYS[page];
  if (key && entityId != null) put(key, entityId);
  return params;
}

export function EntityLink({ source, field, value, onNavigate, children, className = "", title = "Ouvrir la page" }) {
  const route = linkTarget(source, field);
  if (!onNavigate || !route || !isLinkedValue(value)) return children;
  const extra = route.target === "catalog" ? { [route.query]: value, query: route.query } : null;
  const entityId = route.target === "catalog" ? null : value;
  return React.createElement(
    "button",
    {
      type: "button",
      className: `entity-link ${className}`.trim(),
      title,
      onClick: (event) => {
        event.stopPropagation();
        onNavigate(route.target, entityId, extra);
      },
    },
    children,
  );
}
