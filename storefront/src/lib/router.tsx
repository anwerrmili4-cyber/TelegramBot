import { forwardRef, useEffect, useState, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";
import { scrollAfterNavigate, scrollToElement } from "@/components/motion/SmoothScroll";

export const ROUTES = {
  home: "/",
  login: "/connexion",
  register: "/inscription",
  verifyEmail: "/verifier-email",
  forgotPassword: "/mot-de-passe-oublie",
  resetPassword: "/reinitialiser-mot-de-passe",
  account: "/mon-compte",
  shop: "/boutique",
  categories: "/categories",
  deals: "/offres",
  prices: "/prix",
  news: "/annonces",
  help: "/support",
  terms: "/conditions",
  privacy: "/confidentialite",
  contact: "/contact",
  community: "/communaute",
  report: "/signaler",
  messenger: "/messagerie",
} as const;

export function productPath(id: number): string {
  return `/produit/${id}`;
}

export function productId(path: string): number | null {
  const match = /^\/produit\/(\d+)$/.exec(path);
  return match ? Number(match[1]) : null;
}

/** `path` with a `next` parameter to come back to after signing in. */
export function withNext(path: string, next: string): string {
  return `${path}?${new URLSearchParams({ next })}`;
}

/** The `next` parameter, only when it is a path on this site. */
export function nextPath(fallback: string = ROUTES.home): string {
  const next = new URLSearchParams(window.location.search).get("next") ?? "";
  return next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

const NAVIGATE_EVENT = "storefront:navigate";

/** Thin bar at the top of the viewport while a route change is painting. */
export function RouteProgress() {
  const [going, setGoing] = useState(false);

  useEffect(() => {
    let timer = 0;
    const start = () => {
      setGoing(false);
      requestAnimationFrame(() => {
        setGoing(true);
        window.clearTimeout(timer);
        timer = window.setTimeout(() => setGoing(false), 420);
      });
    };
    window.addEventListener(NAVIGATE_EVENT, start);
    window.addEventListener("popstate", start);
    return () => {
      window.removeEventListener(NAVIGATE_EVENT, start);
      window.removeEventListener("popstate", start);
      window.clearTimeout(timer);
    };
  }, []);

  return <div className={going ? "route-progress go" : "route-progress"} />;
}

function subscribe(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener(NAVIGATE_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAVIGATE_EVENT, onChange);
  };
}

function currentPath(): string {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, currentPath);
}

export function navigate(to: string, { replace = false } = {}) {
  if (replace) {
    window.history.replaceState(null, "", to);
  } else {
    window.history.pushState(null, "", to);
  }
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
  scrollAfterNavigate(to);
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string };

/** An anchor that changes route without reloading the page. */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link({ to, onClick, ...rest }, ref) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    const [path, hash] = to.split("#");
    // Same-page anchors go through Lenis. A native jump is overwritten while a smooth scroll is in flight.
    if (hash !== undefined && (path || "/") === currentPath()) {
      const node = document.getElementById(hash);
      if (!node) return;
      event.preventDefault();
      scrollToElement(node);
      return;
    }
    event.preventDefault();
    navigate(to);
  }
  return <a ref={ref} href={to} onClick={handleClick} {...rest} />;
});
