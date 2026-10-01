import { useEffect, useState } from "react";
import { ArrowLeft, Check, Clock, List, Lock, Package, Share2, ShieldCheck, ShoppingBag, TriangleAlert, Zap } from "lucide-react";
import { ProductTile } from "@/components/Hero";
import { QuantityStepper } from "@/components/QuantityStepper";
import { assetUrl } from "@/lib/api";
import { maxOrderable, money, periodLabel } from "@/lib/format";
import { Link, ROUTES } from "@/lib/router";
import type { Offer } from "@/types";

type ProductPageProps = {
  offer: Offer | null;
  loading: boolean;
  related: Offer[];
  inCart: number;
  cartIsFull: boolean;
  onOpenOffer: (offer: Offer) => void;
  onAdd: (offer: Offer, quantity: number) => void;
  onBuyNow: (offer: Offer, quantity: number) => void;
};

const PAY_STEPS = [
  ["Paie ta commande", "Portefeuille, ou D17, Flouci, IZI et Wafa Cash."],
  ["Reçois-le aussitôt", "L'accès arrive sur ta commande dès que le paiement est confirmé."],
  ["Un souci ?", "Le support est à un message."],
];

function receiveLines(description: string) {
  const lines = description
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.length ? lines : ["Service digital disponible directement depuis notre catalogue."];
}

