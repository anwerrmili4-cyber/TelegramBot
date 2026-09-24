import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AdminPage from "./AdminPages";
import NotificationSettings, { NOTIFICATION_CATEGORIES, notificationAction } from "./NotificationSettings";
import WorkspaceHome from "./WorkspaceHome";
import { ControlCenter, DataExplorer } from "./ControlCenter";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  Boxes,
  CalendarDays,
  ChevronRight,
  CheckCheck,
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
  Trash2,
  Users,
  Wrench,
  WalletCards,
  X,
} from "lucide-react";

const NAV_GROUPS = [
  { label: "Espace de travail", items: [
    { id: "overview", label: "Accueil", icon: LayoutDashboard },
    { id: "orders", label: "Commandes", icon: ClipboardList },
    { id: "customers", label: "Clients", icon: Users },
    { id: "support", label: "Support", icon: Headphones },
    { id: "product-requests", label: "Demandes produits", icon: PackageSearch },
    { id: "warranties", label: "Garanties", icon: ShieldCheck },
  ] },
  { label: "Catalogue & finance", items: [
    { id: "catalog", label: "Mon catalogue", icon: ShoppingBag },
    { id: "inventory", label: "Inventaire", icon: Boxes },
    { id: "api-products", label: "Fournisseurs & API", icon: Cloud },
    { id: "deposits", label: "Dépôts & paiements", icon: CircleDollarSign },
    { id: "withdrawals", label: "Retraits", icon: CircleDollarSign },
    { id: "finance", label: "Profit & pertes", icon: CalendarDays },
    { id: "binance-wallet", label: "Portefeuille Binance", icon: WalletCards },
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

function relativeDate(value) {
  if (!value) return "Maintenant";
  const parsed = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date inconnue";
  const seconds = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 1000));
  if (seconds < 60) return "À l’instant";
  if (seconds < 3600) return `Il y a ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `Il y a ${Math.floor(seconds / 3600)} h`;
  return formatDate(value);
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
  const productRequests = data?.summary?.product_requests || 0;
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
            const count = id === "orders" ? pendingOrders : id === "support" ? openTickets : id === "product-requests" ? productRequests : 0;
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
          <Bell size={19} />{alertCount > 0 && <span>{alertCount > 9 ? "9+" : alertCount}</span>}
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
    const tickets = (data.tickets || []).filter((item) => `${item.id} ${item.user_id} ${item.category || ""} ${item.message || ""}`.toLowerCase().includes(normalized)).slice(0, 3).map((item) => ({ id: `ticket-${item.id}`, entityId: item.id, title: item.category === "catalog_request" ? `Demande produit #${item.id}` : `Ticket #${item.id}`, detail: item.message || item.category || `Client ${item.user_id}`, page: item.category === "catalog_request" ? "product-requests" : "support", icon: item.category === "catalog_request" ? PackageSearch : Headphones }));
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
          {results.map(({ id, entityId, title, detail, page, icon: Icon }) => (
            <button key={id} onClick={() => { onNavigate(page, entityId); onClose(); }}><span><Icon size={17} /></span><div><strong>{title}</strong><small>{detail}</small></div><ChevronRight size={16} /></button>
          ))}
        </div>
        <footer><span>↵ ouvrir</span><span>Échap fermer</span></footer>
      </section>
    </div>
  );
}

