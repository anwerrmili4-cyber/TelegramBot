import { useEffect, useState } from "react";
import { Check, Clock, Package, ShieldCheck, ShieldOff, ShoppingBag, X, Zap } from "lucide-react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { Overlay } from "@/components/Overlay";
import { QuantityStepper } from "@/components/QuantityStepper";
import { assetUrl } from "@/lib/api";
import { maxOrderable, money, periodLabel } from "@/lib/format";
import { warrantyBadgeClass, warrantyView } from "@/lib/warranty";
import type { Offer } from "@/types";

type ProductDialogProps = {
  offer: Offer | null;
  inCart: number;
  cartIsFull: boolean;
  onClose: () => void;
  onAdd: (offer: Offer, quantity: number) => void;
  onBuyNow: (offer: Offer, quantity: number) => void;
};

function receiveLines(description: string) {
  const lines = description
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.length ? lines : ["Service digital disponible directement depuis notre catalogue."];
}

export function ProductDialog({ offer, inCart, cartIsFull, onClose, onAdd, onBuyNow }: ProductDialogProps) {
  // Keep the last offer while the dialog animates out.
  const [shown, setShown] = useState<Offer | null>(offer);
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (!offer) return;
    setShown(offer);
    setQuantity(offer.min_quantity);
  }, [offer]);

  if (!shown) return null;
  const ceiling = maxOrderable(shown);
  const blocked = !shown.available || ceiling < shown.min_quantity;
  const lockedOut = cartIsFull && !inCart;
  const showTerms = shown.show_terms !== false;
  const period = showTerms ? periodLabel(shown.period_days) : "";
  const warranty = warrantyView(shown);
  const stock = !shown.available ? "Épuisé" : shown.stock < 0 ? "En stock" : `${shown.stock} en stock`;
  const lines = receiveLines(shown.description);

  return (
    <Overlay open={Boolean(offer)} onClose={onClose} labelledBy="product-title" variant="dialog">
      <div className="product-dialog">
        <header className="dialog-head">
          <div className="product-service">
            <span className="cat-mark">
              {shown.image_url || shown.service_logo_url ? <img src={assetUrl(shown.image_url || shown.service_logo_url)} alt="" decoding="async" /> : shown.service_emoji}
            </span>
            <div>
              <span className="kicker">{shown.service_name}</span>
              <small>Pack #{shown.package_number}</small>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="product-body pdp-layout">
          <div className="pdp-main">
            <div className="gal-stage">
              {shown.video_url ? (
                <video src={assetUrl(shown.video_url)} poster={shown.image_url ? assetUrl(shown.image_url) : undefined} controls playsInline preload="metadata" />
              ) : shown.image_url || shown.service_logo_url ? (
                <img src={assetUrl(shown.image_url || shown.service_logo_url)} alt="" decoding="async" />
              ) : (
                <span className="prod-ph">{shown.service_emoji}</span>
              )}
              <span className="pricechip">{money(shown.price_millimes)}</span>
            </div>

            <div className="pdp-tags">
              <span className="tag tag-blue">{shown.service_name}</span>
              {shown.available ? (
                <span className="tag">
                  <Zap size={13} aria-hidden="true" /> Livraison immédiate
                </span>
              ) : null}
              {showTerms ? (
                <span className={warrantyBadgeClass("poster-warranty", warranty.tone)}>
                  {warranty.tone === "none" ? <ShieldOff size={14} aria-hidden="true" /> : <ShieldCheck size={14} aria-hidden="true" />}
                  {warranty.label}
                </span>
              ) : null}
              {shown.badge ? <span className="tag">{shown.badge}</span> : null}
            </div>

            <h2 id="product-title">{shown.name}</h2>
            <p className="pdp-meta">
              {period ? (
                <span>
                  <Clock size={15} aria-hidden="true" /> {period}
                </span>
              ) : null}
              <span>
                <Package size={15} aria-hidden="true" /> {stock}
              </span>
            </p>

            <section className="desc-card" aria-labelledby="product-desc-title">
              <h3 id="product-desc-title">Description</h3>
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
                <span className="label-caps">{showTerms ? "Livraison et garantie" : "Livraison"}</span>
                <dl className="facts">
                  <div>
                    <dt>
                      <Zap size={16} aria-hidden="true" /> Livraison
                    </dt>
                    <dd>{shown.delivery_delay || "Par email et dans ton espace"}</dd>
                  </div>
                  {showTerms && period ? (
                    <div>
                      <dt>
                        <Clock size={16} aria-hidden="true" /> Durée
                      </dt>
                      <dd>{period}</dd>
                    </div>
                  ) : null}
                  {showTerms ? (
                    <div>
                      <dt>
                        <ShieldCheck size={16} aria-hidden="true" /> Garantie
                      </dt>
                      <dd>{warranty.label}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>
                      <Package size={16} aria-hidden="true" /> Enregistré dans
                    </dt>
                    <dd>Mes achats</dd>
                  </div>
                </dl>
              </div>
            </section>
          </div>

          <aside className="order-card">
            <span className="label-caps">Ta commande</span>
            <FavoriteButton offerId={shown.id} />
            <div className="oline">
              <span className="cat-mark">
                {shown.image_url || shown.service_logo_url ? <img src={assetUrl(shown.image_url || shown.service_logo_url)} alt="" loading="lazy" decoding="async" /> : shown.service_emoji}
              </span>
              <div>
                <b>{shown.name}</b>
                <small>
                  {shown.service_name} · {money(shown.price_millimes)} l'unité
                </small>
              </div>
            </div>
            <p className="order-stock">
              <Package size={15} aria-hidden="true" />
              <span>Stock disponible</span>
              <b>{stock}</b>
            </p>
            {blocked ? (
              <span className="offer-unavailable">Indisponible pour le moment</span>
            ) : (
              <>
                <div className="order-qty">
                  <span>Quantité</span>
                  <QuantityStepper
                    value={quantity}
                    min={shown.min_quantity}
                    max={ceiling}
                    label={`Quantité pour ${shown.name}`}
                    onChange={setQuantity}
                  />
                </div>
                <div className="order-total">
                  <div>
                    <span>Total</span>
                    <small>
                      {quantity} article{quantity > 1 ? "s" : ""} · sans frais ajoutés
                    </small>
                  </div>
                  <b>{money(shown.price_millimes * quantity)}</b>
                </div>
                {shown.remark || shown.requires_info ? (
                  <p className="order-note">
                    <span className="remark-copy">
                      <b>{shown.requires_info ? "Informations à envoyer" : "Remarque"}</b>
                      {shown.remark || "Tu enverras tes informations au moment du paiement."}
                    </span>
                  </p>
                ) : null}
                <p className="order-note">
                  <Zap size={15} aria-hidden="true" />
                  <span>
                    <b>Livraison · {shown.delivery_delay || "immédiate"}</b>
                    L'accès arrive par email et reste dans ton espace dès que le paiement est confirmé.
                  </span>
                </p>
                {showTerms ? (
                  <p className="order-note">
                    <ShieldCheck size={15} aria-hidden="true" />
                    <span>
                      <b>Garantie · {warranty.label}</b>
                      {warranty.covered
                        ? "La demande se fait depuis la commande."
                        : "Vendu comme décrit. Le support reste joignable en cas de souci."}
                    </span>
                  </p>
                ) : null}
                <div className="product-actions">
                  <button
                    type="button"
                    className="button button-ghost"
                    disabled={lockedOut}
                    onClick={() => onAdd(shown, quantity)}
                  >
                    {inCart ? <Check size={16} aria-hidden="true" /> : <ShoppingBag size={16} aria-hidden="true" />}
                    {inCart ? `Au panier (${inCart})` : "Ajouter au panier"}
                  </button>
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={lockedOut}
                    onClick={() => onBuyNow(shown, quantity)}
                  >
                    Acheter maintenant
                  </button>
                </div>
                {lockedOut ? <small className="drawer-notice">Ton panier a atteint sa limite de produits.</small> : null}
              </>
            )}
          </aside>
        </div>
      </div>
    </Overlay>
  );
}
