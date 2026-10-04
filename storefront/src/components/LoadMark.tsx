/** Shown only while a route chunk or the catalog is still empty. */
export function LoadMark() {
  return (
    <div className="load-mark" role="status">
      <i aria-hidden="true" />
      <span>Chargement</span>
    </div>
  );
}

/** Full-screen wait. Covers the shop until the first catalog arrives, and while a page chunk loads. */
export function LoadingPage() {
  return (
    <div className="loading-page" role="status" aria-live="polite" aria-label="Chargement">
      <i aria-hidden="true" />
    </div>
  );
}
