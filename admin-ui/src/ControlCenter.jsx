import { useEffect, useState } from "react";
import { Activity, ArrowUpRight, Boxes, ClipboardList, Database, Download, Headphones, RefreshCw, Search, ShieldCheck, Smartphone, Star, Wallet } from "lucide-react";
import { csvDocument, getAdminJson, readPreference, savePreference } from "./control-utils";

const RESOURCES = {
  orders: { label: "Commandes", path: "orders", page: "orders", columns: [["id", "Commande"], ["user_id", "Client"], ["offer_name", "Produit"], ["charged_total", "Montant"], ["status", "Statut"]], statuses: ["manual_review", "pending_payment", "preparing_delivery", "delivered", "cancelled"] },
  customers: { label: "Clients", path: "customers", page: "customers", columns: [["telegram_id", "Telegram ID"], ["username", "Utilisateur"], ["first_name", "Prénom"]], statuses: [] },
  inventory: { label: "Inventaire masqué", path: "inventory", page: "inventory", columns: [["reference_id", "Référence"], ["offer_id", "Produit"], ["masked_preview", "Aperçu masqué"], ["status", "Statut"]], statuses: ["available", "reserved", "delivered", "disabled"] },
  tickets: { label: "Tickets", path: "tickets", page: "support", columns: [["id", "Ticket"], ["user_id", "Client"], ["category", "Catégorie"], ["status", "Statut"]], statuses: ["open", "waiting_admin", "waiting_customer", "closed"] },
  deposits: { label: "Dépôts", path: "wallet-topups", page: "deposits", columns: [["id", "Dépôt"], ["user_id", "Client"], ["amount", "Montant"], ["currency", "Devise"], ["status", "Statut"]], statuses: ["manual_review", "confirmed", "rejected"] },
};
const LABELS = { manual_review: "À vérifier", pending_payment: "Paiement en attente", preparing_delivery: "Préparation", delivered: "Livrée", cancelled: "Annulée", available: "Disponible", reserved: "Réservé", disabled: "Désactivé", open: "Ouvert", waiting_admin: "Attente administrateur", waiting_customer: "Attente client", closed: "Fermé", confirmed: "Confirmé", rejected: "Refusé" };

export function useAdminResource(path) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision((n) => n + 1);
    window.addEventListener("admin:data-synced", refresh);
    return () => window.removeEventListener("admin:data-synced", refresh);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, error: "", loading: true });
    getAdminJson(path, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ data, error: "", loading: false }); })
      .catch((error) => { if (!controller.signal.aborted) setState({ data: null, error: error.message, loading: false }); });
    return () => controller.abort();
  }, [path, revision]);
  return { ...state, reload: () => setRevision((n) => n + 1) };
}

function ResourceState({ state }) {
  if (state.loading) return <p className="control-empty" role="status">Chargement des données…</p>;
  if (state.error) return <div className="control-error" role="alert"><p>{state.error}</p><button onClick={state.reload}>Réessayer</button></div>;
  return null;
}

export function LiveRevenue({ currency }) {
  const state = useAdminResource("/admin/api/orders?per_page=1");
  const daily = state.data?.analytics?.daily || [];
  const max = Math.max(1, ...daily.map((day) => Number(day.revenue || 0)));
  return <section className="panel revenue-panel"><div className="panel-heading"><div><span className="eyebrow">Données réelles · UTC</span><h2>Revenus sur 7 jours</h2></div><Activity size={20} /></div><ResourceState state={state} />{state.data && <><div className="real-revenue" role="img" aria-label={daily.map((day) => `${day.date} : ${day.revenue} ${currency}`).join(" ; ")}>{daily.map((day) => <div key={day.date}><span>{Number(day.revenue).toLocaleString("fr-FR")}</span><i style={{ height: `${Math.max(2, Number(day.revenue) / max * 125)}px` }} /><small>{new Date(`${day.date}T12:00:00Z`).toLocaleDateString("fr-FR", { weekday: "short", timeZone: "UTC" })}</small></div>)}</div><p className="control-caption">{currency} · commandes payées, confirmées ou livrées, selon leur date de création.</p></>}</section>;
}

