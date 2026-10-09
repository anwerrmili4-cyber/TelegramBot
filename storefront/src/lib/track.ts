import { API_BASE } from "@/lib/api";

/**
 * First-party storefront analytics. Paths stay aligned with
 * `PAGE_LABELS` in `app/domain/site_stats_service.py`.
 * The session key is the same one `useAuth` writes.
 */
const SESSION_KEY = "blackmarket-tn-session";
const VISITOR_KEY = "blackmarket.tn.visitor";

const PAGES = new Set([
  "/",
  "/boutique",
  "/categories",
  "/offres",
  "/prix",
  "/annonces",
  "/support",
  "/aide",
  "/conditions",
  "/confidentialite",
  "/contact",
  "/communaute",
  "/signaler",
  "/messagerie",
  "/connexion",
  "/inscription",
  "/verifier-email",
  "/mot-de-passe-oublie",
  "/reinitialiser-mot-de-passe",
  "/mon-compte",
]);

const ACTIONS = new Set(["cart_add", "checkout", "order", "favorite", "search", "stock_alert"]);

let memoryVisitor = "";
let lastVisitKey = "";
let lastVisitAt = 0;
let lastSearch = "";
let lastSearchAt = 0;

function createId(): string {
  if (typeof crypto === "undefined" || typeof crypto.getRandomValues !== "function") return "";
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function visitorId(): string {
  try {
    const existing = localStorage.getItem(VISITOR_KEY) ?? "";
    if (/^[a-f0-9]{32}$/.test(existing)) return existing;
    const created = createId();
    if (!created) return memoryVisitor;
    localStorage.setItem(VISITOR_KEY, created);
    return created;
  } catch {
    if (!memoryVisitor) memoryVisitor = createId();
    return memoryVisitor;
  }
}

function sessionToken(): string {
  try {
    return localStorage.getItem(SESSION_KEY) ?? "";
  } catch {
    return "";
  }
}

export function normalizePath(path: string): string {
  const bare = path.split("?")[0].split("#")[0].trim();
  const trimmed = bare.length > 1 ? bare.replace(/\/+$/, "") : bare || "/";
  if (trimmed === "/") return "/";
  if (/^\/produit\/[1-9]\d{0,8}$/.test(trimmed)) return trimmed;
  return PAGES.has(trimmed) ? trimmed : "";
}

function send(event: Record<string, unknown>): void {
  const visitor_id = visitorId();
  if (!visitor_id) return;
  const token = sessionToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    void fetch(`${API_BASE}/api/storefront/events`, {
      method: "POST",
      headers,
      body: JSON.stringify({ ...event, visitor_id }),
      keepalive: true,
      credentials: "omit",
    }).catch(() => undefined);
  } catch {
    // A failed beacon must not affect the page the customer is using.
  }
}

/** One page view. Repeated calls for the same path inside a second are ignored. */
export function trackVisit(path: string): void {
  const normalized = normalizePath(path);
  if (!normalized) return;
  const now = Date.now();
  if (normalized === lastVisitKey && now - lastVisitAt < 1500) return;
  lastVisitKey = normalized;
  lastVisitAt = now;
  const product = /^\/produit\/([1-9]\d{0,8})$/.exec(normalized);
  send({
    kind: "visit",
    path: normalized,
    ...(product ? { offer_id: Number(product[1]) } : {}),
  });
}

export function trackInteraction(
  action: string,
  detail: { offerId?: number; label?: string; path?: string } = {},
): void {
  if (!ACTIONS.has(action)) return;
  const path = normalizePath(detail.path ?? (typeof window === "undefined" ? "/" : window.location.pathname)) || "/";
  const label = (detail.label ?? "").replace(/\s+/g, " ").trim().slice(0, 60);
  send({
    kind: "interaction",
    action,
    path,
    ...(detail.offerId ? { offer_id: detail.offerId } : {}),
    ...(label && !label.includes("@") ? { label } : {}),
  });
}

/** A catalogue search. The same term is counted once per half-minute. */
export function trackSearch(term: string): void {
  const label = term.replace(/\s+/g, " ").trim().slice(0, 60);
  if (label.length < 2 || label.includes("@")) return;
  const now = Date.now();
  const key = label.toLowerCase();
  if (key === lastSearch && now - lastSearchAt < 30_000) return;
  lastSearch = key;
  lastSearchAt = now;
  trackInteraction("search", { label });
}
