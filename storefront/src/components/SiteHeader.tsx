import { useEffect, useState } from "react";
import { Menu, ShoppingCart, UserRound, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { money } from "@/lib/format";
import { Link, ROUTES } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

type SiteHeaderProps = {
  cartCount: number;
  cartTotalMillimes: number;
  onOpenCart: () => void;
};

export function SiteHeader({ cartCount, cartTotalMillimes, onOpenCart }: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { customer, loading } = useAuth();
  const firstName = customer?.name.split(" ")[0] ?? "";

  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [menuOpen]);

  return (
    <header className="site-header">
      <Link className="brand" to={ROUTES.home}>
        <img src="/logo.png" alt="" width="40" height="40" />
        <div>
          <strong>BLACKMARKET</strong>
          <small>Tunisie</small>
        </div>
      </Link>

      <nav className={menuOpen ? "site-nav open" : "site-nav"} aria-label="Navigation principale">
        <Link to="/#catalogue" onClick={() => setMenuOpen(false)}>
          Catalogue
        </Link>
        <Link to="/#fonctionnement" onClick={() => setMenuOpen(false)}>
          Comment ça marche
        </Link>
        {customer ? (
          <>
            <Link to={accountPath("commandes")} onClick={() => setMenuOpen(false)}>
              Mes achats
            </Link>
            <Link to={accountPath("portefeuille")} onClick={() => setMenuOpen(false)}>
              Portefeuille
            </Link>
          </>
        ) : null}
      </nav>

      <div className="header-actions">
        {customer ? (
          <Link className="account-link" to={accountPath("commandes")} title={customer.email}>
            <UserRound size={16} aria-hidden="true" />
            <span>{firstName}</span>
          </Link>
        ) : loading ? null : (
          <Link className="account-link" to={ROUTES.login} aria-label="Connexion">
            <UserRound size={16} aria-hidden="true" />
            <span>Connexion</span>
          </Link>
        )}

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
