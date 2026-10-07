import { lazy, Suspense } from "react";

const RELOAD_KEY = "admin-chunk-reload";

// After a deploy the previous hashed chunks are gone; reload once to fetch the new build.
export function lazyPage(loader) {
  return lazy(() => loader().then(
    (module) => {
      window.sessionStorage?.removeItem(RELOAD_KEY);
      return module;
    },
    (error) => {
      if (!window.sessionStorage?.getItem(RELOAD_KEY)) {
        window.sessionStorage?.setItem(RELOAD_KEY, "1");
        window.location.reload();
        return new Promise(() => {});
      }
      throw error;
    },
  ));
}

export function PageSuspense({ children }) {
  return (
    <Suspense fallback={<div className="page-loading" role="status" aria-live="polite">Chargement…</div>}>
      {children}
    </Suspense>
  );
}
