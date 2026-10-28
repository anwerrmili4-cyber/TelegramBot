export function Button({ variant = "primary", type = "button", busy = false, className = "", children, ...props }) {
  return (
    <button
      {...props}
      type={type}
      className={`shell-button shell-button-${variant}${className ? ` ${className}` : ""}`}
      disabled={busy || props.disabled}
    >
      {children}
    </button>
  );
}
