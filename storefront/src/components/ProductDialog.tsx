import { useEffect, useState } from "react";
import {
  CalendarClock,
  Check,
  Layers,
  PackageCheck,
  ShieldCheck,
  ShoppingBag,
  Tag,
  Truck,
  X,
  Zap,
} from "lucide-react";
import { Overlay } from "@/components/Overlay";
import { QuantityStepper } from "@/components/QuantityStepper";
import { ServiceMark } from "@/components/ServiceMark";
import { TiltMedia } from "@/components/TiltMedia";
import { assetUrl } from "@/lib/api";
import { maxOrderable, money, periodLabel } from "@/lib/format";
import type { Offer } from "@/types";

type ProductDialogProps = {
  offer: Offer | null;
  inCart: number;
  cartIsFull: boolean;
  onClose: () => void;
  onAdd: (offer: Offer, quantity: number) => void;
  onBuyNow: (offer: Offer, quantity: number) => void;
};

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
  const period = periodLabel(shown.period_days);
  const facts = [
    { icon: CalendarClock, label: "Durée", value: period || "Selon l'offre" },
    { icon: Truck, label: "Livraison", value: shown.delivery_delay || "Par email et dans ton espace" },
    { icon: ShieldCheck, label: "Garantie", value: shown.warranty || "Support en cas de problème" },
    {
      icon: PackageCheck,
      label: "Disponibilité",
      value: !shown.available ? "Épuisé" : shown.stock < 0 ? "En stock" : `${shown.stock} en stock`,
    },
    {
      icon: Layers,
      label: "Quantité",
      value:
        shown.min_quantity > 1
          ? `De ${shown.min_quantity} à ${shown.max_quantity} par commande`
          : `Jusqu'à ${shown.max_quantity} par commande`,
    },
    { icon: Tag, label: "Catégorie", value: shown.category_label },
  ];

  return (
    <Overlay open={Boolean(offer)} onClose={onClose} labelledBy="product-title" variant="dialog">
      <div className="product-dialog">
        <header className="dialog-head">
          <div className="product-service">
            <ServiceMark offer={shown} />
            <div>
              <span className="kicker">{shown.service_name}</span>
              <small>Pack #{shown.package_number}</small>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="product-body">
          <div className={`product-stage${shown.image_url ? "" : " product-stage-plain"}`}>
            <div className="product-stage-copy">
              <div className="product-title">
                <h2 id="product-title">{shown.name}</h2>
                {shown.badge ? <em className="offer-badge">{shown.badge}</em> : null}
              </div>
              <p className="product-price">
                <strong>{money(shown.price_millimes)}</strong>
                <small>par unité</small>
              </p>
              {period ? <p className="product-stage-period">{period}</p> : null}
              <p className="product-description">
                {shown.description || "Service digital disponible directement depuis notre catalogue."}
              </p>
            </div>
            {shown.image_url ? (
              <TiltMedia className="product-media" restX={6} restY={-8}>
                <img src={assetUrl(shown.image_url)} alt="" decoding="async" />
              </TiltMedia>
            ) : null}
          </div>

          <dl className="product-facts">
            {facts.map(({ icon: Icon, label, value }) => (
              <div key={label}>
                <dt>
                  <Icon size={15} aria-hidden="true" /> {label}
                </dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>

          <p className="product-note">
            <Zap size={16} aria-hidden="true" />
            Payé avec ton portefeuille, un produit en stock est livré immédiatement par email et dans ton espace
            client.
          </p>
        </div>

        <footer className="product-foot">
          {blocked ? (
            <span className="offer-unavailable">Indisponible pour le moment</span>
          ) : (
            <>
              <div className="product-quantity">
                <QuantityStepper
                  value={quantity}
                  min={shown.min_quantity}
                  max={ceiling}
                  label={`Quantité pour ${shown.name}`}
                  onChange={setQuantity}
                />
                <b>{money(shown.price_millimes * quantity)}</b>
              </div>
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
        </footer>
      </div>
    </Overlay>
  );
}