function HealthCard({ label, path }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function check() {
    setBusy(true); setError(""); setResult(null);
    try { const data = await getAdminJson(path, AbortSignal.timeout(15000)); setResult({ at: new Date().toLocaleTimeString("fr-FR"), message: data.message }); }
    catch (err) { setError(err.name === "TimeoutError" ? "Le diagnostic a dépassé 15 secondes." : err.message); }
    finally { setBusy(false); }
  }
  return <article className="health-card"><ShieldCheck size={21} /><h3>{label}</h3><p role="status">{busy ? "Vérification…" : error || (result ? `Connexion vérifiée à ${result.at}` : "Pas encore vérifié")}</p><button disabled={busy} onClick={check}><RefreshCw size={15} className={busy ? "spin" : ""} />{busy ? "Vérification" : "Tester la connexion"}</button></article>;
}

export function ControlCenter({ data, onNavigate, phone = false }) {
  const summary = data.summary || {};
  const [favorites, setFavorites] = useState(() => {
    const saved = readPreference("control-favorites", ["orders", "inventory", "support"]);
    return Array.isArray(saved) ? saved.filter((key) => Object.values(RESOURCES).some((r) => r.page === key)) : ["orders", "inventory", "support"];
  });
  const [notice, setNotice] = useState("");
  const shortcuts = [["orders", "Commandes", ClipboardList], ["inventory", "Inventaire", Boxes], ["customers", "Clients", Database], ["deposits", "Dépôts", Wallet], ["support", "Support", Headphones]];
  const queues = [["orders", "Commandes en attente", summary.pending_orders], ["support", "Tickets ouverts", summary.open_tickets], ["inventory", "Offres à stock faible", summary.low_stock_offers]];
  return <div className="control-center"><div className="control-hero"><span className="eyebrow">Black Market / {phone ? "Mobile" : "Opérations"}</span><h2>{phone ? "Le contrôle, à portée de main." : "Votre espace de pilotage."}</h2><p>{phone ? "Les mêmes données et les mêmes actions, avec une navigation conçue pour le tactile." : "Priorités, accès favoris et diagnostics des connexions."}</p><span className="control-chip"><Smartphone size={14} />{data.bot_username ? `@${data.bot_username}` : "Bot configuré"}</span></div><div className="control-queues">{queues.map(([page, label, count]) => <button key={page} onClick={() => onNavigate(page)}><span>{label}</span><strong>{count ?? "—"}</strong><ArrowUpRight size={18} /></button>)}</div><section className="control-section"><header><h3>Accès favoris</h3><span>Personnalisez avec l’étoile</span></header><div className="control-shortcuts">{[...shortcuts].sort((a, b) => Number(favorites.includes(b[0])) - Number(favorites.includes(a[0]))).map(([page, label, Icon]) => <article key={page}><button onClick={() => onNavigate(page)}><Icon size={24} /><span>{label}</span><ArrowUpRight size={17} /></button><button className="favorite-toggle" aria-label={`${favorites.includes(page) ? "Retirer" : "Ajouter"} ${label} des favoris`} aria-pressed={favorites.includes(page)} onClick={() => { const next = favorites.includes(page) ? favorites.filter((key) => key !== page) : [...favorites, page]; setFavorites(next); setNotice(savePreference("control-favorites", next) ? "" : "Préférence non enregistrée sur cet appareil."); }}><Star size={16} fill={favorites.includes(page) ? "currentColor" : "none"} /></button></article>)}</div>{notice && <p role="status">{notice}</p>}</section><section className="control-section"><header><h3>Connexions & diagnostics</h3><span>Lecture seule · aucun webhook modifié</span></header><div className="health-grid"><HealthCard label="Telegram" path="/admin/api/telegram-health" /><HealthCard label="Binance" path="/admin/api/binance-health" /><HealthCard label="Bybit" path="/admin/api/bybit-health" /></div></section><button className="control-explore" onClick={() => onNavigate("data-explorer")}><Database size={22} /><span><strong>Explorer les données métier</strong><small>Filtres serveur, pagination et export de la page affichée</small></span><ArrowUpRight size={20} /></button>{phone && <details className="phone-help"><summary>Utiliser ce panneau sur iPhone</summary><p>Dans Safari, ouvrez Partager puis « Sur l’écran d’accueil ». Les actions nécessitent une connexion réseau. Après une interruption, vérifiez l’état de synchronisation avant de poursuivre.</p></details>}</div>;
}

