import { normalizeSearchValue, searchableText } from "./control-utils.js";

export const CATALOG_DEFAULTS = Object.freeze({
  search: "",
  category: "",
  searchField: "all",
  status: "all",
  stock: "all",
  source: "all",
  format: "all",
  sort: "default",
  view: "grid",
  page: 1,
  pageSize: 50,
});

const ALLOWED = {
  searchField: new Set(["all", "service", "product", "provider"]),
  status: new Set(["all", "active", "inactive"]),
  stock: new Set(["all", "available", "empty", "unlimited"]),
  source: new Set(["all", "internal", "api"]),
  format: new Set(["all", "inventory", "manual", "unlimited", "method", "bot", "supplier"]),
  sort: new Set(["default", "name", "offers", "stock"]),
  view: new Set(["grid", "list"]),
  pageSize: new Set([25, 50, 100]),
};

export function readCatalogQuery(search = "") {
  const params = new URLSearchParams(search);
  const take = (key, fallback) => ALLOWED[key]?.has(params.get(key)) ? params.get(key) : fallback;
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const pageSizeCandidate = Number.parseInt(params.get("perPage") || "50", 10);
  return {
    search: params.get("q") || CATALOG_DEFAULTS.search,
    category: params.get("category") || CATALOG_DEFAULTS.category,
    searchField: take("searchField", CATALOG_DEFAULTS.searchField),
    status: take("status", CATALOG_DEFAULTS.status),
    stock: take("stock", CATALOG_DEFAULTS.stock),
    source: take("source", CATALOG_DEFAULTS.source),
    format: take("format", CATALOG_DEFAULTS.format),
    sort: take("sort", CATALOG_DEFAULTS.sort),
    view: take("view", CATALOG_DEFAULTS.view),
    page,
    pageSize: ALLOWED.pageSize.has(pageSizeCandidate) ? pageSizeCandidate : CATALOG_DEFAULTS.pageSize,
  };
}

export function catalogQueryString(state, currentSearch = "") {
  const params = new URLSearchParams(currentSearch);
  const values = {
    q: state.search,
    category: state.category,
    searchField: state.searchField,
    status: state.status,
    stock: state.stock,
    source: state.source,
    format: state.format || "all",
    sort: state.sort,
    view: state.view,
    page: Number(state.page) > 1 ? String(state.page) : "",
    perPage: Number(state.pageSize) !== CATALOG_DEFAULTS.pageSize ? String(state.pageSize) : "",
  };
  for (const [key, value] of Object.entries(values)) {
    const defaultKey = key === "q" ? "search" : key === "perPage" ? "pageSize" : key;
    if (value === "" || value === CATALOG_DEFAULTS[defaultKey]) params.delete(key);
    else params.set(key, String(value));
  }
  const result = params.toString();
  return result ? `?${result}` : "";
}

export function filterCatalogServices(services, filters, providerName = (value) => value || "Stock interne") {
  filters = { ...CATALOG_DEFAULTS, ...filters };
  const normalizedSearch = normalizeSearchValue(filters.search?.trim());
  return (services || [])
    .filter((service) => !filters.category || String(service.id) === String(filters.category))
    .map((service) => {
      const serviceMatch = searchableText({ id: service.id, name: service.name, name_ar: service.name_ar }).includes(normalizedSearch);
      const offers = (service.offers || []).filter((item) => {
        if (!(item.sales_channels || ["bot"]).includes("bot")) return false;
        if (filters.format !== "all" && catalogItemFormat(item, service) !== filters.format) return false;
        if (filters.status !== "all" && (item.active === 0 ? "inactive" : "active") !== filters.status) return false;
        if (filters.stock === "available" && Number(item.stock || 0) <= 0 && !item.unlimited_stock) return false;
        if (filters.stock === "empty" && (Number(item.stock || 0) > 0 || item.unlimited_stock)) return false;
        if (filters.stock === "unlimited" && !item.unlimited_stock) return false;
        if (filters.source === "internal" && item.supplier_provider) return false;
        if (filters.source === "api" && !item.supplier_provider) return false;
        if (!normalizedSearch) return true;
        if (filters.searchField === "service") return serviceMatch;
        const productText = searchableText(item);
        const providerText = searchableText({ supplier_provider: item.supplier_provider, provider_label: providerName(item.supplier_provider) });
        const haystack = filters.searchField === "provider" ? providerText
          : filters.searchField === "product" ? productText
            : `${searchableText({ id: service.id, name: service.name, name_ar: service.name_ar })} ${productText} ${providerText}`;
        return haystack.includes(normalizedSearch);
      });
      return { ...service, offers, searchMatch: serviceMatch || offers.length > 0 };
    })
    .filter((service) => {
      const hasFilters = filters.status !== "all" || filters.stock !== "all" || filters.source !== "all" || filters.format !== "all";
      return (!normalizedSearch || (filters.searchField === "service" ? service.searchMatch : service.offers.length > 0)) && (!hasFilters || service.offers.length > 0);
    })
    .sort((left, right) => {
      if (filters.sort === "name") return String(left.name || "").localeCompare(String(right.name || ""), "fr", { sensitivity: "base" });
      if (filters.sort === "offers") return right.offers.length - left.offers.length;
      if (filters.sort === "stock") return Number(right.total_stock || 0) - Number(left.total_stock || 0);
      return 0;
    });
}

