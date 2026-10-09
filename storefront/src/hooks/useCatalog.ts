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
const CACHE_MAX_AGE_MS = 10 * 60 * 1000;

function catalogFrom(raw: string): Catalog | null {
  const parsed = JSON.parse(raw) as Catalog & { savedAt?: number; catalog?: Catalog };
  const catalog = parsed?.catalog && Array.isArray(parsed.catalog.services) ? parsed.catalog : parsed;
  if (!catalog || !Array.isArray(catalog.services)) return null;
  if (parsed?.savedAt && Date.now() - parsed.savedAt > CACHE_MAX_AGE_MS) return null;
  return catalog;
}

function readCachedCatalog(): Catalog | null {
  for (const store of [sessionStorage, localStorage]) {
    try {
      const raw = store.getItem(CACHE_KEY);
      if (!raw) continue;
      const catalog = catalogFrom(raw);
      if (catalog) return catalog;
    } catch {
      // A broken or private store is ignored; the network fills the page.
    }
  }
  return null;
}

function writeCachedCatalog(catalog: Catalog) {
  const raw = JSON.stringify({ savedAt: Date.now(), catalog });
  if (raw.length > 1_500_000) return;
  for (const store of [sessionStorage, localStorage]) {
    try {
      store.setItem(CACHE_KEY, raw);
    } catch {
      // Private mode or a full quota: the page still shows this visit's data.
    }
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
