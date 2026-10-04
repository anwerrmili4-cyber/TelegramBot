import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { errorMessage, fetchCatalog, fetchCatalogFresh } from "@/lib/api";
import type { Catalog, Offer } from "@/types";

type CatalogState = {
  catalog: Catalog | null;
  offers: Offer[];
  loading: boolean;
  error: string;
  reload: () => void;
};

const CACHE_KEY = "bm-catalog-v1";

function readCachedCatalog(): Catalog | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Catalog;
    if (!parsed || !Array.isArray(parsed.services)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedCatalog(catalog: Catalog) {
  try {
    const raw = JSON.stringify(catalog);
    if (raw.length > 1_500_000) return;
    sessionStorage.setItem(CACHE_KEY, raw);
  } catch {
    // Private mode or a full quota: the next visit waits for the network.
  }
}

export function useCatalog(): CatalogState {
  const [catalog, setCatalog] = useState<Catalog | null>(readCachedCatalog);
  const [loading, setLoading] = useState(!catalog);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const catalogRef = useRef(catalog);

  useEffect(() => {
    const controller = new AbortController();
    let ignore = false;
    if (!catalogRef.current) {
      setLoading(true);
      setError("");
    }
    const request = attempt === 0 ? fetchCatalog() : fetchCatalogFresh(controller.signal);
    request
      .then((body) => {
        if (ignore) return;
        if (!Array.isArray(body.services)) throw new Error("Réponse du catalogue invalide.");
        catalogRef.current = body;
        setCatalog(body);
        setError("");
        writeCachedCatalog(body);
      })
      .catch((reason: unknown) => {
        if (ignore || controller.signal.aborted) return;
        if (!catalogRef.current) {
          setError(errorMessage(reason, "Le catalogue est momentanément indisponible."));
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
      controller.abort();
    };
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
