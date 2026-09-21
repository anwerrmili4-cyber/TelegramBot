import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AdminPage from "./AdminPages";
import WorkspaceHome from "./WorkspaceHome";
import { ControlCenter, DataExplorer } from "./ControlCenter";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  Boxes,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  Cloud,
  Database,
  Eye,
  EyeOff,
  Headphones,
  KeyRound,
  LockKeyhole,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Moon,
  PackageSearch,
  RefreshCw,
  Search,
  LogIn,
  LogOut,
  ShieldCheck,
  Settings,
  ShoppingBag,
  Sun,
  Users,
  Wrench,
  X,
} from "lucide-react";

const NAV_GROUPS = [
  { label: "Espace de travail", items: [
    { id: "overview", label: "Accueil", icon: LayoutDashboard },
    { id: "orders", label: "Commandes", icon: ClipboardList },
    { id: "customers", label: "Clients", icon: Users },
    { id: "support", label: "Support", icon: Headphones },
  ] },
  { label: "Catalogue & finance", items: [
    { id: "catalog", label: "Mon catalogue", icon: ShoppingBag },
    { id: "inventory", label: "Inventaire", icon: Boxes },
    { id: "api-products", label: "Fournisseurs & API", icon: Cloud },
    { id: "deposits", label: "Dépôts & paiements", icon: CircleDollarSign },
    { id: "api-clients", label: "Clients API", icon: KeyRound },
  ] },
  { label: "Administration", items: [
    { id: "control-center", label: "Centre de contrôle", icon: Activity },
    { id: "data-explorer", label: "Explorateur", icon: Database },
    { id: "activity", label: "Journal des actions", icon: Activity },
    { id: "interactions", label: "Interactions", icon: MessageSquareText },
    { id: "ai-manager", label: "Assistant IA", icon: Bot },
    { id: "phone", label: "Espace mobile", icon: Menu },
    { id: "settings", label: "Paramètres", icon: Settings },
  ] },
];
const BOT_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);

const ALL_NAV_ITEMS = BOT_NAV_ITEMS;

const STATUS_LABELS = {
  pending_payment: "Paiement en attente",
  awaiting_verification: "À vérifier",
  manual_review: "Révision manuelle",
  paid: "Payée",
  payment_confirmed: "Confirmée",
  delivered: "Livrée",
  cancelled: "Annulée",
};

