import { useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ArrowRight, ArrowUpRight, PackageSearch, Search, ShieldCheck, ShieldOff, Sparkles } from "lucide-react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { FilmReel } from "@/components/FilmReel";
import { HeroReviewReel } from "@/components/PublicReviews";
import { HowItWorks } from "@/components/HowItWorks";
import { requestStockAlert, assetUrl, errorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { accountPath } from "@/lib/accountPath";
import { money } from "@/lib/format";
import { warrantyBadgeClass, warrantyView } from "@/lib/warranty";
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

type ContactTone = "whatsapp" | "instagram" | "facebook";

const CONTACTS: { name: string; href: string; qr: string; tone: ContactTone }[] = [
  {
    name: "WhatsApp",
    href: "https://wa.me/our_blackmarket",
    qr: "/contact/whatsapp-qr.svg",
    tone: "whatsapp",
  },
  {
    name: "Instagram",
    href: "https://www.instagram.com/our_blackmarket/",
    qr: "/contact/instagram-qr.png",
    tone: "instagram",
  },
  {
    name: "Facebook",
    href: "https://www.facebook.com/people/Black-Market-TN/61594924482327/",
    qr: "/contact/facebook-qr.svg",
    tone: "facebook",
  },
];

function ContactMark({ tone }: { tone: ContactTone }) {
  if (tone === "whatsapp") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="currentColor"
          d="M12.04 2C6.58 2 2.15 6.4 2.15 11.83c0 1.74.46 3.44 1.34 4.94L2 22l5.39-1.4a10 10 0 0 0 4.65 1.18h.01c5.46 0 9.89-4.4 9.89-9.83C21.94 6.4 17.5 2 12.04 2zm5.76 13.9c-.24.68-1.4 1.3-1.94 1.38-.5.08-1.12.11-1.81-.11-.42-.14-.95-.31-1.64-.6-2.88-1.24-4.76-4.14-4.9-4.33-.14-.19-1.16-1.54-1.16-2.94s.73-2.08 1-2.37c.24-.26.64-.38.86-.38h.62c.2 0 .46-.04.72.55.27.62.9 2.14.98 2.3.08.15.13.34.03.54-.1.2-.15.33-.3.51-.14.17-.3.39-.43.52-.14.14-.29.3-.12.58.16.28.73 1.2 1.57 1.94 1.08.96 1.99 1.26 2.27 1.4.28.14.44.12.6-.07.17-.2.7-.81.89-1.09.19-.28.38-.23.64-.14.26.08 1.65.78 1.93.92.28.14.47.21.54.33.07.12.07.7-.17 1.38z"
        />
      </svg>
    );
  }
  if (tone === "instagram") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="4" y="4" width="16" height="16" rx="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="16.6" cy="7.5" r="1" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M14.2 21v-7.2h2.4l.36-2.8h-2.76V9.3c0-.81.22-1.36 1.38-1.36H17V5.4c-.24-.03-1.05-.1-2-.1-1.98 0-3.34 1.21-3.34 3.43v1.27H9.2v2.8h2.46V21h2.54z"
      />
    </svg>
  );
}

function HeroContacts() {
  return (
    <aside className="hero-contacts" aria-label="Contact">
      <header>Contact</header>
      <div className="hero-contact-list">
        {CONTACTS.map((item, index) => (
          <a
            key={item.tone}
            className={`hero-contact is-${item.tone}`}
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ "--i": index } as CSSProperties}
          >
            <span className="hero-contact-anim">
              <span className="hero-contact-mark">
                <ContactMark tone={item.tone} />
              </span>
              <span className="hero-contact-copy">
                <strong>{item.name}</strong>
                <small>Scanner le code</small>
              </span>
              <img src={item.qr} alt="" width="148" height="148" />
            </span>
          </a>
        ))}
      </div>
    </aside>
  );
}