export const CATALOG_FORMATS = Object.freeze({
  inventory: "Comptes / codes", manual: "Livraison manuelle", unlimited: "Stock illimité",
  method: "Méthode / médias", bot: "Pack bot", supplier: "API fournisseur",
});

export function catalogItemFormat(item, service = {}) {
  if (item.supplier_provider) return "supplier";
  if (item.feature_key === "bot_like_mine") return "bot";
  if (item.method_media?.length || String(service.name || "").trim().toLowerCase() === "methods") return "method";
  if (item.manual_stock) return "manual";
  if (item.unlimited_stock) return "unlimited";
  return "inventory";
}

export function catalogStockLabel(item) {
  return item.unlimited_stock ? "Illimité" : String(Math.max(0, Number(item.stock) || 0));
}

export function catalogOfferPayload(form, initial, offer) {
  const factors = { days: 1, months: 30, years: 365 };
  const warrantyDays = Number(form.warranty_value || 0) * factors[form.warranty_unit];
  const payload = {
    ...form,
    action: offer ? "update_offer" : "add_offer",
    ...(offer ? { offer_id: offer.id } : {}),
    auto_delivery: form.auto_delivery ? "on" : "",
    period_days: Number(form.period_value || 0) * factors[form.period_unit],
    warranty_days: warrantyDays,
    note: warrantyDays === 0 ? "NW" : `${form.warranty_value} ${form.warranty_unit}`,
  };
  if (offer) {
    // Legacy notes and absent settings must survive an unrelated name/price edit.
    for (const prefix of ["period", "warranty"]) {
      if (String(form[`${prefix}_value`]) === String(initial[`${prefix}_value`]) && form[`${prefix}_unit`] === initial[`${prefix}_unit`]) {
        for (const suffix of ["days", "value", "unit"]) delete payload[`${prefix}_${suffix}`];
        if (prefix === "warranty") delete payload.note;
      }
    }
    for (const field of ["description", "name_ar", "description_ar", "delivery_delay", "auto_delivery", "low_stock_threshold", "bulk_quantity", "bulk_unit_price"]) {
      if (String(form[field]) === String(initial[field])) delete payload[field];
    }
    delete payload.initial_inventory;
  }
  return payload;
}

export function paginateCatalogServices(services, page = 1, pageSize = 50) {
  const total = services.reduce((count, service) => count + (service.offers || []).length, 0);
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(1, page), pages);
  let cursor = 0;
  const start = (currentPage - 1) * pageSize;
  const end = start + pageSize;
  const items = services.flatMap((service) => {
    if (!(service.offers || []).length) return currentPage === 1 ? [{ ...service, offers: [] }] : [];
    const offers = (service.offers || []).filter(() => {
      const included = cursor >= start && cursor < end;
      cursor += 1;
      return included;
    });
    return offers.length ? [{ ...service, offers }] : [];
  });
  return { items, page: currentPage, pages, pageSize, total };
}

export function reorderIds(ids, draggedId, targetId) {
  const next = ids.map(Number);
  const from = next.indexOf(Number(draggedId));
  const to = next.indexOf(Number(targetId));
  if (from < 0 || to < 0 || from === to) return next;
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}
