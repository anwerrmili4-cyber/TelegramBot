import type { Catalog, CheckoutResult } from "@/types";

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

class ApiError extends Error {}

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

  const payload = (body ?? {}) as { error?: string; ok?: boolean };
  if (!response.ok || payload.ok === false) {
    throw new ApiError(payload.error || "Le service est momentanément indisponible.");
  }
  return body as T;
}

export function fetchCatalog(signal?: AbortSignal): Promise<Catalog> {
  return request<Catalog>("/api/storefront/catalog", { signal });
}

export type CheckoutPayload = {
  name: string;
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
