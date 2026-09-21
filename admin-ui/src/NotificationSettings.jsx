import { useEffect, useState } from "react";
import { BellRing, Settings2 } from "lucide-react";

export const NOTIFICATION_CATEGORIES = {
  order: "Commandes", sale: "Ventes", deposit: "Dépôts", support: "Support",
  withdrawal: "Retraits", warranty: "Garanties", stock: "Stock", system: "Système",
};

export async function notificationAction(token, payload) {
  const response = await fetch("/admin/api/notifications", {
    method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Dashboard-Write-Token": token || "" },
    body: JSON.stringify(payload), signal: AbortSignal.timeout(20_000),
  });
  if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Impossible d’enregistrer les notifications.");
  return result;
}

const defaults = { categories: Object.keys(NOTIFICATION_CATEGORIES), urgent_only: false, private: true, pause_minutes: 0 };
const supported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export default function NotificationSettings({ token }) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [preferences, setPreferences] = useState(defaults);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!supported()) { setReady(true); return; }
      try {
        const registration = await navigator.serviceWorker.getRegistration("/admin");
        const subscription = await registration?.pushManager.getSubscription();
        if (!subscription || cancelled) return;
        const result = await notificationAction(token, { action: "status", subscription });
        if (cancelled) return;
        setEnabled(result.enabled && Notification.permission === "granted");
        if (result.enabled) setPreferences({ ...defaults, ...result.preferences });
      } catch (err) { if (!cancelled) setError(err.message); }
      finally { if (!cancelled) setReady(true); }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const run = async (action) => {
    setBusy(true); setError(""); setMessage("");
    try {
      // Request permission directly from the click, before any network await (iOS).
      if (action === "subscribe" && Notification.permission !== "granted") {
        const permission = await Notification.requestPermission();
        if (permission !== "granted") throw new Error("Notifications bloquées. Autorisez-les dans les réglages de ce site, puis réessayez.");
      }
      let registration = await navigator.serviceWorker.getRegistration("/admin");
      if (!registration) registration = await navigator.serviceWorker.register("/admin/notification-sw.js", { scope: "/admin" });
      if (!registration.active) {
        const worker = registration.installing || registration.waiting;
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("Activation du service de notifications trop longue. Réessayez.")), 15000);
          const changed = () => {
            if (worker.state === "activated") { clearTimeout(timeout); resolve(); }
            if (worker.state === "redundant") { clearTimeout(timeout); reject(new Error("Le service de notifications n’a pas pu démarrer.")); }
          };
          worker.addEventListener("statechange", changed); changed();
        });
      }
      let subscription = await registration.pushManager.getSubscription();
      let created = false;
      if (action === "subscribe" && !subscription) {
        const response = await fetch("/admin/api/notifications/config", { cache: "no-store", signal: AbortSignal.timeout(15000) });
        const config = await response.json();
        if (!response.ok || !config.available) throw new Error(config.message || "Le service push est indisponible.");
        const key = config.public_key.replace(/-/g, "+").replace(/_/g, "/");
        const bytes = Uint8Array.from(atob(key + "=".repeat((4 - key.length % 4) % 4)), (char) => char.charCodeAt(0));
        subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes });
        created = true;
      }
      if (!subscription) throw new Error("Activez les notifications sur cet appareil.");
      let result;
      try { result = await notificationAction(token, { action, subscription, preferences }); }
      catch (err) { if (created) await subscription.unsubscribe(); throw err; }
      if (action === "disable") { await subscription.unsubscribe(); setEnabled(false); }
      if (action === "subscribe") { setEnabled(true); setPreferences({ ...defaults, ...result.preferences }); }
      setMessage(result.message || (action === "disable" ? "Notifications désactivées sur cet appareil." : "Préférences enregistrées pour cet appareil."));
    } catch (err) { setError(err.message || "Échec de l’activation. Réessayez."); }
    finally { setBusy(false); }
  };

  return <section className="push-settings">
    <button className="push-settings-toggle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
      <BellRing size={18} /><span><strong>Notifications sur cet appareil</strong><small>{!ready ? "Vérification…" : enabled ? "Push activé · même en arrière-plan" : "Recevez les alertes sur téléphone et PC"}</small></span><Settings2 size={17} />
    </button>
    {expanded && <div className="push-settings-body">
      {!supported() ? <p>Utilisez un navigateur compatible en HTTPS. Sur iPhone/iPad (iOS 16.4+), ajoutez ce site à l’écran d’accueil depuis Safari, puis ouvrez-le depuis son icône.</p> : <>
        <p>Activez chaque appareil séparément. Les notifications lues sont synchronisées entre vos appareils.</p>
        <fieldset disabled={busy || !ready}><legend>Événements à recevoir</legend><div className="push-categories">{Object.entries(NOTIFICATION_CATEGORIES).map(([id, label]) => <label key={id}><input type="checkbox" checked={preferences.categories.includes(id)} onChange={(event) => setPreferences((old) => ({ ...old, categories: event.target.checked ? [...old.categories, id] : old.categories.filter((c) => c !== id) }))} />{label}</label>)}</div>
          <label><input type="checkbox" checked={preferences.urgent_only} onChange={(event) => setPreferences({ ...preferences, urgent_only: event.target.checked })} />Uniquement les alertes critiques</label>
          <label><input type="checkbox" checked={preferences.private} onChange={(event) => setPreferences({ ...preferences, private: event.target.checked })} />Masquer les détails sur l’écran verrouillé</label>
          <label>Pause<select value={preferences.pause_minutes} onChange={(event) => setPreferences({ ...preferences, pause_minutes: Number(event.target.value) })}><option value={0}>Recevoir les notifications</option><option value={60}>1 heure</option><option value={480}>8 heures</option><option value={1440}>24 heures</option></select></label>
          {preferences.paused_until > Date.now() / 1000 && <p>En pause jusqu’au {new Date(preferences.paused_until * 1000).toLocaleString("fr-FR")}.</p>}
        </fieldset>
        <div className="push-actions"><button disabled={busy || !ready} onClick={() => run("subscribe")}>{busy ? "En cours…" : enabled ? "Enregistrer / reprendre" : "Activer sur cet appareil"}</button>{enabled && <><button disabled={busy} onClick={() => run("test")}>Envoyer un test</button><button disabled={busy} onClick={() => run("disable")}>Désactiver</button></>}</div>
        <small>Sur iPhone/iPad : ouvrez le site ajouté à l’écran d’accueil. Le mode Ne pas déranger et les réglages du système peuvent masquer les alertes.</small>
      </>}
    </div>}
    {error && <p className="push-error" role="alert">{error}</p>}
    {message && <p className="push-success" role="status">{message}</p>}
  </section>;
}
