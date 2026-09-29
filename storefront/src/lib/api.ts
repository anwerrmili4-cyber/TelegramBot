import type { AuthSession, Catalog, CheckoutResult, Customer, VerificationRequired } from "@/types";

const configured = (import.meta.env.VITE_STOREFRONT_API_URL ?? "").trim().replace(/\/+$/, "");

/**
 * Same-origin by default: the site is served by `StorefrontHandler`, which also
 * answers `/api/storefront/*` on its own domain. In development that origin is
 * the Vite proxy. Set `VITE_STOREFRONT_API_URL` only when hosting the built
 * app somewhere other than the Python server.
 */
export const API_BASE = configured;

export const WHATSAPP_FALLBACK = "21621994132";

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

export function fetchCatalog(signal?: AbortSignal): Promise<Catalog> {
  return request<Catalog>("/api/storefront/catalog", { signal });
}

export type CheckoutPayload = {
  name: string;
  email: string;
  phone: string;
  payment_method: string;
  note?: string;
  items: { offer_id: number; quantity: number }[];
};

export function submitCheckout(payload: CheckoutPayload): Promise<CheckoutResult> {
  return request<CheckoutResult>("/api/storefront/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
