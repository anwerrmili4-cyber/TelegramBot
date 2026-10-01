import { useEffect, useState } from "react";
import { ChevronDown, LifeBuoy, List, Megaphone, Menu, MessageCircle, ShoppingCart, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { money } from "@/lib/format";
import { Link, ROUTES, usePathname } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

type SiteHeaderProps = {
  cartCount: number;
  cartTotalMillimes: number;
  onOpenCart: () => void;
};

const LINKS = [
  { to: ROUTES.home, label: "Accueil" },
  { to: ROUTES.shop, label: "Boutique" },
  { to: ROUTES.categories, label: "Catégories" },
  { to: ROUTES.deals, label: "Offres" },
];

const MORE = [
  { to: ROUTES.news, label: "Annonces", icon: Megaphone },
  { to: ROUTES.prices, label: "Liste des prix", icon: List },
  { to: ROUTES.help, label: "Support", icon: LifeBuoy },
  { to: ROUTES.messenger, label: "Messagerie", icon: MessageCircle },
];

export function SiteHeader({ cartCount, cartTotalMillimes, onOpenCart }: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const { customer, loading } = useAuth();
  const path = usePathname();
  const firstName = customer?.name.split(" ")[0] ?? "";
  const moreCurrent = MORE.some((item) => item.to === path) || path === "/aide";

  useEffect(() => {
    if (!menuOpen && !moreOpen) return;
    const close = () => {
      setMenuOpen(false);
      setMoreOpen(false);
    };
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [menuOpen, moreOpen]);

  useEffect(() => {
    if (!moreOpen) return;
    const close = (event: MouseEvent) => {
      if (!(event.target instanceof Node)) return;
      if (!(event.target as Element).closest?.(".nav-more")) setMoreOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [moreOpen]);

  return (
    <header className="site-header">
      <Link className="brand" to={ROUTES.home} onClick={() => setMenuOpen(false)}>
        <img src="/logo.png" alt="" width="40" height="40" />
        <strong>BlackMarket</strong>
      </Link>

      <nav className={menuOpen ? "site-nav open" : "site-nav"} aria-label="Navigation principale">
        {LINKS.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            aria-current={path === item.to ? "page" : undefined}
            onClick={() => setMenuOpen(false)}
          >
            {item.label}
          </Link>
        ))}
        <div className={moreOpen ? "nav-more open" : "nav-more"}>
          <button
            type="button"
            aria-expanded={moreOpen}
            aria-haspopup="true"
            aria-current={moreCurrent ? "page" : undefined}
            onClick={() => setMoreOpen((value) => !value)}
          >
            Plus <ChevronDown size={14} aria-hidden="true" />
          </button>
          {moreOpen ? (
            <div className="nav-more-panel" role="menu">
              {MORE.map((item) => {
                const Icon = item.icon;
                return (
                  <Link key={item.to} to={item.to} role="menuitem" onClick={() => { setMoreOpen(false); setMenuOpen(false); }}>
                    <Icon size={16} aria-hidden="true" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ) : null}
        </div>
      </nav>

      <div className="header-actions">
        {customer ? (
          <Link className="account-link" to={accountPath("commandes")} title={customer.email}>
            <span>{firstName}</span>
          </Link>
        ) : loading ? null : (
          <>
            <Link className="button button-ghost" to={ROUTES.login}>
              Connexion
            </Link>
            <Link className="button button-primary header-signup" to={ROUTES.register}>
              Inscription
            </Link>
          </>
        )}

        <button type="button" className="cart-button" onClick={onOpenCart}>
          <ShoppingCart size={17} aria-hidden="true" />
          <span className="cart-button-copy">{cartCount ? money(cartTotalMillimes) : "Panier"}</span>
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
