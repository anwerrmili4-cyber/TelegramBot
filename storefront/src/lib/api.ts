import type {
  AccountOrders,
  AccountReview,
  AccountTicket,
  AccountTickets,
  AccountWarranties,
  AuthSession,
  Catalog,
  CheckoutResult,
  Customer,
  Deposit,
  Favorite,
  SiteNotification,
  VerificationRequired,
  PublicReviews,
  Wallet,
} from "@/types";

const configured = (import.meta.env.VITE_STOREFRONT_API_URL ?? "").trim().replace(/\/+$/, "");

/**
 * Same-origin by default: the site is served by `StorefrontHandler`, which also
 * answers `/api/storefront/*` on its own domain. In development that origin is
 * the Vite proxy. Set `VITE_STOREFRONT_API_URL` only when hosting the built
 * app somewhere other than the Python server.
 */
export const API_BASE = configured;

/** Resolve a catalog image, which the API may return as a relative path. */
export function assetUrl(url: string): string {
  if (!url || /^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url}`;
}

export class ApiError extends Error {
  readonly status: number;
  /** Machine-readable reason, e.g. `email_unverified`. */
  readonly code: string;

  constructor(message: string, status = 0, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Connexion impossible. Vérifie ton réseau puis réessaie.");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // An error page or an empty body: fall through to the status check.
  }

  const payload = (body ?? {}) as { error?: string; ok?: boolean; code?: string };
  if (!response.ok || payload.ok === false) {
    throw new ApiError(
      payload.error || "Le service est momentanément indisponible.",
      response.status,
      payload.code ?? "",
    );
  }
  return body as T;
}

function postJson<T>(path: string, payload: unknown, token?: string): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
}

export function register(payload: { name: string; email: string; password: string }) {
  return postJson<VerificationRequired>("/api/storefront/auth/register", payload);
}

export function verifyEmail(payload: { email: string; code: string }) {
  return postJson<AuthSession>("/api/storefront/auth/verify-email", payload);
}

export function resendVerificationCode(email: string) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/resend-code", { email });
}

export function login(payload: { email: string; password: string }) {
  return postJson<AuthSession>("/api/storefront/auth/login", payload);
}

export function googleLogin(credential: string) {
  return postJson<AuthSession>("/api/storefront/auth/google", { credential });
}

export function fetchAuthConfig() {
  return request<{ ok: boolean; google_client_id: string }>("/api/storefront/auth/config");
}

export function logout(token: string) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/logout", {}, token);
}

export function fetchMe(token: string, signal?: AbortSignal) {
  return request<{ ok: boolean; customer: Customer }>("/api/storefront/auth/me", {
    signal,
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function requestPasswordReset(email: string) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/forgot-password", { email });
}

export function resetPassword(token: string, password: string) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/reset-password", { token, password });
}

let catalogFlight: Promise<Catalog> | null = null;

/** Starts as soon as this module loads, so the catalog is already in flight while React boots. */
export function prefetchCatalog(): Promise<Catalog> {
  if (!catalogFlight) {
    catalogFlight = request<Catalog>("/api/storefront/catalog", { priority: "high" }).catch((error: unknown) => {
      catalogFlight = null;
      throw error;
    });
  }
  return catalogFlight;
}

export function fetchCatalog(): Promise<Catalog> {
  return prefetchCatalog();
}

/** A manual retry. Does not reuse a response that already failed or went stale. */
export function fetchCatalogFresh(signal?: AbortSignal): Promise<Catalog> {
  catalogFlight = request<Catalog>("/api/storefront/catalog", { signal, priority: "high" }).catch((error: unknown) => {
    catalogFlight = null;
    throw error;
  });
  return catalogFlight;
}

if (typeof window !== "undefined") void prefetchCatalog();

export type CheckoutPayload = {
  /** `wallet`, or a transfer method id such as `d17`. */
  payment_method: string;
  /** Same value for every click of this payment, so a retry cannot charge twice. */
  idempotency_key?: string;
  transaction_reference?: string;
  /** Receipt screenshot as a `data:image/...` URL, for transfers only. */
  receipt?: string;
  items: { offer_id: number; quantity: number; info?: string }[];
};

export function submitCheckout(token: string, payload: CheckoutPayload): Promise<CheckoutResult> {
  return postJson<CheckoutResult>("/api/storefront/orders", payload, token);
}

function getAuthed<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal, headers: { Authorization: `Bearer ${token}` } });
}

export function fetchOrders(token: string, signal?: AbortSignal) {
  return getAuthed<AccountOrders>("/api/storefront/auth/orders", token, signal);
}

export function fetchTickets(token: string, signal?: AbortSignal) {
  return getAuthed<AccountTickets>("/api/storefront/auth/tickets", token, signal);
}

export function openTicket(token: string, payload: { message: string; category: string; order_id?: number }) {
  return postJson<{ ok: boolean; ticket: AccountTicket }>("/api/storefront/auth/tickets", payload, token);
}

export function fetchProductRequests(token: string, signal?: AbortSignal) {
  return getAuthed<AccountTickets>("/api/storefront/auth/product-requests", token, signal);
}

export function openProductRequest(token: string, message: string) {
  return postJson<{ ok: boolean; ticket: AccountTicket }>("/api/storefront/auth/product-requests", { message }, token);
}

export function openWarranty(token: string, payload: { order_id: number; reason: string; proofs: string[] }) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/warranties", payload, token);
}

export async function fetchWarrantyProof(token: string, proofId: number): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/storefront/auth/warranty-proof?id=${proofId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError("Connexion impossible. Vérifie ton réseau puis réessaie.");
  }
  if (!response.ok) throw new ApiError("Preuve introuvable.", response.status);
  return response.blob();
}

export function fetchWarranties(token: string, signal?: AbortSignal) {
  return getAuthed<AccountWarranties>("/api/storefront/auth/warranties", token, signal);
}

export function replyToTicket(token: string, payload: { ticket_id: number; message: string }) {
  return postJson<{ ok: boolean; ticket: AccountTicket }>("/api/storefront/auth/ticket-messages", payload, token);
}

/** Download the PDF invoice of a paid order. */
export async function downloadInvoice(token: string, reference: string, filename: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/storefront/auth/invoice?ref=${encodeURIComponent(reference)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError("Connexion impossible. Vérifie ton réseau puis réessaie.");
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    throw new ApiError(payload.error || "Facture indisponible pour le moment.", response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filename}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function fetchWallet(token: string, signal?: AbortSignal) {
  return getAuthed<Wallet>("/api/storefront/auth/wallet", token, signal);
}

export function createDeposit(
  token: string,
  payload: { method: string; amount: string; transaction_reference: string; receipt: string },
) {
  return postJson<{ ok: boolean; deposit: Deposit }>("/api/storefront/auth/deposits", payload, token);
}

export function updateProfile(token: string, payload: { name: string; phone: string }) {
  return postJson<{ ok: boolean; customer: Customer }>("/api/storefront/auth/profile", payload, token);
}

export function changePassword(token: string, payload: { current_password: string; new_password: string }) {
  return postJson<{ ok: boolean }>("/api/storefront/auth/password", payload, token);
}

export function fetchNotifications(token: string, signal?: AbortSignal) {
  return getAuthed<{ ok: boolean; unread: number; items: SiteNotification[] }>(
    "/api/storefront/auth/notifications",
    token,
    signal,
  );
}

export function markNotificationRead(token: string, id: number) {
  return postJson<{ ok: boolean; unread: number; items: SiteNotification[] }>(
    "/api/storefront/auth/notifications",
    { id },
    token,
  );
}

export function markAllNotificationsRead(token: string) {
  return postJson<{ ok: boolean; unread: number; items: SiteNotification[] }>(
    "/api/storefront/auth/notifications",
    { all: 1 },
    token,
  );
}

export function fetchFavorites(token: string, signal?: AbortSignal) {
  return getAuthed<{ ok: boolean; favorites: Favorite[] }>("/api/storefront/auth/favorites", token, signal);
}

export function setFavorite(token: string, offerId: number, saved: boolean) {
  return postJson<{ ok: boolean; saved: boolean; emailed: boolean; favorite?: Favorite }>(
    "/api/storefront/auth/favorites",
    { offer_id: offerId, saved },
    token,
  );
}

export function fetchMyReviews(token: string, signal?: AbortSignal) {
  return getAuthed<{ ok: boolean; reviews: AccountReview[] }>("/api/storefront/auth/reviews", token, signal);
}

export function submitReview(token: string, payload: { order_id: number; score: number; comment: string }) {
  return postJson<{ ok: boolean; review: AccountReview }>("/api/storefront/auth/reviews", payload, token);
}

export function fetchReviews(offerId?: number, signal?: AbortSignal) {
  const query = offerId ? `?offer_id=${offerId}` : "";
  return request<PublicReviews>(`/api/storefront/reviews${query}`, { signal });
}

export function requestStockAlert(offerId: number, email: string, token?: string) {
  return postJson<{ ok: boolean; already_available?: boolean }>(
    "/api/storefront/stock-alerts",
    { offer_id: offerId, email },
    token,
  );
}

export function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
