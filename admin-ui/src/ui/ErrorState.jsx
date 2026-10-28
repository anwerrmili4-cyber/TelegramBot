import { AlertTriangle } from "lucide-react";
import { Button } from "./Button.jsx";
import { SHELL_MESSAGES } from "./messages.js";

export function ErrorState({ title = "Impossible de charger le tableau de bord", message, onRetry }) {
  return (
    <div className="shell-error" role="alert">
      <AlertTriangle size={28} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{message}</p>
      {onRetry ? <Button onClick={onRetry}>{SHELL_MESSAGES.retry}</Button> : null}
    </div>
  );
}
