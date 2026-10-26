import { useEffect, useState } from "react";

// Keep stale responses out of the dossier when the period or product changes.
export function useProductBuyers(filters, enabled) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "")).toString();
  const [state, setState] = useState({ query: null, result: {}, error: "" });
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((value) => value + 1);
  useEffect(() => {
    window.addEventListener("admin:data-synced", refresh);
    return () => window.removeEventListener("admin:data-synced", refresh);
  }, []);
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    setState((current) => ({ ...current, query: null, error: "" }));
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/admin/api/product-buyers?${query}`, {
          credentials: "same-origin", cache: "no-store", signal: controller.signal,
        });
        if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
        if (!response.ok) throw new Error("Les ventes n’ont pas pu être chargées. Réessayez.");
        const result = await response.json();
        if (result.ok === false) throw new Error(result.error || "Impossible de charger les ventes.");
        if (!controller.signal.aborted) setState({ query, result, error: "" });
      } catch (error) {
        if (!controller.signal.aborted) setState({ query, result: {}, error: error.message });
      }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query, enabled, revision]);
  const loading = enabled && state.query !== query;
  return { result: enabled ? state.result : {}, loading, error: enabled ? state.error : "", refresh };
}
