import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AdminPage from "./AdminPages";
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

const BOT_NAV_ITEMS = [
  { id: "overview", label: "Vue d’ensemble", icon: LayoutDashboard },
  { id: "ai-manager", label: "AI Bot Manager", icon: Bot },
  { id: "orders", label: "Commandes", icon: ClipboardList },
  { id: "catalog", label: "Catalogue", icon: ShoppingBag },
  { id: "api-products", label: "Produits API", icon: Cloud },
  { id: "api-clients", label: "Clients API", icon: KeyRound },
  { id: "inventory", label: "Inventaire", icon: Boxes },
  { id: "customers", label: "Clients", icon: Users },
  { id: "deposits", label: "Dépôts", icon: CircleDollarSign },
  { id: "support", label: "Support", icon: Headphones },
  { id: "interactions", label: "Interactions", icon: MessageSquareText },
  { id: "activity", label: "Activité", icon: Activity },
  { id: "settings", label: "Paramètres", icon: Settings },
];

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
          <div><strong>{data?.shop_name || "BlackMarket"}</strong><span>Bot Control Center</span></div>
          <button className="icon-button mobile-only" onClick={onClose} aria-label="Fermer"><X size={20} /></button>
        </div>

        <nav className="nav-list" aria-label="Navigation principale">
          <span className="nav-heading">Bot Telegram</span>
          {navItems.map(({ id, label, icon: Icon }) => {
            const count = id === "orders" ? pendingOrders : id === "support" ? openTickets : 0;
            return (
              <button
                key={id}
                className={`nav-item ${activePage === id ? "active" : ""}`}
                onClick={() => onNavigate(id)}
              >
                <Icon size={19} strokeWidth={1.8} />
                <span>{label}</span>
                {count > 0 && <small>{count}</small>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="connection-dot" />
          <div><strong>Bot connecté</strong><span>@{data?.bot_username || "blackmarketa_bot"}</span></div>
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
        <div><span>Administration du bot</span><h1>{current.label}</h1></div>
      </div>
      <button className="global-search-trigger" onClick={onSearch}>
        <Search size={17} />
        <span>Rechercher commandes, produits ou clients…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className="topbar-actions">
        <button className="header-action" onClick={onRepairTelegram} disabled={Boolean(busyAction)}>
          <Wrench size={16} className={busyAction === "telegram" ? "spin" : ""} /><span>Réparer Telegram</span>
        </button>
        <button className="header-action" onClick={onTestBinance} disabled={Boolean(busyAction)}>
          <ShieldCheck size={16} className={busyAction === "binance" ? "spin" : ""} /><span>Tester Binance</span>
        </button>
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

function StatCard({ label, value, detail, trend, icon: Icon, onClick, tone = "cyan" }) {
  const isPositive = Number(trend) >= 0;
  return (
    <button className="stat-card" onClick={onClick}>
      <div className={`stat-icon ${tone}`}><Icon size={21} /></div>
      <div className="stat-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>
          {trend !== undefined && trend !== null && (
            <b className={isPositive ? "positive" : "negative"}>{isPositive ? "+" : ""}{trend}%</b>
          )}
          {detail}
        </small>
      </div>
      <ChevronRight className="stat-arrow" size={17} />
    </button>
  );
}

function RevenueChart({ data, currency }) {
  const today = Number(data?.revenue_today || 0);
  const week = Number(data?.revenue_7d || 0);
  const month = Number(data?.revenue_30d || 0);
  const values = [week * 0.08, week * 0.11, week * 0.09, week * 0.19, week * 0.14, week * 0.17, today || week * 0.22];
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${index * 100},${116 - (value / max) * 92}`).join(" ");

  return (
    <section className="panel revenue-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">Performance</span><h2>Chiffre d’affaires</h2></div>
        <div className="chart-total"><span>30 derniers jours</span><strong>{formatMoney(month, currency)}</strong></div>
      </div>
      <div className="chart-wrap" aria-label="Aperçu du chiffre d’affaires sur sept jours">
        <svg viewBox="0 0 600 140" role="img" preserveAspectRatio="none">
          <defs>
            <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity=".3" />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[24, 54, 84, 114].map((y) => <line key={y} x1="0" x2="600" y1={y} y2={y} className="grid-line" />)}
          <polygon points={`0,140 ${points} 600,140`} fill="url(#chartFill)" />
          <polyline points={points} fill="none" className="chart-line" />
        </svg>
        <div className="chart-labels"><span>Lun</span><span>Mar</span><span>Mer</span><span>Jeu</span><span>Ven</span><span>Sam</span><span>Aujourd’hui</span></div>
      </div>
      <div className="chart-summary">
        <div><span>Aujourd’hui</span><strong>{formatMoney(today, currency)}</strong></div>
        <div><span>7 jours</span><strong>{formatMoney(week, currency)}</strong></div>
        <div><span>Conversion</span><strong>{Number(data?.conversion_rate || 0).toFixed(1)}%</strong></div>
      </div>
    </section>
  );
}

function AlertsPanel({ alerts = [], onSelect }) {
  return (
    <section className="panel alerts-panel">
      <div className="panel-heading"><div><span className="eyebrow">À surveiller</span><h2>Alertes actives</h2></div><span className="count-chip">{alerts.length}</span></div>
      <div className="alert-list">
        {alerts.length === 0 ? (
          <div className="healthy-state"><div>✓</div><strong>Tout fonctionne normalement</strong><span>Aucune intervention requise.</span></div>
        ) : alerts.slice(0, 5).map((alert, index) => (
          <button className={`alert-row ${alert.severity || "warning"}`} key={`${alert.type}-${index}`} onClick={() => onSelect(alert)}>
            <AlertTriangle size={18} />
            <div><strong>{alert.severity === "error" ? "Action requise" : "Attention"}</strong><span>{alert.message}</span></div>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
      {alerts.length > 5 && <button className="text-button">Voir toutes les alertes <ChevronRight size={16} /></button>}
    </section>
  );
}

function RecentOrders({ orders = [], currency, onOpenLegacy, onSelectOrder }) {
  return (
    <section className="panel orders-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">Activité récente</span><h2>Commandes récentes</h2></div>
        <button className="text-button" onClick={onOpenLegacy}>Tout afficher <ChevronRight size={16} /></button>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Commande</th><th>Client</th><th>Montant</th><th>Statut</th><th>Date</th></tr></thead>
          <tbody>
            {orders.slice(0, 6).map((order) => (
              <tr key={order.id} onClick={() => onSelectOrder(order)} tabIndex="0" onKeyDown={(event) => event.key === "Enter" && onSelectOrder(order)}>
                <td><strong>#{order.id}</strong><span>{order.offer_name || order.service_name || "Commande"}</span></td>
                <td>{order.username ? `@${order.username}` : order.user_id || "—"}</td>
                <td><strong>{formatMoney(orderAmount(order), currency)}</strong></td>
                <td><span className={`status ${order.status || "pending"}`}>{STATUS_LABELS[order.status] || order.status || "—"}</span></td>
                <td>{formatDate(order.created_at)}</td>
              </tr>
            ))}
            {orders.length === 0 && <tr><td colSpan="5" className="empty-cell">Aucune commande récente</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ServicePanel({ services = [], currency, onSelect }) {
  const ranked = [...services].sort((a, b) => Number(b.total_revenue || 0) - Number(a.total_revenue || 0)).slice(0, 5);
  const max = Math.max(...ranked.map((service) => Number(service.total_revenue || 0)), 1);
  return (
    <section className="panel service-panel">
      <div className="panel-heading"><div><span className="eyebrow">Catalogue</span><h2>Services performants</h2></div><PackageSearch size={20} /></div>
      <div className="service-list">
        {ranked.map((service) => (
          <button className="service-row" key={service.id} onClick={() => onSelect(service)}>
            <div className="service-avatar">{initials(service.name)}</div>
            <div className="service-info"><strong>{service.name}</strong><span>{service.total_sales || 0} vente(s) · {service.total_stock || 0} en stock</span><div><i style={{ width: `${(Number(service.total_revenue || 0) / max) * 100}%` }} /></div></div>
            <strong>{formatMoney(service.total_revenue, currency)}</strong>
            <ChevronRight size={15} />
          </button>
        ))}
        {ranked.length === 0 && <div className="empty-cell">Aucun service configuré</div>}
      </div>
    </section>
  );
}

function Overview({ data, onNavigate, onOpenBot }) {
  const summary = data.summary || {};
  const currency = data.currency || "USDT";
  const defaultWidgets = ["revenue", "alerts", "orders", "services"];
  const widgetLabels = { revenue: "Chiffre d’affaires", alerts: "Alertes actives", orders: "Commandes récentes", services: "Services performants" };
  const readStoredArray = (key, fallback) => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || "null");
      return Array.isArray(parsed) ? parsed : fallback;
    } catch { return fallback; }
  };
  const [widgetOrder, setWidgetOrder] = useState(() => {
    const stored = readStoredArray("admin-dashboard-order", defaultWidgets);
    return [...stored.filter((item) => defaultWidgets.includes(item)), ...defaultWidgets.filter((item) => !stored.includes(item))];
  });
  const [hiddenWidgets, setHiddenWidgets] = useState(() => readStoredArray("admin-dashboard-hidden", []));
  const [customizing, setCustomizing] = useState(false);
  const saveOrder = (next) => { setWidgetOrder(next); window.localStorage.setItem("admin-dashboard-order", JSON.stringify(next)); };
  const moveWidget = (id, direction) => {
    const index = widgetOrder.indexOf(id);
    const target = index + direction;
    if (target < 0 || target >= widgetOrder.length) return;
    const next = [...widgetOrder];
    [next[index], next[target]] = [next[target], next[index]];
    saveOrder(next);
  };
  const toggleWidget = (id) => {
    const next = hiddenWidgets.includes(id) ? hiddenWidgets.filter((item) => item !== id) : [...hiddenWidgets, id];
    setHiddenWidgets(next);
    window.localStorage.setItem("admin-dashboard-hidden", JSON.stringify(next));
  };
  const widgets = {
    revenue: <RevenueChart key="revenue" data={summary} currency={currency} />,
    alerts: <AlertsPanel key="alerts" alerts={data.alerts} onSelect={(alert) => onNavigate(alert.type?.includes("stock") ? "inventory" : alert.type?.includes("ticket") ? "support" : "orders")} />,
    orders: <RecentOrders key="orders" orders={data.orders} currency={currency} onOpenLegacy={() => onNavigate("orders")} onSelectOrder={() => onNavigate("orders")} />,
    services: <ServicePanel key="services" services={data.services} currency={currency} onSelect={() => onNavigate("catalog")} />,
  };
  return (
    <>
      <div className="welcome-row">
        <div><span className="eyebrow">Centre de contrôle</span><h2>Bonjour, Admin</h2><p>Voici ce qui se passe dans votre boutique aujourd’hui.</p></div>
        <div className="welcome-actions"><button className="secondary-button" onClick={() => setCustomizing(true)}><Settings size={16} />Personnaliser</button><button className="primary-button" onClick={onOpenBot}>Ouvrir le bot <ChevronRight size={17} /></button></div>
      </div>

      <div className="stats-grid">
        <StatCard label="Revenu aujourd’hui" value={formatMoney(summary.revenue_today, currency)} detail=" vs hier" trend={summary.revenue_yesterday ? ((summary.revenue_day_delta / summary.revenue_yesterday) * 100).toFixed(1) : 0} icon={CircleDollarSign} onClick={() => onNavigate("orders")} tone="cyan" />
        <StatCard label="Commandes" value={summary.orders_today || 0} detail=" aujourd’hui" trend={summary.orders_yesterday ? ((summary.orders_day_delta / summary.orders_yesterday) * 100).toFixed(1) : 0} icon={ShoppingBag} onClick={() => onNavigate("orders")} tone="violet" />
        <StatCard label="Nouveaux clients" value={summary.new_users_today || 0} detail=" cette semaine" trend={summary.users_7d_change_pct || 0} icon={Users} onClick={() => onNavigate("customers")} tone="green" />
        <StatCard label="Stock disponible" value={summary.available_inventory || 0} detail={`${summary.low_stock_offers || 0} offre(s) faible(s)`} icon={Database} onClick={() => onNavigate("inventory")} tone="amber" />
      </div>

      <div className="dashboard-grid custom-layout">
        {widgetOrder.filter((id) => !hiddenWidgets.includes(id)).map((id) => widgets[id])}
      </div>
      {customizing && <div className="dialog-backdrop" onMouseDown={() => setCustomizing(false)}><section className="dashboard-customizer" onMouseDown={(event) => event.stopPropagation()}><header><div><span className="eyebrow">Mise en page</span><h3>Personnaliser le dashboard</h3></div><button className="icon-button" onClick={() => setCustomizing(false)}><X size={17} /></button></header><div className="dashboard-widget-list">{widgetOrder.map((id, index) => <article className={hiddenWidgets.includes(id) ? "hidden" : ""} key={id}><label><input type="checkbox" checked={!hiddenWidgets.includes(id)} onChange={() => toggleWidget(id)} /><span>{widgetLabels[id]}</span></label><div><button disabled={index === 0} onClick={() => moveWidget(id, -1)}>↑</button><button disabled={index === widgetOrder.length - 1} onClick={() => moveWidget(id, 1)}>↓</button></div></article>)}</div><footer><button onClick={() => { saveOrder(defaultWidgets); setHiddenWidgets([]); window.localStorage.removeItem("admin-dashboard-hidden"); }}>Réinitialiser</button><button className="primary-button" onClick={() => setCustomizing(false)}>Terminer</button></footer></section></div>}
    </>
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
  const [refreshing, setRefreshing] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState(null);
  const [pendingActionCount, setPendingActionCount] = useState(0);
  const [density, setDensity] = useState(window.localStorage.getItem("admin-density") === "compact" ? "compact" : "comfortable");
  const [theme, setTheme] = useState(window.localStorage.getItem("admin-theme") === "light" ? "light" : "dark");
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
        lastSyncRef.current = Date.now();
        if (background) window.dispatchEvent(new Event("admin:data-synced"));
      } catch (requestError) {
        if (!background) setError(requestError.message || "Une erreur inattendue est survenue.");
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
      if (type === "telegram") {
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
        const response = await fetch("/admin/api/binance-health", { credentials: "same-origin", cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || "Connexion Binance indisponible.");
        setToast({ title: "Binance opérationnel", message: payload.message || "La connexion API fonctionne correctement." });
      }
    } catch (actionError) {
      setToast({ type: "error", title: type === "telegram" ? "Échec Telegram" : "Échec Binance", message: actionError.message });
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
        <Header activePage={activePage} alertCount={alertCount} busyAction={busyAction} density={density} isRefreshing={refreshing || pendingActionCount > 0} onLogout={logout} onMenu={() => setMobileOpen(true)} onNotifications={() => setNotificationsOpen(true)} onRefresh={() => loadData(true)} onRepairTelegram={() => runHealthCheck("telegram")} onSearch={() => setSearchOpen(true)} onTestBinance={() => runHealthCheck("binance")} onToggleDensity={() => setDensity((current) => { const next = current === "compact" ? "comfortable" : "compact"; window.localStorage.setItem("admin-density", next); return next; })} onToggleTheme={() => setTheme((current) => { const next = current === "dark" ? "light" : "dark"; window.localStorage.setItem("admin-theme", next); return next; })} theme={theme} />
        <main className="content">
          {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => loadData()} /> : !data ? <ErrorState message="La session administrateur n’a pas pu être restaurée." onRetry={() => loadData()} /> : activePage === "overview" ? <Overview data={data} onNavigate={navigate} onOpenBot={() => window.open(`https://t.me/${data.bot_username || "blackmarketa_bot"}`, "_blank", "noopener,noreferrer")} /> : <AdminPage key={activePage} page={activePage} data={data} onAction={adminAction} onHealthCheck={runHealthCheck} onNavigate={navigate} setToast={setToast} />}
        </main>
      </div>
      {searchOpen && data && <SearchDialog data={data} onClose={() => setSearchOpen(false)} onNavigate={navigate} />}
      {notificationsOpen && <NotificationsDrawer alerts={data?.alerts || []} onClose={() => setNotificationsOpen(false)} onNavigate={navigate} />}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
