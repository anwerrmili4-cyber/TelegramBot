import { useSyncExternalStore } from "react";
import { Home, ReceiptText, ShoppingBag, UserRound, Wallet } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Link, ROUTES } from "@/lib/router";
import { accountPath } from "@/pages/AccountPage";

function subscribe(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener("storefront:navigate", onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener("storefront:navigate", onChange);
  };
}

function locationKey() {
  return window.location.pathname + window.location.search;
}

export function MobileTabBar() {
  const here = useSyncExternalStore(subscribe, locationKey);
  const path = here.split("?")[0].replace(/\/+$/, "") || "/";
  const tab = new URLSearchParams(here.split("?")[1] ?? "").get("onglet");
  const { customer } = useAuth();
  const orders = customer ? accountPath("commandes") : ROUTES.login;
  const wallet = customer ? accountPath("portefeuille") : ROUTES.login;
  const account = customer ? accountPath("profil") : ROUTES.login;
  const onAccount = path === ROUTES.account;

  const items = [
    { to: ROUTES.home, label: "Accueil", icon: Home, on: path === ROUTES.home },
    { to: ROUTES.shop, label: "Boutique", icon: ShoppingBag, on: path === ROUTES.shop || path.startsWith("/produit/") },
    { to: orders, label: "Commandes", icon: ReceiptText, on: onAccount && (tab === "commandes" || !tab) },
    { to: wallet, label: "Portefeuille", icon: Wallet, on: onAccount && tab === "portefeuille" },
    { to: account, label: customer ? "Compte" : "Connexion", icon: UserRound, on: path === ROUTES.login || (onAccount && tab === "profil") },
  ];

  return (
    <nav className="tabbar" aria-label="Navigation rapide">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.label} to={item.to} className={item.on ? "on" : undefined}>
            <Icon size={18} aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
