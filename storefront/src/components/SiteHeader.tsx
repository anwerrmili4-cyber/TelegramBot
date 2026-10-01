import { useEffect, useState, type FormEvent } from "react";
import { ChevronDown, LifeBuoy, List, Megaphone, Menu, MessageCircle, Search, ShoppingCart, X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { money } from "@/lib/format";
import { Link, navigate, ROUTES, usePathname } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

type SiteHeaderProps = {
  cartCount: number;
  cartTotalMillimes: number;
  categories: { id: string; label: string; count: number }[];
  onOpenCart: () => void;
};

const BEFORE = [
  { to: ROUTES.home, label: "Accueil" },
  { to: ROUTES.shop, label: "Boutique" },
];

const AFTER = [{ to: ROUTES.deals, label: "Offres" }];

const MORE = [
  { to: ROUTES.news, label: "Annonces", icon: Megaphone },
  { to: ROUTES.prices, label: "Liste des prix", icon: List },
  { to: ROUTES.help, label: "Support", icon: LifeBuoy },
  { to: ROUTES.messenger, label: "Messagerie", icon: MessageCircle },
];

export function SiteHeader({ cartCount, cartTotalMillimes, categories, onOpenCart }: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [catsOpen, setCatsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const { customer, loading } = useAuth();
  const path = usePathname();
  const firstName = customer?.name.split(" ")[0] ?? "";
  const moreCurrent = MORE.some((item) => item.to === path) || path === "/aide";
  const catsCurrent = path === ROUTES.categories;

  function closeMenus() {
    setMenuOpen(false);
    setMoreOpen(false);
    setCatsOpen(false);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const term = query.trim();
    closeMenus();
    navigate(`${ROUTES.shop}${term ? `?q=${encodeURIComponent(term)}` : ""}#catalogue`);
  }

  useEffect(() => {
    if (!menuOpen && !moreOpen && !catsOpen) return;
    const close = () => {
      setMenuOpen(false);
      setMoreOpen(false);
      setCatsOpen(false);
    };
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [menuOpen, moreOpen, catsOpen]);

  useEffect(() => {
    if (!moreOpen && !catsOpen) return;
    const close = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest(".site-header")) {
        setMoreOpen(false);
        setCatsOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMoreOpen(false);
        setCatsOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [moreOpen, catsOpen]);

  return (
    <header className="site-header">
      <Link className="brand" to={ROUTES.home} onClick={closeMenus}>
        <img src="/logo.png" alt="" width="40" height="40" />
        <strong>BlackMarket</strong>
      </Link>

      <nav className={menuOpen ? "site-nav open" : "site-nav"} aria-label="Navigation principale">
        {BEFORE.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            aria-current={path === item.to ? "page" : undefined}
            onClick={closeMenus}
          >
            {item.label}
          </Link>
        ))}
        <div className={catsOpen ? "nav-more nav-cat open" : "nav-more nav-cat"}>
          <button
            type="button"
            aria-expanded={catsOpen}
            aria-haspopup="true"
            aria-current={catsCurrent ? "page" : undefined}
            onClick={() => {
              setCatsOpen((value) => !value);
              setMoreOpen(false);
            }}
          >
            Catégories <ChevronDown size={14} aria-hidden="true" />
          </button>
          {catsOpen ? (
            <div className="nav-more-panel nav-cat-panel" role="menu">
              {categories.map((category) => (
                <Link
                  key={category.id}
                  to={`${ROUTES.shop}?categorie=${encodeURIComponent(category.id)}#catalogue`}
                  role="menuitem"
                  onClick={closeMenus}
                >
                  {category.label}
                  <small>{category.count}</small>
                </Link>
              ))}
              <Link to={ROUTES.categories} role="menuitem" onClick={closeMenus}>
                Toutes les catégories
              </Link>
            </div>
          ) : null}
        </div>
        {AFTER.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            aria-current={path === item.to ? "page" : undefined}
            onClick={closeMenus}
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
            onClick={() => {
              setMoreOpen((value) => !value);
              setCatsOpen(false);
            }}
          >
            Plus <ChevronDown size={14} aria-hidden="true" />
          </button>
          {moreOpen ? (
            <div className="nav-more-panel" role="menu">
              {MORE.map((item) => {
                const Icon = item.icon;
                return (
                  <Link key={item.to} to={item.to} role="menuitem" onClick={closeMenus}>
                    <Icon size={16} aria-hidden="true" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ) : null}
        </div>
      </nav>

      <form className="header-search" onSubmit={submitSearch}>
        <Search size={16} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Rechercher"
          aria-label="Rechercher un produit"
        />
      </form>

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