export function DataExplorer({ onNavigate }) {
  const [resource, setResource] = useState("orders");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");
  const meta = RESOURCES[resource];
  useEffect(() => { const timer = setTimeout(() => { setQuery(search); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  const state = useAdminResource(`/admin/api/${meta.path}?${new URLSearchParams({ search: query, status: status || (resource === "deposits" ? "all" : ""), page: String(page), per_page: "25" })}`);
  const rows = state.data?.items || [];
  function exportPage() {
    const url = URL.createObjectURL(new Blob([csvDocument(meta.columns, rows)], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${resource}-page-${page}.csv`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="control-center"><div className="control-hero"><span className="eyebrow">Administration / données</span><h2>Une vue claire sur vos données.</h2><p>Explorez les ressources métier. Les modifications restent dans leurs outils de gestion.</p></div><div className="resource-tabs" role="group" aria-label="Type de données">{Object.entries(RESOURCES).map(([key, value]) => <button key={key} aria-pressed={resource === key} onClick={() => { setResource(key); setPage(1); setStatus(""); setSearch(""); setQuery(""); setNotice(""); }}>{value.label}</button>)}</div><div className="explorer-toolbar"><label><Search size={18} /><input type="search" placeholder="Rechercher dans la base…" aria-label="Rechercher dans la base" value={search} onChange={(e) => setSearch(e.target.value)} /></label>{meta.statuses.length > 0 && <select aria-label="Filtrer les données par statut" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>{["", ...meta.statuses].map((s) => <option key={s} value={s}>{LABELS[s] || "Tous les statuts"}</option>)}</select>}<button onClick={() => { setNotice(savePreference("control-saved-view", { resource, status }) ? "Vue enregistrée sur cet appareil (type et statut)." : "Enregistrement indisponible sur cet appareil."); }}>Enregistrer la vue</button><button onClick={() => { const saved = readPreference("control-saved-view", null); if (!saved || !RESOURCES[saved.resource]) { setNotice("Aucune vue enregistrée."); return; } setResource(saved.resource); setStatus(RESOURCES[saved.resource].statuses.includes(saved.status) ? saved.status : ""); setPage(1); setSearch(""); setQuery(""); setNotice("Vue restaurée."); }}>Restaurer la vue</button></div>{notice && <p className="control-caption" role="status">{notice}</p>}<div className="explorer-panel"><header><span>{state.data ? `${state.data.total ?? 0} résultat(s)` : "Données serveur"}</span><button disabled={!rows.length || state.loading || search !== query} onClick={exportPage}><Download size={16} />Exporter cette page</button></header><ResourceState state={state} />{state.data && <><div className="explorer-table"><table><thead><tr>{meta.columns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={row.id ?? row.reference_id ?? row.telegram_id ?? i}>{meta.columns.map(([key, label]) => <td key={key} data-label={label}>{key === "status" ? LABELS[row[key]] || row[key] || "—" : String(row[key] ?? "—")}</td>)}</tr>)}</tbody></table></div>{rows.length === 0 && <p className="control-empty">Aucun résultat pour ces filtres.</p>}<footer><button disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Précédent</button><span>Page {page} / {state.data.pages || 1}</span><button disabled={page >= (state.data.pages || 1)} onClick={() => setPage((n) => n + 1)}>Suivant</button></footer></>}</div><button className="control-explore" onClick={() => onNavigate(meta.page)}><ArrowUpRight size={20} />Ouvrir la gestion : {meta.label}</button></section>;
}