function TileNotify({ offerId }: { offerId: number }) {
  const { customer, token } = useAuth();
  const [email, setEmail] = useState("");
  const [ask, setAsk] = useState(false);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(address: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await requestStockAlert(offerId, address.trim(), token || undefined);
      setDone(result.already_available ? "Déjà en stock" : "C'est noté");
    } catch (reason) {
      setError(errorMessage(reason, "Alerte impossible"));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <p className="tile-notify-done" role="status">
        {done}
      </p>
    );
  }

  if (!customer && ask) {
    return (
      <form
        className="tile-notify"
        onSubmit={(event) => {
          event.preventDefault();
          void send(email);
        }}
      >
        <input
          required
          type="email"
          autoComplete="email"
          inputMode="email"
          aria-label="Email"
          value={email}
          placeholder="toi@exemple.com"
          onChange={(event) => setEmail(event.target.value)}
        />
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? "Enregistrement…" : "Me prévenir"}
        </button>
        {error ? <small className="form-error">{error}</small> : null}
      </form>
    );
  }

  return (
    <div className="tile-notify">
      <button
        type="button"
        className="button button-primary"
        disabled={busy}
        aria-label="Me prévenir quand c'est disponible"
        onClick={() => {
          if (customer?.email) void send(customer.email);
          else setAsk(true);
        }}
      >
        {busy ? "Enregistrement…" : "Me prévenir"}
      </button>
      {error ? <small className="form-error">{error}</small> : null}
    </div>
  );
}

export function ProductTile({ offer, onOpen, index = 0 }: { offer: Offer; onOpen: (offer: Offer) => void; index?: number }) {
  const stock = !offer.available ? "Épuisé" : offer.stock < 0 ? "En stock" : `${offer.stock} en stock`;
  const warranty = warrantyView(offer);
  const tileRef = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);

  useLayoutEffect(() => {
    const node = tileRef.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      { threshold: 0.2 },
    );
    node.classList.add("is-armed");
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const classes = [offer.available ? "prod-tile" : "prod-tile sold-out", shown ? "is-in" : ""].filter(Boolean).join(" ");
  return (
    <article ref={tileRef} className={classes} style={{ "--i": index } as CSSProperties}>
      <button type="button" className="prod-tile-open" aria-label={offer.name} onClick={() => onOpen(offer)}>
        <span className="prod-tile-media">
          {offer.image_url || offer.service_logo_url ? <img src={assetUrl(offer.image_url || offer.service_logo_url)} alt="" loading="lazy" /> : <span className="prod-ph">{offer.service_emoji}</span>}
          {offer.available ? null : <span className="sold-stamp">Épuisé</span>}
        </span>
      </button>
      <div className="prod-tile-body">
        <button type="button" className="prod-tile-copy" onClick={() => onOpen(offer)}>
          <span className={warrantyBadgeClass("poster-warranty", warranty.tone)}>
            {warranty.tone === "none" ? <ShieldOff size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}
            {warranty.label}
          </span>
        </button>
        <div className="prod-tile-line">
          <button type="button" className="prod-tile-copy" onClick={() => onOpen(offer)}>
            <em>{offer.service_name}</em>
            <strong>{offer.name}</strong>
            <small>
              {stock}
              {warranty.duration ? ` · ${warranty.duration}` : ""}
            </small>
          </button>
          <FavoriteButton compact icon offerId={offer.id} />
        </div>
        <button type="button" className="prod-tile-copy is-rest" onClick={() => onOpen(offer)}>
          <span className="prod-tile-foot">
            <b>{money(offer.price_millimes)}</b>
            <span className="go" aria-hidden="true">
              <ArrowUpRight size={16} />
            </span>
          </span>
        </button>
      </div>
      {offer.available ? null : <TileNotify offerId={offer.id} />}
    </article>
  );
}