export function ProductPage({ offer, loading, related, inCart, cartIsFull, onOpenOffer, onAdd, onBuyNow }: ProductPageProps) {
  const [quantity, setQuantity] = useState(1);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!offer) return;
    setQuantity(offer.min_quantity);
    setCopied(false);
  }, [offer]);

  if (!offer) {
    return (
      <section className="doc-page">
        <header className="page-intro">
          <span className="kicker">BlackMarket</span>
          <h1>{loading ? "Chargement…" : "Produit introuvable"}</h1>
          <p>
            <Link to={ROUTES.shop}>Retour à la boutique</Link>
          </p>
        </header>
      </section>
    );
  }

  const ceiling = maxOrderable(offer);
  const blocked = !offer.available || ceiling < offer.min_quantity;
  const lockedOut = cartIsFull && !inCart;
  const period = periodLabel(offer.period_days);
  const stockLabel = !offer.available ? "Épuisé" : offer.stock < 0 ? "En stock" : `${offer.stock} en stock`;
  const low = offer.available && offer.stock > 0 && offer.stock <= 3;
  const bar = offer.stock < 0 ? 100 : Math.max(6, Math.min(100, offer.stock * 8));
  const lines = receiveLines(offer.description);
  const shopCategory = `${ROUTES.shop}?categorie=${encodeURIComponent(String(offer.service_id))}#catalogue`;
  const shareTitle = offer.name;

  async function share() {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: shareTitle, url });
        return;
      } catch {
        return;
      }
    }
    await navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <article className="pdp-page">
      <div className="pdp-top">
        <nav className="crumbs" aria-label="Fil d'Ariane">
          <Link to={ROUTES.shop} aria-label="Boutique">
            <ArrowLeft size={16} aria-hidden="true" />
          </Link>
          <Link to={ROUTES.shop}>Boutique</Link>
          <span>/</span>
          <Link to={shopCategory}>{offer.service_name}</Link>
        </nav>
        <button type="button" className="button button-ghost pdp-share" onClick={() => void share()}>
          <Share2 size={15} aria-hidden="true" />
          {copied ? "Lien copié" : "Partager"}
        </button>
      </div>

      <div className="pdp-layout">
        <div className="pdp-main">
          <div className="gal-stage">
            {offer.image_url ? (
              <img src={assetUrl(offer.image_url)} alt="" decoding="async" />
            ) : (
              <span className="prod-ph">{offer.service_emoji}</span>
            )}
            <span className="pricechip">{money(offer.price_millimes)}</span>
          </div>

          <div className="pdp-tags">
            <span className="tag tag-blue">{offer.service_name}</span>
            {offer.available ? (
              <span className="tag">
                <Zap size={13} aria-hidden="true" /> Livraison immédiate
              </span>
            ) : null}
            {offer.warranty ? (
              <span className="tag">
                <ShieldCheck size={13} aria-hidden="true" /> Garantie
              </span>
            ) : null}
            {offer.badge ? <span className="tag">{offer.badge}</span> : null}
          </div>

          <h1 id="product-title">{offer.name}</h1>
          <p className="pdp-meta">
            {period ? (
              <span>
                <Clock size={15} aria-hidden="true" /> {period}
              </span>
            ) : null}
            <span>
              <Package size={15} aria-hidden="true" /> {stockLabel}
            </span>
          </p>

          <section className="desc-card" aria-labelledby="product-desc-title">
            <h2 id="product-desc-title">
              <List size={18} aria-hidden="true" /> Description
            </h2>
            <div className="desc-sec">
              <span className="label-caps">Ce que tu reçois</span>
              <div className="rich">
                {lines.map((line) => (
                  <p key={line}>
                    <Check size={16} aria-hidden="true" />
                    {line}
                  </p>
                ))}
              </div>
            </div>
            <div className="desc-sec">
              <span className="label-caps">Livraison et garantie</span>
              <dl className="facts">
                <div>
                  <dt>
                    <Zap size={16} aria-hidden="true" /> Livraison
                  </dt>
                  <dd>{offer.delivery_delay || "Instantané, depuis le stock"}</dd>
                </div>
                <div>
                  <dt>
                    <Clock size={16} aria-hidden="true" /> Durée
                  </dt>
                  <dd>{period || "—"}</dd>
                </div>
                <div>
                  <dt>
                    <ShieldCheck size={16} aria-hidden="true" /> Garantie
                  </dt>
                  <dd>{offer.warranty || "Sans garantie"}</dd>
                </div>
                <div>
                  <dt>
                    <ShieldCheck size={16} aria-hidden="true" /> Remplacement
                  </dt>
                  <dd>{offer.warranty ? "Depuis la commande" : "Non couvert"}</dd>
                </div>
                <div>
                  <dt>
                    <Package size={16} aria-hidden="true" /> Enregistré dans
                  </dt>
                  <dd>Mes achats</dd>
                </div>
              </dl>
            </div>
          </section>

          {related.length ? (
            <section className="also" aria-labelledby="also-title">
              <span className="kicker">Tu pourrais aimer</span>
              <div className="also-head">
                <h2 id="also-title">Plus de {offer.service_name}</h2>
                <Link to={shopCategory}>
                  Voir tout <ArrowLeft size={14} aria-hidden="true" className="also-arrow" />
                </Link>
              </div>
              <div className="tile-grid">
                {related.slice(0, 4).map((item) => (
                  <ProductTile key={item.id} offer={item} onOpen={onOpenOffer} />
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <div className="pdp-side">
          <aside className="order-card">
            <span className="label-caps">Ta commande</span>
            <div className="oline">
              <span className="order-thumb">
                {offer.image_url ? <img src={assetUrl(offer.image_url)} alt="" /> : offer.service_emoji}
              </span>
              <div>
                <b>{offer.name}</b>
                <small>
                  BlackMarket · {money(offer.price_millimes)} l'unité
                </small>
              </div>
            </div>

            <div className={`stockbox${low ? " low" : ""}`}>
              <div>
                <span className="sb-label">
                  <Package size={16} aria-hidden="true" /> Stock disponible
                </span>
                <b className="sb-count">
                  {offer.available && offer.stock >= 0 ? (
                    <>
                      {offer.stock} <small>en stock</small>
                    </>
                  ) : (
                    stockLabel
                  )}
                </b>
              </div>
              <div className="sb-meter" aria-hidden="true">
                <i style={{ width: `${blocked ? 0 : bar}%` }} />
              </div>
              {low ? (
                <p className="sb-note">
                  <TriangleAlert size={14} aria-hidden="true" /> Plus que {offer.stock} — commande bientôt
                </p>
              ) : null}
            </div>

            {blocked ? (
              <span className="offer-unavailable">Indisponible pour le moment</span>
            ) : (
              <>
                {ceiling > offer.min_quantity ? (
                  <div className="order-qty">
                    <span>Quantité</span>
                    <QuantityStepper
                      value={quantity}
                      min={offer.min_quantity}
                      max={ceiling}
                      label={`Quantité pour ${offer.name}`}
                      onChange={setQuantity}
                    />
                  </div>
                ) : null}
                <div className="order-total">
                  <div>
                    <span>Total</span>
                    <small>
                      {quantity} article{quantity > 1 ? "s" : ""} · sans frais ajoutés
                    </small>
                  </div>
                  <b>{money(offer.price_millimes * quantity)}</b>
                </div>
                <div className="info-box">
                  <div>
                    <b>Livraison · {offer.available ? "immédiate" : "indisponible"}</b>
                    <p>L'accès arrive sur ta commande dès que le paiement est confirmé.</p>
                  </div>
                  <div>
                    <b>Garantie · {offer.warranty || "Sans garantie"}</b>
                    <p>
                      {offer.warranty
                        ? "La demande se fait depuis la commande."
                        : "Vendu comme décrit. Le support reste joignable en cas de souci."}
                    </p>
                  </div>
                </div>
                <div className="order-actions">
                  <button
                    type="button"
                    className="button button-primary pdp-pay"
                    disabled={lockedOut}
                    onClick={() => onBuyNow(offer, quantity)}
                  >
                    Acheter maintenant
                  </button>
                  <button
                    type="button"
                    className="button button-ghost pdp-pay"
                    disabled={lockedOut}
                    onClick={() => onAdd(offer, quantity)}
                  >
                    {inCart ? <Check size={16} aria-hidden="true" /> : <ShoppingBag size={16} aria-hidden="true" />}
                    {inCart ? `Au panier (${inCart})` : "Ajouter au panier"}
                  </button>
                </div>
                {lockedOut ? <small className="drawer-notice">Ton panier a atteint sa limite de produits.</small> : null}
              </>
            )}
            <p className="order-secure">
              <Lock size={14} aria-hidden="true" /> Paiement sécurisé par <b>BlackMarket</b>
            </p>
          </aside>

          <aside className="pay-steps">
            <span className="label-caps">Du paiement à ton produit</span>
            <ol>
              {PAY_STEPS.map(([title, body], index) => (
                <li key={title}>
                  <span>{index + 1}</span>
                  <div>
                    <b>{title}</b>
                    <p>{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      </div>
    </article>
  );
}
