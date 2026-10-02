import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { RotateCcw, Search, ServerCrash, SearchX } from "lucide-react";
import { ProductTile } from "@/components/Hero";
import { searchable } from "@/lib/format";
import { prefersReducedMotion, stagger, withViewTransition } from "@/lib/motion";
import { placeSlidingPill } from "@/lib/slidingPill";
import type { Category, Offer } from "@/types";

type CatalogSectionProps = {
  offers: Offer[];
  categories: Category[];
  loading: boolean;
  error: string;
  onReload: () => void;
  onOpenOffer: (offer: Offer) => void;
};

export function CatalogSection({
  offers,
  categories,
  loading,
  error,
  onReload,
  onOpenOffer,
}: CatalogSectionProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const filtersRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextQuery = params.get("q");
    const nextCategory = params.get("categorie");
    if (nextQuery) setQuery(nextQuery);
    if (nextCategory) setCategory(nextCategory);
  }, []);

  const visible = useMemo(() => {
    const term = searchable(query.trim());
    return offers
      .filter((offer) => category === "all" || String(offer.service_id) === category)
      .filter(
        (offer) =>
          !term ||
          searchable(`${offer.name} ${offer.service_name} ${offer.description}`).includes(term),
      );
  }, [offers, category, query]);

  useLayoutEffect(() => {
    const list = filtersRef.current;
    if (!list) return;
    const place = () => {
      const active = list.querySelector<HTMLButtonElement>("button.active");
      placeSlidingPill(list, active);
      if (!active) return;
      const edge = 8;
      const start = active.offsetLeft;
      const end = start + active.offsetWidth;
      if (start < list.scrollLeft + edge || end > list.scrollLeft + list.clientWidth - edge) {
        list.scrollTo({
          left: Math.max(0, start - 16),
          behavior: prefersReducedMotion() ? "auto" : "smooth",
        });
      }
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(list);
    for (const button of list.querySelectorAll("button")) observer.observe(button);
    return () => observer.disconnect();
  }, [category, categories]);

  return (
    <section className="catalog" id="catalogue" aria-labelledby="catalog-title">
      <div className="section-head">
        <div>
          <span className="kicker">Le catalogue</span>
          <h2 id="catalog-title">Compose ton panier</h2>
        </div>
        <p>
          Prix et stock en direct. Clique sur un produit pour voir tous ses détails avant
          d'acheter.
        </p>
      </div>

      <div className="catalog-toolbar">
        <label className="search">
          <Search size={17} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Rechercher Netflix, Canva, ChatGPT…"
            aria-label="Rechercher une offre"
          />
        </label>
        <div className="filters" role="group" aria-label="Filtrer par catégorie" ref={filtersRef}>
          <span className="filter-pill" aria-hidden="true" />
          <button
            type="button"
            className={category === "all" ? "active" : ""}
            onClick={() => withViewTransition(() => setCategory("all"))}
          >
            Tout
          </button>
          {categories.map((item) => (
            <button
              type="button"
              key={item.id}
              className={category === item.id ? "active" : ""}
              onClick={() => withViewTransition(() => setCategory(item.id))}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="tile-grid" aria-busy="true" aria-label="Chargement du catalogue">
          {[0, 1, 2, 3, 4, 5].map((key) => (
            <div className="offer-skeleton" key={key} style={stagger(key)}>
              <i />
              <b />
              <span />
              <span />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="catalog-state">
          <ServerCrash size={34} aria-hidden="true" />
          <h3>Le catalogue ne répond pas</h3>
          <p>{error}</p>
          <button type="button" className="button button-primary" onClick={onReload}>
            <RotateCcw size={16} aria-hidden="true" /> Réessayer
          </button>
        </div>
      ) : visible.length ? (
        <div className="tile-grid">
          {visible.map((offer) => (
            <ProductTile key={offer.id} offer={offer} onOpen={onOpenOffer} />
          ))}
        </div>
      ) : (
        <div className="catalog-state">
          <SearchX size={34} aria-hidden="true" />
          <h3>Aucune offre ne correspond</h3>
          <p>Essaie un autre mot-clé ou retire le filtre actif.</p>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              withViewTransition(() => {
                setQuery("");
                setCategory("all");
              })
            }
          >
            Tout afficher
          </button>
        </div>
      )}
    </section>
  );
}