function categoryMark(offers: Offer[], categoryId: string) {
  const inCategory = offers.filter((offer) => String(offer.service_id) === categoryId);
  const logo = inCategory.find((offer) => offer.service_logo_url);
  if (logo) return { src: assetUrl(logo.service_logo_url), emoji: "" };
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
            <span className="hero-lead-long">
              Des produits digitaux aux meilleurs prix, payés en dinar. Livraison rapide, et tes accès restent dans ton compte.
            </span>
            <span className="hero-lead-short">Payé en dinar. Tes accès restent dans ton compte.</span>
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
            <button type="submit" className="button button-primary" aria-label="Chercher">
              <Search className="hero-search-go" size={18} aria-hidden="true" />
              <span className="hero-search-label">Chercher</span>
            </button>
          </form>
          <div className="hero-cats">
            {categories.slice(0, 6).map((category) => (
              <Link key={category.id} to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
                {category.label}
              </Link>
            ))}
          </div>
          <div className="hero-missing-slot">
            <Link className="hero-missing" to={accountPath("demande")}>
              <span className="hero-missing-icon" aria-hidden="true">
                <PackageSearch size={18} />
              </span>
              <span className="hero-missing-copy">
                <strong>Tu n&apos;as pas trouvé ton service ?</strong>
                <small>
                  Demander un produit
                  <ArrowRight size={14} aria-hidden="true" />
                </small>
              </span>
            </Link>
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
                const mark = offer.service_logo_url;
                return (
                  <li key={offer.id}>
                    <button type="button" onClick={() => onOpenOffer(offer)}>
                      <span className="pop-mark">
                        {mark ? <img src={assetUrl(mark)} alt="" decoding="async" /> : offer.service_emoji}
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
        <HeroContacts />
        <HeroReviewReel />
        {highlighted.length ? (
          <div className="hero-picks">
            {highlighted.slice(0, 2).map((offer, index) => (
              <ProductTile key={offer.id} offer={offer} index={index} onOpen={onOpenOffer} />
            ))}
          </div>
        ) : null}
      </section>

      <section className="home-block home-cats" aria-labelledby="cats-title">
        <h2 id="cats-title">Catégories phares</h2>
        <p>Là où le catalogue est le plus fourni.</p>
        <div className="cat-grid">
          {categories.slice(0, 8).map((category) => {
            const count = offers.filter((offer) => String(offer.service_id) === category.id).length;
            const mark = categoryMark(offers, category.id);
            return (
              <Link key={category.id} className="cat-card" to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}>
                <span className="cat-mark">
                  {mark.src ? <img src={mark.src} alt="" loading="lazy" decoding="async" /> : mark.emoji}
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
        <Link className="home-more" to={ROUTES.shop}>
          Voir plus
        </Link>
      </section>

      <FilmReel offers={offers} />

      <section className="home-block home-trends" aria-labelledby="trend-title">
        <h2 id="trend-title">Tendances</h2>
        <p>Les produits mis en avant, ou ceux qui sont en stock.</p>
        <div className="tile-grid">
          {trending.map((offer, index) => (
            <ProductTile key={offer.id} offer={offer} index={index} onOpen={onOpenOffer} />
          ))}
        </div>
        <Link className="home-more" to={ROUTES.shop}>
          Voir plus
        </Link>
      </section>

      {fresh.length ? (
        <section className="home-block home-fresh" aria-labelledby="new-title">
          <h2 id="new-title">Nouveautés</h2>
          <div className="tile-grid">
            {fresh.map((offer, index) => (
              <ProductTile key={offer.id} offer={offer} index={index} onOpen={onOpenOffer} />
            ))}
          </div>
          <Link className="home-more" to={ROUTES.shop}>
            Voir plus
          </Link>
        </section>
      ) : null}

      <HowItWorks />

      <section className="home-block home-faq" aria-labelledby="faq-title">
        <h2 id="faq-title">Questions fréquentes</h2>
        <p>Sinon, le support est à un message.</p>
        {FAQ.map(([title, body]) => (
          <details
            key={title}
            onToggle={(event) => {
              event.currentTarget.querySelector("summary")?.setAttribute("aria-expanded", String(event.currentTarget.open));
            }}
          >
            <summary aria-expanded="false">{title}</summary>
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
