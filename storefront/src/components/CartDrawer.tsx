import { ArrowRight, ShoppingBag, Trash2, X } from "lucide-react";
import { Overlay } from "@/components/Overlay";
import { QuantityStepper } from "@/components/QuantityStepper";
import { maxOrderable, money, plural } from "@/lib/format";
import { stagger } from "@/lib/motion";
import type { Cart } from "@/hooks/useCart";

type CartDrawerProps = {
  open: boolean;
  cart: Cart;
  maxLines: number;
  onClose: () => void;
  onCheckout: () => void;
};

export function CartDrawer({ open, cart, maxLines, onClose, onCheckout }: CartDrawerProps) {
  return (
    <Overlay open={open} onClose={onClose} labelledBy="cart-title" variant="drawer">
      <header className="drawer-head">
        <div>
          <span className="kicker">Panier</span>
          <h2 id="cart-title">
            {cart.count
              ? `${cart.count} ${plural(cart.count, "article", "articles")}`
              : "Ton panier"}
          </h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer le panier">
          <X size={18} aria-hidden="true" />
        </button>
      </header>

      {cart.lines.length ? (
        <>
          <ul className="cart-lines">
            {cart.lines.map(({ offer, quantity }, index) => (
              <li key={offer.id} style={stagger(index)}>
                <div className="cart-line-head">
                  <div>
                    <strong>{offer.name}</strong>
                    <small>
                      {offer.service_name} · {money(offer.price_millimes)} / unité
                    </small>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => cart.remove(offer.id)}
                    aria-label={`Retirer ${offer.name} du panier`}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
                <div className="cart-line-foot">
                  <QuantityStepper
                    value={quantity}
                    min={offer.min_quantity}
                    max={maxOrderable(offer)}
                    label={`Quantité pour ${offer.name}`}
                    onChange={(next) => cart.setQuantity(offer, next)}
                  />
                  <b>{money(offer.price_millimes * quantity)}</b>
                </div>
              </li>
            ))}
          </ul>

          <footer className="drawer-foot">
            {cart.isFull ? (
              <p className="drawer-notice">
                Un panier accepte au maximum {maxLines} produits différents.
              </p>
            ) : null}
            <div className="cart-total">
              <span>Total à payer</span>
              <strong>{money(cart.totalMillimes)}</strong>
            </div>
            <button type="button" className="button button-primary button-block" onClick={onCheckout}>
              Passer la commande <ArrowRight size={17} aria-hidden="true" />
            </button>
            <button type="button" className="button button-quiet button-block" onClick={cart.clear}>
              Vider le panier
            </button>
          </footer>
        </>
      ) : (
        <div className="drawer-empty">
          <ShoppingBag size={34} aria-hidden="true" />
          <h3>Ton panier est vide</h3>
          <p>Ajoute un ou plusieurs services, puis règle tout en une seule fois.</p>
          <button type="button" className="button button-primary" onClick={onClose}>
            Parcourir le catalogue
          </button>
        </div>
      )}
    </Overlay>
  );
}
