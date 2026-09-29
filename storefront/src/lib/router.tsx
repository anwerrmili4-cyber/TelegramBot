import { useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

export const ROUTES = {
  home: "/",
  login: "/connexion",
  register: "/inscription",
  verifyEmail: "/verifier-email",
  forgotPassword: "/mot-de-passe-oublie",
  resetPassword: "/reinitialiser-mot-de-passe",
} as const;

const NAVIGATE_EVENT = "storefront:navigate";

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
  if (!to.includes("#")) window.scrollTo({ top: 0 });
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string };

/** An anchor that changes route without reloading the page. */
export function Link({ to, onClick, ...rest }: LinkProps) {
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
    // Let the browser scroll to an anchor on the page already shown.
    if (hash !== undefined && (path || "/") === currentPath()) return;
    event.preventDefault();
    navigate(to);
    if (hash) {
      requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView());
    }
  }
  return <a href={to} onClick={handleClick} {...rest} />;
}
