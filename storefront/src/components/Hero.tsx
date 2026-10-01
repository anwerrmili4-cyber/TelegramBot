import { useState, type FormEvent } from "react";
import { Search, Sparkles } from "lucide-react";
import { money } from "@/lib/format";
import { Link, navigate, ROUTES } from "@/lib/router";
import type { Category, Offer } from "@/types";

type HeroProps = {
  offers: Offer[];
  categories: Category[];
  onOpenOffer: (offer: Offer) => void;
};

export function Hero({ offers, categories, onOpenOffer }: HeroProps) {
  const [query, setQuery] = useState("");
  const popular = offers.filter((offer) => offer.available).slice(0, 4);
  const inStock = offers.filter((offer) => offer.available).length;

  function search(event: FormEvent) {
    event.preventDefault();
    const term = query.trim();
    navigate(`${ROUTES.shop}${term ? `?q=${encodeURIComponent(term)}` : ""}#catalogue`);
  }

  return (
    <section className="hero" aria-labelledby="hero-title">
      <div>
        <span className="hero-eyebrow">
          <Sparkles size={14} aria-hidden="true" /> Catalogue en direct
        </span>
        <h1 id="hero-title">
          BlackMarket <em>livré en secondes.</em>
        </h1>
        <p className="hero-lead">
          Recharge ton portefeuille par D17, Flouci, IZI ou Wafa Cash, puis achète en un clic. Tes accès
          arrivent par email et restent dans ton compte.
        </p>
        <form className="hero-search" onSubmit={search}>
          <Search size={18} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Rechercher ChatGPT, Canva, NordVPN…"
            aria-label="Rechercher un produit"
          />
          <button type="submit" className="button button-primary">
            Chercher
          </button>
        </form>
        <div className="hero-cats">
          {categories.slice(0, 8).map((category) => (
            <Link key={category.id} to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
              {category.label}
            </Link>
          ))}
        </div>
      </div>

      <aside className="hero-popular" aria-label="Produits populaires">
        <header>
          <span>Populaires</span>
          <span>{inStock} en stock</span>
        </header>
        <ul>
          {popular.map((offer) => (
            <li key={offer.id}>
              <button type="button" onClick={() => onOpenOffer(offer)}>
                <span>
                  <strong>{offer.name}</strong>
                  <small>{offer.service_name}</small>
                </span>
                <b>{money(offer.price_millimes)}</b>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <ul className="hero-stats">
        <li>
          <strong>{offers.length || "—"}</strong>
          <span>produits au catalogue</span>
        </li>
        <li>
          <strong>{categories.length || "—"}</strong>
          <span>catégories</span>
        </li>
        <li>
          <strong>DT</strong>
          <span>prix affichés en dinar</span>
        </li>
        <li>
          <strong>4</strong>
          <span>moyens de paiement</span>
        </li>
      </ul>
    </section>
  );
}
