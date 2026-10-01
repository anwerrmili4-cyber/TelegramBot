import { useState, type FormEvent } from "react";
import { ArrowRight, ArrowUpRight, Search, Sparkles } from "lucide-react";
import { HowItWorks } from "@/components/HowItWorks";
import { assetUrl } from "@/lib/api";
import { money } from "@/lib/format";
import { warrantyView } from "@/lib/warranty";
import { Link, navigate, ROUTES } from "@/lib/router";
import type { Category, Offer } from "@/types";

type HeroProps = {
  offers: Offer[];
  categories: Category[];
  onOpenOffer: (offer: Offer) => void;
};

const FAQ = [
  ["La livraison est rapide ?", "Si le produit est en stock, l'accès part par email dès que le paiement est confirmé, et reste dans Mes achats."],
  ["Il y a une garantie ?", "Quand l'offre en a une, la durée est sur la fiche. La demande se fait depuis la commande."],
  ["Comment payer ?", "Portefeuille, ou D17, Flouci, IZI et Wafa Cash avec le reçu. Le solde bouge après vérification."],
  ["Un compte est obligatoire ?", "Tu peux parcourir le catalogue librement. La connexion est demandée au moment de payer."],
];

function searchTo(query: string) {
  const term = query.trim();
  navigate(`${ROUTES.shop}${term ? `?q=${encodeURIComponent(term)}` : ""}#catalogue`);
}

export function ProductTile({ offer, onOpen }: { offer: Offer; onOpen: (offer: Offer) => void }) {
  const stock = !offer.available ? "Épuisé" : offer.stock < 0 ? "En stock" : `${offer.stock} en stock`;
  const warranty = warrantyView(offer);
  return (
    <button type="button" className={offer.available ? "prod-tile" : "prod-tile sold-out"} onClick={() => onOpen(offer)}>
      <span className="prod-tile-media">
        {offer.image_url ? <img src={assetUrl(offer.image_url)} alt="" /> : <span className="prod-ph">{offer.service_emoji}</span>}
        <span className={warranty.covered ? "warranty-badge is-covered" : "warranty-badge is-open"}>{warranty.label}</span>
      </span>
      <span className="prod-tile-body">
        <em>{offer.service_name}</em>
        <strong>{offer.name}</strong>
        <small>
          {stock}
          {warranty.duration ? ` · ${warranty.duration}` : ""}
        </small>
        <span className="prod-tile-foot">
          <b>{money(offer.price_millimes)}</b>
          <span className="go" aria-hidden="true">
            <ArrowUpRight size={16} />
          </span>
        </span>
      </span>
    </button>
  );
}

function categoryMark(offers: Offer[], categoryId: string) {
  const inCategory = offers.filter((offer) => String(offer.service_id) === categoryId);
  const logo = inCategory.find((offer) => offer.service_logo_url);
  if (logo) return { src: assetUrl(logo.service_logo_url), emoji: "" };
  const image = inCategory.find((offer) => offer.image_url);
  if (image) return { src: assetUrl(image.image_url), emoji: "" };
  return { src: "", emoji: inCategory.find((offer) => offer.service_emoji)?.service_emoji ?? "" };
}

