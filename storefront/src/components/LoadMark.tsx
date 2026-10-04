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
    <div className="loading-page" role="status" aria-live="polite">
      <div className="loading-page-card">
        <img src="/logo.png" alt="" width="88" height="88" />
        <LoadMark />
        <strong>BLACKMARKET</strong>
        <span>Tunisie</span>
      </div>
    </div>
  );
}
