import { SHELL_MESSAGES } from "./messages.js";

export function Empty({ title = SHELL_MESSAGES.empty, detail, children }) {
  return (
    <div className="shell-empty">
      <strong>{title}</strong>
      {detail ? <p>{detail}</p> : null}
      {children}
    </div>
  );
}