export function Hero({ offers, categories, onOpenOffer }: HeroProps) {
  const [query, setQuery] = useState("");
  const available = offers.filter((offer) => offer.available);
  const featured = offers.filter((offer) => offer.featured);
  const highlighted = featured.length ? featured : available;
  const popular = highlighted.slice(0, 4);
  const trending = highlighted.slice(0, 8);
  const fresh = [...available].sort((a, b) => b.id - a.id).slice(0, 4);

  function search(event: FormEvent) {
    event.preventDefault();
    searchTo(query);
  }

  return (
    <>
      <section className={popular.length ? "hero has-popular" : "hero"} aria-labelledby="hero-title">
        <div className="hero-card">
          <span className="hero-eyebrow">
            <Sparkles size={14} aria-hidden="true" /> Livraison immédiate · 24/7
          </span>
          <h1 id="hero-title">
            BlackMarket <em>livré en secondes.</em>
          </h1>
          <p className="hero-lead">
            Des produits digitaux aux meilleurs prix, payés en dinar. Livraison rapide, et tes accès restent dans ton compte.
          </p>
          <form className="hero-search" onSubmit={search}>
            <Search size={18} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Que cherches-tu ?"
              aria-label="Rechercher un produit"
            />
            <button type="submit" className="button button-primary">
              Chercher
            </button>
          </form>
          <div className="hero-cats">
            {categories.slice(0, 6).map((category) => (
              <Link key={category.id} to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
                {category.label}
              </Link>
            ))}
          </div>
        </div>
        {popular.length ? (
          <aside className="hero-popular" aria-label="Populaire en ce moment">
            <header>
              <span>Populaire en ce moment</span>
              <span className="live">
                <span className="live-dot" aria-hidden="true" /> En direct
              </span>
            </header>
            <ul>
              {popular.map((offer) => {
                const mark = offer.image_url || offer.service_logo_url;
                return (
                  <li key={offer.id}>
                    <button type="button" onClick={() => onOpenOffer(offer)}>
                      <span className="pop-mark">
                        {mark ? <img src={assetUrl(mark)} alt="" /> : offer.service_emoji}
                      </span>
                      <span className="pop-copy">
                        <strong>{offer.name}</strong>
                        <small>{offer.service_name}</small>
                      </span>
                      <b>{money(offer.price_millimes)}</b>
                    </button>
                  </li>
                );
              })}
            </ul>
            <Link className="pop-more" to={ROUTES.shop}>
              Voir les tendances <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </aside>
        ) : null}
        <ul className="hero-stats">
          <li>
            <strong>{offers.length || "—"}</strong>
            <span>produits</span>
          </li>
          <li>
            <strong>{available.length || "—"}</strong>
            <span>en stock</span>
          </li>
          <li>
            <strong>{categories.length || "—"}</strong>
            <span>catégories</span>
          </li>
        </ul>
      </section>

      <section className="home-block" aria-labelledby="cats-title">
        <h2 id="cats-title">Catégories phares</h2>
        <p>Là où le catalogue est le plus fourni.</p>
        <div className="cat-grid">
          {categories.slice(0, 8).map((category) => {
            const count = offers.filter((offer) => String(offer.service_id) === category.id).length;
            const mark = categoryMark(offers, category.id);
            return (
              <Link key={category.id} className="cat-card" to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
                <span className="cat-mark">
                  {mark.src ? <img src={mark.src} alt="" /> : mark.emoji}
                </span>
                <span className="go" aria-hidden="true">
                  <ArrowUpRight size={15} />
                </span>
                <strong>{category.label}</strong>
                <small>
                  {count} produit{count > 1 ? "s" : ""}
                </small>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="home-block" aria-labelledby="trend-title">
        <h2 id="trend-title">Tendances</h2>
        <p>Les produits mis en avant, ou ceux qui sont en stock.</p>
        <div className="tile-grid">
          {trending.map((offer) => (
            <ProductTile key={offer.id} offer={offer} onOpen={onOpenOffer} />
          ))}
        </div>
      </section>

      {fresh.length ? (
        <section className="home-block" aria-labelledby="new-title">
          <h2 id="new-title">Nouveautés</h2>
          <div className="tile-grid">
            {fresh.map((offer) => (
              <ProductTile key={offer.id} offer={offer} onOpen={onOpenOffer} />
            ))}
          </div>
        </section>
      ) : null}

      <HowItWorks />

      <section className="home-block home-faq" aria-labelledby="faq-title">
        <h2 id="faq-title">Questions fréquentes</h2>
        <p>Sinon, le support est à un message.</p>
        {FAQ.map(([title, body]) => (
          <details key={title}>
            <summary>{title}</summary>
            <p>{body}</p>
          </details>
        ))}
      </section>

      <section className="home-block home-cta">
        <div>
          <h2>Prêt quand tu l'es.</h2>
          <p>Parcours le catalogue, paie en dinar, et retrouve tes accès dans ton compte.</p>
        </div>
        <div>
          <Link className="button button-primary" to={ROUTES.shop}>
            Voir la boutique
          </Link>
          <Link className="button button-ghost" to={ROUTES.register}>
            Créer un compte
          </Link>
        </div>
      </section>
    </>
  );
}
