import { useEffect, useRef, useState } from "react";
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
const WORKER_URL = "/admin/notification-sw.js?v=3";
const supported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && "showNotification" in ServiceWorkerRegistration.prototype;
const isAppleMobile = () => /iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
const decodeApplicationKey = (value) => {
  const key = value.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(key + "=".repeat((4 - key.length % 4) % 4)), (char) => char.charCodeAt(0));
};

export default function NotificationSettings({ token }) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [preferences, setPreferences] = useState(defaults);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState({});
  const registrationRef = useRef(null);
  const subscriptionRef = useRef(null);
  const applicationKeyRef = useRef(null);
  const needsAppleInstall = isAppleMobile() && !isStandalone();
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!supported() || needsAppleInstall) { setReady(true); return; }
      try {
        if ("clearAppBadge" in navigator) navigator.clearAppBadge().catch(() => {});
        const [registered, response] = await Promise.all([
          navigator.serviceWorker.register(WORKER_URL, { scope: "/admin", updateViaCache: "none" }),
          fetch("/admin/api/notifications/config", { credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(15_000) }),
        ]);
        const config = await response.json();
        if (!response.ok || !config.available) throw new Error(config.message || "Le service push est indisponible.");
        const registration = registered.active ? registered : await navigator.serviceWorker.ready;
        registrationRef.current = registration;
        applicationKeyRef.current = decodeApplicationKey(config.public_key);
        const subscription = await registration.pushManager.getSubscription();
        subscriptionRef.current = subscription;
        if (!subscription || cancelled) return;
        const result = await notificationAction(token, { action: "status", subscription, app_origin: window.location.origin });
        if (cancelled) return;
        setEnabled(result.enabled && Notification.permission === "granted");
        if (result.enabled) setPreferences({ ...defaults, ...result.preferences });
        setDiagnostics(result.diagnostics || {});
      } catch (err) { if (!cancelled) setError(err.message); }
      finally { if (!cancelled) setReady(true); }
    })();
    return () => { cancelled = true; };
  }, [needsAppleInstall, token]);

  const run = async (action) => {
    setBusy(true); setError(""); setMessage("");
    try {
      const registration = registrationRef.current;
      if (!registration || !applicationKeyRef.current) throw new Error("Le service de notifications se prépare encore. Fermez puis rouvrez ce panneau.");
      let subscription = subscriptionRef.current;
      let created = false;
      if (action === "subscribe" && !subscription) {
        // On iOS this must be the first awaited browser call from the user's tap.
        subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationKeyRef.current });
        subscriptionRef.current = subscription;
        created = true;
      }
      if (!subscription) throw new Error("Activez les notifications sur cet appareil.");
      let result;
      try { result = await notificationAction(token, { action, subscription, preferences, app_origin: window.location.origin }); }
      catch (err) { if (created) await subscription.unsubscribe(); throw err; }
      if (action === "disable") { await subscription.unsubscribe(); subscriptionRef.current = null; setEnabled(false); setDiagnostics({}); }
      if (action === "subscribe") { setEnabled(true); setPreferences({ ...defaults, ...result.preferences }); }
      if (result.diagnostics) setDiagnostics(result.diagnostics);
      setMessage(result.message || (action === "disable" ? "Notifications désactivées sur cet appareil." : "Préférences enregistrées pour cet appareil."));
    } catch (err) {
      const blocked = err?.name === "NotAllowedError" || Notification.permission === "denied";
      setError(blocked ? "Autorisation refusée. Sur iPhone, ouvrez Réglages → Notifications → Black Market, autorisez les notifications, puis réessayez depuis l’icône de l’écran d’accueil." : err.message || "Échec de l’activation. Réessayez.");
    }
    finally { setBusy(false); }
  };

  return <section className="push-settings">
    <button className="push-settings-toggle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
      <BellRing size={18} /><span><strong>Notifications sur cet appareil</strong><small>{!ready ? "Vérification…" : enabled ? "Push activé · même en arrière-plan" : "Recevez les alertes sur téléphone et PC"}</small></span><Settings2 size={17} />
    </button>
    {expanded && <div className="push-settings-body">
      {needsAppleInstall ? <div className="push-install-help"><strong>Étape obligatoire sur iPhone/iPad</strong><p>Ouvrez ce site dans Safari, touchez Partager → Ajouter à l’écran d’accueil, puis lancez Black Market depuis sa nouvelle icône. Les notifications en arrière-plan ne fonctionnent pas dans un onglet Safari.</p></div> : !supported() ? <p>Utilisez un navigateur compatible en HTTPS. Sur iPhone/iPad, les notifications nécessitent iOS 16.4 ou une version ultérieure.</p> : <>
        <p>Activez chaque appareil séparément. Les notifications lues sont synchronisées entre vos appareils.</p>
        <fieldset disabled={busy || !ready}><legend>Événements à recevoir</legend><div className="push-categories">{Object.entries(NOTIFICATION_CATEGORIES).map(([id, label]) => <label key={id}><input type="checkbox" checked={preferences.categories.includes(id)} onChange={(event) => setPreferences((old) => ({ ...old, categories: event.target.checked ? [...old.categories, id] : old.categories.filter((c) => c !== id) }))} />{label}</label>)}</div>
          <label><input type="checkbox" checked={preferences.urgent_only} onChange={(event) => setPreferences({ ...preferences, urgent_only: event.target.checked })} />Uniquement les alertes critiques</label>
          <label><input type="checkbox" checked={preferences.private} onChange={(event) => setPreferences({ ...preferences, private: event.target.checked })} />Masquer les détails sur l’écran verrouillé</label>
          <label>Pause<select value={preferences.pause_minutes} onChange={(event) => setPreferences({ ...preferences, pause_minutes: Number(event.target.value) })}><option value={0}>Recevoir les notifications</option><option value={60}>1 heure</option><option value={480}>8 heures</option><option value={1440}>24 heures</option></select></label>
          {preferences.paused_until > Date.now() / 1000 && <p>En pause jusqu’au {new Date(preferences.paused_until * 1000).toLocaleString("fr-FR")}.</p>}
        </fieldset>
        <div className="push-actions"><button disabled={busy || !ready} onClick={() => run("subscribe")}>{busy ? "En cours…" : enabled ? "Enregistrer / reprendre" : "Activer sur cet appareil"}</button>{enabled && <><button disabled={busy} onClick={() => run("test")}>Envoyer un test</button><button disabled={busy} onClick={() => run("disable")}>Désactiver</button></>}</div>
        {enabled && <div className="push-diagnostics"><strong>État de cet appareil</strong><span><i className="ok" />Abonnement actif via {diagnostics.provider || "Web Push"}</span><span>{diagnostics.last_sent_at ? `Dernier envoi accepté : ${new Date(diagnostics.last_sent_at * 1000).toLocaleString("fr-FR")}` : "Aucun test envoyé depuis l’activation."}</span>{diagnostics.last_error_at && <span className="error">Dernier échec : {diagnostics.last_error_status || "inconnu"} · {new Date(diagnostics.last_error_at * 1000).toLocaleString("fr-FR")}</span>}</div>}
        <small>Sur iPhone/iPad : ouvrez l’app depuis l’écran d’accueil, envoyez un test, puis verrouillez l’écran. Le mode Concentration et Réglages → Notifications → Black Market peuvent masquer les alertes.</small>
      </>}
    </div>}
    {error && <p className="push-error" role="alert">{error}</p>}
    {message && <p className="push-success" role="status">{message}</p>}
  </section>;
}
