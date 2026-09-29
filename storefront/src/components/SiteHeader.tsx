import { useEffect, useState } from "react";
import { MessageCircle, Menu, ShoppingCart, X } from "lucide-react";
import { money } from "@/lib/format";

type SiteHeaderProps = {
  cartCount: number;
  cartTotalMillimes: number;
  whatsappNumber: string;
  onOpenCart: () => void;
};

export function SiteHeader({
  cartCount,
  cartTotalMillimes,
  whatsappNumber,
  onOpenCart,
}: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [menuOpen]);

  return (
    <header className="site-header">
      <a className="brand" href="#top">
        <img src="/logo.png" alt="" width="40" height="40" />
        <div>
          <strong>BLACKMARKET</strong>
          <small>Tunisie</small>
        </div>
      </a>

      <nav className={menuOpen ? "site-nav open" : "site-nav"} aria-label="Navigation principale">
        <a href="#catalogue" onClick={() => setMenuOpen(false)}>
          Catalogue
        </a>
        <a href="#fonctionnement" onClick={() => setMenuOpen(false)}>
          Comment ça marche
        </a>
        <a href={`https://wa.me/${whatsappNumber}`} target="_blank" rel="noreferrer">
          Assistance
        </a>
      </nav>

      <div className="header-actions">
        <a
          className="support-link"
          href={`https://wa.me/${whatsappNumber}`}
          target="_blank"
          rel="noreferrer"
        >
          <MessageCircle size={16} aria-hidden="true" />
          <span>Aide</span>
        </a>

        <button type="button" className="cart-button" onClick={onOpenCart}>
          <ShoppingCart size={17} aria-hidden="true" />
          <span className="cart-button-copy">
            {cartCount ? money(cartTotalMillimes) : "Panier"}
          </span>
          {/* Remounting on every change replays the badge's pop animation. */}
          {cartCount ? (
            <b key={cartCount} aria-label={`${cartCount} articles dans le panier`}>
              {cartCount}
            </b>
          ) : null}
        </button>

        <button
          type="button"
          className="icon-button menu-toggle"
          onClick={() => setMenuOpen((value) => !value)}
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
        >
          {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