function formatMoney(value, currency = "USDT") {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(Number(value || 0))} ${currency}`;
}

function orderAmount(order = {}) {
  return order.charged_total ?? Number(order.total_price || 0) + Number(order.wallet_amount || 0);
}

function formatDate(value) {
  if (!value) return "—";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function initials(value = "BM") {
  return value
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function Sidebar({ activePage, data, mobileOpen, onClose, onNavigate }) {
  const pendingOrders = data?.summary?.pending_orders || 0;
  const openTickets = data?.summary?.open_tickets || 0;
  const navItems = BOT_NAV_ITEMS;

  return (
    <>
      <button
        className={`sidebar-backdrop ${mobileOpen ? "is-open" : ""}`}
        aria-label="Fermer le menu"
        onClick={onClose}
      />
      <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">{initials(data?.shop_name || "BlackMarket")}</div>
          <div><strong>{data?.shop_name || "BlackMarket"}</strong><span>Commerce workspace</span></div>
          <button className="icon-button mobile-only" onClick={onClose} aria-label="Fermer"><X size={20} /></button>
        </div>

        <nav className="nav-list" aria-label="Navigation principale">
          {NAV_GROUPS.map((group) => <div className="nav-group" key={group.label}><span className="nav-heading">{group.label}</span>{group.items.map(({ id, label, icon: Icon }) => {
            const count = id === "orders" ? pendingOrders : id === "support" ? openTickets : 0;
            return <button key={id} className={`nav-item ${activePage === id ? "active" : ""}`} aria-current={activePage === id ? "page" : undefined} onClick={() => onNavigate(id)}><Icon size={18} strokeWidth={1.7} /><span>{label}</span>{count > 0 && <small>{count}</small>}</button>;
          })}</div>)}
        </nav>

        <div className="sidebar-footer">
          <div className="connection-dot neutral" />
          <div><strong>Bot configuré</strong><span>@{data?.bot_username || "—"}</span></div>
        </div>
      </aside>
    </>
  );
}

function Header({ activePage, alertCount, busyAction, density, isRefreshing, onLogout, onMenu, onNotifications, onRefresh, onRepairTelegram, onSearch, onTestBinance, onToggleDensity, onToggleTheme, theme }) {
  const navItems = BOT_NAV_ITEMS;
  const current = navItems.find((item) => item.id === activePage) || navItems[0];
  return (
    <header className="topbar">
      <div className="topbar-title">
        <button className="icon-button menu-button" onClick={onMenu} aria-label="Ouvrir le menu"><Menu size={21} /></button>
        <div><span>Workspace / {NAV_GROUPS.find((group) => group.items.some((item) => item.id === activePage))?.label}</span><h1>{current.label}</h1></div>
      </div>
      <button className="global-search-trigger" onClick={onSearch} aria-label="Rechercher dans le panneau">
        <Search size={17} />
        <span>Rechercher commandes, produits ou clients…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className="topbar-actions">
        <button className={`icon-button density-button ${density === "compact" ? "active" : ""}`} onClick={onToggleDensity} aria-label="Changer la densité" title={density === "compact" ? "Affichage confortable" : "Affichage compact"}><Database size={18} /></button>
        <button className="icon-button theme-button" onClick={onToggleTheme} aria-label="Changer le thème" title={theme === "dark" ? "Activer le thème clair" : "Activer le thème sombre"}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>
        <button className="icon-button" onClick={onRefresh} aria-label="Actualiser" title="Actualiser les données">
          <RefreshCw size={19} className={isRefreshing ? "spin" : ""} />
        </button>
        <button className="icon-button notification-button" onClick={onNotifications} aria-label={`${alertCount} alertes`}>
          <Bell size={19} />{alertCount > 0 && <span>{Math.min(alertCount, 9)}</span>}
        </button>
        <button className="avatar" onClick={onLogout} aria-label="Se déconnecter" title="Se déconnecter">AD<span><LogOut size={12} /></span></button>
      </div>
    </header>
  );
}

function SearchDialog({ data, onClose, onNavigate }) {
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLowerCase();
  const results = useMemo(() => {
    if (!normalized) return [];
    const orders = (data.orders || []).filter((item) => `${item.id} ${item.user_id} ${item.username || ""} ${item.offer_name || ""} ${item.service_name || ""} ${item.txid || ""}`.toLowerCase().includes(normalized)).slice(0, 4).map((item) => ({ id: `order-${item.id}`, title: `Commande #${item.id}`, detail: item.txid ? `${item.offer_name || "Produit"} · TXID ${item.txid}` : item.offer_name || `Client ${item.user_id}`, page: "orders", icon: ClipboardList }));
    const customers = (data.users || []).filter((item) => `${item.telegram_id || item.user_id || ""} ${item.username || ""} ${item.first_name || ""} ${item.last_name || ""}`.toLowerCase().includes(normalized)).slice(0, 4).map((item) => ({ id: `customer-${item.telegram_id || item.user_id}`, title: item.username ? `@${item.username}` : `Client ${item.telegram_id || item.user_id}`, detail: [item.first_name, item.last_name].filter(Boolean).join(" ") || "Client Telegram", page: "customers", icon: Users }));
    const services = (data.services || []).filter((item) => `${item.name || ""} ${(item.offers || []).map((offer) => `${offer.name} ${offer.supplier_provider || ""}`).join(" ")}`.toLowerCase().includes(normalized)).slice(0, 4).map((item) => ({ id: `service-${item.id}`, title: item.name, detail: `${item.offer_count || 0} offre(s)`, page: "catalog", icon: ShoppingBag }));
    const tickets = (data.tickets || []).filter((item) => `${item.id} ${item.user_id} ${item.category || ""} ${item.message || ""}`.toLowerCase().includes(normalized)).slice(0, 3).map((item) => ({ id: `ticket-${item.id}`, title: `Ticket #${item.id}`, detail: item.category || `Client ${item.user_id}`, page: "support", icon: Headphones }));
    return [...orders, ...customers, ...services, ...tickets].slice(0, 10);
  }, [data, normalized]);

  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <section className="search-dialog" role="dialog" aria-modal="true" aria-label="Recherche globale" onMouseDown={(event) => event.stopPropagation()}>
        <div className="search-dialog-input"><Search size={20} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nom, commande, TXID, produit, client ou ticket…" /><button onClick={onClose}><X size={18} /></button></div>
        <div className="search-results">
          {!normalized && <div className="search-empty"><Search size={25} /><strong>Recherche globale</strong><span>Saisissez un nom, un identifiant, un TXID, un produit ou un ticket.</span></div>}
          {normalized && results.length === 0 && <div className="search-empty"><strong>Aucun résultat</strong><span>Essayez un autre terme de recherche.</span></div>}
          {results.map(({ id, title, detail, page, icon: Icon }) => (
            <button key={id} onClick={() => { onNavigate(page); onClose(); }}><span><Icon size={17} /></span><div><strong>{title}</strong><small>{detail}</small></div><ChevronRight size={16} /></button>
          ))}
        </div>
        <footer><span>↵ ouvrir</span><span>Échap fermer</span></footer>
      </section>
    </div>
  );
}

