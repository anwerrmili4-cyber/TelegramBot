import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { createPortal } from "react-dom";
import {
  ChevronDown,
  Headset,
  Heart,
  Home,
  LayoutGrid,
  LifeBuoy,
  List,
  LogIn,
  Megaphone,
  Menu,
  MessageCircle,
  Moon,
  Percent,
  Search,
  ShoppingBag,
  ShoppingCart,
  Sun,
  X,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { money } from "@/lib/format";
import { toggleTheme, useTheme } from "@/lib/theme";
import { Link, navigate, ROUTES, usePathname } from "@/lib/router";
import { placeSlidingPill } from "@/lib/slidingPill";
import { accountPath } from "@/lib/accountPath";
import { NotificationBell } from "@/components/NotificationBell";

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

function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener("storefront:navigate", onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener("storefront:navigate", onChange);
  };
}

const MORE = [
  { to: ROUTES.news, label: "Annonces", icon: Megaphone },
  { to: ROUTES.prices, label: "Liste des prix", icon: List },
  { to: ROUTES.help, label: "Support", icon: LifeBuoy },
  { to: ROUTES.messenger, label: "Messagerie", icon: MessageCircle },
];

const PHONE_SHOP = [
  { to: ROUTES.home, label: "Accueil", icon: Home },
  { to: ROUTES.shop, label: "Boutique", icon: ShoppingBag },
  { to: ROUTES.categories, label: "Catégories", icon: LayoutGrid },
  { to: ROUTES.deals, label: "Offres", icon: Percent },
  { to: ROUTES.prices, label: "Liste des prix", icon: List },
  { to: ROUTES.news, label: "Annonces", icon: Megaphone },
  { to: accountPath("favoris"), label: "Favoris", icon: Heart },
];

const PHONE_HELP = [
  { to: ROUTES.help, label: "Support", icon: Headset },
  { to: ROUTES.messenger, label: "Messagerie", icon: MessageCircle },
];

export function SiteHeader({ cartCount, cartTotalMillimes, categories, onOpenCart }: SiteHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [catsOpen, setCatsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navRef = useRef<HTMLElement>(null);
  const { customer, loading } = useAuth();
  const theme = useTheme();
  const path = usePathname();
  const search = useSyncExternalStore(subscribeLocation, () => window.location.search);
  const favoritesOn = path === ROUTES.account && new URLSearchParams(search).get("onglet") === "favoris";
  const firstName = customer?.name.split(" ")[0] ?? "";
  const moreCurrent = MORE.some((item) => item.to === path) || path === "/aide";
  const catsCurrent = path === ROUTES.categories;

  function pillOn(kind: "home" | "shop" | "cats" | "deals" | "fav" | "more") {
    if (favoritesOn) return kind === "fav";
    if (catsOpen) return kind === "cats";
    if (moreOpen) return kind === "more";
    if (kind === "home") return path === ROUTES.home;
    if (kind === "shop") return path === ROUTES.shop;
    if (kind === "deals") return path === ROUTES.deals;
    if (kind === "cats") return catsCurrent;
    return moreCurrent;
  }

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const place = () => {
      placeSlidingPill(nav, nav.querySelector<HTMLElement>("[data-pill-target]"));
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(nav);
    for (const control of nav.querySelectorAll<HTMLElement>(":scope > a, :scope > .nav-more > button")) {
      observer.observe(control);
    }
    return () => observer.disconnect();
  }, [path, catsOpen, moreOpen, favoritesOn]);

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
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

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

  const phoneMenu = menuOpen
    ? createPortal(
        <div className="phone-menu" onClick={closeMenus}>
          <div
            className="phone-menu-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="phone-menu-head">
              <Link className="phone-menu-brand" to={ROUTES.home} onClick={closeMenus}>
                <img src="/logo.png" alt="" width="28" height="28" />
                <strong>BlackMarket</strong>
              </Link>
              <button type="button" className="phone-menu-close" onClick={closeMenus} aria-label="Fermer le menu">
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <form className="phone-menu-search" onSubmit={submitSearch}>
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Rechercher un produit"
                aria-label="Rechercher un produit"
              />
            </form>

            <div className="phone-menu-scroll">
              <p>Boutique</p>
              <nav aria-label="Boutique">
                {PHONE_SHOP.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      aria-current={path === item.to ? "page" : undefined}
                      onClick={closeMenus}
                    >
                      <Icon size={18} aria-hidden="true" />
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
              <p>Aide</p>
              <nav aria-label="Aide">
                {PHONE_HELP.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      aria-current={path === item.to ? "page" : undefined}
                      onClick={closeMenus}
                    >
                      <Icon size={18} aria-hidden="true" />
                      {item.label}
                    </Link>
                  );
                })}
                <button type="button" onClick={toggleTheme}>
                  {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
                  {theme === "dark" ? "Thème clair" : "Thème sombre"}
                </button>
              </nav>
            </div>

            <div className="phone-menu-foot">
              {customer ? (
                <Link className="button button-primary" to={accountPath("profil")} onClick={closeMenus}>
                  Mon compte
                </Link>
              ) : (
                <>
                  <Link className="button button-ghost" to={ROUTES.login} onClick={closeMenus}>
                    Connexion
                  </Link>
                  <Link className="button button-primary" to={ROUTES.register} onClick={closeMenus}>
                    Inscription
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
    <header className="site-header">
      <Link className="brand" to={ROUTES.home} onClick={closeMenus}>
        <img src="/logo.png" alt="" width="40" height="40" />
        <strong>BlackMarket</strong>
      </Link>

      <nav className="site-nav" aria-label="Navigation principale" ref={navRef}>
        <span className="site-nav-pill" aria-hidden="true" />
        {BEFORE.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            aria-current={path === item.to ? "page" : undefined}
            data-pill-target={pillOn(item.to === ROUTES.home ? "home" : "shop") ? "true" : undefined}
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
            data-pill-target={pillOn("cats") ? "true" : undefined}
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
            data-pill-target={pillOn("deals") ? "true" : undefined}
            onClick={closeMenus}
          >
            {item.label}
          </Link>
        ))}
        <Link
          to={accountPath("favoris")}
          aria-current={favoritesOn ? "page" : undefined}
          data-pill-target={pillOn("fav") ? "true" : undefined}
          onClick={closeMenus}
        >
          Favoris
        </Link>
        <div className={moreOpen ? "nav-more open" : "nav-more"}>
          <button
            type="button"
            aria-expanded={moreOpen}
            aria-haspopup="true"
            aria-current={moreCurrent ? "page" : undefined}
            data-pill-target={pillOn("more") ? "true" : undefined}
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
            <span className="account-mark" aria-hidden="true">{(firstName || "B").slice(0, 1)}</span>
            <span className="account-name">{firstName}</span>
          </Link>
        ) : loading ? null : (
          <>
            <Link className="button button-ghost header-login" to={ROUTES.login}>
              <LogIn size={16} aria-hidden="true" />
              <span>Connexion</span>
            </Link>
            <Link className="button button-primary header-signup" to={ROUTES.register}>
              Inscription
            </Link>
          </>
        )}

        <NotificationBell />

        <button
          type="button"
          className="icon-button theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Passer au thème clair" : "Passer au thème sombre"}
        >
          {theme === "dark" ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
        </button>

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
    {phoneMenu}
    </>
  );
}
