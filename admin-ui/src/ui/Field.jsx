export function Field({ id, label, hint, error, children }) {
  return (
    <div className={`shell-field${error ? " has-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error ? <p id={`${id}-error`} className="shell-field-error" role="alert">{error}</p> : null}
      {hint && !error ? <p className="shell-field-hint">{hint}</p> : null}
    </div>
  );
}