function NotificationsDrawer({ alerts = [], onClose, onNavigate }) {
  const [filter, setFilter] = useState("all");
  const criticalCount = alerts.filter((alert) => alert.severity === "error").length;
  const warningCount = alerts.length - criticalCount;
  const visible = [...alerts]
    .filter((alert) => filter === "all" || (filter === "critical" ? alert.severity === "error" : alert.severity !== "error"))
    .sort((a, b) => (a.severity === "error" ? 0 : 1) - (b.severity === "error" ? 0 : 1));
  const destination = (alert) => alert.type?.includes("stock")
    ? "inventory"
    : alert.type?.includes("ticket") ? "support"
      : alert.type?.includes("api") || alert.type?.includes("provider") ? "api-products"
        : alert.type?.includes("error") ? "activity" : "orders";
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="notifications-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span className="eyebrow">Centre d’alertes</span><h2>Notifications</h2></div><button className="icon-button" onClick={onClose}><X size={18} /></button></header>
        <div className="alert-summary"><div className="critical"><strong>{criticalCount}</strong><span>Critiques</span></div><div><strong>{warningCount}</strong><span>Attention</span></div><div><strong>{alerts.length}</strong><span>Total</span></div></div>
        <div className="alert-filters"><button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>Toutes <span>{alerts.length}</span></button><button className={filter === "critical" ? "active" : ""} onClick={() => setFilter("critical")}>Critiques <span>{criticalCount}</span></button><button className={filter === "warning" ? "active" : ""} onClick={() => setFilter("warning")}>Attention <span>{warningCount}</span></button></div>
        <div className="drawer-alerts">
          {visible.length === 0 ? <div className="search-empty"><strong>Aucune alerte</strong><span>{alerts.length ? "Aucune alerte dans ce filtre." : "Votre boutique fonctionne normalement."}</span></div> : visible.map((alert, index) => (
            <button key={`${alert.type}-${index}`} onClick={() => { onNavigate(destination(alert)); onClose(); }} className={alert.severity || "warning"}>
              <span><AlertTriangle size={17} /></span><div><strong>{alert.severity === "error" ? "Action requise" : "À surveiller"}</strong><small>{alert.message}</small><em>Ouvrir la section concernée</em></div><ChevronRight size={16} />
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}

function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(onClose, 4500);
    return () => window.clearTimeout(timeout);
  }, [toast, onClose]);
  if (!toast) return null;
  return <div className={`toast ${toast.type || "success"}`}><span>{toast.type === "error" ? "!" : "✓"}</span><div><strong>{toast.title}</strong><small>{toast.message}</small></div><button onClick={onClose}><X size={15} /></button></div>;
}

function LoadingState() {
  return <div className="loading-state"><div className="loader" /><strong>Chargement du centre de contrôle…</strong><span>Connexion sécurisée aux données du bot.</span></div>;
}

function ErrorState({ message, onRetry }) {
  return <div className="loading-state error-state"><AlertTriangle size={32} /><strong>Impossible de charger le dashboard</strong><span>{message}</span><button className="primary-button" onClick={onRetry}>Réessayer</button></div>;
}

