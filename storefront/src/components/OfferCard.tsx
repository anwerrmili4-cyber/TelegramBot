import { useState } from "react";
import { CalendarClock, Check, ChevronRight, ShieldCheck, ShoppingBag, Truck } from "lucide-react";
import { QuantityStepper } from "@/components/QuantityStepper";
import { ServiceMark } from "@/components/ServiceMark";
import { TiltMedia } from "@/components/TiltMedia";
import { assetUrl } from "@/lib/api";
import { maxOrderable, money, periodLabel } from "@/lib/format";
import { stagger } from "@/lib/motion";
import type { Offer } from "@/types";

type OfferCardProps = {
  offer: Offer;
  index: number;
  inCart: number;
  cartIsFull: boolean;
  onAdd: (offer: Offer, quantity: number) => void;
  onOpen: (offer: Offer) => void;
};

export function OfferCard({ offer, index, inCart, cartIsFull, onAdd, onOpen }: OfferCardProps) {
  const [quantity, setQuantity] = useState(offer.min_quantity);
  const ceiling = maxOrderable(offer);
  const period = periodLabel(offer.period_days);
  const blocked = !offer.available || ceiling < offer.min_quantity;
  const lockedOut = cartIsFull && !inCart;

  return (
    <article
      className={`offer${blocked ? " offer-blocked" : ""}`}
      // A per-offer transition name lets a card glide to its new position when
      // the customer changes filter, rather than blinking out and back in.
      style={{ ...stagger(index), viewTransitionName: `offer-${offer.id}` }}
    >
      <header>
        <ServiceMark offer={offer} />
        <div>
          <p>{offer.service_name}</p>
          <span>Pack #{offer.package_number}</span>
        </div>
        {offer.badge ? <em className="offer-badge">{offer.badge}</em> : null}
      </header>

      <button type="button" className="offer-open" onClick={() => onOpen(offer)} aria-label={`Voir le détail de ${offer.name}`}>
        {offer.image_url ? (
          <TiltMedia className="offer-media" restX={7 + (index % 3) * 2} restY={-16 + (index % 4) * 4}>
            <img src={assetUrl(offer.image_url)} alt="" loading="lazy" decoding="async" />
          </TiltMedia>
        ) : null}

        <h3>{offer.name}</h3>
        <span className="offer-more">
          Voir le détail <ChevronRight size={14} aria-hidden="true" />
        </span>
      </button>

      <ul className="offer-facts">
        {period ? (
          <li>
            <CalendarClock size={14} aria-hidden="true" /> {period}
          </li>
        ) : null}
        {offer.delivery_delay ? (
          <li>
            <Truck size={14} aria-hidden="true" /> {offer.delivery_delay}
          </li>
        ) : null}
        {offer.warranty ? (
          <li>
            <ShieldCheck size={14} aria-hidden="true" /> {offer.warranty}
          </li>
        ) : null}
        <li className={offer.available ? "in-stock" : "out-of-stock"}>
          <i aria-hidden="true" />
          {offer.available
            ? offer.stock < 0
              ? "En stock"
              : `${offer.stock} en stock`
            : "Épuisé"}
        </li>
      </ul>

      <footer>
        <div className="offer-price">
          <small>Prix unitaire</small>
          <strong>{money(offer.price_millimes)}</strong>
        </div>
        {blocked ? (
          <span className="offer-unavailable">Indisponible</span>
        ) : (
          <div className="offer-actions">
            <QuantityStepper
              value={quantity}
              min={offer.min_quantity}
              max={ceiling}
              label={`Quantité pour ${offer.name}`}
              onChange={setQuantity}
            />
            <button
              type="button"
              className="button button-primary"
              disabled={lockedOut}
              title={lockedOut ? "Ton panier a atteint sa limite de produits." : undefined}
              onClick={() => {
                onAdd(offer, quantity);
                setQuantity(offer.min_quantity);
              }}
            >
              {inCart ? <Check size={16} aria-hidden="true" /> : <ShoppingBag size={16} aria-hidden="true" />}
              {inCart ? `Au panier (${inCart})` : "Ajouter"}
            </button>
          </div>
        )}
      </footer>
    </article>
  );
}
