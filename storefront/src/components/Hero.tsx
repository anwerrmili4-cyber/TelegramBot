import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ArrowRight, ArrowUpRight, PackageSearch, Search, ShieldCheck, ShieldOff, Sparkles } from "lucide-react";
import BlurText from "@/components/bits/BlurText.jsx";
import CountUp from "@/components/bits/CountUp.jsx";
import StarBorder from "@/components/bits/StarBorder.jsx";

const LightRays = lazy(() => import("@/components/bits/LightRays.jsx"));
import { FavoriteButton } from "@/components/FavoriteButton";
import { useHomeReveals } from "@/components/motion/useHomeReveals";
import { filmOffers } from "@/components/FilmReel";
import { HeroReviewReel } from "@/components/PublicReviews";
import { HowItWorks } from "@/components/HowItWorks";
import { requestStockAlert, assetUrl, errorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { accountPath } from "@/lib/accountPath";
import { money } from "@/lib/format";
import { warrantyBadgeClass, warrantyView } from "@/lib/warranty";
import { Link, navigate, ROUTES } from "@/lib/router";
import { trackInteraction, trackSearch } from "@/lib/track";
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
  ["Un compte est obligatoire ?", "Oui. Après l'introduction, le site se regarde quelques secondes, puis la fenêtre d'inscription s'ouvre."],
];

function spotlightSafe(offers: Offer[]) {
  return offers.filter((offer) => offer.featured || offer.available).length;
}

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
  return <img src={`/contact/${tone}.svg`} alt="" width="36" height="36" />;
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
              <img className="hero-contact-qr" src={item.qr} alt="" width="148" height="148" />
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
      trackInteraction("stock_alert", { offerId });
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
  const showTerms = offer.show_terms !== false;
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
          {showTerms ? (
            <span className={warrantyBadgeClass("poster-warranty", warranty.tone)}>
              {warranty.tone === "none" ? <ShieldOff size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}
              {warranty.label}
            </span>
          ) : null}
        </button>
        <div className="prod-tile-line">
          <button type="button" className="prod-tile-copy" onClick={() => onOpen(offer)}>
            <em>{offer.service_name}</em>
            <strong>{offer.name}</strong>
            <small>
              {stock}
              {showTerms && warranty.duration ? ` · ${warranty.duration}` : ""}
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

function useHeroMotion() {
  const [desktop, setDesktop] = useState(true);
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const width = window.matchMedia("(max-width: 760px)");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      setDesktop(!width.matches);
      setReduced(motion.matches);
    };
    apply();
    width.addEventListener("change", apply);
    motion.addEventListener("change", apply);
    return () => {
      width.removeEventListener("change", apply);
      motion.removeEventListener("change", apply);
    };
  }, []);
  return { desktop, reduced };
}

export function Hero({ offers, categories, onOpenOffer }: HeroProps) {
  const [query, setQuery] = useState("");
  const { desktop, reduced } = useHeroMotion();
  const homeRef = useHomeReveals(`${categories.length}:${spotlightSafe(offers)}`);
  const available = offers.filter((offer) => offer.available);
  const featured = offers.filter((offer) => offer.featured);
  const highlighted = featured.length ? featured : available;
  const popular = highlighted.slice(0, 4);
  const trending = highlighted.slice(0, 8);
  const spotlight = filmOffers(offers, 8);
  const fresh = [...available].sort((a, b) => b.id - a.id).slice(0, 4);

  function search(event: FormEvent) {
    event.preventDefault();
    trackSearch(query);
    searchTo(query);
  }

  return (
    <div className="home-stage" ref={homeRef}>
      <section className={popular.length ? "hero has-popular" : "hero"} aria-labelledby="hero-title">
        <div className="hero-card">
          <div className="hero-rays" aria-hidden="true">
            {reduced ? null : (
              <Suspense fallback={null}>
              <LightRays
                raysOrigin="top-left"
                raysColor="#1a73ff"
                raysSpeed={desktop ? 0.45 : 0.28}
                lightSpread={0.55}
                rayLength={2.1}
                rayDensity={desktop ? 0.72 : 0.45}
                glow={0.28}
                haze={0.12}
                intensity={desktop ? 0.42 : 0.24}
                followMouse={desktop}
                mouseInfluence={0.06}
                cursorShadow={false}
                clickPulse={false}
                noiseAmount={0}
                intro
                opacity={0.72}
                maxDevicePixelRatio={desktop ? 1.5 : 1}
              />
              </Suspense>
            )}
          </div>
          <span className="hero-eyebrow">
            <Sparkles size={14} aria-hidden="true" /> Livraison immédiate · 24/7
          </span>
          <h1 id="hero-title" className="hero-title">
            <BlurText
              as="span"
              className="hero-blur"
              text="BlackMarket"
              animateBy="words"
              direction="bottom"
              blur={8}
              distance={16}
              delay={60}
              stepDuration={0.42}
              trigger="load"
            />{" "}
            <em>
              <BlurText
                as="span"
                className="hero-blur"
                text="livré en secondes."
                animateBy="words"
                direction="bottom"
                blur={8}
                distance={16}
                delay={110}
                stepDuration={0.42}
                trigger="load"
              />
            </em>
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
                  <span className="stat-slot">
                    <span className="stat-sizer" aria-hidden="true">{count}</span>
                    <CountUp to={count} duration={0.9} className="stat-count" />
                  </span>
                  {` produit${count > 1 ? "s" : ""}`}
                </small>
              </Link>
            );
            })}
        </div>
        <Link className="home-more" to={ROUTES.shop}>
          Voir plus
        </Link>
      </section>

      {spotlight.length ? (
        <section className="home-block home-offers" aria-labelledby="offers-title">
          <h2 id="offers-title">Offres</h2>
          <p>Les produits mis en avant, ou ceux qui sont en stock.</p>
          <div className="tile-grid">
            {spotlight.map((offer, index) => (
              <ProductTile key={offer.id} offer={offer} index={index} onOpen={onOpenOffer} />
            ))}
          </div>
          <Link className="home-more" to={ROUTES.deals}>
            Voir plus
          </Link>
        </section>
      ) : null}

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
          <StarBorder
            as={Link}
            to={ROUTES.shop}
            className="button button-primary"
            color="#9ec1ff"
            trailColor="#1a73ff"
            backgroundColor="transparent"
            textColor="#ffffff"
            borderColor="rgba(255,255,255,0.28)"
            radius={999}
            thickness={1.25}
            duration={7}
            glow={0.4}
            stars={1}
            trailLength={0.22}
            hover="brighten"
            sparkle={false}
          >
            Voir la boutique
          </StarBorder>
          <Link className="button button-ghost" to={ROUTES.register}>
            Créer un compte
          </Link>
        </div>
      </section>
    </div>
  );
}
