/** Shown only while a route chunk or the catalog is still empty. */
export function LoadMark() {
  return (
    <div className="load-mark" role="status">
      <i aria-hidden="true" />
      <span>Chargement</span>
    </div>
  );
}
