"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowRight, BadgeCheck, Check, ChevronDown, Clock3, Headphones,
  Menu, PackageCheck, Search, ShieldCheck, ShoppingBag, Sparkles, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

type Offer = {
  id: number; package_number: string; name: string; description: string;
  price_millimes: number; available: boolean; stock: number;
  min_quantity: number; max_quantity: number; delivery_delay: string;
  period_days: number; warranty: string; featured: boolean; badge: string;
  image_url: string; category: string; category_label: string;
  serviceName?: string; serviceEmoji?: string;
};
type Catalog = {
  ok: boolean; whatsapp: string;
  categories: { id: string; label: string }[];
  services: { id: number; name: string; emoji: string; offers: Offer[] }[];
};
type OrderResult = {
  order_id: number; tracking_token: string; total_millimes: number; whatsapp_url: string;
};

const API_BASE = (
  process.env.NEXT_PUBLIC_STOREFRONT_API_URL || "https://blackmarket.up.railway.app"
).replace(/\/$/, "");
const WHATSAPP_NUMBER = "21621994132";

function money(millimes: number) {
  return `${(millimes / 1000).toLocaleString("fr-TN", {
    minimumFractionDigits: 3, maximumFractionDigits: 3,
  })} DT`;
}

function absoluteAsset(url: string) {
  if (!url || /^https:\/\//.test(url)) return url;
  return `${API_BASE}${url}`;
}

function OfferCard({ offer, onOrder }: { offer: Offer; onOrder: (offer: Offer) => void }) {
  return (
    <article className="offer-card group">
      <div className="offer-topline">
        <div className="service-mark" aria-hidden="true">{offer.serviceEmoji || "✦"}</div>
        <div><p>{offer.serviceName}</p><span>Pack #{offer.package_number}</span></div>
        {offer.badge ? <span className="offer-badge">{offer.badge}</span> : null}
      </div>
      {offer.image_url ? (
        <div className="offer-image-wrap">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={absoluteAsset(offer.image_url)} alt="" className="offer-image" />
        </div>
      ) : null}
      <div className="offer-copy">
        <h3>{offer.name}</h3>
        <p>{offer.description || "Une offre digitale disponible directement depuis notre catalogue."}</p>
      </div>
      <div className="offer-meta">
        {offer.period_days > 0 ? <span><Clock3 /> {offer.period_days} jours</span> : null}
        <span className={offer.available ? "available" : "unavailable"}>
          <i /> {offer.available ? "Disponible" : "Indisponible"}
        </span>
      </div>
      <footer>
        <div className="price-block"><small>À partir de</small><strong>{money(offer.price_millimes)}</strong></div>
        <Button disabled={!offer.available} className="order-button" onClick={() => onOrder(offer)}>
          Commander <ArrowRight />
        </Button>
      </footer>
    </article>
  );
}

export function Storefront() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [selected, setSelected] = useState<Offer | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [result, setResult] = useState<OrderResult | null>(null);

  async function loadCatalog() {
    setLoading(true); setError("");
    try {
      const response = await fetch(`${API_BASE}/api/storefront/catalog`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Le catalogue ne répond pas.");
      const body = await response.json();
      if (!Array.isArray(body.services)) throw new Error("Réponse catalogue invalide.");
      setCatalog(body);
    } catch {
      setError("Le catalogue est momentanément indisponible. Réessaie dans quelques instants.");
    } finally { setLoading(false); }
  }

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/storefront/catalog`, { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) throw new Error("Le catalogue ne répond pas.");
        return response.json();
      })
      .then((body) => {
        if (!Array.isArray(body.services)) throw new Error("Réponse catalogue invalide.");
        if (active) setCatalog(body);
      })
      .catch(() => { if (active) setError("Le catalogue est momentanément indisponible. Réessaie dans quelques instants."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const offers = useMemo(() => {
    const all = (catalog?.services || []).flatMap((service) => service.offers.map((offer) => ({
      ...offer, serviceName: service.name, serviceEmoji: service.emoji,
    })));
    const term = query.trim().toLocaleLowerCase("fr");
    return all
      .filter((offer) => category === "all" || offer.category === category)
      .filter((offer) => !term || `${offer.name} ${offer.serviceName} ${offer.description}`.toLocaleLowerCase("fr").includes(term))
      .sort((a, b) => Number(b.featured) - Number(a.featured));
  }, [catalog, category, query]);

  async function submitOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setSubmitting(true); setFormError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_BASE}/api/storefront/orders`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"), phone: form.get("phone"),
          quantity: Number(form.get("quantity") || 1),
          payment_method: form.get("payment_method"), offer_id: selected.id,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Impossible de créer la commande.");
      setResult(body);
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Impossible de créer la commande.");
    } finally { setSubmitting(false); }
  }

  function closeCheckout(open: boolean) {
    if (!open) { setSelected(null); setResult(null); setFormError(""); }
  }

  return (
    <div className="site-shell">
      <header className="site-header">
        <a href="#top" className="brand" aria-label="BlackMarket, accueil">
          <span>BM</span><div><strong>BLACKMARKET</strong><small>Services digitaux</small></div>
        </a>
        <nav className={menuOpen ? "nav-links open" : "nav-links"} aria-label="Navigation principale">
          <a href="#catalogue" onClick={() => setMenuOpen(false)}>Catalogue</a>
          <a href="#comment-ca-marche" onClick={() => setMenuOpen(false)}>Comment ça marche</a>
          <a href={`https://wa.me/${WHATSAPP_NUMBER}`} target="_blank" rel="noreferrer">Aide</a>
        </nav>
        <div className="header-actions">
          <a className="support-pill" href={`https://wa.me/${WHATSAPP_NUMBER}`} target="_blank" rel="noreferrer">
            <Headphones /> <span>Besoin d’aide ?</span>
          </a>
          <button className="menu-button" onClick={() => setMenuOpen((value) => !value)} aria-label="Ouvrir le menu" aria-expanded={menuOpen}>
            {menuOpen ? <X /> : <Menu />}
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-glow" />
          <div className="hero-copy">
            <span className="eyebrow"><Sparkles /> Catalogue connecté au bot Telegram</span>
            <h1 id="hero-title">Tes services digitaux, <em>sans détour.</em></h1>
            <p>Choisis ton offre, règle par D17 ou Flouci, puis envoie ton reçu sur WhatsApp. On vérifie ton paiement manuellement.</p>
            <div className="hero-actions">
              <Button asChild className="hero-primary"><a href="#catalogue">Voir les offres <ArrowRight /></a></Button>
              <a className="hero-secondary" href={`https://wa.me/${WHATSAPP_NUMBER}`} target="_blank" rel="noreferrer">Parler au support</a>
            </div>
            <div className="hero-trust">
              <span><ShieldCheck /> Vérification humaine</span>
              <span><PackageCheck /> Catalogue en direct</span>
              <span><BadgeCheck /> Prix en DT</span>
            </div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/blackmarket-welcome.png" alt="" />
            <div className="floating-note note-one"><Check /> Paiement simple</div>
            <div className="floating-note note-two">D17 · Flouci</div>
          </div>
        </section>

        <section className="catalog-section" id="catalogue" aria-labelledby="catalog-title">
          <div className="section-heading">
            <div><span className="section-kicker">Le catalogue</span><h2 id="catalog-title">Trouve ton prochain service</h2></div>
            <p>Les disponibilités et prix viennent directement du même catalogue MongoDB que le bot.</p>
          </div>
          <div className="catalog-toolbar">
            <label className="search-box"><Search /><span className="sr-only">Rechercher une offre</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher Netflix, Canva, ChatGPT…" /></label>
            <div className="category-tabs" role="group" aria-label="Filtrer par catégorie">
              <button className={category === "all" ? "active" : ""} onClick={() => setCategory("all")}>Tout</button>
              {(catalog?.categories || []).map((item) => <button key={item.id} className={category === item.id ? "active" : ""} onClick={() => setCategory(item.id)}>{item.label}</button>)}
            </div>
          </div>
          {loading ? (
            <div className="offer-grid" aria-label="Chargement du catalogue">{[1, 2, 3, 4].map((item) => <div className="offer-skeleton" key={item}><i /><b /><span /><span /></div>)}</div>
          ) : error ? (
            <div className="catalog-state"><ShoppingBag /><h3>Le catalogue fait une petite pause</h3><p>{error}</p><Button onClick={loadCatalog}>Réessayer</Button></div>
          ) : offers.length ? (
            <div className="offer-grid">{offers.map((offer) => <OfferCard key={offer.id} offer={offer} onOrder={setSelected} />)}</div>
          ) : (
            <div className="catalog-state"><Search /><h3>Aucune offre trouvée</h3><p>Essaie un autre mot ou enlève le filtre actif.</p><Button onClick={() => { setQuery(""); setCategory("all"); }}>Tout afficher</Button></div>
          )}
        </section>

        <section className="steps-section" id="comment-ca-marche" aria-labelledby="steps-title">
          <div className="steps-intro"><span className="section-kicker">Simple et transparent</span><h2 id="steps-title">Ta commande en trois étapes.</h2></div>
          <ol className="steps-grid">
            <li><span>01</span><div><h3>Choisis ton offre</h3><p>Consulte le prix, la durée et la disponibilité en temps réel.</p></div></li>
            <li><span>02</span><div><h3>Règle ton paiement</h3><p>Paye avec D17 ou Flouci en suivant les informations reçues.</p></div></li>
            <li><span>03</span><div><h3>Envoie ton reçu</h3><p>WhatsApp s’ouvre avec ta référence. Ajoute ton justificatif pour vérification.</p></div></li>
          </ol>
        </section>
      </main>

      <footer className="site-footer">
        <div className="brand"><span>BM</span><div><strong>BLACKMARKET</strong><small>Services digitaux</small></div></div>
        <p>Paiements D17 et Flouci vérifiés manuellement. Aucun paiement n’est confirmé automatiquement.</p>
        <a href={`https://wa.me/${WHATSAPP_NUMBER}`} target="_blank" rel="noreferrer">WhatsApp +216 21 994 132 <ArrowRight /></a>
      </footer>

      <Dialog open={Boolean(selected)} onOpenChange={closeCheckout}>
        <DialogContent className="checkout-dialog sm:max-w-[620px]">
          {selected && !result ? (
            <>
              <DialogHeader><span className="dialog-kicker">Commande sécurisée</span><DialogTitle>{selected.name}</DialogTitle><DialogDescription>Crée ta commande, puis envoie le reçu sur WhatsApp pour vérification.</DialogDescription></DialogHeader>
              <div className="checkout-summary"><div><span>{selected.serviceName}</span><small>Pack #{selected.package_number}</small></div><strong>{money(selected.price_millimes)}</strong></div>
              <form className="checkout-form" onSubmit={submitOrder}>
                <label>Nom complet<Input required name="name" autoComplete="name" placeholder="Ex. Amine Ben Salah" /></label>
                <label>Numéro WhatsApp tunisien<Input required name="phone" inputMode="tel" autoComplete="tel" placeholder="21 994 132" /></label>
                <div className="form-row">
                  <label>Quantité<Input required name="quantity" type="number" min={selected.min_quantity} max={selected.max_quantity} defaultValue={selected.min_quantity} /></label>
                  <label>Moyen de paiement<select required name="payment_method" defaultValue="d17"><option value="d17">D17</option><option value="flouci">Flouci</option></select><ChevronDown aria-hidden="true" /></label>
                </div>
                <div className="manual-note"><ShieldCheck /><p><strong>Vérification manuelle</strong><span>Après la commande, WhatsApp s’ouvre. Envoie ton reçu : aucun paiement n’est validé automatiquement.</span></p></div>
                {formError ? <p className="form-error" role="alert">{formError}</p> : null}
                <Button className="checkout-submit" type="submit" disabled={submitting}>{submitting ? "Création en cours…" : "Continuer vers WhatsApp"}<ArrowRight /></Button>
              </form>
            </>
          ) : result ? (
            <div className="success-state">
              <span className="success-icon"><Check /></span>
              <DialogHeader><DialogTitle>Commande #{result.order_id} créée</DialogTitle><DialogDescription>Il reste une étape : envoie maintenant ton reçu D17 ou Flouci sur WhatsApp.</DialogDescription></DialogHeader>
              <div className="success-total"><span>Total à vérifier</span><strong>{money(result.total_millimes)}</strong></div>
              <Button asChild className="checkout-submit"><a href={result.whatsapp_url} target="_blank" rel="noreferrer">Ouvrir WhatsApp <ArrowRight /></a></Button>
              <p>Garde ta référence <strong>#{result.order_id}</strong> jusqu’à la livraison.</p>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
