import { useEffect, useState, type MouseEvent } from "react";
import { Heart } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { fetchFavorites, setFavorite, errorMessage } from "@/lib/api";
import { navigate, productPath, ROUTES, withNext } from "@/lib/router";

const savedIds = new Map<string, Set<number>>();
const inflight = new Map<string, Promise<void>>();
/** Latest tap, kept until the server agrees, so a slow reply cannot undo it. */
const pending = new Map<string, Map<number, boolean>>();
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

function loadFavorites(token: string) {
  const current = inflight.get(token);
  if (current) return current;
  const request = fetchFavorites(token)
    .then((result) => {
      const ids = new Set(result.favorites.map((item) => item.offer_id));
      for (const [offerId, saved] of pending.get(token) ?? []) {
        if (saved) ids.add(offerId);
        else ids.delete(offerId);
      }
      savedIds.set(token, ids);
      notify();
    })
    .catch(() => undefined)
    .finally(() => {
      inflight.delete(token);
    });
  inflight.set(token, request);
  return request;
}

export function noteFavorite(token: string, offerId: number, saved: boolean) {
  remember(token, offerId, saved);
}

function remember(token: string, offerId: number, saved: boolean) {
  const ids = new Set(savedIds.get(token) ?? []);
  if (saved) ids.add(offerId);
  else ids.delete(offerId);
  savedIds.set(token, ids);
  notify();
}

type FavoriteButtonProps = {
  offerId: number;
  compact?: boolean;
  /** Heart only. The accessible name stays on the button. */
  icon?: boolean;
};

export function FavoriteButton({ offerId, compact = false, icon = false }: FavoriteButtonProps) {
  const { customer, token } = useAuth();
  const [, refresh] = useState(0);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [pop, setPop] = useState(false);
  const saved = Boolean(token && savedIds.get(token)?.has(offerId));

  useEffect(() => {
    const listener = () => refresh((value) => value + 1);
    listeners.add(listener);
    if (token) void loadFavorites(token);
    return () => {
      listeners.delete(listener);
    };
  }, [token]);

  async function toggle(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (!token || !customer) {
      navigate(withNext(ROUTES.login, productPath(offerId)));
      return;
    }
    const next = !saved;
    const taps = pending.get(token) ?? new Map<number, boolean>();
    taps.set(offerId, next);
    pending.set(token, taps);
    remember(token, offerId, next);
    setPop(next);
    setError("");
    setNote("");
    if (!compact) {
      setNote(next ? "Ajouté à tes favoris." : "Retiré de tes favoris.");
    }
    try {
      const result = await setFavorite(token, offerId, next);
      if (taps.get(offerId) !== next) return;
      taps.delete(offerId);
      remember(token, offerId, result.saved);
    } catch (reason) {
      if (taps.get(offerId) !== next) return;
      taps.delete(offerId);
      remember(token, offerId, !next);
      setPop(false);
      setNote("");
      setError(errorMessage(reason, "Le favori n'a pas pu être enregistré."));
    }
  }

  const label = saved ? "Retirer des favoris" : "Ajouter aux favoris";
  const heartClass = ["fav-heart", saved ? "is-saved" : "", pop ? "is-pop" : ""].filter(Boolean).join(" ");

  if (compact) {
    return (
      <button
        type="button"
        className={heartClass}
        aria-pressed={saved}
        aria-label={label}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => void toggle(event)}
        onAnimationEnd={() => setPop(false)}
      >
        <Heart size={16} aria-hidden="true" fill={saved ? "currentColor" : "none"} />
        {icon ? null : <span>{saved ? "Favori" : "J'aime"}</span>}
      </button>
    );
  }

  return (
    <div className="favorite-row">
      <button
        type="button"
        className={saved ? "button button-ghost favorite-button is-saved" : "button button-ghost favorite-button"}
        aria-pressed={saved}
        onClick={(event) => void toggle(event)}
      >
        <Heart className={pop ? "is-pop" : undefined} size={16} aria-hidden="true" fill={saved ? "currentColor" : "none"} />
        {saved ? "Dans tes favoris" : "J'aime"}
      </button>
      {note ? <p className="favorite-note" role="status">{note}</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
