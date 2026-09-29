import { useCallback, useEffect, useMemo, useState } from "react";
import { errorMessage, fetchCatalog } from "@/lib/api";
import type { Catalog, Offer } from "@/types";

type CatalogState = {
  catalog: Catalog | null;
  offers: Offer[];
  loading: boolean;
  error: string;
  reload: () => void;
};

export function useCatalog(): CatalogState {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchCatalog(controller.signal)
      .then((body) => {
        if (!Array.isArray(body.services)) throw new Error("Réponse du catalogue invalide.");
        setCatalog(body);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason, "Le catalogue est momentanément indisponible."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);

  // Featured offers first, then available ones: a sold-out product should never
  // outrank something the customer can actually buy today.
  const offers = useMemo(() => {
    const flat = (catalog?.services ?? []).flatMap((service) => service.offers);
    return flat.sort(
      (a, b) =>
        Number(b.featured) - Number(a.featured) ||
        Number(b.available) - Number(a.available) ||
        a.price_millimes - b.price_millimes,
    );
  }, [catalog]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  return { catalog, offers, loading, error, reload };
}
