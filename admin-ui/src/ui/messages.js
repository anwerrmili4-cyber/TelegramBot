export const SHELL_MESSAGES = Object.freeze({
  empty: "Aucun élément",
  sessionExpired: "Session expirée. Reconnecte-toi.",
  network: "Connexion interrompue. Réessaie.",
  unexpected: "Une erreur inattendue est survenue.",
  retry: "Réessayer",
});

export function shellErrorMessage(error) {
  if (!error) return SHELL_MESSAGES.unexpected;
  const name = error.name || "";
  if (name === "AbortError" || name === "TimeoutError") return SHELL_MESSAGES.network;
  if (error instanceof TypeError) return SHELL_MESSAGES.network;
  const message = String(error.message || "").trim();
  if (!message || message === "Failed to fetch") return SHELL_MESSAGES.unexpected;
  return message;
}