function NotificationsDrawer({ token, lastSynced, error, loading, notifications = [], onClose, onDeleteAll, onMarkAllRead, onMarkRead, onNavigate, onRefresh, readIds }) {
  const [filter, setFilter] = useState("unread");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const isRead = (notification) => readIds.has(notification.id);
  const unreadCount = notifications.filter((notification) => !isRead(notification)).length;
  const criticalCount = notifications.filter((notification) => notification.severity === "error").length;
  const actionableCount = notifications.filter((notification) => notification.actionable).length;
  const visible = notifications.filter((notification) => {
    if (category && notification.category !== category) return false;
    if (search && !`${notification.title} ${notification.message}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())) return false;
    if (filter === "unread") return !isRead(notification);
    if (filter === "urgent") return notification.actionable;
    return true;
  });
  const iconFor = (notification) => ({
    order: ClipboardList,
    sale: ShoppingBag,
    deposit: CircleDollarSign,
    withdrawal: CircleDollarSign,
    support: Headphones,
    warranty: ShieldCheck,
    stock: Boxes,
    system: Activity,
  }[notification.category] || Bell);
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="notifications-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span className={`notification-live ${error ? "is-disconnected" : ""}`}><i />{error ? "Synchronisation interrompue" : lastSynced ? `Synchronisé à ${lastSynced.toLocaleTimeString("fr-FR")} · 5 s` : "Connexion…"}</span><h2>Notifications</h2></div><div className="notification-head-actions"><button className="icon-button" onClick={onRefresh} aria-label="Actualiser les notifications"><RefreshCw size={17} className={loading ? "spin" : ""} /></button><button className="icon-button" onClick={onClose} aria-label="Fermer les notifications"><X size={18} /></button></div></header>
        <NotificationSettings token={token} />
        <div className="notification-search"><input aria-label="Rechercher une notification" placeholder="Rechercher une notification…" value={search} onChange={(event) => setSearch(event.target.value)} /><select aria-label="Catégorie de notification" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Toutes les catégories</option>{Object.entries(NOTIFICATION_CATEGORIES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
        <div className="alert-summary"><div className="critical"><strong>{criticalCount}</strong><span>Critiques</span></div><div><strong>{actionableCount}</strong><span>À traiter</span></div><div><strong>{unreadCount}</strong><span>Non lues</span></div></div>
        <div className="notification-toolbar"><div className="alert-filters"><button className={filter === "unread" ? "active" : ""} onClick={() => setFilter("unread")}>Non lues <span>{unreadCount}</span></button><button className={filter === "urgent" ? "active" : ""} onClick={() => setFilter("urgent")}>À traiter <span>{actionableCount}</span></button><button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>Toutes <span>{notifications.length}</span></button></div><div className="notification-toolbar-actions"><button className="mark-all-read" disabled={!unreadCount} onClick={onMarkAllRead}><CheckCheck size={14} />Tout lire</button><button className="delete-all-notifications" disabled={!notifications.length || deleting} onClick={() => setConfirmDelete(true)}><Trash2 size={14} />Tout supprimer</button></div></div>
        {confirmDelete && <div className="notification-delete-confirm" role="alert"><span>Supprimer les {notifications.length} notifications affichées ?</span><button onClick={() => setConfirmDelete(false)} disabled={deleting}>Annuler</button><button className="danger" disabled={deleting} onClick={async () => { setDeleting(true); const deleted = await onDeleteAll(); setDeleting(false); if (deleted) setConfirmDelete(false); }}>{deleting ? "Suppression…" : "Supprimer"}</button></div>}
        {error && <div className="notification-error"><AlertTriangle size={15} /><span>{error}</span><button onClick={onRefresh}>Réessayer</button></div>}
        <div className="drawer-alerts">
          {loading && !notifications.length ? <div className="notification-loading"><RefreshCw className="spin" size={19} />Lecture des événements réels…</div> : visible.length === 0 ? <div className="search-empty"><CheckCheck size={25} /><strong>{notifications.length ? "Aucun résultat pour ces filtres" : "Aucune notification"}</strong><span>{notifications.length ? "Les nouvelles opérations apparaîtront automatiquement." : "Aucune intervention n’est nécessaire actuellement."}</span></div> : visible.map((notification) => {
            const Icon = iconFor(notification);
            const read = isRead(notification);
            return <button key={notification.id} onClick={() => { onMarkRead(notification.id); onNavigate(notification.target?.page || "overview", notification.target?.entity_id); onClose(); }} className={`${notification.severity || "info"} ${read ? "is-read" : "is-unread"}`}>
              <span><Icon size={17} /></span><div><header><strong>{notification.title}</strong><time>{relativeDate(notification.created_at)}</time></header><small>{notification.message}</small><em>{notification.actionable ? "Ouvrir et traiter" : "Voir les détails"}</em></div>{!read && <i className="unread-dot" aria-label="Non lue" />}<ChevronRight size={16} />
            </button>;
          })}
        </div>
      </aside>
    </div>
  );
}

function Toast({ toast, onClose }) {
  const [leaving, setLeaving] = useState(false);
  const onCloseRef = useRef(onClose);
  const dismissTimerRef = useRef(null);
  const removeTimerRef = useRef(null);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    window.clearTimeout(dismissTimerRef.current);
    window.clearTimeout(removeTimerRef.current);
    setLeaving(false);
    if (!toast) return undefined;
    dismissTimerRef.current = window.setTimeout(() => {
      setLeaving(true);
      removeTimerRef.current = window.setTimeout(() => onCloseRef.current(), 260);
    }, 4200);
    return () => {
      window.clearTimeout(dismissTimerRef.current);
      window.clearTimeout(removeTimerRef.current);
    };
  }, [toast]);

  if (!toast) return null;
  const type = toast.type || "success";
  const Icon = type === "success" ? CheckCheck : AlertTriangle;
  const dismiss = () => {
    if (leaving) return;
    window.clearTimeout(dismissTimerRef.current);
    setLeaving(true);
    removeTimerRef.current = window.setTimeout(() => onCloseRef.current(), 260);
  };

  return <div className="toast-stage">
    <div key={`${type}-${toast.title}-${toast.message}`} className={`toast ${type}${leaving ? " is-leaving" : ""}`} role={type === "error" ? "alert" : "status"} aria-live={type === "error" ? "assertive" : "polite"} aria-atomic="true">
      <span className="toast-icon" aria-hidden="true"><Icon size={21} strokeWidth={2.25} /></span>
      <div className="toast-copy"><strong>{toast.title}</strong>{toast.message && <small>{toast.message}</small>}</div>
      <button type="button" onClick={dismiss} aria-label="Ignorer la notification" title="Ignorer cette notification"><span>Ignorer</span><X size={15} /></button>
      <i className="toast-progress" aria-hidden="true" />
    </div>
  </div>;
}

function LoadingState() {
  return <div className="loading-state"><div className="loader" /><strong>Chargement du centre de contrôle…</strong><span>Connexion sécurisée aux données du bot.</span></div>;
}

function ErrorState({ message, onRetry }) {
  return <div className="loading-state error-state"><AlertTriangle size={32} /><strong>Impossible de charger le dashboard</strong><span>{message}</span><button className="primary-button" onClick={onRetry}>Réessayer</button></div>;
}

const SPECIALIZED_CONFIRMATION_ACTIONS = /^(archive_|delete_|bulk_|refund_|cancel_|revoke|undo_|reject_|approve_)/;
const IMMEDIATE_ACTIONS = new Set(["reply_ticket"]);

function describeAdminChange(params = {}) {
  const action = String(params.action || "change");
  const labels = {
    add_inventory: ["Ajouter au stock", "De nouvelles unités seront enregistrées dans l’inventaire du bot."],
    add_service: ["Créer ce service", "Le nouveau service deviendra disponible dans l’administration du catalogue."],
    adjust_user_wallet: ["Modifier le portefeuille", "Le solde du client sera ajusté avec le montant et le motif indiqués."],
    create: ["Créer cet accès", "Un nouvel accès administré sera créé avec les réglages renseignés."],
    duplicate_offer: ["Dupliquer ce produit", "Une nouvelle fiche sera créée à partir du produit sélectionné."],
    manual_deliver_order: ["Livrer cette commande", "Le contenu saisi sera envoyé au client et la commande sera mise à jour."],
    message_customer: ["Envoyer ce message", "Le client recevra le message saisi depuis le bot."],
    run_external_connector: ["Exécuter cette requête", "La requête sera envoyée au connecteur externe sélectionné."],
    save_external_connector: ["Enregistrer cette API", "La configuration du connecteur sera chiffrée puis enregistrée."],
    save_reseller_product: ["Enregistrer ce produit", "Le prix, la disponibilité et les réglages reseller seront mis à jour."],
    save_settings: ["Enregistrer les paramètres", "Les nouveaux réglages seront appliqués au fonctionnement du bot."],
    close_all_tickets: ["Fermer tous les tickets", "Toutes les conversations encore ouvertes seront fermées en une seule opération."],
    close_ticket: ["Fermer ce ticket", "La conversation sera fermée et pourra ensuite être archivée."],
    ticket_archive: ["Archiver ce ticket", "Le ticket disparaîtra de la boîte active, mais son historique restera disponible dans les archives."],
    ticket_unarchive: ["Restaurer ce ticket", "Le ticket archivé reviendra dans la liste principale du support."],
    tickets_archive_closed: ["Archiver les tickets fermés", "Tous les tickets fermés ou résolus seront déplacés vers les archives."],
    complete_withdrawal: ["Confirmer le paiement du retrait", "Le retrait sera marqué comme payé et le client recevra une confirmation Telegram."],
    withdrawal_reject: ["Refuser et rembourser ce retrait", "Le montant réservé sera recrédité dans le portefeuille du client."],
    warranty_accept: ["Accepter cette garantie", "La demande passera à l’étape de résolution : remplacement ou remboursement."],
    warranty_refuse: ["Refuser cette garantie", "Le motif saisi sera envoyé au client dans Telegram."],
    warranty_refund: ["Rembourser cette garantie", "Le montant calculé sera crédité une seule fois dans le portefeuille du client."],
    warranty_replacement: ["Envoyer ce remplacement", "Le contenu saisi sera livré au client dans Telegram et la garantie sera finalisée."],
    toggle_ban: ["Changer l’accès du client", "Le statut d’accès de ce client sera immédiatement modifié."],
    toggle_inventory: ["Changer la disponibilité", "Cette unité de stock sera activée ou désactivée."],
    toggle_offer: ["Changer la visibilité du produit", "La disponibilité de ce produit dans le catalogue sera modifiée."],
    toggle_service: ["Changer la visibilité du service", "La disponibilité de ce service dans le catalogue sera modifiée."],
    update_order_admin: ["Enregistrer la commande", "Le statut et la note administrateur seront remplacés par les valeurs affichées."],
    update_service: ["Modifier ce service", "Le nom et la présentation du service seront mis à jour."],
  };
  const [title, description] = labels[action] || [
    "Confirmer la modification",
    "Cette modification sera appliquée aux données du bot et enregistrée dans le journal d’activité.",
  ];
  const target = params.order_id != null ? `Commande #${params.order_id}`
    : params.user_id != null ? `Client ${params.user_id}`
    : params.offer_id != null ? `Produit #${params.offer_id}`
    : params.service_id != null ? `Service #${params.service_id}`
    : params.ticket_id != null ? `Ticket #${params.ticket_id}` : "Administration du bot";
  return { title, description, target };
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
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState("");
  const [notificationReadIds, setNotificationReadIds] = useState(() => new Set());
  const [notificationsSynced, setNotificationsSynced] = useState(null);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState(null);
  const [pendingActionCount, setPendingActionCount] = useState(0);
  const [actionConfirmation, setActionConfirmation] = useState(null);
  const [density, setDensity] = useState(window.localStorage.getItem("admin-density") === "compact" ? "compact" : "comfortable");
  const [theme, setTheme] = useState(window.localStorage.getItem("admin-theme") === "dark" ? "dark" : "light");
  const dataRequestRef = useRef(null);
  const lastSyncRef = useRef(0);
  const pendingActionsRef = useRef(new Set());
  const actionConfirmationResolverRef = useRef(null);
  const syncChannelRef = useRef(null);
  const notificationRequestRef = useRef(null);
  const previousNotificationIdsRef = useRef(null);

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

  const loadNotifications = useCallback(async (silent = false) => {
    if (notificationRequestRef.current) return notificationRequestRef.current;
    const request = (async () => {
      if (!silent) setNotificationsLoading(true);
      try {
        const response = await fetch("/admin/api/notifications?limit=120", {
          credentials: "same-origin",
          cache: "no-store",
          signal: AbortSignal.timeout(12000),
        });
        if (response.status === 401) {
          window.dispatchEvent(new Event("admin:session-expired"));
          return;
        }
        if (!response.ok) throw new Error(`Erreur serveur (${response.status}).`);
        const payload = await response.json();
        const items = Array.isArray(payload.items) ? payload.items : [];
        const nextIds = new Set(items.map((item) => item.id));
        const previousIds = previousNotificationIdsRef.current;
        if (previousIds) {
          const fresh = items.find((item) => !previousIds.has(item.id) && item.actionable);
          if (fresh) setToast({ type: fresh.severity === "error" ? "error" : "success", title: fresh.title, message: fresh.message });
        }
        previousNotificationIdsRef.current = nextIds;
        setNotifications(items);
        setNotificationReadIds(new Set(payload.read_ids || []));
        setNotificationsSynced(new Date());
        setNotificationsError("");
      } catch (requestError) {
        setNotificationsError(requestError.message || "Les notifications ne peuvent pas être actualisées.");
      } finally {
        setNotificationsLoading(false);
      }
    })();
    notificationRequestRef.current = request;
    try {
      await request;
    } finally {
      if (notificationRequestRef.current === request) notificationRequestRef.current = null;
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    if (!authenticated) return undefined;
    loadNotifications();
    const refresh = () => {
      if (document.visibilityState === "visible" && navigator.onLine) loadNotifications(true);
    };
    const timer = window.setInterval(refresh, 5_000);
    const offline = () => setNotificationsError("Hors ligne. La synchronisation reprendra à la reconnexion.");
    window.addEventListener("offline", offline);
    window.addEventListener("online", refresh);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", refresh);
      previousNotificationIdsRef.current = null;
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [authenticated, loadNotifications]);
  useEffect(() => {
    if (notificationsOpen) loadNotifications(true);
  }, [notificationsOpen, loadNotifications]);
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

  const navigate = (page, entityId = null) => {
    const updatePage = () => {
      setActivePage(page);
      setMobileOpen(false);
      const target = page === "overview" ? "/admin" : `/admin/${page}`;
      const query = page === "orders" && entityId != null
        ? `?order=${encodeURIComponent(entityId)}`
        : page === "support" && entityId != null
          ? `?ticket=${encodeURIComponent(entityId)}`
          : page === "product-requests" && entityId != null
            ? `?request=${encodeURIComponent(entityId)}`
          : page === "customers" && entityId != null
            ? `?user=${encodeURIComponent(entityId)}`
          : page === "withdrawals" && entityId != null
            ? `?withdrawal=${encodeURIComponent(entityId)}`
            : page === "warranties" && entityId != null
              ? `?warranty=${encodeURIComponent(entityId)}`
          : "";
      window.history.pushState({}, "", target + query);
      window.dispatchEvent(new CustomEvent("admin:navigate", { detail: { page, entityId } }));
    };
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (document.startViewTransition && !reduceMotion && page !== activePage) {
      document.startViewTransition(updatePage);
    } else {
      updatePage();
    }
  };

  const markNotificationsRead = async (ids) => {
    try {
      await notificationAction(data?.dashboard_write_token, { action: "read", ids });
      setNotificationReadIds((current) => new Set([...current, ...ids]));
      await loadNotifications(true);
    } catch (err) { setNotificationsError(err.message); }
  };
  const markNotificationRead = (id) => markNotificationsRead([id]);
  const markAllNotificationsRead = () => markNotificationsRead(notifications.map((item) => item.id));
  const deleteAllNotifications = async () => {
    try {
      await notificationAction(data?.dashboard_write_token, {
        action: "delete_all",
        ids: notifications.map((item) => item.id),
      });
      setNotifications([]);
      setNotificationReadIds(new Set());
      setToast({ title: "Notifications supprimées", message: "La liste des notifications a été vidée." });
      return true;
    } catch (err) {
      setNotificationsError(err.message);
      return false;
    }
  };

  const executeAdminAction = async (params, { quiet = false, refreshGlobal = true } = {}) => {
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
      if (!quiet) setToast({ title: "Action enregistrée", message: payload.message || "Les modifications ont été appliquées." });
      if (refreshGlobal) {
        await loadData(true, true);
        await loadNotifications(true);
      }
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

  const adminAction = (params) => {
    if (IMMEDIATE_ACTIONS.has(String(params?.action || ""))) {
      return executeAdminAction(params, { quiet: true, refreshGlobal: false });
    }
    if (SPECIALIZED_CONFIRMATION_ACTIONS.test(String(params?.action || ""))) {
      return executeAdminAction(params);
    }
    if (actionConfirmationResolverRef.current) return Promise.resolve(null);
    return new Promise((resolve) => {
      actionConfirmationResolverRef.current = resolve;
      setActionConfirmation({ params, ...describeAdminChange(params) });
    });
  };

  const closeActionConfirmation = () => {
    actionConfirmationResolverRef.current?.(null);
    actionConfirmationResolverRef.current = null;
    setActionConfirmation(null);
  };

  const confirmAdminAction = async () => {
    if (!actionConfirmation) return;
    const { params } = actionConfirmation;
    const resolve = actionConfirmationResolverRef.current;
    actionConfirmationResolverRef.current = null;
    setActionConfirmation(null);
    const result = await executeAdminAction(params);
    resolve?.(result);
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

  const alertCount = useMemo(
    () => notifications.filter((notification) => !notificationReadIds.has(notification.id)).length,
    [notificationReadIds, notifications],
  );
  useEffect(() => {
    document.title = alertCount
      ? `(${alertCount}) Black Market · Control Room`
      : "Black Market · Control Room";
  }, [alertCount]);

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
      <div className={`main-shell page-${activePage}`}>
        <Header activePage={activePage} alertCount={alertCount} busyAction={busyAction} density={density} isRefreshing={refreshing || pendingActionCount > 0} onLogout={logout} onMenu={() => setMobileOpen(true)} onNotifications={() => setNotificationsOpen(true)} onRefresh={async () => { await loadData(true); await loadNotifications(true); }} onRepairTelegram={() => runHealthCheck("telegram-repair")} onSearch={() => setSearchOpen(true)} onTestBinance={() => runHealthCheck("binance")} onToggleDensity={() => setDensity((current) => { const next = current === "compact" ? "comfortable" : "compact"; window.localStorage.setItem("admin-density", next); return next; })} onToggleTheme={() => setTheme((current) => { const next = current === "dark" ? "light" : "dark"; window.localStorage.setItem("admin-theme", next); return next; })} theme={theme} />
        <div className={`sync-status ${syncError ? "has-error" : ""}`} role="status"><span>{syncError || (lastSynced ? `Synchronisé à ${lastSynced.toLocaleTimeString("fr-FR")}` : "Connexion au panneau…")}</span>{syncError && <button onClick={() => loadData(true)}>Réessayer</button>}</div>
        <main className={`content page-${activePage}`} id="main-content">
          {data?.preview_mode && <p className="preview-notice" role="status">Prévisualisation locale · données fictives · aucune écriture réelle</p>}
          {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => loadData()} /> : !data ? <ErrorState message="La session administrateur n’a pas pu être restaurée." onRetry={() => loadData()} /> : activePage === "overview" ? <WorkspaceHome data={data} onNavigate={navigate} /> : activePage === "control-center" || activePage === "phone" ? <ControlCenter data={data} onNavigate={navigate} phone={activePage === "phone"} /> : activePage === "data-explorer" ? <DataExplorer onNavigate={navigate} /> : <AdminPage key={activePage} page={activePage} data={data} onAction={adminAction} onHealthCheck={runHealthCheck} onNavigate={navigate} setToast={setToast} />}
        </main>
      </div>
      {searchOpen && data && <SearchDialog data={data} onClose={() => setSearchOpen(false)} onNavigate={navigate} />}
      {notificationsOpen && <NotificationsDrawer token={data?.dashboard_write_token} lastSynced={notificationsSynced} error={notificationsError} loading={notificationsLoading} notifications={notifications} onClose={() => setNotificationsOpen(false)} onDeleteAll={deleteAllNotifications} onMarkAllRead={markAllNotificationsRead} onMarkRead={markNotificationRead} onNavigate={navigate} onRefresh={() => loadNotifications()} readIds={notificationReadIds} />}
      {actionConfirmation && <div className="action-confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeActionConfirmation(); }}><section className="action-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="admin-change-title" aria-describedby="admin-change-description"><span className="action-confirm-icon"><ShieldCheck size={23} /></span><div><small>Vérification avant action</small><h2 id="admin-change-title">{actionConfirmation.title}</h2><p id="admin-change-description">{actionConfirmation.description}</p><strong>{actionConfirmation.target}</strong></div><footer><button type="button" className="secondary-button" onClick={closeActionConfirmation}>Annuler</button><button type="button" className="primary-button" onClick={confirmAdminAction}>Confirmer la modification</button></footer></section></div>}
      {authenticated && <nav className="phone-nav" aria-label="Navigation mobile">{[["phone", "Pilotage", LayoutDashboard], ["orders", "Commandes", ClipboardList], ["deposits", "Dépôts", CircleDollarSign], ["support", "Support", Headphones]].map(([id, label, Icon]) => <button key={id} aria-current={activePage === id ? "page" : undefined} onClick={() => navigate(id)}><Icon size={21} /><span>{label}</span></button>)}<button onClick={() => setMobileOpen(true)} aria-label="Tous les outils"><Menu size={21} /><span>Plus</span></button></nav>}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