function LoginPage({ onAuthenticated }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setMessage("Renseignez votre identifiant et votre mot de passe.");
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch("/admin/api/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "Connexion impossible.");
      await onAuthenticated();
    } catch (loginError) {
      setMessage(loginError.message || "Connexion impossible. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-story" aria-label="BlackMarket Control Center">
        <div className="login-brand"><div className="login-brand-mark">BM</div><div><strong>BlackMarket</strong><span>Control Center</span></div></div>
        <div className="login-story-copy">
          <span className="login-kicker"><i /> Espace administrateur</span>
          <h1>Votre boutique.<br /><em>Sous contrôle.</em></h1>
          <p>Pilotez vos commandes, votre catalogue et vos clients depuis un espace unique, conçu pour aller à l’essentiel.</p>
        </div>
        <div className="login-security-note"><ShieldCheck size={18} /><div><strong>Accès sécurisé</strong><span>Vos données restent protégées et confidentielles.</span></div></div>
        <div className="login-orb login-orb-one" /><div className="login-orb login-orb-two" />
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <header><span className="login-lock"><LockKeyhole size={21} /></span><div><h2>Bon retour parmi nous</h2><p>Connectez-vous pour accéder au tableau de bord.</p></div></header>
          <label className="login-field"><span>Identifiant</span><div><KeyRound size={17} /><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" spellCheck="false" aria-invalid={Boolean(message)} autoFocus /></div></label>
          <label className="login-field"><span>Mot de passe</span><div><LockKeyhole size={17} /><input type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" aria-invalid={Boolean(message)} /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
          {message && <div className="login-error" role="alert"><AlertTriangle size={15} />{message}</div>}
          <button className="login-submit" type="submit" disabled={submitting}>{submitting ? <><span className="login-spinner" />Connexion en cours…</> : <>Se connecter <LogIn size={17} /></>}</button>
          <footer><ShieldCheck size={13} /> Session sécurisée · Accès réservé</footer>
        </form>
        <p className="login-help">Un problème d’accès ? Contactez le propriétaire du bot.</p>
      </section>
    </main>
  );
}

export default function App() {
  const routePage = () => window.location.pathname.replace(/^\/admin(?:-v2)?\/?/, "").split("/")[0] || "overview";
  const initialPage = routePage();
  const [activePage, setActivePage] = useState(ALL_NAV_ITEMS.some((item) => item.id === initialPage) ? initialPage : "overview");
  const [data, setData] = useState(null);
  const [authenticated, setAuthenticated] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncError, setSyncError] = useState("");
  const [lastSynced, setLastSynced] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState(null);
  const [pendingActionCount, setPendingActionCount] = useState(0);
  const [density, setDensity] = useState(window.localStorage.getItem("admin-density") === "compact" ? "compact" : "comfortable");
  const [theme, setTheme] = useState(window.localStorage.getItem("admin-theme") === "dark" ? "dark" : "light");
  const dataRequestRef = useRef(null);
  const lastSyncRef = useRef(0);
  const pendingActionsRef = useRef(new Set());
  const syncChannelRef = useRef(null);

  const loadData = useCallback(async (background = false, forceFresh = false) => {
    if (dataRequestRef.current) {
      await dataRequestRef.current;
      if (!forceFresh) return;
    }
    const request = (async () => {
      background ? setRefreshing(true) : setLoading(true);
      if (!background) setError("");
      try {
        const response = await fetch("/admin/api/data", { credentials: "same-origin", cache: "no-store" });
        if (response.status === 401) {
          setAuthenticated(false);
          setLoading(false);
          return;
        }
        if (!response.ok) throw new Error(`Erreur serveur (${response.status}).`);
        setData(await response.json());
        setAuthenticated(true);
        setSyncError("");
        setLastSynced(new Date());
        lastSyncRef.current = Date.now();
        if (background) window.dispatchEvent(new Event("admin:data-synced"));
      } catch (requestError) {
        if (!background) setError(requestError.message || "Une erreur inattendue est survenue.");
        else setSyncError("Actualisation impossible. Les données affichées peuvent être anciennes.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    })();
    dataRequestRef.current = request;
    try {
      await request;
    } finally {
      if (dataRequestRef.current === request) dataRequestRef.current = null;
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    const expired = () => { setAuthenticated(false); setData(null); };
    const offline = () => setSyncError("Connexion interrompue. Reconnectez-vous au réseau avant d’agir.");
    const failedRead = (event) => setSyncError(event.detail);
    window.addEventListener("admin:session-expired", expired);
    window.addEventListener("offline", offline);
    window.addEventListener("admin:read-error", failedRead);
    return () => { window.removeEventListener("admin:session-expired", expired); window.removeEventListener("offline", offline); window.removeEventListener("admin:read-error", failedRead); };
  }, []);
  useEffect(() => {
    if (!mobileOpen) return undefined;
    const close = (event) => { if (event.key === "Escape") setMobileOpen(false); };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", close);
    return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", close); };
  }, [mobileOpen]);
  useEffect(() => {
    const refreshWhenUseful = () => {
      if (document.visibilityState === "visible" && navigator.onLine && Date.now() - lastSyncRef.current > 15_000) loadData(true);
    };
    const timer = window.setInterval(refreshWhenUseful, 30_000);
    window.addEventListener("focus", refreshWhenUseful);
    window.addEventListener("online", refreshWhenUseful);
    document.addEventListener("visibilitychange", refreshWhenUseful);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshWhenUseful);
      window.removeEventListener("online", refreshWhenUseful);
      document.removeEventListener("visibilitychange", refreshWhenUseful);
    };
  }, [loadData]);
  useEffect(() => {
    if (!("BroadcastChannel" in window)) return undefined;
    const channel = new BroadcastChannel("blackmarket-admin-sync");
    syncChannelRef.current = channel;
    channel.onmessage = (event) => {
      if (event.data?.type === "data-changed") loadData(true, true);
    };
    return () => {
      syncChannelRef.current = null;
      channel.close();
    };
  }, [loadData]);
  useEffect(() => { document.documentElement.dataset.adminDensity = density; }, [density]);
  useEffect(() => { document.documentElement.dataset.adminTheme = theme; }, [theme]);
  useEffect(() => {
    const openSearch = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", openSearch);
    return () => window.removeEventListener("keydown", openSearch);
  }, []);
  useEffect(() => {
    const synchronizeRoute = () => {
      const page = routePage();
      const nextPage = ALL_NAV_ITEMS.some((item) => item.id === page) ? page : "overview";
      setActivePage(nextPage);
    };
    const restorePage = (event) => {
      synchronizeRoute();
      if (event.persisted) loadData(true, true);
    };
    window.addEventListener("popstate", synchronizeRoute);
    window.addEventListener("pageshow", restorePage);
    return () => {
      window.removeEventListener("popstate", synchronizeRoute);
      window.removeEventListener("pageshow", restorePage);
    };
  }, [loadData]);

  const navigate = (page) => {
    setActivePage(page);
    setMobileOpen(false);
    window.history.pushState({}, "", page === "overview" ? "/admin" : `/admin/${page}`);
  };

  const adminAction = async (params) => {
    const actionSignature = JSON.stringify(Object.entries(params).sort(([left], [right]) => left.localeCompare(right)));
    if (pendingActionsRef.current.has(actionSignature)) return null;
    pendingActionsRef.current.add(actionSignature);
    setPendingActionCount(pendingActionsRef.current.size);
    try {
      const response = await fetch("/admin", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-Dashboard-Write-Token": data?.dashboard_write_token || "",
        },
        body: new URLSearchParams(Object.entries(params).map(([key, value]) => [key, value == null ? "" : String(value)])),
      });
      const payload = await response.json();
      if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
      if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || "Action refusée.");
      setToast({ title: "Action enregistrée", message: payload.message || "Les modifications ont été appliquées." });
      await loadData(true, true);
      syncChannelRef.current?.postMessage({ type: "data-changed", at: Date.now() });
      return payload;
    } catch (actionError) {
      setToast({ type: "error", title: "Action impossible", message: actionError.message });
      return null;
    } finally {
      pendingActionsRef.current.delete(actionSignature);
      setPendingActionCount(pendingActionsRef.current.size);
    }
  };

  const runHealthCheck = async (type) => {
    setBusyAction(type);
    try {
      if (type === "telegram-repair") {
        const response = await fetch("/admin", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-Dashboard-Write-Token": data?.dashboard_write_token || "",
          },
          body: new URLSearchParams({ action: "repair_telegram_webhook" }),
        });
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || "Réparation refusée.");
        setToast({ title: "Telegram réparé", message: payload.message || "Le webhook est correctement configuré." });
      } else {
        const service = type === "telegram" ? "Telegram" : "Binance";
        const response = await fetch(`/admin/api/${type === "telegram" ? "telegram" : "binance"}-health`, { credentials: "same-origin", cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || "Connexion Binance indisponible.");
        setToast({ title: `${service} opérationnel`, message: payload.message || "La connexion API fonctionne correctement." });
      }
    } catch (actionError) {
      setToast({ type: "error", title: type.startsWith("telegram") ? "Échec Telegram" : "Échec Binance", message: actionError.message });
    } finally {
      setBusyAction("");
    }
  };

  const alertCount = useMemo(() => data?.alerts?.length || 0, [data]);

  const logout = async () => {
    await fetch("/admin/api/logout", { method: "POST", credentials: "same-origin" });
    setData(null);
    setAuthenticated(false);
    window.history.replaceState({}, "", "/admin/login");
  };

  if (authenticated === false) {
    return <LoginPage onAuthenticated={async () => {
      await loadData(false, true);
      window.history.replaceState({}, "", "/admin");
    }} />;
  }

  return (
    <div className={`app-shell ${refreshing || pendingActionCount ? "is-synchronizing" : ""}`} aria-busy={refreshing || pendingActionCount > 0}>
      <Sidebar activePage={activePage} data={data} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} onNavigate={navigate} />
      <div className="main-shell">
        <Header activePage={activePage} alertCount={alertCount} busyAction={busyAction} density={density} isRefreshing={refreshing || pendingActionCount > 0} onLogout={logout} onMenu={() => setMobileOpen(true)} onNotifications={() => setNotificationsOpen(true)} onRefresh={() => loadData(true)} onRepairTelegram={() => runHealthCheck("telegram-repair")} onSearch={() => setSearchOpen(true)} onTestBinance={() => runHealthCheck("binance")} onToggleDensity={() => setDensity((current) => { const next = current === "compact" ? "comfortable" : "compact"; window.localStorage.setItem("admin-density", next); return next; })} onToggleTheme={() => setTheme((current) => { const next = current === "dark" ? "light" : "dark"; window.localStorage.setItem("admin-theme", next); return next; })} theme={theme} />
        <div className={`sync-status ${syncError ? "has-error" : ""}`} role="status"><span>{syncError || (lastSynced ? `Synchronisé à ${lastSynced.toLocaleTimeString("fr-FR")}` : "Connexion au panneau…")}</span>{syncError && <button onClick={() => loadData(true)}>Réessayer</button>}</div>
        <main className={`content page-${activePage}`} id="main-content">
          {data?.preview_mode && <p className="preview-notice" role="status">Prévisualisation locale · données fictives · aucune écriture réelle</p>}
          {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => loadData()} /> : !data ? <ErrorState message="La session administrateur n’a pas pu être restaurée." onRetry={() => loadData()} /> : activePage === "overview" ? <WorkspaceHome data={data} onNavigate={navigate} /> : activePage === "control-center" || activePage === "phone" ? <ControlCenter data={data} onNavigate={navigate} phone={activePage === "phone"} /> : activePage === "data-explorer" ? <DataExplorer onNavigate={navigate} /> : <AdminPage key={activePage} page={activePage} data={data} onAction={adminAction} onHealthCheck={runHealthCheck} onNavigate={navigate} setToast={setToast} />}
        </main>
      </div>
      {searchOpen && data && <SearchDialog data={data} onClose={() => setSearchOpen(false)} onNavigate={navigate} />}
      {notificationsOpen && <NotificationsDrawer alerts={data?.alerts || []} onClose={() => setNotificationsOpen(false)} onNavigate={navigate} />}
      {authenticated && <nav className="phone-nav" aria-label="Navigation mobile">{[["phone", "Pilotage", LayoutDashboard], ["orders", "Commandes", ClipboardList], ["deposits", "Dépôts", CircleDollarSign], ["support", "Support", Headphones]].map(([id, label, Icon]) => <button key={id} aria-current={activePage === id ? "page" : undefined} onClick={() => navigate(id)}><Icon size={21} /><span>{label}</span></button>)}<button onClick={() => setMobileOpen(true)} aria-label="Tous les outils"><Menu size={21} /><span>Plus</span></button></nav>}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
