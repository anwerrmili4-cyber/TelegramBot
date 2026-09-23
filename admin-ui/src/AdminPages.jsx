import SupportInbox from "./SupportInbox";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Archive,
  Ban,
  Boxes,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Columns3,
  Clock3,
  ClipboardList,
  Cloud,
  Copy,
  CreditCard,
  Database,
  Download,
  Edit3,
  ExternalLink,
  Eye,
  Globe2,
  Headphones,
  KeyRound,
  MessageSquareText,
  PackageCheck,
  PackagePlus,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  ShoppingBag,
  SlidersHorizontal,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  TrendingDown,
  TrendingUp,
  Trash2,
  Upload,
  UserRound,
  Users,
  X,
} from "lucide-react";

const STATUS_LABELS = {
  pending_payment: "Paiement en attente",
  awaiting_verification: "À vérifier",
  payment_confirmed: "Paiement confirmé",
  preparing_delivery: "Préparation",
  delivered: "Livrée",
  verification_failed: "Échec de vérification",
  manual_review: "Révision manuelle",
  cancelled: "Annulée",
  refunded: "Remboursée",
  expired: "Expirée",
  paid: "Payée",
  stock_issue: "Problème de stock",
  confirmed: "Confirmé",
  rejected: "Refusée",
  open: "Ouvert",
  waiting_admin: "Attente admin",
  waiting_customer: "Attente client",
  resolved: "Résolu",
  closed: "Fermé",
  pending: "En attente",
  approved: "Approuvé",
  completed: "Terminé",
  pending_admin_check: "Contrôle admin",
  accepted: "Acceptée",
  replacement_pending: "Remplacement requis",
  replacement_delivered: "Remplacement livré",
  refused: "Refusée",
  replacement_sent: "Remplacement envoyé",
  refund_approved: "Remboursement approuvé",
};

const PROVIDERS = [
  ["mailreader", "MailReader"],
  ["shamekh", "Shamekh’s bot"],
  ["kakao", "Kakao Shop"],
  ["vex", "VEX Reseller"],
  ["canboso", "Piggy AI"],
  ["gpt_cheap", "GPT Cheap"],
  ["shop_cron", "Shop Cron"],
  ["upibot", "UPIBot Shop"],
  ["toolorax", "ToolOraX Store Bot"],
  ["cgpt_active", "Rich AI Store"],
];

const PROVIDER_LABELS = Object.fromEntries(PROVIDERS);
const SERVICE_COLORS = ["#a78bfa", "#22d3ee", "#34d399", "#f59e0b", "#fb7185", "#60a5fa"];

function providerLabel(value) {
  return PROVIDER_LABELS[value] || value || "Stock interne";
}

function money(value, currency = "USDT") {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(Number(value || 0))} ${currency}`;
}

function orderAmount(order = {}) {
  return order.charged_total ?? Number(order.total_price || 0) + Number(order.wallet_amount || 0);
}

function orderCustomerName(order = {}) {
  const customer = order.customer || {};
  return order.customer_name
    || customer.full_name
    || [order.first_name || customer.first_name, order.last_name || customer.last_name].filter(Boolean).join(" ")
    || (order.username || customer.username ? `@${order.username || customer.username}` : `Client ${order.user_id || customer.telegram_id || "—"}`);
}

function orderCustomerReference(order = {}) {
  const customer = order.customer || {};
  const username = order.username || customer.username;
  const userId = order.user_id || customer.telegram_id || "—";
  return `${username ? `@${username} · ` : ""}ID ${userId}`;
}

function date(value) {
  if (!value) return "—";
  const parsed =
    typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(parsed);
}

function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

function ActionButton({
  children,
  icon: Icon,
  secondary = false,
  danger = false,
  ...props
}) {
  return (
    <button
      className={`action-button ${secondary ? "secondary" : ""} ${danger ? "danger" : ""}`}
      {...props}
    >
      {Icon && <Icon size={16} />}
      {children}
    </button>
  );
}

function Modal({ title, children, onClose, wide = false, fullScreen = false }) {
  const dialog = useRef(null);
  useEffect(() => {
    const node = dialog.current;
    const previous = document.body.style.overflow;
    node.showModal();
    document.body.style.overflow = "hidden";
    return () => { node.close(); document.body.style.overflow = previous; };
  }, []);
  return (
      <dialog ref={dialog} aria-label={title}
        className={`form-dialog ${wide ? "wide" : ""} ${fullScreen ? "full-screen" : ""}`}
        onCancel={(event) => { event.preventDefault(); onClose(); }}
      >
        <header>
          <h3>{title}</h3>
          <button type="button" onClick={onClose} aria-label="Fermer la fenêtre">
            <X size={19} />
          </button>
        </header>
        <div className="form-dialog-body">{children}</div>
      </dialog>
  );
}

function Field({ label, children, wide = false }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Empty({
  icon: Icon = Database,
  title = "Aucune donnée",
  text = "Les éléments apparaîtront ici.",
}) {
  return (
    <div className="page-empty">
      <Icon size={28} />
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function FilterBar({
  search,
  setSearch,
  children,
  placeholder = "Rechercher…",
  options = [],
  searchField = "all",
  setSearchField,
  resultCount,
}) {
  return (
    <div className={`filter-bar ${search ? "has-search" : ""}`}>
      <label className="smart-search">
        <Search size={17} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
        />
        {search && <button type="button" onClick={() => setSearch("")} title="Effacer la recherche" aria-label="Effacer la recherche"><X size={15} /></button>}
      </label>
      {options.length > 0 && (
        <label className="search-field-select">
          <span>Rechercher par</span>
          <select value={searchField} onChange={(event) => setSearchField?.(event.target.value)}>
            {options.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
        </label>
      )}
      {children}
      {search && resultCount !== undefined && <span className="search-result-count">{resultCount} résultat(s)</span>}
    </div>
  );
}

function Pagination({ value, onChange }) {
  if (!value || value.pages <= 1) return null;
  return (
    <div className="pagination">
      <button
        disabled={value.page <= 1}
        onClick={() => onChange(value.page - 1)}
      >
        <ChevronLeft size={16} /> Précédent
      </button>
      <span>
        Page {value.page} sur {value.pages} · {value.total} résultat(s)
      </span>
      <button
        disabled={value.page >= value.pages}
        onClick={() => onChange(value.page + 1)}
      >
        Suivant <ChevronRight size={16} />
      </button>
    </div>
  );
}

function useRemoteList(endpoint, filters, { refreshInterval = 0 } = {}) {
  const [result, setResult] = useState({
    items: [],
    page: 1,
    pages: 1,
    total: 0,
  });
  const [loading, setLoading] = useState(true);
  const [syncVersion, setSyncVersion] = useState(0);
  const query = new URLSearchParams(
    Object.entries(filters)
      .filter(([, value]) => value !== "" && value != null)
      .map(([key, value]) => [key, String(value)]),
  ).toString();
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    const synchronize = () => setSyncVersion((value) => value + 1);
    window.addEventListener("admin:data-synced", synchronize);
    return () => window.removeEventListener("admin:data-synced", synchronize);
  }, []);
  useEffect(() => {
    if (!refreshInterval) return undefined;
    const refresh = () => {
      if (document.visibilityState === "visible" && navigator.onLine) setSyncVersion((value) => value + 1);
    };
    const timer = window.setInterval(refresh, refreshInterval);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [refreshInterval]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    fetch(`${endpoint}?${debouncedQuery}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    })
      .then((response) => {
        if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        setResult({
          ...payload,
          items: Array.isArray(payload?.items) ? payload.items : [],
          page: Number(payload?.page) || 1,
          pages: Math.max(1, Number(payload?.pages) || 1),
          total: Math.max(0, Number(payload?.total) || 0),
        });
      })
      .catch((error) => {
        if (active && error.name !== "AbortError") window.dispatchEvent(new CustomEvent("admin:read-error", { detail: "La liste n’a pas pu être actualisée. Réessayez avant d’agir." }));
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      controller.abort();
    };
  }, [endpoint, debouncedQuery, syncVersion]);
  return [result, loading];
}

function DeliveredProductDescription({ order, compact = false }) {
  const [copied, setCopied] = useState(false);
  if (order.status !== "delivered") return null;
  const description = order.product_description || "Description indisponible pour cette ancienne commande.";
  const copyDescription = async () => {
    if (!navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(description);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  return (
    <div className={`delivered-product-description ${compact ? "compact" : ""}`}>
      <header><span>Description du produit</span>{!compact && order.product_description && <button type="button" onClick={copyDescription} aria-label="Copier la description du produit"><Copy size={14} />{copied ? "Copié" : "Copier"}</button>}</header>
      <p>{description}</p>
      {!compact && <small className="copy-description-status" aria-live="polite">{copied ? "Description copiée dans le presse-papiers." : ""}</small>}
    </div>
  );
}

function OrderDetailPage({ order, onAction, onBack, onNavigate, onReload, currency }) {
  const [status, setStatus] = useState(order.status || "pending_payment");
  const [note, setNote] = useState(order.admin_note || "");
  const [message, setMessage] = useState("");
  const [delivery, setDelivery] = useState(
    order.delivery_content ||
      (order.delivery_text === "[encrypted automatic delivery]"
        ? ""
        : order.delivery_text || ""),
  );
  const [confirmation, setConfirmation] = useState(null);
  const customer = order.customer || {};
  const submit = async (action, extra = {}) => {
    if (await onAction({ action, order_id: order.id, ...extra })) {
      setConfirmation(null);
      await onReload();
    }
  };
  const requestSensitiveAction = (action, label, extra) => setConfirmation({ action, label, extra });
  const timeline = [
    { label: "Commande créée", value: order.created_at, complete: true },
    { label: "Paiement reçu", value: order.paid_at || order.confirmed_at, complete: Boolean(order.paid_at || order.confirmed_at || ["paid", "payment_confirmed", "preparing_delivery", "delivered"].includes(order.status)) },
    { label: "Paiement confirmé", value: order.verified_at || order.confirmed_at, complete: ["payment_confirmed", "preparing_delivery", "delivered"].includes(order.status) },
    { label: "Commande livrée", value: order.delivered_at, complete: order.status === "delivered" },
  ];
  return (
    <div className="order-detail-page">
      <header className="order-detail-header">
        <button type="button" onClick={onBack}><ArrowLeft size={18} />Toutes les commandes</button>
        <div><span className="eyebrow">Dossier de commande</span><h2>Commande #{order.id}</h2><p>{order.offer_name || order.service_name || "Produit sans nom"}</p></div>
        <span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status || "—"}</span>
      </header>

      <section className="order-detail-summary">
        <article><span><CircleDollarSign size={18} /></span><div><small>Montant encaissé</small><strong>{money(orderAmount(order), currency)}</strong><em>{order.qty || 1} × {money(order.unit_price, currency)}</em></div></article>
        <article className="order-customer-summary"><span><UserRound size={18} /></span><button type="button" onClick={() => onNavigate("customers", order.user_id || customer.telegram_id)} title="Ouvrir le profil client"><small>Client</small><strong>{orderCustomerName(order)} <ExternalLink size={13} /></strong><em>{orderCustomerReference(order)}</em></button></article>
        <article><span><CreditCard size={18} /></span><div><small>Paiement</small><strong>{order.verify_method || "Non renseigné"}</strong><em>{order.txid ? `TXID ${order.txid}` : "Aucun TXID"}</em></div></article>
        <article><span><PackageCheck size={18} /></span><div><small>Livraison</small><strong>{order.delivered_at ? "Effectuée" : "En attente"}</strong><em>{order.delivered_at ? date(order.delivered_at) : "À traiter"}</em></div></article>
      </section>

      <div className="order-detail-layout">
        <div className="order-detail-main">
          <section className="order-detail-card order-progress-card">
            <header><div><span className="eyebrow">Progression</span><h3>Chronologie de la commande</h3></div><Clock3 size={19} /></header>
            <div className="order-progress">{timeline.map((step, index) => <article className={step.complete ? "complete" : ""} key={step.label}><i>{step.complete ? <Check size={14} /> : index + 1}</i><div><strong>{step.label}</strong><small>{step.value ? date(step.value) : step.complete ? "Terminé" : "En attente"}</small></div></article>)}</div>
          </section>

          <section className="order-detail-card">
            <header><div><span className="eyebrow">Informations</span><h3>Détails commerciaux et techniques</h3></div></header>
            <div className="order-facts">
              <div><span>Produit</span><strong>{order.offer_name || order.service_name || "—"}</strong></div>
              {order.status === "delivered" && <div className="wide order-product-description-detail"><DeliveredProductDescription order={order} /></div>}
              <div><span>Commande créée</span><strong>{date(order.created_at)}</strong></div>
              <div><span>ID offre</span><strong>{order.offer_id || "—"}</strong></div>
              <div><span>Quantité</span><strong>{order.qty || 1}</strong></div>
              <div><span>Prix unitaire</span><strong>{money(order.unit_price, currency)}</strong></div>
              <div><span>Note administrateur</span><strong>{order.admin_note || "Aucune note"}</strong></div>
              <div className="wide"><span>TXID</span><strong title={order.txid || ""}>{order.txid || "Aucun identifiant de transaction"}</strong></div>
            </div>
          </section>

          <section className="delivery-detail">
            <header><div><span>Contenu livré au client</span><small>{delivery ? "Contenu complet de la livraison" : "Aucun contenu livré pour cette commande"}</small></div>{delivery && <button type="button" onClick={() => navigator.clipboard?.writeText(delivery)} title="Copier le contenu"><Copy size={15} /> Copier</button>}</header>
            <pre>{delivery || "—"}</pre>
          </section>
        </div>

        <aside className="order-action-panel">
          <header><span className="eyebrow">Pilotage</span><h3>Mettre à jour la commande</h3><p>Les changements sont appliqués et synchronisés immédiatement.</p></header>
          <Field label="Statut"><select value={status} onChange={(event) => setStatus(event.target.value)}>{Object.entries(STATUS_LABELS).slice(0, 11).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field>
          <Field label="Note administrateur"><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note interne…" /></Field>
          <ActionButton icon={Check} onClick={() => submit("update_order_admin", { status, admin_note: note })}>Enregistrer les changements</ActionButton>
          <hr />
          <Field label="Message au client"><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Message Telegram…" /></Field>
          <ActionButton secondary icon={Send} disabled={!message.trim()} onClick={() => submit("message_customer", { message })}>Envoyer le message</ActionButton>
          <Field label="Contenu de livraison"><textarea value={delivery} onChange={(event) => setDelivery(event.target.value)} placeholder="Identifiants ou code…" /></Field>
          <ActionButton secondary icon={PackagePlus} disabled={!delivery.trim()} onClick={() => submit("manual_deliver_order", { delivery_text: delivery })}>Livrer la commande</ActionButton>
          <div className="order-secondary-actions"><button type="button" onClick={() => submit("reset_order")}><RefreshCw size={15} />Réinitialiser</button><button type="button" onClick={() => submit("resend_delivery")}><Send size={15} />Renvoyer</button></div>
          <hr />
          <div className="order-danger-actions"><button type="button" onClick={() => requestSensitiveAction("refund_order", "Confirmer le remboursement", { reason: note || "Remboursement depuis le dashboard React" })}><CircleDollarSign size={15} />Rembourser</button><button type="button" onClick={() => requestSensitiveAction("cancel_order", "Confirmer l’annulation", { reason: note || "Annulée depuis le dashboard React" })}><X size={15} />Annuler</button></div>
          {confirmation && <div className="order-confirmation" role="alertdialog" aria-label={confirmation.label}><div><strong>{confirmation.label} ?</strong><span>Cette action peut notifier le client.</span></div><button type="button" onClick={() => setConfirmation(null)}>Retour</button><button type="button" className="danger" onClick={() => submit(confirmation.action, confirmation.extra)}>Confirmer</button></div>}
        </aside>
      </div>
    </div>
  );
}

function OrdersPage({ data, onAction, onNavigate }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("");
  const [queue, setQueue] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("date");
  const [direction, setDirection] = useState("desc");
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [viewMode, setViewMode] = useState(() => window.matchMedia("(max-width: 640px)").matches ? "cards" : window.localStorage.getItem("admin-orders-view") || "table");
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(() => {
    const defaults = ["customer", "product", "amount", "status", "date"];
    try {
      const stored = JSON.parse(window.localStorage.getItem("admin-orders-columns") || "null");
      return Array.isArray(stored) ? stored : defaults;
    } catch {
      return defaults;
    }
  });
  const toggleColumn = (column) => {
    const next = visibleColumns.includes(column)
      ? visibleColumns.filter((item) => item !== column)
      : [...visibleColumns, column];
    setVisibleColumns(next);
    window.localStorage.setItem("admin-orders-columns", JSON.stringify(next));
  };
  const [result, loading] = useRemoteList("/admin/api/orders", {
    search,
    search_field: searchField,
    status,
    queue,
    page,
    per_page: 25,
    sort,
    direction,
  }, { refreshInterval: 5_000 });
  const analytics = result.analytics || {};
  const daily = analytics.daily || [];
  const chartPoints = useMemo(() => {
    const maximum = Math.max(...daily.map((item) => Number(item.count || 0)), 1);
    return daily.map((item, index) => ({
      ...item,
      x: daily.length <= 1 ? 0 : (index / (daily.length - 1)) * 600,
      y: 142 - (Number(item.count || 0) / maximum) * 112,
    }));
  }, [daily]);
  const maximumRevenue = Math.max(...daily.map((item) => Number(item.revenue || 0)), 1);
  const statusSegments = useMemo(() => {
    const colors = {
      delivered: "#34d399",
      paid: "#d9f780",
      payment_confirmed: "#a9c878",
      cancelled: "#fb7185",
      refunded: "#f97316",
      pending_payment: "#fbbf24",
      manual_review: "#d4b77a",
    };
    return Object.entries(analytics.statuses || {})
      .map(([key, value]) => ({ key, value, color: colors[key] || "#8b9982" }))
      .sort((a, b) => b.value - a.value);
  }, [analytics.statuses]);
  const kanbanColumns = useMemo(() => [
    { id: "waiting", label: "À vérifier", statuses: ["pending_payment", "awaiting_verification", "manual_review"] },
    { id: "confirmed", label: "Confirmées", statuses: ["paid", "payment_confirmed"] },
    { id: "delivery", label: "Livraison", statuses: ["preparing_delivery", "stock_issue"] },
    { id: "completed", label: "Terminées", statuses: ["delivered", "refunded", "cancelled", "rejected", "expired", "verification_failed"] },
  ].map((column) => ({
    ...column,
    items: (result.items || []).filter((item) => column.statuses.includes(item.status)),
    total: column.statuses.reduce((sum, itemStatus) => sum + Number(analytics.statuses?.[itemStatus] || 0), 0),
  })), [result.items, analytics.statuses]);
  const pipelineMaximum = Math.max(...kanbanColumns.map((column) => column.total), 1);
  const totalStatuses = statusSegments.reduce((sum, item) => sum + item.value, 0);
  let donutCursor = 0;
  const donutBackground = statusSegments.length
    ? `conic-gradient(${statusSegments.map((item) => {
        const start = donutCursor;
        donutCursor += (item.value / totalStatuses) * 100;
        return `${item.color} ${start}% ${donutCursor}%`;
      }).join(", ")})`
    : "conic-gradient(var(--line) 0 100%)";
  const toggleSort = (nextSort) => {
    if (sort === nextSort) setDirection((value) => (value === "desc" ? "asc" : "desc"));
    else {
      setSort(nextSort);
      setDirection("desc");
    }
    setPage(1);
  };
  const openOrder = async (order, updateRoute = true) => {
    setDetailLoading(true);
    try {
      const response = await fetch(`/admin/api/orders?detail=1&order_id=${order.id}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      setSelected(response.ok ? await response.json() : order);
      window.scrollTo({ top: 0, behavior: "auto" });
      const target = `/admin/orders/${encodeURIComponent(order.id)}`;
      if (updateRoute && window.location.pathname !== target) {
        const notificationRoute = new URLSearchParams(window.location.search).get("order") === String(order.id);
        window.history[notificationRoute ? "replaceState" : "pushState"]({}, "", target);
      }
    } finally {
      setDetailLoading(false);
    }
  };
  const closeOrder = () => {
    setSelected(null);
    window.scrollTo({ top: 0, behavior: "auto" });
    window.history.pushState({}, "", "/admin/orders");
  };
  useEffect(() => {
    const pathMatch = window.location.pathname.match(/^\/admin\/orders\/(\d+)\/?$/);
    const requested = pathMatch?.[1] || new URLSearchParams(window.location.search).get("order");
    if (requested && /^\d+$/.test(requested)) openOrder({ id: Number(requested) });
    const navigateToOrder = (event) => {
      if (event.detail?.page === "orders" && event.detail?.entityId != null) openOrder({ id: event.detail.entityId });
    };
    const restoreOrderRoute = () => {
      const match = window.location.pathname.match(/^\/admin\/orders\/(\d+)\/?$/);
      if (match) openOrder({ id: Number(match[1]) }, false);
      else setSelected(null);
    };
    window.addEventListener("admin:navigate", navigateToOrder);
    window.addEventListener("popstate", restoreOrderRoute);
    return () => {
      window.removeEventListener("admin:navigate", navigateToOrder);
      window.removeEventListener("popstate", restoreOrderRoute);
    };
  }, []);
  if (selected) return <OrderDetailPage key={selected.id} order={selected} currency={data.currency} onAction={onAction} onBack={closeOrder} onNavigate={onNavigate} onReload={() => openOrder({ id: selected.id }, false)} />;
  if (detailLoading) return <div className="order-detail-loading"><RefreshCw className="spin" size={24} /><strong>Ouverture de la commande…</strong></div>;
  return (
    <>
      <PageHeader
        eyebrow="Ventes"
        title="Vos commandes, en un seul endroit."
        description="Suivez les paiements, livraisons et interventions manuelles."
      />
      <section className="order-kpis" aria-label="Statistiques des commandes">
        <article><span className="order-kpi-icon violet"><ClipboardList size={19} /></span><div><small>Total commandes</small><strong>{analytics.total || 0}</strong><em>Volume global</em></div></article>
        <article><span className="order-kpi-icon cyan"><CircleDollarSign size={19} /></span><div><small>Chiffre d'affaires</small><strong>{money(analytics.revenue, data.currency)}</strong><em>Commandes encaissées</em></div></article>
        <article><span className="order-kpi-icon green"><CheckCircle2 size={19} /></span><div><small>Taux de livraison</small><strong>{analytics.success_rate || 0}%</strong><em>{analytics.delivered || 0} livrée(s)</em></div></article>
        <article><span className="order-kpi-icon amber"><Clock3 size={19} /></span><div><small>À traiter</small><strong>{analytics.pending || 0}</strong><em>Action requise</em></div></article>
      </section>
      <details className="workspace-analytics order-analytics-visible"><summary><TrendingUp size={19} /><span>Analyse des commandes<small>Activité sur 7 jours, statuts et progression</small></span></summary><div className="order-analytics-grid">
        <article className="data-panel order-trend-card">
          <header><div><span className="eyebrow">Activité</span><h3>Volume et revenus sur 7 jours</h3></div><div className="chart-key"><span><i className="volume" />Commandes</span><span><i className="revenue" />Revenus</span></div></header>
          <div className="order-line-chart">
            <svg viewBox="0 0 600 160" preserveAspectRatio="none" role="img" aria-label="Courbe des commandes sur 7 jours">
              {[30, 86, 142].map((y) => <line key={y} x1="0" x2="600" y1={y} y2={y} className="order-grid-line" />)}
              {daily.map((item, index) => <rect key={`revenue-${item.date}`} x={(index / Math.max(daily.length, 1)) * 600 + 10} y={150 - (Number(item.revenue || 0) / maximumRevenue) * 92} width={Math.max(16, 600 / Math.max(daily.length, 1) - 25)} height={(Number(item.revenue || 0) / maximumRevenue) * 92} rx="5" className="order-revenue-bar"><title>{money(item.revenue, data.currency)} encaissé</title></rect>)}
              {chartPoints.length > 1 && <polygon points={`0,160 ${chartPoints.map((point) => `${point.x},${point.y}`).join(" ")} 600,160`} className="order-area" />}
              {chartPoints.length > 1 && <polyline points={chartPoints.map((point) => `${point.x},${point.y}`).join(" ")} className="order-chart-line" />}
              {chartPoints.map((point) => <circle key={point.date} cx={point.x} cy={point.y} r="4" className="order-chart-dot"><title>{point.count} commande(s)</title></circle>)}
            </svg>
            <div className="order-chart-labels">{daily.map((item) => <span key={item.date}>{new Intl.DateTimeFormat("fr-FR", { weekday: "short" }).format(new Date(`${item.date}T12:00:00`))}</span>)}</div>
          </div>
        </article>
        <article className="data-panel order-status-card">
          <header><div><span className="eyebrow">Répartition</span><h3>Statuts des commandes</h3></div></header>
          <div className="order-status-content">
            <div className="order-donut" style={{ background: donutBackground }}><div><strong>{analytics.total || 0}</strong><span>Total</span></div></div>
            <div className="order-legend">{statusSegments.slice(0, 5).map((item) => <button key={item.key} onClick={() => { setStatus(item.key); setPage(1); }}><i style={{ background: item.color }} /><span>{STATUS_LABELS[item.key] || item.key}</span><strong>{item.value}</strong></button>)}</div>
          </div>
        </article>
        <article className="data-panel order-pipeline-card">
          <header><div><span className="eyebrow">Flux opérationnel</span><h3>Progression des commandes</h3></div><Boxes size={19} /></header>
          <div className="order-pipeline">{kanbanColumns.map((column) => <button type="button" key={column.id} onClick={() => { setStatus(""); setQueue(column.id === "waiting" ? "attention" : column.id === "delivery" ? "delivery" : ""); setPage(1); }}><div><span>{column.label}</span><strong>{column.total}</strong></div><i><b className={column.id} style={{ width: `${Math.max(4, column.total / pipelineMaximum * 100)}%` }} /></i><small>{analytics.total ? Math.round(column.total / analytics.total * 100) : 0}% du total</small></button>)}</div>
        </article>
      </div></details>
      <div className="workspace-tabs order-quick-filters" role="group" aria-label="Files de commandes"><button aria-pressed={!status && !queue} onClick={() => { setStatus(""); setQueue(""); setPage(1); }}>Toutes</button><button aria-pressed={queue === "attention"} onClick={() => { setStatus(""); setQueue("attention"); setPage(1); }}>Urgentes <span>{analytics.attention || 0}</span></button><button aria-pressed={status === "manual_review"} onClick={() => { setQueue(""); setStatus("manual_review"); setPage(1); }}>À vérifier</button><button aria-pressed={status === "pending_payment"} onClick={() => { setQueue(""); setStatus("pending_payment"); setPage(1); }}>Paiement en attente</button><button aria-pressed={queue === "delivery"} onClick={() => { setStatus(""); setQueue("delivery"); setPage(1); }}>À livrer</button><button aria-pressed={status === "delivered"} onClick={() => { setQueue(""); setStatus("delivered"); setPage(1); }}>Livrées</button></div>
      <FilterBar
        search={search}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["name", "Produit / service"], ["txid", "TXID"], ["order_id", "ID commande"], ["user_id", "ID client"]]}
        resultCount={result.total}
        setSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
        placeholder="Nom, TXID, ID commande ou client…"
      >
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setQueue("");
            setPage(1);
          }}
        >
          <option value="">Tous les statuts</option>
          {Object.entries(STATUS_LABELS)
            .slice(0, 11)
            .map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
        </select>
        <select value={`${sort}-${direction}`} onChange={(event) => { const [nextSort, nextDirection] = event.target.value.split("-"); setSort(nextSort); setDirection(nextDirection); setPage(1); }} aria-label="Trier les commandes">
          <option value="date-desc">Plus récentes</option>
          <option value="date-asc">Plus anciennes</option>
          <option value="amount-desc">Montant décroissant</option>
          <option value="amount-asc">Montant croissant</option>
        </select>
        <div className="order-view-switch" aria-label="Mode d’affichage"><button className={viewMode === "cards" ? "active" : ""} onClick={() => { setViewMode("cards"); window.localStorage.setItem("admin-orders-view", "cards"); }} type="button"><ClipboardList size={14} />Cartes</button><button className={viewMode === "table" ? "active" : ""} onClick={() => { setViewMode("table"); window.localStorage.setItem("admin-orders-view", "table"); }} type="button"><ClipboardList size={14} />Tableau</button><button className={viewMode === "kanban" ? "active" : ""} onClick={() => { setViewMode("kanban"); window.localStorage.setItem("admin-orders-view", "kanban"); }} type="button"><Boxes size={14} />Kanban</button></div>
        {viewMode === "table" && <button className="column-picker-trigger" type="button" onClick={() => setColumnsOpen(true)}><Columns3 size={14} />Colonnes</button>}
      </FilterBar>
      <section className="data-panel">
        {viewMode === "cards" ? <div className="mobile-order-cards">{result.items.map((order) => <button className={order.needs_attention ? "needs-attention" : ""} key={order.id} onClick={() => openOrder(order)}><header><strong>#{order.id}</strong><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></header>{order.attention_reason && <em className="order-attention">{order.attention_reason}</em>}<h3>{order.offer_name || order.service_name || "Produit"}</h3><DeliveredProductDescription order={order} compact /><span className="order-customer-display"><strong>{orderCustomerName(order)}</strong><small>{orderCustomerReference(order)}</small></span><footer><strong>{money(orderAmount(order), data.currency)}</strong><span>{date(order.created_at)}</span></footer><small>Ouvrir la fiche et les actions →</small></button>)}</div> : viewMode === "table" ? <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th><button className={`sort-button ${sort === "date" ? "active" : ""}`} onClick={() => toggleSort("date")}>Commande <span>{sort === "date" ? (direction === "desc" ? "↓" : "↑") : "↕"}</span></button></th>
                {visibleColumns.includes("customer") && <th>Client</th>}
                {visibleColumns.includes("product") && <th>Produit</th>}
                {visibleColumns.includes("amount") && <th><button className={`sort-button ${sort === "amount" ? "active" : ""}`} onClick={() => toggleSort("amount")}>Montant <span>{sort === "amount" ? (direction === "desc" ? "↓" : "↑") : "↕"}</span></button></th>}
                {visibleColumns.includes("status") && <th>Statut</th>}
                {visibleColumns.includes("date") && <th>Date</th>}
                <th />
              </tr>
            </thead>
            <tbody>
              {result.items.map((order) => (
                <tr className={order.needs_attention ? "needs-attention" : ""} key={order.id} onClick={() => openOrder(order)}>
                  <td>
                    <strong>#{order.id}</strong>
                  </td>
                  {visibleColumns.includes("customer") && <td><button type="button" className="order-table-customer" onClick={(event) => { event.stopPropagation(); onNavigate("customers", order.user_id); }} title="Ouvrir le profil client"><strong>{orderCustomerName(order)} <ExternalLink size={12} /></strong><small>{orderCustomerReference(order)}</small></button></td>}
                  {visibleColumns.includes("product") && <td><div className="order-table-product"><strong>{order.offer_name || order.service_name || "—"}</strong><DeliveredProductDescription order={order} compact /></div></td>}
                  {visibleColumns.includes("amount") && <td>
                    <strong>{money(orderAmount(order), data.currency)}</strong>
                  </td>}
                  {visibleColumns.includes("status") && <td>
                    <span className={`status ${order.status}`}>
                      {STATUS_LABELS[order.status] || order.status}
                    </span>
                  </td>}
                  {visibleColumns.includes("date") && <td>{date(order.created_at)}</td>}
                  <td>
                    <button className="row-action">
                      <Edit3 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div> : <div className="orders-kanban">{kanbanColumns.map((column) => <section className={`kanban-column ${column.id}`} key={column.id}><header><div><span>{column.label}</span><small>{column.items.length} sur cette page</small></div><strong>{column.total}</strong></header><div className="kanban-cards">{column.items.map((order) => <button className={`kanban-order ${order.needs_attention ? "needs-attention" : ""}`} onClick={() => openOrder(order)} key={order.id}><div><strong>#{order.id}</strong><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></div>{order.attention_reason && <em className="order-attention">{order.attention_reason}</em>}<h4>{order.offer_name || order.service_name || "Produit"}</h4><DeliveredProductDescription order={order} compact /><span className="order-customer-display"><strong>{orderCustomerName(order)}</strong><small>{orderCustomerReference(order)}</small></span><footer><b>{money(orderAmount(order), data.currency)}</b><small>{date(order.created_at)}</small></footer></button>)}{!column.items.length && <div className="kanban-empty">Aucune commande sur cette page</div>}</div></section>)}</div>}
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !result.items.length && (
            <Empty icon={ClipboardList} title="Aucune commande" />
          )
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {columnsOpen && <Modal title="Colonnes du tableau" onClose={() => setColumnsOpen(false)}><div className="column-picker"><p>Choisissez les informations visibles. Ce réglage est mémorisé sur cet appareil.</p>{[["customer", "Client"], ["product", "Produit"], ["amount", "Montant"], ["status", "Statut"], ["date", "Date"]].map(([key, label]) => <label key={key}><input type="checkbox" checked={visibleColumns.includes(key)} onChange={() => toggleColumn(key)} /><span>{label}</span><Check size={15} /></label>)}<div><ActionButton secondary onClick={() => { const all = ["customer", "product", "amount", "status", "date"]; setVisibleColumns(all); window.localStorage.setItem("admin-orders-columns", JSON.stringify(all)); }}>Tout afficher</ActionButton><ActionButton onClick={() => setColumnsOpen(false)}>Terminer</ActionButton></div></div></Modal>}
    </>
  );
}

async function optimizeProductImage(file) {
  const allowed = ["image/jpeg", "image/png", "image/webp"];
  if (!allowed.includes(file.type)) throw new Error("Choisissez une image JPG, PNG ou WebP.");
  if (file.size > 8_000_000) throw new Error("L’image originale doit faire moins de 8 Mo.");
  const source = URL.createObjectURL(file);
  try {
    const image = await new Promise((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error("Cette image ne peut pas être lue."));
      element.src = source;
    });
    const scale = Math.min(1, 1400 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    const makeBlob = (quality) => new Promise((resolve) => canvas.toBlob(resolve, "image/webp", quality));
    let blob = await makeBlob(0.84);
    if (blob?.size > 1_100_000) blob = await makeBlob(0.68);
    if (!blob || blob.size > 1_200_000) throw new Error("L’image reste trop volumineuse après optimisation.");
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Impossible de lire l’image."));
      reader.readAsDataURL(blob);
    });
    return { data, type: blob.type || "image/png", size: blob.size };
  } finally {
    URL.revokeObjectURL(source);
  }
}

function OfferForm({ services, offer, onAction, onClose, defaultChannel = "both" }) {
  const currentChannels = offer?.sales_channels || ["bot"];
  const [form, setForm] = useState({
    service_id: offer?.service_id || services[0]?.id || "",
    name: offer?.name || "",
    emoji: offer?.custom_emoji_id || offer?.emoji || "",
    price: offer?.price ?? "",
    bulk_quantity: offer?.bulk_quantity ?? 0,
    bulk_unit_price: offer?.bulk_unit_price ?? "",
    description: offer?.description || "",
    note: offer?.note || "",
    period_value: offer?.period_value ?? offer?.period_days ?? 30,
    period_unit: offer?.period_unit || "days",
    warranty_value: offer?.warranty_value ?? offer?.warranty_days ?? (offer?.note === "NW" ? 0 : (Number((offer?.note || "").match(/\d+/)?.[0]) || 0)),
    warranty_unit: offer?.warranty_unit || "days",
    delivery_delay: offer?.delivery_delay || "Instantané après confirmation",
    low_stock_threshold: offer?.low_stock_threshold ?? 5,
    auto_delivery: offer?.auto_delivery !== false,
    initial_inventory: "",
    sales_channel: "bot",
    name_ar: offer?.name_ar || "",
    description_ar: offer?.description_ar || "",
  });
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event) => {
    event.preventDefault();
    const action = offer ? "update_offer" : "add_offer";
    const factors = { days: 1, months: 30, years: 365 };
    const periodDays = Number(form.period_value || 0) * factors[form.period_unit];
    const warrantyDays = Number(form.warranty_value || 0) * factors[form.warranty_unit];
    const payload = {
      ...form,
      period_days: periodDays,
      warranty_days: warrantyDays,
      note: warrantyDays === 0 ? "NW" : `${form.warranty_value} ${form.warranty_unit}`,
      action,
      custom_emoji_id: form.emoji,
      ...(offer
        ? { offer_id: offer.id, sort_order: offer.sort_order || 0 }
        : {}),
      auto_delivery: form.auto_delivery ? "on" : "",
    };
    if (await onAction(payload)) onClose();
  };
  return (
    <Modal
      title={offer ? "Modifier le produit" : "Nouveau produit"}
      onClose={onClose}
      wide
    >
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Service">
            <select
              value={form.service_id}
              onChange={(event) => set("service_id", event.target.value)}
            >
              {services.map((service) => (
                <option value={service.id} key={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Nom">
            <input
              required
              value={form.name}
              onChange={(event) => set("name", event.target.value)}
            />
          </Field>
          <Field label="Emoji / Icône">
            <input
              value={form.emoji}
              onChange={(event) => set("emoji", event.target.value)}
              placeholder="Ex: 🤖, 🍿, ✈️..."
              style={{ maxWidth: 100, textAlign: "center", fontSize: "1.2rem" }}
            />
          </Field>
          <Field label="Canal de vente">
            <select value={form.sales_channel} onChange={(event) => set("sales_channel", event.target.value)}>
              <option value="bot">Bot uniquement</option>
            </select>
          </Field>
          <Field label="Prix">
            <input
              required
              min="0"
              step="0.01"
              type="number"
              value={form.price}
              onChange={(event) => set("price", event.target.value)}
            />
          </Field>
          <Field label="Quantité en gros">
            <input
              min="0"
              step="1"
              type="number"
              value={form.bulk_quantity}
              onChange={(event) => set("bulk_quantity", event.target.value)}
              placeholder="0 = désactivé"
            />
          </Field>
          <Field label="Prix en gros / unité">
            <input
              min="0"
              step="0.01"
              type="number"
              value={form.bulk_unit_price}
              onChange={(event) => set("bulk_unit_price", event.target.value)}
              placeholder="Prix réduit par unité"
            />
          </Field>
          <Field label="Seuil de stock">
            <input
              min="0"
              type="number"
              value={form.low_stock_threshold}
              onChange={(event) =>
                set("low_stock_threshold", event.target.value)
              }
            />
          </Field>
          <Field label="Description" wide>
            <textarea
              value={form.description}
              onChange={(event) => set("description", event.target.value)}
            />
          </Field>
          <Field label="Nom arabe" wide>
            <input dir="rtl" value={form.name_ar} onChange={(event) => set("name_ar", event.target.value)} placeholder="اسم المنتج بالعربية" />
          </Field>
          <Field label="Description arabe" wide>
            <textarea dir="rtl" value={form.description_ar} onChange={(event) => set("description_ar", event.target.value)} placeholder="وصف المنتج بالعربية" />
          </Field>
          <Field label="Période">
            <div className="duration-input">
              <input type="number" min="1" value={form.period_value} onChange={(event) => set("period_value", event.target.value)} required />
              <select value={form.period_unit} onChange={(event) => set("period_unit", event.target.value)}>
                <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
              </select>
            </div>
          </Field>
          <Field label="Garantie (0 = NW)">
            <div className="duration-input">
              <input type="number" min="0" value={form.warranty_value} onChange={(event) => set("warranty_value", event.target.value)} required />
              <select value={form.warranty_unit} onChange={(event) => set("warranty_unit", event.target.value)}>
                <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
              </select>
            </div>
          </Field>
          {!offer && (
            <Field label="Stock initial" wide>
              <textarea
                value={form.initial_inventory}
                onChange={(event) =>
                  set("initial_inventory", event.target.value)
                }
                placeholder="#1&#10;Email: …&#10;Password: …"
              />
            </Field>
          )}
          <Field label="Livraison">
            <input
              value={form.delivery_delay}
              onChange={(event) => set("delivery_delay", event.target.value)}
            />
          </Field>
          <Field label="Automatisation">
            <label className="switch">
              <input
                type="checkbox"
                checked={form.auto_delivery}
                onChange={(event) => set("auto_delivery", event.target.checked)}
              />
              <span /> Livraison automatique
            </label>
          </Field>
        </div>
        <div className="dialog-actions">
          <ActionButton secondary onClick={onClose} type="button">
            Annuler
          </ActionButton>
          <ActionButton icon={Check} type="submit">
            Enregistrer
          </ActionButton>
        </div>
      </form>
    </Modal>
  );
}

function CatalogPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [offer, setOffer] = useState(undefined);
  const [showOffer, setShowOffer] = useState(false);
  const [showService, setShowService] = useState(false);
  const [serviceName, setServiceName] = useState("");
  const [serviceNameAr, setServiceNameAr] = useState("");
  const [serviceEmoji, setServiceEmoji] = useState("📦");
  const [serviceSuffixEmoji, setServiceSuffixEmoji] = useState("");
  const [serviceChannel, setServiceChannel] = useState("bot");
  const [stockOffer, setStockOffer] = useState(null);
  const [stock, setStock] = useState("");
  const [editService, setEditService] = useState(null);
  const [editServiceName, setEditServiceName] = useState("");
  const [editServiceNameAr, setEditServiceNameAr] = useState("");
  const [editServiceEmoji, setEditServiceEmoji] = useState("📦");
  const [editServiceSuffixEmoji, setEditServiceSuffixEmoji] = useState("");
  const [editServiceChannel, setEditServiceChannel] = useState("both");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selectedOffers, setSelectedOffers] = useState(new Set());
  const [bulkOfferAction, setBulkOfferAction] = useState(null);
  const [bulkOfferValue, setBulkOfferValue] = useState("");

  const startEditService = (service) => {
    setEditService(service);
    setEditServiceName(service.name || "");
    setEditServiceNameAr(service.name_ar || "");
    setEditServiceEmoji(service.emoji || "📦");
    setEditServiceSuffixEmoji(service.suffix_emoji || "");
    setEditServiceChannel("bot");
  };

  const updateService = async (event) => {
    event.preventDefault();
    if (!editService) return;
    if (
      await onAction({
        action: "update_service",
        service_id: editService.id,
        name: editServiceName,
        name_ar: editServiceNameAr,
        emoji: editServiceEmoji,
        suffix_emoji: editServiceSuffixEmoji,
        sales_channel: editServiceChannel,
      })
    )
      setEditService(null);
  };
  const createService = async (event) => {
    event.preventDefault();
    if (
      await onAction({
        action: "add_service",
        name: serviceName,
        name_ar: serviceNameAr,
        emoji: serviceEmoji,
        suffix_emoji: serviceSuffixEmoji,
        sales_channel: serviceChannel,
      })
    )
      setShowService(false);
  };
  const normalizedSearch = search.trim().toLowerCase();
  const visibleServices = (data.services || []).filter((service) => !category || String(service.id) === category).map((service) => {
    const serviceMatch = `${service.name || ""} ${service.id || ""}`.toLowerCase().includes(normalizedSearch);
    const offers = (service.offers || []).filter((item) => {
      const channels = item.sales_channels || ["bot"];
      if (!channels.includes("bot")) return false;
      if (!normalizedSearch) return true;
      if (searchField === "service") return serviceMatch;
      const searchable = {
        product: `${item.name || ""} ${item.id || ""}`,
        provider: `${item.supplier_provider || ""} ${providerLabel(item.supplier_provider)}`,
      };
      const haystack = searchField === "all"
        ? `${service.name || ""} ${Object.values(searchable).join(" ")}`
        : searchable[searchField] || "";
      return haystack.toLowerCase().includes(normalizedSearch);
    });
    return { ...service, offers, searchMatch: serviceMatch || offers.length > 0 };
  }).filter((service) => !normalizedSearch || service.searchMatch);
  const visibleOfferIds = visibleServices.flatMap((service) => (service.offers || []).map((item) => item.id));
  const toggleOfferSelection = (offerId) => setSelectedOffers((current) => {
    const next = new Set(current);
    if (next.has(offerId)) next.delete(offerId); else next.add(offerId);
    return next;
  });
  const applyBulkOfferAction = async () => {
    if (!bulkOfferAction || !selectedOffers.size) return;
    const toggle = ["activate", "deactivate"].includes(bulkOfferAction);
    const operation = bulkOfferAction === "price" ? "price_percent" : bulkOfferAction === "move" ? "move_service" : bulkOfferAction;
    const result = await onAction(toggle ? {
      action: "bulk_toggle_offers", offer_ids: [...selectedOffers].join(","), active: bulkOfferAction === "activate" ? "1" : "0",
    } : {
      action: "bulk_update_offers", offer_ids: [...selectedOffers].join(","), operation, value: bulkOfferValue,
    });
    if (result) setSelectedOffers(new Set());
    setBulkOfferAction(null);
    setBulkOfferValue("");
  };
  return (
    <>
      <PageHeader
        eyebrow="Commerce / Mon catalogue"
        title="Des offres qui donnent envie."
        description="Gérez les catégories et produits publiés dans le bot Telegram."
        actions={
          <>
            <ActionButton
              secondary
              icon={Plus}
              onClick={() => setShowService(true)}
            >
              Service
            </ActionButton>
            <ActionButton
              icon={PackagePlus}
              onClick={() => {
                setOffer(undefined);
                setShowOffer(true);
              }}
            >
              Produit
            </ActionButton>
          </>
        }
      />
      <div className="catalog-command-bar"><div><span>COLLECTIONS</span><strong>{(data.services || []).length}</strong></div><div><span>OFFRES CHARGÉES</span><strong>{(data.services || []).reduce((total, service) => total + (service.offers || []).length, 0)}</strong></div><div><span>SÉLECTION</span><strong>{selectedOffers.size}</strong></div><p>Organisez vos services, ajustez les prix et gérez la disponibilité de chaque offre.</p></div>
      <div className="workspace-tabs" role="group" aria-label="Collections du catalogue"><button aria-pressed={!category} onClick={() => { setCategory(""); setSelectedOffers(new Set()); }}>Toutes les collections</button>{(data.services || []).map((service) => <button key={service.id} aria-pressed={category === String(service.id)} onClick={() => { setCategory(String(service.id)); setSelectedOffers(new Set()); }}>{service.name}<small> {(service.offers || []).length}</small></button>)}</div>
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["service", "Service"], ["product", "Produit"], ["provider", "API fournisseur"]]}
        resultCount={visibleServices.length}
        placeholder="Nom du service, produit ou API…"
      />
      <div className={`catalog-bulk-bar ${selectedOffers.size ? "visible" : ""}`}>
        <div><span>{selectedOffers.size}</span><strong>produit(s) sélectionné(s)</strong><button type="button" onClick={() => setSelectedOffers(new Set(visibleOfferIds))}>Tout sélectionner</button><button type="button" onClick={() => setSelectedOffers(new Set())}>Effacer</button></div>
        <div><ActionButton secondary icon={ToggleRight} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("activate")}>Activer</ActionButton><ActionButton secondary icon={ToggleLeft} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("deactivate")}>Désactiver</ActionButton><ActionButton secondary icon={CircleDollarSign} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("price")}>Prix</ActionButton><ActionButton secondary icon={ShoppingBag} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("move")}>Service</ActionButton><ActionButton danger icon={Archive} disabled={!selectedOffers.size} onClick={() => setBulkOfferAction("archive")}>Archiver</ActionButton></div>
      </div>
      <div className="catalog-react-grid">
        {visibleServices.map((service, serviceIndex) => {
          const providers = [...new Set((service.offers || []).map((item) => item.supplier_provider || "").filter(Boolean))];
          return (
          <section className="catalog-service" key={service.id} style={{ "--service-accent": SERVICE_COLORS[serviceIndex % SERVICE_COLORS.length] }}>
            <header>
              <div>
                <span className="catalog-service-icon">{service.emoji || "◆"}</span>
                <div>
                  <h3>{service.name} {service.suffix_emoji || ""}</h3>
                  <small>
                    {service.offers?.length || 0} produit(s) ·{" "}
                    {service.total_stock || 0} en stock
                  </small>
                  <div className="service-providers">
                    {providers.length ? providers.map((provider) => (
                      <span key={provider}><Cloud size={11} />{providerLabel(provider)}</span>
                    )) : (
                      <span className="internal"><Database size={11} />Stock interne</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="catalog-service-actions">
                <button title="Modifier le service" onClick={() => startEditService(service)}>
                  <Edit3 size={16} />
                </button>
                <button title="Activer/désactiver" onClick={() => onAction({ action: "toggle_service", service_id: service.id })}>
                  {service.active === 0 ? <ToggleLeft /> : <ToggleRight />}
                </button>
                <button className="danger" title="Supprimer le service" onClick={() => setDeleteTarget({ type: "service", item: service })}>
                  <Trash2 size={16} />
                </button>
              </div>
            </header>
            <div>
              {service.offers?.map((item, index) => (
                <article
                  className={`offer-card ${selectedOffers.has(item.id) ? "selected" : ""}`}
                  key={item.id || `${service.id}-${item.name}-${index}`}
                >
                  <button className="offer-select" type="button" onClick={() => toggleOfferSelection(item.id)} aria-label={`${selectedOffers.has(item.id) ? "Désélectionner" : "Sélectionner"} ${item.name}`}>{selectedOffers.has(item.id) ? <Check size={13} /> : null}</button>
                  <div>
                    <strong>{item.name}</strong>
                    <span>
                      {money(item.price, data.currency)} · Stock{" "}
                      {item.stock || 0}
                    </span>
                    {Number(item.bulk_quantity || 0) > 0 && item.bulk_unit_price != null && (
                      <span>Gros: {money(item.bulk_unit_price, data.currency)} / unité dès {item.bulk_quantity}</span>
                    )}
                    <span className="offer-channel">
                      Bot
                    </span>
                    <span className={`offer-provider ${item.supplier_provider ? "api" : "internal"}`}>
                      {item.supplier_provider ? <Cloud size={11} /> : <Database size={11} />}
                      {providerLabel(item.supplier_provider)}
                    </span>
                  </div>
                  <div className="offer-actions">
                    <button
                      title="Ajouter du stock"
                      onClick={() => setStockOffer(item)}
                    >
                      <Boxes size={15} />
                    </button>
                    <button
                      title="Dupliquer"
                      onClick={() =>
                        onAction({
                          action: "duplicate_offer",
                          offer_id: item.id,
                        })
                      }
                    >
                      <Copy size={15} />
                    </button>
                    <button
                      title="Modifier"
                      onClick={() => {
                        setOffer(item);
                        setShowOffer(true);
                      }}
                    >
                      <Edit3 size={15} />
                    </button>
                    <button
                      title="Activer/désactiver"
                      onClick={() =>
                        onAction({ action: "toggle_offer", offer_id: item.id })
                      }
                    >
                      {item.active === 0 ? (
                        <ToggleLeft size={17} />
                      ) : (
                        <ToggleRight size={17} />
                      )}
                    </button>
                    <button className="danger" title="Supprimer le produit" onClick={() => setDeleteTarget({ type: "offer", item })}>
                      <Trash2 size={15} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
          );
        })}
      </div>
      {!visibleServices.length && (
        <Empty
          icon={ShoppingBag}
          title={search ? "Aucun résultat" : "Catalogue vide"}
          text={search ? "Essayez un autre nom, produit ou fournisseur API." : "Créez votre premier service puis ajoutez des produits."}
        />
      )}
      {showOffer && (
        <OfferForm
          services={data.services || []}
          offer={offer}
          onAction={onAction}
          onClose={() => setShowOffer(false)}
          defaultChannel="bot"
        />
      )}
      {bulkOfferAction && <Modal title="Confirmer l’action groupée" onClose={() => { setBulkOfferAction(null); setBulkOfferValue(""); }}><div className="bulk-confirm"><span className={["deactivate", "archive"].includes(bulkOfferAction) ? "deactivate" : "activate"}>{bulkOfferAction === "activate" ? <ToggleRight size={28} /> : bulkOfferAction === "price" ? <CircleDollarSign size={28} /> : bulkOfferAction === "move" ? <ShoppingBag size={28} /> : bulkOfferAction === "archive" ? <Archive size={28} /> : <ToggleLeft size={28} />}</span><strong>{{ activate: "Activer", deactivate: "Désactiver", price: "Modifier le prix de", move: "Déplacer", archive: "Archiver" }[bulkOfferAction]} {selectedOffers.size} produit(s) ?</strong>{bulkOfferAction === "price" && <Field label="Variation en pourcentage"><input type="number" min="-90" max="500" step="0.1" value={bulkOfferValue} onChange={(event) => setBulkOfferValue(event.target.value)} placeholder="Ex. 10 ou -5" /></Field>}{bulkOfferAction === "move" && <Field label="Service de destination"><select value={bulkOfferValue} onChange={(event) => setBulkOfferValue(event.target.value)}><option value="">Choisir un service</option>{(data.services || []).map((service) => <option value={service.id} key={service.id}>{service.name}</option>)}</select></Field>}<p>{bulkOfferAction === "archive" ? "Les produits disparaîtront du catalogue. Cette action pourra être restaurée depuis le journal pendant 24 heures." : "La modification sera auditée et pourra être restaurée depuis le journal pendant 24 heures."}</p><div><ActionButton secondary onClick={() => { setBulkOfferAction(null); setBulkOfferValue(""); }}>Annuler</ActionButton><ActionButton danger={["deactivate", "archive"].includes(bulkOfferAction)} icon={Check} disabled={["price", "move"].includes(bulkOfferAction) && !bulkOfferValue} onClick={applyBulkOfferAction}>Confirmer</ActionButton></div></div></Modal>}
      {showService && (
        <Modal title="Nouveau service" onClose={() => setShowService(false)}>
          <form onSubmit={createService}>
            <div className="form-grid">
              <Field label="Nom">
                <input
                  required
                  value={serviceName}
                  onChange={(event) => setServiceName(event.target.value)}
                />
              </Field>
              <Field label="Emoji">
                <input
                  value={serviceEmoji}
                  onChange={(event) => setServiceEmoji(event.target.value)}
                />
              </Field>
              <Field label="Emoji droit">
                <input value={serviceSuffixEmoji} onChange={(event) => setServiceSuffixEmoji(event.target.value)} placeholder="✅" />
              </Field>
              <Field label="Nom arabe" wide>
                <input dir="rtl" value={serviceNameAr} onChange={(event) => setServiceNameAr(event.target.value)} />
              </Field>
              <Field label="Canal" wide>
                <select value={serviceChannel} onChange={(event) => setServiceChannel(event.target.value)}>
                  <option value="bot">Bot uniquement</option>
                </select>
              </Field>
            </div>
            <div className="dialog-actions">
              <ActionButton type="submit" icon={Plus}>
                Créer
              </ActionButton>
            </div>
          </form>
        </Modal>
      )}
      {editService && (
        <Modal title={`Modifier le service · ${editService.name}`} onClose={() => setEditService(null)}>
          <form onSubmit={updateService}>
            <div className="form-grid">
              <Field label="Nom">
                <input
                  required
                  value={editServiceName}
                  onChange={(event) => setEditServiceName(event.target.value)}
                />
              </Field>
              <Field label="Emoji">
                <input
                  value={editServiceEmoji}
                  onChange={(event) => setEditServiceEmoji(event.target.value)}
                  style={{ maxWidth: 80, textAlign: "center", fontSize: "1.25rem" }}
                />
              </Field>
              <Field label="Emoji droit">
                <input value={editServiceSuffixEmoji} onChange={(event) => setEditServiceSuffixEmoji(event.target.value)} placeholder="✅" style={{ maxWidth: 80, textAlign: "center", fontSize: "1.25rem" }} />
              </Field>
              <Field label="Nom arabe" wide>
                <input dir="rtl" value={editServiceNameAr} onChange={(event) => setEditServiceNameAr(event.target.value)} />
              </Field>
              <Field label="Canal" wide>
                <select value={editServiceChannel} onChange={(event) => setEditServiceChannel(event.target.value)}>
                  <option value="bot">Bot uniquement</option>
                </select>
              </Field>
            </div>
            <div className="dialog-actions">
              <ActionButton type="submit" icon={Check}>
                Enregistrer
              </ActionButton>
            </div>
          </form>
        </Modal>
      )}
      {stockOffer && (
        <Modal
          title={`Stock · ${stockOffer.name}`}
          onClose={() => setStockOffer(null)}
        >
          <Field label="Éléments à chiffrer">
            <textarea
              value={stock}
              onChange={(event) => setStock(event.target.value)}
              placeholder="#1&#10;Compte: …"
            />
          </Field>
          <div className="dialog-actions">
            <ActionButton
              icon={PackagePlus}
              onClick={async () => {
                if (
                  await onAction({
                    action: "add_inventory",
                    offer_id: stockOffer.id,
                    items: stock,
                  })
                )
                  setStockOffer(null);
              }}
            >
              Ajouter
            </ActionButton>
          </div>
        </Modal>
      )}
      {deleteTarget && (
        <Modal
          title={deleteTarget.type === "service" ? "Supprimer le service" : "Supprimer le produit"}
          onClose={() => setDeleteTarget(null)}
        >
          <div className="delete-confirmation">
            <span><Trash2 size={22} /></span>
            <div>
              <h4>Supprimer « {deleteTarget.item.name} » ?</h4>
              <p>
                {deleteTarget.type === "service"
                  ? `Le service et ses ${deleteTarget.item.offer_count || 0} produit(s) disparaîtront du catalogue. Les commandes historiques seront conservées.`
                  : "Le produit disparaîtra du catalogue et du bot. Les commandes historiques seront conservées."}
              </p>
            </div>
          </div>
          <div className="dialog-actions">
            <ActionButton secondary onClick={() => setDeleteTarget(null)}>Annuler</ActionButton>
            <ActionButton
              danger
              icon={Trash2}
              onClick={async () => {
                const payload = deleteTarget.type === "service"
                  ? { action: "archive_service", service_id: deleteTarget.item.id }
                  : { action: "archive_offer", offer_id: deleteTarget.item.id };
                if (await onAction(payload)) setDeleteTarget(null);
              }}
            >
              Supprimer
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}

function ApiProductsPage({ data, onAction, setToast }) {
  const [provider, setProvider] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState("catalog");
  const [providerError, setProviderError] = useState("");
  const providerRequest = useRef(0);
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(false);
  const [providerMeta, setProviderMeta] = useState([]);
  const [providerHealth, setProviderHealth] = useState({});
  const [checkingAll, setCheckingAll] = useState(false);
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [usageFilter, setUsageFilter] = useState("all");
  const [comparison, setComparison] = useState(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const loadProvider = async (providerId, { showToast = false, selectCatalog = true } = {}) => {
    if (!providerId) return false;
    const requestId = selectCatalog ? ++providerRequest.current : null;
    const startedAt = performance.now();
    if (selectCatalog) { setLoading(true); setCatalog(null); }
    setProviderHealth((current) => ({
      ...current,
      [providerId]: { ...current[providerId], status: "checking", error: "" },
    }));
    try {
      const response = await fetch(
        `/admin/api/reseller-products?provider=${encodeURIComponent(providerId)}`,
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "API indisponible");
      if (selectCatalog && requestId === providerRequest.current) setCatalog(payload);
      setProviderHealth((current) => ({
        ...current,
        [providerId]: {
          status: "online",
          latency: Math.max(1, Math.round(performance.now() - startedAt)),
          balance: payload.balance,
          currency: payload.currency || "USDT",
          products: payload.products?.length || 0,
          inStock: (payload.products || []).filter((item) => Number(item.stock || 0) > 0).length,
          used: payload.used_count ?? payload.selected_count ?? 0,
          checkedAt: new Date().toISOString(),
          error: "",
        },
      }));
      return true;
    } catch (error) {
      if (selectCatalog && requestId === providerRequest.current) setCatalog(null);
      setProviderHealth((current) => ({
        ...current,
        [providerId]: {
          ...current[providerId],
          status: "offline",
          latency: Math.max(1, Math.round(performance.now() - startedAt)),
          checkedAt: new Date().toISOString(),
          error: error.message,
        },
      }));
      if (showToast) setToast({ type: "error", title: "Fournisseur indisponible", message: error.message });
      return false;
    } finally {
      if (selectCatalog && requestId === providerRequest.current) setLoading(false);
    }
  };
  const load = () => loadProvider(provider, { showToast: true, selectCatalog: true });
  useEffect(() => {
    fetch("/admin/api/reseller-providers", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Configuration fournisseurs indisponible");
        setProviderMeta(payload.providers || []);
        setProvider((current) => current || (payload.providers || []).find((item) => item.configured)?.id || "");
      })
      .catch((error) => setProviderError(error.message));
  }, []);
  useEffect(() => {
    if (provider) load();
  }, [provider]);
  const testAllProviders = async () => {
    const configured = providerMeta.filter((item) => item.configured);
    if (!configured.length) {
      setToast({ type: "warning", title: "Aucune API configurée", message: "Ajoutez au moins une clé fournisseur dans Railway." });
      return;
    }
    setCheckingAll(true);
    const results = await Promise.all(configured.map((item) => loadProvider(item.id, {
      selectCatalog: item.id === provider,
    })));
    const online = results.filter(Boolean).length;
    setToast({
      type: online === configured.length ? "success" : "warning",
      title: "Diagnostic terminé",
      message: `${online}/${configured.length} fournisseur(s) opérationnel(s).`,
    });
    setCheckingAll(false);
  };
  const comparePrices = async () => {
    setComparisonLoading(true);
    try {
      const response = await fetch(
        "/admin/api/reseller-comparison?refresh=1",
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Comparaison indisponible");
      }
      setComparison(payload);
      if (payload.method !== "external_ai") {
        setToast({
          type: "warning",
          title: "Mode de secours utilisé",
          message: "Configurez HP_AI_API_URL, HP_AI_API_KEY et HP_AI_MODELS dans Railway.",
        });
      }
    } catch (error) {
      setToast({ type: "error", title: "Comparaison impossible", message: error.message });
    } finally {
      setComparisonLoading(false);
    }
  };
  const chooseComparedOffer = async (offer) => {
    setProvider(offer.provider);
    try {
      const response = await fetch(
        `/admin/api/reseller-products?provider=${encodeURIComponent(offer.provider)}`,
        { credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Produit indisponible");
      setCatalog(payload);
      const product = (payload.products || []).find(
        (item) => String(item.id) === String(offer.product_id),
      );
      if (!product) throw new Error("Ce produit n’est plus disponible chez le fournisseur.");
      setEditing(product);
    } catch (error) {
      setToast({ type: "error", title: "Sélection impossible", message: error.message });
    }
  };
  const catalogProducts = catalog?.products || [];
  const usedCount = catalog?.used_count ?? catalogProducts.filter((product) => product.enabled).length;
  const unusedCount = catalog?.unused_count ?? catalogProducts.length - usedCount;
  const visibleProducts = catalogProducts.filter((product) => {
    if (usageFilter === "used" && !product.enabled) return false;
    if (usageFilter === "unused" && product.enabled) return false;
    const searchable = {
      name: `${product.display_name || ""} ${product.name || ""}`,
      product_id: `${product.id || ""}`,
      description: product.description || "",
    };
    const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
    return !search || haystack.toLowerCase().includes(search.toLowerCase());
  }).sort((left, right) => Number(Boolean(right.enabled)) - Number(Boolean(left.enabled)));
  const saveProduct = async (payload) => {
    const result = await onAction(payload);
    if (result) await loadProvider(provider, { selectCatalog: true });
    return result;
  };
  return (
    <>
      <PageHeader
        eyebrow="Approvisionnement / Intégrations"
        title="Votre réseau de fournisseurs."
        description="Connectez les fournisseurs et publiez leurs produits dans votre boutique."
        actions={
          <div className="inline-actions">
            <ActionButton icon={Sparkles} onClick={comparePrices} disabled={comparisonLoading || !providerMeta.some((item) => item.configured)}>
              {comparisonLoading ? "Analyse IA…" : "Comparer les prix avec l’IA"}
            </ActionButton>
            <ActionButton secondary icon={RefreshCw} onClick={load} disabled={!provider || loading}>
              Synchroniser
            </ActionButton>
          </div>
        }
      />
      <div className="workspace-tabs supplier-workspace-tabs" role="group" aria-label="Espace fournisseurs">{[["catalog", "Catalogue fournisseur"], ["health", "Connexions & diagnostics"], ["keys", "Clés clients"], ["connectors", "Connecteurs personnalisés"]].map(([id, label]) => <button key={id} aria-pressed={workspaceTab === id} onClick={() => setWorkspaceTab(id)}>{label}</button>)}</div>
      {providerError && <p className="control-error" role="alert">{providerError}</p>}
      {workspaceTab === "health" && <section className="provider-health-center">

        <header>
          <div><span className="comparison-kicker"><Cloud size={14} /> Centre de santé API</span><h2>État des fournisseurs externes</h2><p>Testez les connexions uniquement à la demande pour éviter les appels inutiles.</p></div>
          <ActionButton secondary icon={RefreshCw} onClick={testAllProviders} disabled={checkingAll || !providerMeta.length}>{checkingAll ? "Diagnostic…" : "Tester toutes les API"}</ActionButton>
        </header>
        <div className="provider-health-grid">
          {providerMeta.map((item) => {
            const health = providerHealth[item.id] || {};
            const state = !item.configured ? "unconfigured" : health.status || "unknown";
            return <article className={`provider-health-card ${state} ${provider === item.id ? "selected" : ""}`} key={item.id}>
              <button className="provider-health-main" onClick={() => setProvider(item.id)}>
                <div className="provider-health-title"><span className="provider-health-icon"><Cloud size={17} /></span><div><strong>{item.name}</strong><small>{item.configured ? "Clé configurée" : "Non configurée"}</small></div><i /></div>
                <div className="provider-health-stats"><span><small>Solde</small><b>{health.balance == null ? "—" : money(health.balance, health.currency)}</b></span><span><small>Produits</small><b>{health.products ?? "—"}</b></span><span><small>Utilisés</small><b>{health.used ?? "—"}</b></span><span><small>En stock</small><b>{health.inStock ?? "—"}</b></span></div>
                <div className="provider-health-foot"><span>{state === "online" ? `Opérationnelle · ${health.latency} ms` : state === "offline" ? "Connexion échouée" : state === "checking" ? "Test en cours…" : state === "unconfigured" ? "Ajoutez la clé dans Railway" : "Pas encore testée"}</span>{health.checkedAt && <small>{date(health.checkedAt)}</small>}</div>
                {health.error && <p title={health.error}>{health.error}</p>}
              </button>
              <button className="provider-test-button" disabled={!item.configured || state === "checking"} onClick={() => loadProvider(item.id, { showToast: true, selectCatalog: item.id === provider })}>{state === "checking" ? <RefreshCw className="spin" size={13} /> : <ShieldCheck size={13} />}Tester</button>
            </article>;
          })}
        </div>
      </section>}
      {workspaceTab === "catalog" && comparison && (
        <section className="ai-comparison-panel">
          <header>
            <div>
              <span className="comparison-kicker"><Sparkles size={14} /> Comparateur intelligent</span>
              <h2>{comparison.compared_group_count} service(s) commun(s) détecté(s)</h2>
              <p>
                {comparison.method === "external_ai"
                  ? `Analyse IA avec ${comparison.ai_model}`
                  : "Analyse locale de secours — configurez votre API IA pour une détection sémantique"}
                {` · ${comparison.catalog_product_count} produits · ${comparison.provider_count} fournisseurs`}
              </p>
            </div>
            <button className="comparison-close" onClick={() => setComparison(null)} aria-label="Fermer">
              <X size={17} />
            </button>
          </header>
          {!!comparison.provider_errors?.length && (
            <div className="comparison-warning">
              {comparison.provider_errors.length} fournisseur(s) indisponible(s) pendant l’analyse.
            </div>
          )}
          <div className="comparison-grid">
            {(comparison.groups || []).map((group, groupIndex) => (
              <article className="comparison-card" key={`${group.label}-${groupIndex}`}>
                <div className="comparison-title">
                  <div>
                    <h3>{group.label}</h3>
                    <span>Confiance {Math.round((group.confidence || 0) * 100)}%</span>
                  </div>
                  {!!group.savings_vs_next && (
                    <strong>Économie {money(group.savings_vs_next, group.currency)}</strong>
                  )}
                </div>
                <p>{group.reason}</p>
                <div className="comparison-offers">
                  {group.offers.map((offer) => {
                    const cheapest = offer.item_id === group.cheapest_item_id;
                    return (
                      <div className={cheapest ? "cheapest" : ""} key={offer.item_id}>
                        <div>
                          <span>{offer.provider_name}</span>
                          <small>{offer.name} · {offer.stock > 0 ? `${offer.stock} en stock` : "épuisé"}</small>
                        </div>
                        <strong>{money(offer.price, group.currency)}</strong>
                        {cheapest && <b>Meilleur prix</b>}
                        <button disabled={offer.stock <= 0} onClick={() => chooseComparedOffer(offer)}>
                          Choisir
                        </button>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
          {!comparison.groups?.length && (
            <Empty
              icon={Sparkles}
              title="Aucun service commun détecté"
              text="Les catalogues disponibles ne contiennent pas encore d’offres suffisamment équivalentes."
            />
          )}
        </section>
      )}
      {workspaceTab === "catalog" && <div className="supplier-browser"><aside className="supplier-directory"><div className="supplier-directory-heading"><Cloud size={18} /><strong>Fournisseurs</strong><span>{providerMeta.length}</span></div>{providerMeta.map((item) => <button key={item.id} disabled={!item.configured} className={provider === item.id ? "active" : ""} onClick={() => setProvider(item.id)}><span className="supplier-monogram">{(item.name || item.id).slice(0, 2).toUpperCase()}</span><span><strong>{item.name || item.id}</strong><small>{item.configured ? "Connexion configurée" : "Configuration requise"}</small></span><ChevronRight size={15} /></button>)}{!providerMeta.length && <p className="control-caption">{providerError ? "Liste indisponible." : "Aucun fournisseur disponible."}</p>}<p className="control-caption">Les fournisseurs non configurés restent visibles, leurs actions sont indisponibles.</p></aside><div className="supplier-catalog">
      {!provider && <div className="supplier-empty"><Cloud size={38} /><h3>Connectez votre premier fournisseur</h3><p>Les produits apparaîtront après configuration d’une connexion. Consultez les diagnostics ou ajoutez un connecteur personnalisé.</p><ActionButton secondary onClick={() => setWorkspaceTab("connectors")}>Ouvrir les connecteurs</ActionButton></div>}
      {catalog && (
        <div className="api-summary">
          <div>
            <span>Fournisseur</span>
            <strong>{catalog.supplier_name || provider}</strong>
          </div>
          <div>
            <span>Solde</span>
            <strong>
              {money(catalog.balance, catalog.currency || "USDT")}
            </strong>
          </div>
          <div>
            <span>Produits utilisés</span>
            <strong>{usedCount}</strong>
          </div>
          <div>
            <span>Produits disponibles</span>
            <strong>{catalog.products?.length || 0}</strong>
          </div>
        </div>
      )}
      {catalog && <div className="api-usage-classifier" aria-label="Classer les produits API"><button className={usageFilter === "all" ? "active" : ""} onClick={() => setUsageFilter("all")}><Boxes size={16} /><span><strong>Tous les produits</strong><small>Catalogue complet</small></span><b>{catalogProducts.length}</b></button><button className={`used ${usageFilter === "used" ? "active" : ""}`} onClick={() => setUsageFilter("used")}><CheckCircle2 size={16} /><span><strong>Produits utilisés</strong><small>Actifs dans votre catalogue</small></span><b>{usedCount}</b></button><button className={`unused ${usageFilter === "unused" ? "active" : ""}`} onClick={() => setUsageFilter("unused")}><Archive size={16} /><span><strong>Produits non utilisés</strong><small>Disponibles chez le fournisseur</small></span><b>{unusedCount}</b></button></div>}
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["name", "Nom du produit"], ["product_id", "ID fournisseur"], ["description", "Description"]]}
        resultCount={visibleProducts.length}
        placeholder="Nom, ID fournisseur ou description…"
      />
      <section className="data-panel">
        <div className="product-api-grid">
          {visibleProducts.map((product) => (
            <article className={product.enabled ? "api-product-used" : "api-product-unused"} key={product.id}>
              <header>
                <div className="api-product-badges"><span className={product.enabled ? "api-usage-badge used" : "api-usage-badge unused"}>{product.enabled ? <CheckCircle2 size={11} /> : <Archive size={11} />}{product.enabled ? "Utilisé" : "Non utilisé"}</span><span
                  className={product.stock > 0 ? "api-online" : "api-offline"}
                >
                  {product.stock > 0 ? `${product.stock} en stock` : "Épuisé"}
                </span></div>
                <button aria-label={`Configurer ${product.display_name || product.name}`} onClick={() => setEditing(product)}>
                  <Edit3 size={15} />
                </button>
              </header>
              <h3>{product.display_name || product.name}</h3>
              <p>{product.description || "Produit fournisseur"}</p>
              <div>
                <span>
                  Achat {money(product.wholesale_price, product.currency)}
                </span>
                <strong>{money(product.retail_price, product.currency)}</strong>
              </div>
            </article>
          ))}
        </div>
        {loading && (
          <div className="table-loading">Connexion au fournisseur…</div>
        )}
        {!loading && !visibleProducts.length && (
          <Empty
            icon={Cloud}
            title={search ? "Aucun résultat" : "Aucun produit API"}
            text={search ? "Essayez un autre nom ou identifiant fournisseur." : "Vérifiez la configuration de ce fournisseur."}
          />
        )}
      </section>
      </div></div>}
      {workspaceTab === "keys" && <BuyerKeys setToast={setToast} writeToken={data.dashboard_write_token} />}
      {workspaceTab === "connectors" && <CustomExternalApis setToast={setToast} writeToken={data.dashboard_write_token} />}
      {editing && (
        <ApiProductEditor
          product={editing}
          provider={provider}
          services={data.services || []}
          onAction={saveProduct}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function BuyerKeys({ setToast, writeToken }) {
  const [keys, setKeys] = useState([]);
  const [show, setShow] = useState(false);
  const [userId, setUserId] = useState("");
  const [label, setLabel] = useState("Buyer API");
  const [issued, setIssued] = useState("");
  const load = () =>
    fetch("/admin/api/buyer-keys", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((payload) => setKeys(payload.keys || []));
  useEffect(() => {
    load();
  }, []);
  const request = async (body) => {
    const response = await fetch("/admin/api/buyer-keys", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Dashboard-Write-Token": writeToken || "",
      },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      setToast({
        type: "error",
        title: "Clé API",
        message: payload.message || payload.error || "Action refusée",
      });
      return null;
    }
    await load();
    return payload;
  };
  return (
    <section className="data-panel buyer-keys">
      <header>
        <div>
          <span className="eyebrow">Accès revendeurs</span>
          <h3>Clés Buyer API</h3>
        </div>
        <ActionButton icon={KeyRound} onClick={() => setShow(true)}>
          Nouvelle clé
        </ActionButton>
      </header>
      <div className="responsive-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Client</th>
              <th>Libellé</th>
              <th>Créée</th>
              <th>Dernière utilisation</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id}>
                <td>#{key.id}</td>
                <td>{key.user_id}</td>
                <td>{key.label}</td>
                <td>{date(key.created_at)}</td>
                <td>{date(key.last_used_at)}</td>
                <td>
                  <button
                    className="row-action"
                    onClick={() =>
                      request({ action: "revoke", key_id: key.id })
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!keys.length && <Empty icon={KeyRound} title="Aucune clé active" />}
      {show && (
        <Modal title="Créer une clé Buyer API" onClose={() => setShow(false)}>
          <div className="form-grid">
            <Field label="Telegram ID">
              <input
                type="number"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              />
            </Field>
            <Field label="Libellé">
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
              />
            </Field>
          </div>
          {issued && <pre className="secret-preview">{issued}</pre>}
          <div className="dialog-actions">
            <ActionButton
              icon={KeyRound}
              onClick={async () => {
                const payload = await request({
                  action: "create",
                  user_id: userId,
                  label,
                });
                if (payload)
                  setIssued(
                    payload.key?.secret ||
                      payload.key?.key ||
                      JSON.stringify(payload.key),
                  );
              }}
            >
              Créer
            </ActionButton>
          </div>
        </Modal>
      )}
    </section>
  );
}

function CustomExternalApis({ setToast, writeToken }) {
  const emptyForm = {
    name: "",
    endpoint: "https://",
    method: "GET",
    auth_type: "none",
    auth_header: "X-API-Key",
    secret: "",
    headers: "{}",
    body_template: "",
  };
  const [connectors, setConnectors] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(false);
  const [running, setRunning] = useState(null);
  const [runBody, setRunBody] = useState("");
  const [runResult, setRunResult] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => fetch("/admin/api/external-connectors", {
    credentials: "same-origin",
    cache: "no-store",
  }).then((response) => response.json()).then((payload) => setConnectors(payload.connectors || []));
  useEffect(() => { load(); }, []);
  const post = async (payload) => {
    setBusy(true);
    try {
      const response = await fetch("/admin", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-Dashboard-Write-Token": writeToken || "",
        },
        body: new URLSearchParams(Object.entries(payload).map(([key, value]) => [key, value == null ? "" : String(value)])),
      });
      const result = await response.json();
      if (!response.ok || result.ok === false) {
        const error = new Error(result.message || result.error || `Erreur HTTP ${response.status}`);
        error.payload = result;
        throw error;
      }
      return result;
    } finally {
      setBusy(false);
    }
  };
  const openEditor = (connector = null) => {
    setForm(connector ? {
      connector_id: connector.id,
      name: connector.name,
      endpoint: connector.endpoint,
      method: connector.method,
      auth_type: connector.auth_type,
      auth_header: connector.auth_header || "X-API-Key",
      secret: "",
      headers: JSON.stringify(connector.headers || {}, null, 2),
      body_template: connector.body_template || "",
    } : emptyForm);
    setEditing(true);
  };
  return (
    <section className="data-panel custom-apis">
      <header>
        <div><span className="eyebrow">Connexion libre</span><h3>API personnalisées</h3><p>Ajoutez et utilisez manuellement un endpoint externe sécurisé.</p></div>
        <ActionButton icon={Plus} onClick={() => openEditor()}>Ajouter une API</ActionButton>
      </header>
      <div className="custom-api-grid">
        {connectors.map((connector) => (
          <article key={connector.id}>
            <div className="custom-api-icon"><Globe2 size={20} /></div>
            <div className="custom-api-copy">
              <div><strong>{connector.name}</strong><span className={`method-badge ${connector.method.toLowerCase()}`}>{connector.method}</span></div>
              <code>{connector.endpoint}</code>
              <small>{connector.auth_type === "none" ? "Sans authentification" : connector.auth_type === "bearer" ? "Bearer token chiffré" : `${connector.auth_header} chiffrée`}</small>
            </div>
            <div className="custom-api-actions">
              <button title="Exécuter" onClick={() => { setRunning(connector); setRunBody(connector.body_template || ""); setRunResult(null); }}><Send size={15} /></button>
              <button title="Modifier" onClick={() => openEditor(connector)}><Edit3 size={15} /></button>
              <button className="danger" title="Supprimer" onClick={() => setDeleting(connector)}><Trash2 size={15} /></button>
            </div>
          </article>
        ))}
      </div>
      {!connectors.length && <Empty icon={Globe2} title="Aucune API personnalisée" text="Ajoutez votre premier endpoint HTTPS directement depuis le site." />}
      {editing && (
        <Modal title={form.connector_id ? "Modifier l’API externe" : "Ajouter une API externe"} onClose={() => setEditing(false)} wide>
          <div className="form-grid">
            <Field label="Nom"><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Mon fournisseur" /></Field>
            <Field label="Méthode"><select value={form.method} onChange={(event) => setForm({ ...form, method: event.target.value })}>{["GET", "POST", "PUT", "PATCH", "DELETE"].map((method) => <option key={method}>{method}</option>)}</select></Field>
            <Field label="Endpoint HTTPS" wide><input value={form.endpoint} onChange={(event) => setForm({ ...form, endpoint: event.target.value })} placeholder="https://api.example.com/v1/products" /></Field>
            <Field label="Authentification"><select value={form.auth_type} onChange={(event) => setForm({ ...form, auth_type: event.target.value })}><option value="none">Aucune</option><option value="bearer">Bearer token</option><option value="api_key">Clé API</option></select></Field>
            {form.auth_type === "api_key" && <Field label="Nom de l’en-tête"><input value={form.auth_header} onChange={(event) => setForm({ ...form, auth_header: event.target.value })} /></Field>}
            {form.auth_type !== "none" && <Field label={form.connector_id ? "Nouvelle clé (laisser vide pour conserver)" : "Clé ou token"} wide><input type="password" value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} autoComplete="new-password" /></Field>}
            <Field label="En-têtes JSON" wide><textarea value={form.headers} onChange={(event) => setForm({ ...form, headers: event.target.value })} placeholder={'{"Accept": "application/json"}'} /></Field>
            <Field label="Corps JSON par défaut" wide><textarea value={form.body_template} onChange={(event) => setForm({ ...form, body_template: event.target.value })} placeholder={'{"product_id": "123", "quantity": 1}'} /></Field>
          </div>
          <div className="external-api-notice"><ShieldCheck size={16} /><span>HTTPS public uniquement. Les clés sont chiffrées et ne seront jamais réaffichées.</span></div>
          <div className="dialog-actions"><ActionButton secondary onClick={() => setEditing(false)}>Annuler</ActionButton><ActionButton icon={Check} disabled={busy} onClick={async () => { try { await post({ action: "save_external_connector", ...form }); await load(); setEditing(false); setToast({ title: "API enregistrée", message: "La connexion externe est prête à être testée." }); } catch (error) { setToast({ type: "error", title: "API refusée", message: error.message }); } }}>Enregistrer</ActionButton></div>
        </Modal>
      )}
      {running && (
        <Modal title={`Exécuter · ${running.name}`} onClose={() => setRunning(null)} wide>
          <div className="external-run-meta"><span className={`method-badge ${running.method.toLowerCase()}`}>{running.method}</span><code>{running.endpoint}</code></div>
          {running.method !== "GET" && <Field label="Corps JSON"><textarea value={runBody} onChange={(event) => setRunBody(event.target.value)} /></Field>}
          {runResult && <div className={`external-response ${runResult.ok ? "success" : "error"}`}><header><strong>HTTP {runResult.status}</strong><span>{runResult.duration_ms} ms</span></header><pre>{JSON.stringify(runResult.response, null, 2)}</pre></div>}
          <div className="dialog-actions"><ActionButton icon={Send} disabled={busy} onClick={async () => { try { const result = await post({ action: "run_external_connector", connector_id: running.id, body: runBody }); setRunResult(result); } catch (error) { if (error.payload?.status) setRunResult(error.payload); setToast({ type: "error", title: "Appel API échoué", message: error.message }); } }}>Envoyer la requête</ActionButton></div>
        </Modal>
      )}
      {deleting && (
        <Modal title="Supprimer la connexion API" onClose={() => setDeleting(null)}>
          <div className="delete-confirmation"><span><Trash2 size={22} /></span><div><h4>Supprimer « {deleting.name} » ?</h4><p>L’endpoint et sa clé chiffrée seront définitivement supprimés.</p></div></div>
          <div className="dialog-actions"><ActionButton secondary onClick={() => setDeleting(null)}>Annuler</ActionButton><ActionButton danger icon={Trash2} disabled={busy} onClick={async () => { try { await post({ action: "delete_external_connector", connector_id: deleting.id }); await load(); setDeleting(null); setToast({ title: "API supprimée", message: "La connexion externe a été retirée." }); } catch (error) { setToast({ type: "error", title: "Suppression impossible", message: error.message }); } }}>Supprimer</ActionButton></div>
        </Modal>
      )}
    </section>
  );
}

function ApiProductEditor({ product, provider, services, onAction, onClose }) {
  const [form, setForm] = useState({
    display_name: product.display_name || product.name,
    retail_price: product.retail_price || "",
    service_id: product.service_id || services[0]?.id || "",
    emoji: product.service_emoji || product.custom_emoji_id || product.emoji || "📦",
    enabled: Boolean(product.enabled),
    description: product.description || "",
    warranty: product.warranty || "",
    period_value: product.period_value ?? product.period_days ?? 30,
    period_unit: product.period_unit || "days",
    warranty_value: product.warranty_value ?? product.warranty_days ?? (product.warranty === "NW" ? 0 : (Number((product.warranty || "").match(/\d+/)?.[0]) || 0)),
    warranty_unit: product.warranty_unit || "days",
    delivery_delay: product.delivery_delay || "Instantané après confirmation",
    low_stock_threshold: product.low_stock_threshold || 5,
  });
  const [newServiceName, setNewServiceName] = useState("");
  const [newServiceEmoji, setNewServiceEmoji] = useState("📦");
  const [creatingSvc, setCreatingSvc] = useState(false);
  const isNewService = form.service_id === "__new__";
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));

  const wholesalePrice = Number(product.wholesale_price || 0);
  const retailPrice = Number(form.retail_price || 0);
  const margin = wholesalePrice > 0 && retailPrice > 0
    ? (((retailPrice - wholesalePrice) / wholesalePrice) * 100).toFixed(1)
    : null;
  const marginColor = margin === null ? "var(--muted)" : Number(margin) >= 30 ? "#34d399" : Number(margin) >= 10 ? "#f59e0b" : "#fb7185";

  const handlePublish = async () => {
    let serviceId = form.service_id;
    const activeEmoji = isNewService ? (newServiceEmoji || "📦") : (form.emoji || "📦");
    if (isNewService) {
      if (!newServiceName.trim()) return;
      setCreatingSvc(true);
      try {
        const result = await onAction({
          action: "add_service",
          name: newServiceName.trim(),
          emoji: activeEmoji,
        });
        if (!result) { setCreatingSvc(false); return; }
        serviceId = result.service_id || result.id || "";
        if (!serviceId) { setCreatingSvc(false); return; }
      } catch {
        setCreatingSvc(false);
        return;
      }
      setCreatingSvc(false);
    }
    const factors = { days: 1, months: 30, years: 365 };
    const periodDays = Number(form.period_value || 0) * factors[form.period_unit];
    const warrantyDays = Number(form.warranty_value || 0) * factors[form.warranty_unit];
    if (
      await onAction({
        action: "save_reseller_product",
        provider,
        product_id: product.id,
        ...form,
        period_days: periodDays,
        warranty_days: warrantyDays,
        warranty: warrantyDays === 0 ? "NW" : `${form.warranty_value} ${form.warranty_unit}`,
        service_id: serviceId,
        service_emoji: activeEmoji,
        custom_emoji_id: activeEmoji,
        emoji: activeEmoji,
        enabled: form.enabled ? "1" : "0",
      })
    )
      onClose();
  };

  return (
    <Modal title={product.name} onClose={onClose} wide>
      <div className="detail-grid" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
        <div>
          <span>Prix d'achat (fournisseur)</span>
          <strong>{money(wholesalePrice, product.currency)}</strong>
        </div>
        <div>
          <span>Prix de vente</span>
          <strong style={{ color: retailPrice > 0 ? "#22d3ee" : "var(--muted)" }}>
            {retailPrice > 0 ? money(retailPrice, product.currency) : "Non défini"}
          </strong>
        </div>
        <div>
          <span>Marge bénéficiaire</span>
          <strong style={{ color: marginColor }}>
            {margin !== null ? `${margin}%` : "—"}
          </strong>
        </div>
      </div>
      <div className="form-grid">
        <Field label="Nom public">
          <input
            value={form.display_name}
            onChange={(event) => set("display_name", event.target.value)}
          />
        </Field>
        <Field label="Prix de vente">
          <input
            type="number"
            step="0.01"
            value={form.retail_price}
            onChange={(event) => set("retail_price", event.target.value)}
            placeholder={wholesalePrice > 0 ? `Min. ${wholesalePrice}` : ""}
          />
        </Field>
        <Field label="Service">
          <select
            value={form.service_id}
            onChange={(event) => set("service_id", event.target.value)}
          >
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
            <option disabled>──────────</option>
            <option value="__new__">＋ Nouvelle catégorie…</option>
          </select>
        </Field>
        {!isNewService && (
          <Field label="Emoji / Icône">
            <input
              value={form.emoji}
              onChange={(event) => set("emoji", event.target.value)}
              placeholder="Ex: 🤖, 🍿, ✈️..."
              style={{ maxWidth: 90, textAlign: "center", fontSize: "1.2rem" }}
            />
          </Field>
        )}
        {isNewService && (
          <>
            <Field label="Nom de la catégorie">
              <input
                value={newServiceName}
                onChange={(event) => setNewServiceName(event.target.value)}
                placeholder="Ex. Spotify, Disney+…"
                autoFocus
              />
            </Field>
            <Field label="Emoji">
              <input
                value={newServiceEmoji}
                onChange={(event) => setNewServiceEmoji(event.target.value)}
                style={{ maxWidth: 80, textAlign: "center", fontSize: "1.25rem" }}
              />
            </Field>
          </>
        )}
        <Field label="Publication">
          <label className="switch">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => set("enabled", event.target.checked)}
            />
            <span />
            Visible dans le bot
          </label>
        </Field>
        <Field label="Description" wide>
          <textarea
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
          />
        </Field>
        <Field label="Période">
          <div className="duration-input">
            <input type="number" min="1" value={form.period_value} onChange={(event) => set("period_value", event.target.value)} required />
            <select value={form.period_unit} onChange={(event) => set("period_unit", event.target.value)}>
              <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
            </select>
          </div>
        </Field>
        <Field label="Garantie (0 = NW)">
          <div className="duration-input">
            <input type="number" min="0" value={form.warranty_value} onChange={(event) => set("warranty_value", event.target.value)} required />
            <select value={form.warranty_unit} onChange={(event) => set("warranty_unit", event.target.value)}>
              <option value="days">Jours</option><option value="months">Mois</option><option value="years">Années</option>
            </select>
          </div>
        </Field>
        <Field label="Délai de livraison">
          <input
            value={form.delivery_delay}
            onChange={(event) => set("delivery_delay", event.target.value)}
          />
        </Field>
      </div>
      <div className="dialog-actions">
        <ActionButton
          icon={Check}
          disabled={creatingSvc || (isNewService && !newServiceName.trim())}
          onClick={handlePublish}
        >
          {creatingSvc ? "Création…" : "Publier"}
        </ActionButton>
      </div>
    </Modal>
  );
}

function InventoryPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("");
  const [offerId, setOfferId] = useState("");
  const [page, setPage] = useState(1);
  const [revealed, setRevealed] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/inventory", {
    search,
    search_field: searchField,
    status,
    offer_id: offerId,
    page,
    per_page: 25,
  });
  const reveal = async (item) => {
    const response = await fetch("/admin", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-Dashboard-Write-Token": data.dashboard_write_token || "",
      },
      body: new URLSearchParams({
        action: "reveal_inventory",
        inventory_id: item.reference_id,
      }),
    });
    const payload = await response.json();
    if (response.ok) setRevealed({ item, value: payload.value });
  };
  return (
    <>
      <PageHeader
        eyebrow="Livraison"
        title="Inventaire"
        description="Stock chiffré, réservations et livraisons automatiques."
        actions={
          <a
            className="action-button secondary"
            href="/admin/api/inventory-export"
          >
            <Download size={16} />
            Exporter CSV
          </a>
        }
      />
      <FilterBar
        search={search}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["preview", "Aperçu masqué"], ["reference_id", "ID référence"], ["product_id", "ID produit"], ["order_id", "ID commande"]]}
        resultCount={result.total}
        setSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
        placeholder="Référence, produit, commande ou aperçu…"
      >
        <select
          value={offerId}
          onChange={(event) => {
            setOfferId(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Tous les produits</option>
          {data.services
            ?.flatMap((service) => service.offers || [])
            .map((offer, index) => (
              <option
                value={offer.id}
                key={offer.id || `${offer.name}-${index}`}
              >
                {offer.name}
              </option>
            ))}
        </select>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Tous les états</option>
          {["available", "reserved", "delivered", "disabled"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Référence</th>
                <th>Produit</th>
                <th>Aperçu</th>
                <th>État</th>
                <th>Commande</th>
                <th>Date</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={item.reference_id}>
                  <td>#{item.reference_id}</td>
                  <td>#{item.offer_id}</td>
                  <td>
                    <code>{item.masked_preview || "••••••"}</code>
                  </td>
                  <td>
                    <span className={`status ${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.reserved_order_id || item.delivered_order_id || "—"}
                  </td>
                  <td>{date(item.created_at)}</td>
                  <td>
                    <div className="inline-actions">
                      <button title="Révéler" onClick={() => reveal(item)}>
                        <Eye size={15} />
                      </button>
                      <button
                        title="Activer/désactiver"
                        onClick={() =>
                          onAction({
                            action: "toggle_inventory",
                            inventory_id: item.reference_id,
                            disabled: item.status === "disabled" ? "0" : "1",
                          })
                        }
                      >
                        {item.status === "disabled" ? (
                          <ToggleLeft size={16} />
                        ) : (
                          <ToggleRight size={16} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !result.items.length && <Empty icon={Boxes} title="Inventaire vide" />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {revealed && (
        <Modal
          title={`Référence #${revealed.item.reference_id}`}
          onClose={() => setRevealed(null)}
        >
          <pre className="secret-preview">{revealed.value}</pre>
          <div className="dialog-actions">
            <ActionButton
              icon={Copy}
              onClick={() => navigator.clipboard.writeText(revealed.value)}
            >
              Copier
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}

function CustomerDetail({ customer, onAction, onClose, onNavigate, currency }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [loadingOrder, setLoadingOrder] = useState(null);
  const [customerTab, setCustomerTab] = useState("timeline");
  const openOrder = async (order) => {
    setLoadingOrder(order.id);
    try {
      const response = await fetch(`/admin/api/orders?detail=1&order_id=${order.id}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      setSelectedOrder(response.ok ? await response.json() : order);
    } finally {
      setLoadingOrder(null);
    }
  };
  const displayName = [customer.first_name, customer.last_name].filter(Boolean).join(" ")
    || customer.full_name
    || (customer.username ? `@${customer.username}` : `Client ${customer.telegram_id}`);
  const tabs = [
    ["timeline", Activity, "Chronologie", customer.timeline?.length || 0],
    ["orders", ShoppingBag, "Achats", (customer.orders?.length || 0) + (customer.api_purchases?.length || 0)],
    ["finance", CircleDollarSign, "Finances", (customer.topups?.length || 0) + (customer.withdrawals?.length || 0)],
    ["support", Headphones, "Support", customer.tickets?.length || 0],
    ["warranties", ShieldCheck, "Garanties", customer.warranties?.length || 0],
  ];
  return (
    <>
      <Modal
        title={
          customer.username
            ? `@${customer.username}`
            : `Client ${customer.telegram_id}`
        }
        onClose={onClose}
        fullScreen
      >
      <div className="customer-profile-head customer-profile-hero">
        <span>{(customer.first_name || customer.username || "C").slice(0, 1).toUpperCase()}</span>
        <div><strong>{displayName}</strong><small>{customer.username ? `@${customer.username} · ` : ""}ID {customer.telegram_id} · {String(customer.lang || customer.language || "en").toUpperCase()}</small></div>
        <div className="customer-profile-actions">
          <button type="button" onClick={() => {
            const firstTicket = customer.tickets?.[0];
            onClose();
            onNavigate("support", firstTicket?.id || null);
          }}><MessageSquareText size={16} />Messages support</button>
          <i className={customer.banned ? "blocked" : "active"}>{customer.banned ? "Bloqué" : "Actif"}</i>
        </div>
      </div>
      <div className="customer-profile-layout">
        <div className="customer-profile-main">
          <div className="customer-profile-kpis">
            <article><span>Portefeuille</span><strong>{money(customer.wallet_balance, currency)}</strong><small>solde disponible</small></article>
            <article><span>Dépensé</span><strong>{money(customer.total_spent, currency)}</strong><small>{customer.paid_order_count || 0} achat(s) payé(s)</small></article>
            <article><span>Dépôts</span><strong>{money(customer.deposit_total, currency)}</strong><small>{customer.topups?.length || 0} opération(s)</small></article>
            <article><span>Affiliation</span><strong>{customer.referral_count || 0}</strong><small>{money(customer.affiliate_earned, currency)} gagné</small></article>
          </div>
          <div className="customer-facts">
            <div><span>Inscription</span><strong>{date(customer.created_at)}</strong></div>
            <div><span>Dernière activité</span><strong>{date(customer.last_active_at || customer.last_order_at)}</strong></div>
            <div><span>Niveau fidélité</span><strong>{customer.loyalty?.level || "Standard"}</strong></div>
            <div><span>Interactions</span><strong>{customer.interaction_total || customer.interaction_count || 0}</strong></div>
          </div>
        </div>
        <aside className="customer-wallet-control">
          <span className="eyebrow">Contrôle administrateur</span>
          <h4>Portefeuille et accès</h4>
          <div className="form-grid">
            <Field label="Montant"><input type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="+10 ou -5" /></Field>
            <Field label="Motif"><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Correction, bonus…" /></Field>
          </div>
          <div className="dialog-actions wrap">
            <ActionButton icon={CircleDollarSign} disabled={!amount || !reason.trim()} onClick={() => onAction({ action: "adjust_user_wallet", user_id: customer.telegram_id, amount, reason })}>Ajuster</ActionButton>
            <ActionButton danger icon={Ban} onClick={() => onAction({ action: "toggle_ban", user_id: customer.telegram_id, banned: customer.banned ? "0" : "1" })}>{customer.banned ? "Débloquer" : "Bloquer"}</ActionButton>
          </div>
        </aside>
      </div>
      <div className="customer-detail-tabs" role="tablist">
        {tabs.map(([key, Icon, label, count]) => <button key={key} type="button" role="tab" aria-selected={customerTab === key} className={customerTab === key ? "active" : ""} onClick={() => setCustomerTab(key)}><Icon size={14} />{label}<span>{count}</span></button>)}
      </div>
      {customerTab === "timeline" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Vue à 360°</span><h4>Chronologie du client</h4></div><strong>{customer.timeline?.length || 0}</strong></header>
        {customer.timeline?.length ? <div className="customer-timeline">{customer.timeline.map((event, index) => {
          const EventIcon = { order: ShoppingBag, topup: CircleDollarSign, withdrawal: Database, ticket: Headphones, warranty: ShieldCheck, reward: Sparkles, adjustment: Edit3 }[event.type] || Activity;
          return <article key={`${event.type}-${event.id}-${index}`}><span className={`timeline-icon ${event.type}`}><EventIcon size={15} /></span><div><strong>{event.title}</strong><p>{event.description}</p><small>{date(event.created_at)}</small></div><aside>{event.status && <span className={`status ${event.status}`}>{STATUS_LABELS[event.status] || event.status}</span>}{event.amount !== undefined && event.amount !== null && <b className={Number(event.amount) < 0 ? "negative" : ""}>{Number(event.amount) > 0 ? "+" : ""}{money(event.amount, currency)}</b>}</aside></article>;
        })}</div> : <Empty icon={Activity} title="Aucune activité" text="Les futures opérations apparaîtront ici." />}
        <div className="customer-profile-split">
          <div><h5>Programme fidélité</h5><dl><div><dt>Niveau</dt><dd>{customer.loyalty?.level || "Standard"}</dd></div><div><dt>Réduction</dt><dd>{customer.loyalty?.discount_percent || 0}%</dd></div><div><dt>Total reconnu</dt><dd>{money(customer.loyalty?.total_spend, currency)}</dd></div></dl></div>
          <div><h5>Dernières interactions</h5>{customer.interactions?.length ? <ul>{customer.interactions.slice(0, 6).map((event, index) => <li key={`${event.created_at}-${index}`}><span>{event.action || event.interaction_type || "Interaction"}</span><small>{date(event.created_at)}</small></li>)}</ul> : <p>Aucune interaction enregistrée.</p>}</div>
        </div>
        {!!customer.referrals?.length && <div className="customer-subsection"><h5>Profils parrainés</h5><div className="compact-history">{customer.referrals.map((referral, index) => <article key={referral.referred_id || index}><div><strong>{referral.customer?.username ? `@${referral.customer.username}` : referral.customer?.first_name || `Client ${referral.referred_id}`}</strong><small>Telegram ID {referral.referred_id}{referral.qualified_order_id ? ` · commande #${referral.qualified_order_id}` : ""}</small></div><span className={`status ${referral.valid === false ? "pending" : "confirmed"}`}>{referral.valid === false ? "À qualifier" : "Qualifié"}</span><time>{date(referral.qualified_at || referral.created_at)}</time></article>)}</div></div>}
      </section>}
      {customerTab === "orders" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Historique complet</span><h4>Produits achetés</h4></div><strong>{customer.orders?.length || 0}</strong></header>
        {customer.orders?.length ? <div className="customer-purchase-grid">{customer.orders.map((order) => <button type="button" key={order.id} onClick={() => openOrder(order)}>
          <header><span>Commande #{order.id}</span><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></header>
          <h5>{order.offer_name || order.service_name || "Produit supprimé"}</h5>
          <p>{order.product_description || "La description de ce produit n’est plus disponible dans le catalogue."}</p>
          <dl><div><dt>Montant</dt><dd>{money(orderAmount(order), currency)}</dd></div><div><dt>Quantité</dt><dd>{order.qty || 1}</dd></div><div><dt>Garantie</dt><dd>{order.warranty || order.warranty_days ? `${order.warranty || order.warranty_days} j` : "—"}</dd></div></dl>
          <footer><span>{date(order.created_at)}</span><span>Voir tous les détails <Eye size={14} /></span></footer>
        </button>)}</div> : <Empty icon={ShoppingBag} title="Aucun achat" text="Ce client n’a encore passé aucune commande." />}
        {!!customer.api_purchases?.length && <div className="customer-subsection"><h5>Achats via API</h5><div className="compact-history">{customer.api_purchases.map((purchase, index) => <article key={purchase.idempotency_key || index}><div><strong>{purchase.response?.productType || purchase.status || "Achat API"}</strong><small>{purchase.idempotency_key || `Opération ${index + 1}`}</small></div><span className={`status ${purchase.response?.success ? "delivered" : "rejected"}`}>{purchase.response?.success ? "Réussi" : "Échec"}</span><b>{money(purchase.response?.amount, currency)}</b><time>{date(purchase.created_at)}</time></article>)}</div></div>}
        {loadingOrder && <div className="table-loading">Chargement de la commande #{loadingOrder}…</div>}
      </section>}
      {customerTab === "finance" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Traçabilité financière</span><h4>Dépôts, retraits et ajustements</h4></div><strong>{(customer.topups?.length || 0) + (customer.withdrawals?.length || 0)}</strong></header>
        <div className="customer-finance-columns">
          <div><h5>Dépôts</h5>{customer.topups?.length ? <div className="compact-history">{customer.topups.map((item, index) => <article key={item.id || item.txid || index}><div><strong>{DEPOSIT_PROVIDER_LABELS[item.provider] || item.provider || "Dépôt"}</strong><small>{item.txid || `Dépôt #${item.id}`}</small></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b>+{money(item.amount, item.currency || currency)}</b><time>{date(item.created_at)}</time></article>)}</div> : <p>Aucun dépôt.</p>}</div>
          <div><h5>Retraits</h5>{customer.withdrawals?.length ? <div className="compact-history">{customer.withdrawals.map((item, index) => <article key={item.id || index}><div><strong>{item.method || "Retrait"}</strong><small>{item.destination || `Retrait #${item.id}`}</small></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b className="negative">-{money(item.amount, currency)}</b><time>{date(item.created_at)}</time></article>)}</div> : <p>Aucun retrait.</p>}</div>
        </div>
        {!!customer.wallet_adjustments?.length && <div className="customer-subsection"><h5>Ajustements administrateur</h5><div className="compact-history">{customer.wallet_adjustments.map((item) => <article key={item.id}><div><strong>{item.details?.reason || "Ajustement"}</strong><small>Admin {item.actor_id || "système"} · solde après {money(item.details?.balance, currency)}</small></div><b className={Number(item.details?.amount) < 0 ? "negative" : ""}>{Number(item.details?.amount) > 0 ? "+" : ""}{money(item.details?.amount, currency)}</b><time>{date(item.created_at)}</time></article>)}</div></div>}
      </section>}
      {customerTab === "support" && <section className="customer-profile-section"><header><div><span className="eyebrow">Support client</span><h4>Tous les tickets</h4></div><strong>{customer.tickets?.length || 0}</strong></header>{customer.tickets?.length ? <div className="customer-ticket-list">{customer.tickets.map((ticket) => <button type="button" key={ticket.id} onClick={() => { onClose(); onNavigate("support", ticket.id); }}><div><strong>Ticket #{ticket.id}</strong><span className={`status ${ticket.status}`}>{STATUS_LABELS[ticket.status] || ticket.status}</span></div><p>{ticket.subject || ticket.category || ticket.message || "Demande de support"}</p><small>Mis à jour {date(ticket.updated_at || ticket.created_at)}</small><span className="customer-ticket-open">Ouvrir les messages <ChevronRight size={15} /></span></button>)}</div> : <Empty icon={Headphones} title="Aucun ticket" text="Ce client n’a aucune demande de support." />}</section>}
      {customerTab === "warranties" && <section className="customer-profile-section"><header><div><span className="eyebrow">Après-vente</span><h4>Demandes de garantie</h4></div><strong>{customer.warranties?.length || 0}</strong></header>{customer.warranties?.length ? <div className="customer-warranty-grid">{customer.warranties.map((item) => <article key={item.id}><header><strong>Garantie #{item.id}</strong><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span></header><h5>Commande #{item.order_id}</h5><p>{item.reason || "Aucun motif communiqué."}</p><footer><span>{item.days_used || 0} jour(s) utilisé(s)</span><b>{money(item.refund_amount, currency)}</b><time>{date(item.updated_at || item.created_at)}</time></footer></article>)}</div> : <Empty icon={ShieldCheck} title="Aucune garantie" text="Aucune demande après-vente pour ce client." />}</section>}
      </Modal>
      {selectedOrder && (
        <OrderEditor
          order={selectedOrder}
          currency={currency}
          onAction={onAction}
          onClose={() => setSelectedOrder(null)}
        />
      )}
    </>
  );
}

function PendingWalletTopups({ onAction }) {
  const [topups, setTopups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const load = () => {
    setLoading(true);
    return fetch("/admin/api/wallet-topups?status=manual_review", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((payload) => setTopups(payload.items || []))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  const decide = async (topup, approved) => {
    setBusyId(topup.id);
    try {
      const result = await onAction({
        action: approved ? "approve_wallet_topup" : "reject_wallet_topup",
        topup_id: topup.id,
      });
      if (result) await load();
    } finally {
      setBusyId(null);
    }
  };
  if (!loading && !topups.length) return null;
  return (
    <section className="data-panel pending-topups">
      <header>
        <div>
          <span className="eyebrow">Validation manuelle</span>
          <h3>Rechargements on-chain en attente</h3>
          <p>Vérifiez le TXID avant de créditer le portefeuille.</p>
        </div>
        <span className="pending-topup-count">{topups.length}</span>
      </header>
      <div className="responsive-table">
        <table>
          <thead><tr><th>Demande</th><th>Client</th><th>Réseau</th><th>Montant</th><th>TXID</th><th>Date</th><th>Décision</th></tr></thead>
          <tbody>
            {topups.map((topup) => (
              <tr key={topup.id}>
                <td><strong>#{topup.id}</strong></td>
                <td><strong>{topup.username ? `@${topup.username}` : topup.first_name || `Client ${topup.user_id}`}</strong><small>{topup.user_id}</small></td>
                <td><span className="status manual_review">{topup.network === "bsc" ? "BSC (BEP20)" : "Polygon"}</span></td>
                <td><strong>{money(topup.amount, topup.currency || "USDT")}</strong></td>
                <td><a className="txid-link" href={topup.explorer_url} target="_blank" rel="noreferrer" title={topup.txid}>{`${topup.txid.slice(0, 9)}…${topup.txid.slice(-6)}`}</a></td>
                <td>{date(topup.created_at)}</td>
                <td>
                  <div className="topup-actions">
                    <ActionButton icon={Check} disabled={busyId === topup.id} onClick={() => decide(topup, true)}>Accepter</ActionButton>
                    <ActionButton danger icon={X} disabled={busyId === topup.id} onClick={() => decide(topup, false)}>Refuser</ActionButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && <div className="table-loading">Chargement des demandes…</div>}
    </section>
  );
}

const DEPOSIT_PROVIDER_LABELS = {
  binance: "Binance Pay",
  bybit: "Bybit",
  bsc: "BSC (BEP20)",
  polygon: "Polygon",
  solana: "Solana",
  unknown: "Autre",
};

function DepositsPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("all");
  const [provider, setProvider] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/wallet-topups", {
    search,
    search_field: searchField,
    status,
    provider,
    sort: sort === "amount" ? "amount" : "created_at",
    direction: sort === "oldest" ? "asc" : "desc",
    page,
    per_page: 25,
  });
  const summary = result.summary || {};
  const decide = async (topup, approved) => {
    setBusyId(topup.id);
    try {
      await onAction({
        action: approved ? "approve_wallet_topup" : "reject_wallet_topup",
        topup_id: topup.id,
      });
    } finally {
      setBusyId(null);
    }
  };
  const customerName = (topup) => topup.username
    ? `@${topup.username}`
    : topup.full_name || topup.first_name || `Client ${topup.user_id}`;
  return (
    <>
      <PageHeader
        eyebrow="Portefeuilles clients"
        title="Historique des dépôts"
        description="Tous les dépôts effectués par tous les clients, quel que soit le moyen de paiement."
      />
      <div className="order-kpis deposit-kpis">
        <article><div className="order-kpi-icon violet"><Database size={19} /></div><div><small>Dépôts affichés</small><strong>{summary.count || 0}</strong><em>selon les filtres actifs</em></div></article>
        <article><div className="order-kpi-icon green"><CircleDollarSign size={19} /></div><div><small>Montant confirmé</small><strong>{money(summary.confirmed_amount, data.currency || "USDT")}</strong><em>{summary.confirmed || 0} dépôt(s)</em></div></article>
        <article><div className="order-kpi-icon amber"><Clock3 size={19} /></div><div><small>À vérifier</small><strong>{summary.manual_review || 0}</strong><em>validation manuelle</em></div></article>
        <article><div className="order-kpi-icon cyan"><X size={19} /></div><div><small>Refusés</small><strong>{summary.rejected || 0}</strong><em>dépôts non crédités</em></div></article>
      </div>
      <FilterBar
        search={search}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["customer", "Client"], ["user_id", "Telegram ID"], ["txid", "TXID"], ["deposit_id", "N° dépôt"]]}
        resultCount={result.total}
        setSearch={(value) => { setSearch(value); setPage(1); }}
        placeholder="Client, Telegram ID, TXID ou numéro de dépôt…"
      >
        <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filtrer par statut">
          <option value="all">Tous les statuts</option>
          <option value="confirmed">Confirmés</option>
          <option value="manual_review">À vérifier</option>
          <option value="rejected">Refusés</option>
        </select>
        <select value={provider} onChange={(event) => { setProvider(event.target.value); setPage(1); }} aria-label="Filtrer par moyen de paiement">
          <option value="all">Tous les moyens</option>
          <option value="binance">Binance Pay</option>
          <option value="bybit">Bybit</option>
          <option value="bsc">BSC (BEP20)</option>
          <option value="polygon">Polygon</option>
          <option value="solana">Solana</option>
        </select>
        <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }} aria-label="Trier les dépôts">
          <option value="newest">Plus récents</option>
          <option value="oldest">Plus anciens</option>
          <option value="amount">Montant le plus élevé</option>
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead><tr><th>Dépôt</th><th>Client</th><th>Moyen</th><th>Montant crédité</th><th>Montant reçu</th><th>TXID</th><th>Statut</th><th>Date</th><th /></tr></thead>
            <tbody>
              {result.items.map((topup, index) => (
                <tr key={topup.id ?? `${topup.txid}-${index}`}>
                  <td><strong>{topup.id ? `#${topup.id}` : "—"}</strong></td>
                  <td><strong>{customerName(topup)}</strong><small>{topup.user_id}</small></td>
                  <td><span className="deposit-provider">{DEPOSIT_PROVIDER_LABELS[topup.provider] || topup.provider}</span></td>
                  <td><strong>{money(topup.amount, topup.currency || data.currency || "USDT")}</strong></td>
                  <td>{topup.source_amount ? `${topup.source_amount} ${topup.source_currency || ""}` : "—"}</td>
                  <td>{topup.explorer_url ? <a className="txid-link" href={topup.explorer_url} target="_blank" rel="noreferrer" title={topup.txid}>{`${topup.txid.slice(0, 9)}…${topup.txid.slice(-6)}`}</a> : <span className="txid-text" title={topup.txid}>{topup.txid ? `${topup.txid.slice(0, 9)}…${topup.txid.slice(-6)}` : "—"}</span>}</td>
                  <td><span className={`status ${topup.status}`}>{STATUS_LABELS[topup.status] || topup.status}</span></td>
                  <td>{date(topup.created_at)}</td>
                  <td>{topup.status === "manual_review" && <div className="topup-actions"><button className="row-action approve" disabled={busyId === topup.id} onClick={() => decide(topup, true)} title="Accepter"><Check size={15} /></button><button className="row-action reject" disabled={busyId === topup.id} onClick={() => decide(topup, false)} title="Refuser"><X size={15} /></button></div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? <div className="table-loading">Chargement de l’historique…</div> : !result.items.length && <Empty icon={CircleDollarSign} title="Aucun dépôt" text="Aucun dépôt ne correspond aux filtres sélectionnés." />}
        <Pagination value={result} onChange={setPage} />
      </section>
    </>
  );
}

function FinancePage({ data }) {
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [month, setMonth] = useState(currentMonth);
  const [selectedDate, setSelectedDate] = useState("");
  const [result, loading] = useRemoteList("/admin/api/finance", { month }, { refreshInterval: 30_000 });
  const totals = result.totals || {};
  const averages = result.averages || {};
  const days = result.month === month ? result.days || [] : [];
  const currency = result.currency || data.currency || "USDT";
  const monthDate = new Date(`${month}-01T12:00:00Z`);
  const leadingDays = (monthDate.getUTCDay() + 6) % 7;
  const selected = days.find((item) => item.date === selectedDate);
  const monthTotals = days.reduce((summary, day) => ({
    revenue: summary.revenue + Number(day.revenue || 0),
    cost: summary.cost + Number(day.cost || 0),
    profit: summary.profit + Number(day.profit || 0),
  }), { revenue: 0, cost: 0, profit: 0 });
  const changeMonth = (direction) => {
    const next = new Date(`${month}-01T12:00:00Z`);
    next.setUTCMonth(next.getUTCMonth() + direction);
    setMonth(next.toISOString().slice(0, 7));
    setSelectedDate("");
  };
  const startedAt = result.started_at
    ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" }).format(new Date(result.started_at * 1000))
    : "le lancement du bot";
  return (
    <>
      <PageHeader eyebrow="Finance" title="Gains, dépenses et profit." description={`Résultats des ventes et achats API reseller depuis ${startedAt}.`} />
      <section className="finance-kpis" aria-label="Résumé financier">
        <article className="income"><span><TrendingUp size={20} /></span><div><small>Argent gagné</small><strong>{money(totals.revenue, currency)}</strong><em>Ventes encaissées</em></div></article>
        <article className="expense"><span><TrendingDown size={20} /></span><div><small>Argent dépensé</small><strong>{money(totals.cost, currency)}</strong><em>Achats API reseller</em></div></article>
        <article className={Number(totals.profit || 0) < 0 ? "loss" : "profit"}><span><CircleDollarSign size={20} /></span><div><small>Profit net</small><strong>{money(totals.profit, currency)}</strong><em>Gains moins dépenses</em></div></article>
        <article><span><CalendarDays size={20} /></span><div><small>Jours gagnants / pertes</small><strong>{result.profitable_days || 0} / {result.loss_days || 0}</strong><em>Jours avec mouvement</em></div></article>
      </section>
      <section className="finance-averages">
        <article><small>Moyenne par jour</small><strong className={Number(averages.daily_profit || 0) < 0 ? "negative" : "positive"}>{money(averages.daily_profit, currency)}</strong><span>{money(averages.daily_revenue, currency)} de ventes / jour</span></article>
        <article><small>Moyenne par semaine</small><strong className={Number(averages.weekly_profit || 0) < 0 ? "negative" : "positive"}>{money(averages.weekly_profit, currency)}</strong><span>{money(averages.weekly_revenue, currency)} de ventes / semaine</span></article>
        <article><small>{new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(monthDate)}</small><strong className={monthTotals.profit < 0 ? "negative" : "positive"}>{money(monthTotals.profit, currency)}</strong><span>{money(monthTotals.revenue, currency)} gagné · {money(monthTotals.cost, currency)} dépensé</span></article>
      </section>
      <section className="finance-calendar data-panel">
        <header><div><span className="eyebrow">Calendrier du profit</span><h3>{new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(monthDate)}</h3></div><div><button type="button" onClick={() => changeMonth(-1)} aria-label="Mois précédent"><ChevronLeft size={18} /></button><button type="button" onClick={() => { setMonth(currentMonth); setSelectedDate(""); }}>Aujourd’hui</button><button type="button" onClick={() => changeMonth(1)} disabled={month >= currentMonth} aria-label="Mois suivant"><ChevronRight size={18} /></button></div></header>
        {loading ? <div className="table-loading">Calcul des finances…</div> : <>
          <div className="finance-weekdays">{["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((day) => <span key={day}>{day}</span>)}</div>
          <div className="finance-days">{Array.from({ length: leadingDays }).map((_, index) => <i key={`blank-${index}`} />)}{days.map((day) => {
            const profit = Number(day.profit || 0);
            const active = Number(day.revenue || 0) !== 0 || Number(day.cost || 0) !== 0;
            return <button type="button" key={day.date} className={`${profit > 0 ? "gain" : profit < 0 ? "loss" : "neutral"} ${selectedDate === day.date ? "selected" : ""}`} onClick={() => setSelectedDate(day.date)} aria-label={`${day.date}, profit ${money(profit, currency)}`}><span>{Number(day.date.slice(-2))}</span>{active ? <><strong>{profit > 0 ? "+" : ""}{money(profit, currency)}</strong><small>{day.orders || 0} vente(s)</small></> : <small>Aucun mouvement</small>}</button>;
          })}</div>
        </>}
      </section>
      {selected && <section className="finance-day-detail"><div><span>{new Intl.DateTimeFormat("fr-FR", { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${selected.date}T12:00:00Z`))}</span><strong className={selected.profit < 0 ? "negative" : "positive"}>{money(selected.profit, currency)}</strong></div><dl><div><dt>Ventes</dt><dd>{money(selected.revenue, currency)}</dd></div><div><dt>Coût reseller</dt><dd>{money(selected.cost, currency)}</dd></div><div><dt>Commandes</dt><dd>{selected.orders || 0}</dd></div></dl></section>}
      {Number(result.cost_quality?.estimated || 0) > 0 && <p className="finance-estimate-note">{result.cost_quality.estimated} ancien(s) achat(s) utilisent le dernier prix fournisseur enregistré. Les nouveaux achats conservent automatiquement le prix au moment de l’achat.</p>}
      {Number(result.cost_quality?.unknown || 0) > 0 && <p className="finance-estimate-note">{result.cost_quality.unknown} achat(s) fournisseur n’ont pas de prix d’achat enregistré. Le profit affiché peut être surestimé.</p>}
    </>
  );
}

function CustomersPage({ data, onAction, onNavigate }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [walletFilter, setWalletFilter] = useState("all");
  const [ordersFilter, setOrdersFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkAmount, setBulkAmount] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [revision, setRevision] = useState(0);
  const [result, loading] = useRemoteList("/admin/api/customers", {
    search,
    search_field: searchField,
    status: statusFilter,
    wallet: walletFilter,
    orders: ordersFilter,
    sort,
    page,
    per_page: 25,
    revision,
  });
  const open = async (user) => {
    const response = await fetch(
      `/admin/api/customers?user_id=${user.telegram_id}`,
      { credentials: "same-origin", cache: "no-store" },
    );
    if (response.ok) setSelected(await response.json());
  };
  const closeCustomer = () => {
    setSelected(null);
    if (new URLSearchParams(window.location.search).has("user")) window.history.replaceState({}, "", "/admin/customers");
  };
  useEffect(() => {
    const openRequestedCustomer = (userId) => {
      if (userId != null && /^\d+$/.test(String(userId))) open({ telegram_id: Number(userId) });
    };
    openRequestedCustomer(new URLSearchParams(window.location.search).get("user"));
    const navigateToCustomer = (event) => {
      if (event.detail?.page === "customers") openRequestedCustomer(event.detail.entityId);
    };
    const restoreCustomerRoute = () => {
      const requested = new URLSearchParams(window.location.search).get("user");
      if (requested) openRequestedCustomer(requested);
      else setSelected(null);
    };
    window.addEventListener("admin:navigate", navigateToCustomer);
    window.addEventListener("popstate", restoreCustomerRoute);
    return () => {
      window.removeEventListener("admin:navigate", navigateToCustomer);
      window.removeEventListener("popstate", restoreCustomerRoute);
    };
  }, []);
  const customerAction = async (payload) => {
    const result = await onAction(payload);
    if (result) {
      setRevision((value) => value + 1);
      if (selected) await open(selected);
    }
    return result;
  };
  const visible = result.items || [];
  const visibleWallets = visible.reduce((sum, user) => sum + Number(user.wallet_balance || 0), 0);
  const visibleSpent = visible.reduce((sum, user) => sum + Number(user.total_spent || 0), 0);
  const activeVisible = visible.filter((user) => !user.banned).length;
  const hasCustomerFilters = Boolean(
    search
      || searchField !== "all"
      || statusFilter !== "all"
      || walletFilter !== "all"
      || ordersFilter !== "all"
      || sort !== "newest",
  );
  const resetCustomerFilters = () => {
    setSearch("");
    setSearchField("all");
    setStatusFilter("all");
    setWalletFilter("all");
    setOrdersFilter("all");
    setSort("newest");
    setPage(1);
  };
  return (
    <>
      <PageHeader
        eyebrow="CRM"
        title="Profils clients"
        description="Une vue complète de chaque client : identité, portefeuille, achats, dépôts, affiliation, support et activité."
        actions={
          <ActionButton
            icon={CircleDollarSign}
            onClick={() => setBulkOpen(true)}
          >
            Crédit collectif
          </ActionButton>
        }
      />
      <PendingWalletTopups onAction={onAction} />
      <div className="customer-directory-kpis">
        <article><span><Users size={17} /></span><div><small>Clients trouvés</small><strong>{result.total || 0}</strong><em>{activeVisible} actifs sur cette page</em></div></article>
        <article><span><CircleDollarSign size={17} /></span><div><small>Soldes affichés</small><strong>{money(visibleWallets, data.currency)}</strong><em>portefeuilles disponibles</em></div></article>
        <article><span><ShoppingBag size={17} /></span><div><small>Achats affichés</small><strong>{money(visibleSpent, data.currency)}</strong><em>dépenses cumulées</em></div></article>
      </div>
      <section className={`customer-filter-shell ${hasCustomerFilters ? "is-filtered" : ""}`} aria-label="Recherche et filtres clients">
        <header className="customer-filter-heading">
          <div><span><SlidersHorizontal size={16} /></span><div><strong>Affiner les clients</strong><small>Recherchez un profil ou combinez plusieurs critères.</small></div></div>
          <div><strong>{result.total || 0}</strong><span>profil{result.total === 1 ? "" : "s"}</span></div>
        </header>
        <div className="customer-filter-search-row">
          <label className="customer-search-box">
            <Search size={19} aria-hidden="true" />
            <span className="sr-only">Rechercher un client</span>
            <input
              type="search"
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(1); }}
              placeholder="Nom, username ou Telegram ID…"
              aria-label="Rechercher un client par nom, username ou Telegram ID"
            />
            {search && <button type="button" onClick={() => { setSearch(""); setPage(1); }} title="Effacer la recherche" aria-label="Effacer la recherche"><X size={15} /></button>}
          </label>
          <label className="customer-filter-field customer-filter-scope">
            <span>Rechercher dans</span>
            <select value={searchField} onChange={(event) => { setSearchField(event.target.value); setPage(1); }}>
              <option value="all">Tous les champs</option>
              <option value="name">Nom / prénom</option>
              <option value="username">Username</option>
              <option value="telegram_id">Telegram ID</option>
            </select>
          </label>
        </div>
        <div className="customer-filter-controls">
          <label className="customer-filter-field">
            <span>Statut</span>
            <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les statuts</option>
              <option value="active">Clients actifs</option>
              <option value="banned">Clients bloqués</option>
            </select>
          </label>
          <label className="customer-filter-field">
            <span>Portefeuille</span>
            <select value={walletFilter} onChange={(event) => { setWalletFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les soldes</option>
              <option value="funded">Solde positif</option>
              <option value="empty">Solde vide</option>
            </select>
          </label>
          <label className="customer-filter-field">
            <span>Commandes</span>
            <select value={ordersFilter} onChange={(event) => { setOrdersFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les clients</option>
              <option value="with_orders">Avec commandes</option>
              <option value="without_orders">Sans commande</option>
            </select>
          </label>
          <label className="customer-filter-field customer-filter-sort">
            <span>Trier par</span>
            <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
              <option value="newest">Plus récents</option>
              <option value="oldest">Plus anciens</option>
              <option value="balance">Solde le plus élevé</option>
              <option value="spent">Dépenses les plus élevées</option>
              <option value="orders">Plus de commandes</option>
            </select>
          </label>
          <button className="customer-filter-reset" type="button" onClick={resetCustomerFilters} disabled={!hasCustomerFilters}>
            <X size={15} /> Réinitialiser
          </button>
        </div>
      </section>
      <section className="data-panel customer-directory">
        <header className="customer-directory-head"><div><span className="eyebrow">Répertoire CRM</span><h3>Cartes clients</h3></div><span>{result.total || 0} profil(s)</span></header>
        <div className="customer-card-grid">
          {visible.map((user) => {
            const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.full_name || (user.username ? `@${user.username}` : `Client ${user.telegram_id}`);
            return <button type="button" className="customer-card" key={user.telegram_id} onClick={() => open(user)}>
              <header><span className="customer-card-avatar">{(user.first_name || user.username || "C").slice(0, 1).toUpperCase()}</span><div><strong>{name}</strong><small>{user.username ? `@${user.username} · ` : ""}ID {user.telegram_id}</small></div><i className={user.banned ? "blocked" : "active"}>{user.banned ? "Bloqué" : "Actif"}</i></header>
              <div className="customer-card-money"><span><small>Portefeuille</small><strong>{money(user.wallet_balance, data.currency)}</strong></span><span><small>Total dépensé</small><strong>{money(user.total_spent, data.currency)}</strong></span></div>
              <div className="customer-card-metrics"><span><ShoppingBag size={14} /><strong>{user.order_count || 0}</strong><small>achats</small></span><span><Database size={14} /><strong>{user.deposit_count || 0}</strong><small>dépôts</small></span><span><Users size={14} /><strong>{user.referral_count || 0}</strong><small>filleuls</small></span><span><Headphones size={14} /><strong>{user.ticket_count || 0}</strong><small>tickets</small></span></div>
              <footer><div><small>Dernier achat</small><strong>{user.last_order_name || "Aucun achat"}</strong><span>{user.last_order_at ? date(user.last_order_at) : `Inscrit ${date(user.created_at)}`}</span></div><span className="customer-card-open">Profil complet <ChevronRight size={15} /></span></footer>
            </button>;
          })}
        </div>
        {loading ? (
          <div className="table-loading">Chargement des profils…</div>
        ) : (
          !visible.length && <Empty icon={Users} title="Aucun client" text="Aucun profil ne correspond aux filtres sélectionnés." />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {selected && (
        <CustomerDetail
          customer={selected}
          onAction={customerAction}
          onNavigate={onNavigate}
          currency={data.currency}
          onClose={closeCustomer}
        />
      )}
      {bulkOpen && (
        <Modal
          title="Créditer tous les portefeuilles"
          onClose={() => setBulkOpen(false)}
        >
          <div className="warning-box">
            Cette action crédite chaque utilisateur actif. Elle est idempotente
            grâce à un identifiant d’opération unique.
          </div>
          <div className="form-grid">
            <Field label={`Montant (${data.currency})`}>
              <input
                type="number"
                step="0.01"
                value={bulkAmount}
                onChange={(event) => setBulkAmount(event.target.value)}
              />
            </Field>
            <Field label="Confirmation">
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="CREDIT ALL"
              />
            </Field>
          </div>
          <div className="dialog-actions">
            <ActionButton
              danger
              icon={CircleDollarSign}
              disabled={!bulkAmount || confirmation !== "CREDIT ALL"}
              onClick={async () => {
                if (
                  await onAction({
                    action: "bulk_credit_wallets",
                    amount: bulkAmount,
                    confirmation,
                    operation_id: `react-${Date.now()}`,
                  })
                )
                  setBulkOpen(false);
              }}
            >
              Créditer tous
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}

function ResellerClientsPage({ data }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("activity");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/reseller-clients", {
    search,
    search_field: searchField,
    status,
    sort,
    page,
    per_page: 25,
    refresh,
  });
  const summary = result.summary || {};
  const clientName = (client) =>
    client.username
      ? `@${client.username}`
      : client.full_name || client.first_name || `Client ${client.telegram_id}`;
  return (
    <>
      <PageHeader
        eyebrow="API revendeur"
        title="Clients API"
        description="Suivez les accès, portefeuilles, commandes et dépenses des revendeurs utilisant votre API."
        actions={
          <ActionButton secondary icon={RefreshCw} onClick={() => setRefresh((value) => value + 1)}>
            Actualiser
          </ActionButton>
        }
      />
      <section className="order-kpis" aria-label="Statistiques des clients API">
        <article><span className="order-kpi-icon violet"><Users size={19} /></span><div><small>Clients API</small><strong>{summary.clients || 0}</strong><em>{summary.active_clients || 0} actif(s)</em></div></article>
        <article><span className="order-kpi-icon green"><KeyRound size={19} /></span><div><small>Clés actives</small><strong>{summary.active_keys || 0}</strong><em>Secrets toujours masqués</em></div></article>
        <article><span className="order-kpi-icon cyan"><ClipboardList size={19} /></span><div><small>Commandes API</small><strong>{summary.api_orders || 0}</strong><em>Achats réussis</em></div></article>
        <article><span className="order-kpi-icon amber"><CircleDollarSign size={19} /></span><div><small>Dépenses API</small><strong>{money(summary.total_spent, data.currency)}</strong><em>{money(summary.spent_30d, data.currency)} sur 30 jours</em></div></article>
      </section>
      <FilterBar
        search={search}
        setSearch={(value) => { setSearch(value); setPage(1); }}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["name", "Nom"], ["username", "Username"], ["telegram_id", "Telegram ID"], ["prefix", "Préfixe de clé"]]}
        resultCount={result.total}
        placeholder="Nom, username, Telegram ID ou préfixe…"
      >
        <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Filtrer les clients API par statut">
          <option value="all">Tous les accès</option>
          <option value="active">Clé active</option>
          <option value="revoked">Toutes les clés révoquées</option>
        </select>
        <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }} aria-label="Trier les clients API">
          <option value="activity">Activité récente</option>
          <option value="spent">Dépenses les plus élevées</option>
          <option value="orders">Plus de commandes</option>
          <option value="balance">Solde le plus élevé</option>
          <option value="created">Accès les plus récents</option>
        </select>
      </FilterBar>
      <section className="data-panel reseller-clients-panel">
        <div className="responsive-table">
          <table>
            <thead><tr><th>Client</th><th>Telegram ID</th><th>Clé API</th><th>Portefeuille</th><th>Commandes</th><th>Dépensé</th><th>Dernière activité</th><th>Statut</th><th /></tr></thead>
            <tbody>{result.items.map((client) => {
              const activeKey = client.keys.find((key) => key.active) || client.keys[0];
              return <tr key={client.telegram_id} onClick={() => setSelected(client)}>
                <td><strong>{clientName(client)}</strong><small>{client.first_name || client.full_name || "Utilisateur Telegram"}</small></td>
                <td><code>{client.telegram_id}</code></td>
                <td><code>{activeKey ? `${activeKey.prefix}••••` : "—"}</code><small>{client.key_count} clé(s) au total</small></td>
                <td><strong>{money(client.wallet_balance, data.currency)}</strong></td>
                <td><strong>{client.api_order_count || 0}</strong><small>{client.failed_order_count || 0} échec(s)</small></td>
                <td><strong>{money(client.total_spent, data.currency)}</strong><small>{money(client.spent_30d, data.currency)} / 30 j</small></td>
                <td>{date(client.last_activity_at)}</td>
                <td><span className={`status ${client.active_key_count ? "delivered" : "cancelled"}`}>{client.active_key_count ? "Actif" : "Révoqué"}</span></td>
                <td><button className="row-action" aria-label={`Voir ${clientName(client)}`}><Eye size={15} /></button></td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        {loading ? <div className="table-loading">Chargement des clients API…</div> : !result.items.length && <Empty icon={KeyRound} title="Aucun client API" text="Les utilisateurs apparaîtront après la création de leur première clé." />}
        <Pagination value={result} onChange={setPage} />
      </section>
      {selected && (
        <Modal title={`Revendeur · ${clientName(selected)}`} onClose={() => setSelected(null)} wide>
          <div className="detail-grid">
            <div><span>Telegram ID</span><strong>{selected.telegram_id}</strong></div>
            <div><span>Langue</span><strong>{selected.language || "—"}</strong></div>
            <div><span>Inscription</span><strong>{date(selected.joined_at)}</strong></div>
            <div><span>Compte Telegram</span><strong>{selected.banned ? "Bloqué" : "Actif"}</strong></div>
            <div><span>Portefeuille</span><strong>{money(selected.wallet_balance, data.currency)}</strong></div>
            <div><span>Commandes réussies</span><strong>{selected.api_order_count || 0}</strong></div>
            <div><span>Échecs / attentes</span><strong>{selected.failed_order_count || 0} / {selected.pending_order_count || 0}</strong></div>
            <div><span>Total API dépensé</span><strong>{money(selected.total_spent, data.currency)}</strong></div>
          </div>
          <section className="customer-orders">
            <header><div><span className="eyebrow">Sécurité</span><h4>Clés API</h4></div><strong>{selected.keys.length}</strong></header>
            <div className="responsive-table">
              <table>
                <thead><tr><th>ID</th><th>Préfixe masqué</th><th>Libellé</th><th>Créée</th><th>Dernière utilisation</th><th>Statut</th></tr></thead>
                <tbody>{selected.keys.map((key) => <tr key={key.id}><td>#{key.id}</td><td><code>{key.prefix}••••••••</code></td><td>{key.label}</td><td>{date(key.created_at)}</td><td>{date(key.last_used_at)}</td><td><span className={`status ${key.active ? "delivered" : "cancelled"}`}>{key.active ? "Active" : "Révoquée"}</span></td></tr>)}</tbody>
              </table>
            </div>
          </section>
          <section className="customer-orders">
            <header><div><span className="eyebrow">Historique récent</span><h4>Commandes passées via l’API</h4></div><strong>{selected.api_order_count || 0}</strong></header>
            <div className="responsive-table">
              <table>
                <thead><tr><th>Commande</th><th>Produit</th><th>Qté</th><th>Montant</th><th>Résultat</th><th>Date</th></tr></thead>
                <tbody>{selected.recent_purchases.map((purchase, index) => {
                  const resultStatus = purchase.success === true ? "delivered" : purchase.success === false ? "cancelled" : "pending_payment";
                  return <tr key={`${purchase.order_id || "pending"}-${index}`}><td>{purchase.order_id ? `BM-${purchase.order_id}` : "—"}<small>{purchase.idempotency_key || "—"}</small></td><td>{purchase.product || "—"}</td><td>{purchase.quantity || "—"}</td><td>{money(purchase.amount, data.currency)}</td><td><span className={`status ${resultStatus}`}>{purchase.success === true ? "Réussie" : purchase.success === false ? purchase.error_code || "Échec" : "En cours"}</span></td><td>{date(purchase.created_at)}</td></tr>;
                })}</tbody>
              </table>
            </div>
          </section>
        </Modal>
      )}
    </>
  );
}

function OperationsSummary({ items }) {
  return <div className="operations-summary">{items.map(([label, value, tone]) => <article key={label} className={tone || ""}><span>{label}</span><strong>{value}</strong></article>)}</div>;
}

function WithdrawalsPage({ onAction, data }) {
  const initial = new URLSearchParams(window.location.search).get("withdrawal") || "";
  const [search, setSearch] = useState(initial);
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState(null);
  const [note, setNote] = useState("");
  const [result, loading] = useRemoteList("/admin/api/withdrawals", { search, status, page, per_page: 25 }, { refreshInterval: 10000 });
  const refresh = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));
  const run = async (payload) => {
    const completed = await onAction(payload);
    if (completed) { setEditor(null); setNote(""); refresh(); }
  };
  return <div className="operations-page">
    <PageHeader eyebrow="Portefeuille" title="Retraits" description="Traitez les demandes créées dans le bot et suivez les paiements déjà terminés." />
    <OperationsSummary items={[["En attente", result.summary?.pending || 0, "warning"], ["Montant réservé", money(result.summary?.pending_amount, data.currency), "accent"], ["Terminés", result.summary?.completed || 0, "success"], ["Refusés", result.summary?.rejected || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="ID, client, méthode ou destination…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut du retrait"><option value="all">Tous les statuts</option><option value="pending">En attente</option><option value="completed">Terminés</option><option value="rejected">Refusés</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des retraits…</div> : !result.items.length ? <Empty icon={CircleDollarSign} title="Aucun retrait" text="Les demandes envoyées depuis le bot apparaîtront ici." /> : <div className="operation-list">{result.items.map((item) => <article key={item.id} className="operation-card">
        <header><span className="operation-icon"><CircleDollarSign size={20} /></span><div><small>Retrait #{item.id}</small><strong>{item.username ? `@${item.username}` : item.full_name || `Client ${item.user_id}`}</strong></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span></header>
        <div className="operation-amount"><strong>{money(item.amount, data.currency)}</strong><span>{item.method === "bep20" ? "USDT BEP20" : item.method || "Méthode non précisée"}</span></div>
        <dl><div><dt>Destination</dt><dd><code>{item.destination || "—"}</code></dd></div><div><dt>Demandé le</dt><dd>{date(item.created_at)}</dd></div>{item.admin_note && <div><dt>Note admin</dt><dd>{item.admin_note}</dd></div>}</dl>
        {item.status === "pending" && <footer><ActionButton icon={CheckCircle2} onClick={() => run({ action: "complete_withdrawal", withdrawal_id: item.id })}>Marquer payé</ActionButton><ActionButton icon={X} danger onClick={() => { setEditor({ type: "reject", item }); setNote(""); }}>Refuser et rembourser</ActionButton></footer>}
      </article>)}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor?.type === "reject" && <Modal title={`Refuser le retrait #${editor.item.id}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "withdrawal_reject", withdrawal_id: editor.item.id, admin_note: note }); }}><p>Le montant réservé sera automatiquement recrédité dans le portefeuille du client.</p><Field label="Motif du refus" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={5} required autoFocus /></Field><div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Annuler</ActionButton><ActionButton type="submit" danger icon={X}>Refuser et rembourser</ActionButton></div></form></Modal>}
  </div>;
}

function WarrantiesPage({ onAction, data }) {
  const initial = new URLSearchParams(window.location.search).get("warranty") || "";
  const [search, setSearch] = useState(initial);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState(null);
  const [value, setValue] = useState("");
  const [result, loading] = useRemoteList("/admin/api/warranties", { search, status, page, per_page: 25 }, { refreshInterval: 10000 });
  const refresh = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));
  const run = async (payload) => {
    const completed = await onAction(payload);
    if (completed) { setEditor(null); setValue(""); refresh(); }
  };
  const openEditor = (type, item) => { setEditor({ type, item }); setValue(""); };
  return <div className="operations-page warranty-page">
    <PageHeader eyebrow="Après-vente" title="Garanties" description="Examinez les demandes du bot, remboursez le portefeuille ou livrez un remplacement." />
    <OperationsSummary items={[["À traiter", result.summary?.actionable || 0, "warning"], ["Nouvelles", result.summary?.pending || 0, "accent"], ["Acceptées", result.summary?.accepted || 0, "info"], ["Terminées", result.summary?.completed || 0, "success"]]} />
    <FilterBar search={search} setSearch={(next) => { setSearch(next); setPage(1); }} placeholder="Demande, commande, client ou motif…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut de garantie"><option value="">Tous les statuts</option><option value="pending_admin_check">Contrôle admin</option><option value="accepted">Acceptées</option><option value="replacement_pending">Remplacement requis</option><option value="replacement_delivered">Remplacements livrés</option><option value="refunded">Remboursées</option><option value="refused">Refusées</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des garanties…</div> : !result.items.length ? <Empty icon={ShieldCheck} title="Aucune garantie" text="Les demandes créées dans le bot apparaîtront ici." /> : <div className="operation-list warranty-list">{result.items.map((item) => <article key={item.id} className="operation-card">
        <header><span className="operation-icon"><ShieldCheck size={20} /></span><div><small>Garantie #{item.id} · Commande #{item.order_id}</small><strong>{item.product}</strong></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span></header>
        <div className="warranty-customer"><span>{item.username ? `@${item.username}` : item.full_name || `Client ${item.user_id}`}</span><b>{item.days_used || 0} jour(s) utilisé(s)</b></div>
        <p>{item.reason || "Aucun motif communiqué."}</p>
        <dl><div><dt>Garantie produit</dt><dd>{item.warranty}</dd></div><div><dt>Remboursement calculé</dt><dd>{money(item.refund_amount, data.currency)}</dd></div><div><dt>Mise à jour</dt><dd>{date(item.updated_at || item.created_at)}</dd></div>{item.admin_note && <div><dt>Note admin</dt><dd>{item.admin_note}</dd></div>}</dl>
        <footer>{item.status === "pending_admin_check" && <><ActionButton icon={Check} onClick={() => run({ action: "warranty_accept", warranty_id: item.id })}>Accepter</ActionButton><ActionButton danger icon={X} onClick={() => openEditor("refuse", item)}>Refuser</ActionButton></>}{item.status === "accepted" && <><ActionButton icon={PackageCheck} onClick={() => openEditor("replacement", item)}>Remplacement</ActionButton><ActionButton secondary icon={CircleDollarSign} onClick={() => run({ action: "warranty_refund", warranty_id: item.id })}>Rembourser</ActionButton></>}{item.status === "replacement_pending" && <ActionButton icon={Send} onClick={() => openEditor("replacement", item)}>Envoyer le remplacement</ActionButton>}</footer>
      </article>)}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor && <Modal title={editor.type === "refuse" ? `Refuser la garantie #${editor.item.id}` : `Remplacement pour la garantie #${editor.item.id}`} onClose={() => setEditor(null)} wide={editor.type === "replacement"}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run(editor.type === "refuse" ? { action: "warranty_refuse", warranty_id: editor.item.id, admin_note: value } : { action: "warranty_replacement", warranty_id: editor.item.id, replacement: value }); }}><p>{editor.type === "refuse" ? "Le client recevra ce motif dans Telegram." : "Ce contenu sera envoyé directement au client comme nouvelle livraison."}</p><Field label={editor.type === "refuse" ? "Motif du refus" : "Compte ou contenu de remplacement"} wide><textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={editor.type === "refuse" ? 1000 : 3600} rows={editor.type === "refuse" ? 5 : 9} required autoFocus /></Field><div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Annuler</ActionButton><ActionButton type="submit" danger={editor.type === "refuse"} icon={editor.type === "refuse" ? X : Send}>{editor.type === "refuse" ? "Refuser" : "Envoyer au client"}</ActionButton></div></form></Modal>}
  </div>;
}

function SupportPage({ onAction, onNavigate, data }) {
  const initialTicket = new URLSearchParams(window.location.search).get("ticket") || "";
  const [search, setSearch] = useState(initialTicket);
  const [searchField, setSearchField] = useState(initialTicket ? "ticket_id" : "all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [targetTicketId, setTargetTicketId] = useState(initialTicket);
  useEffect(() => {
    const navigateToTicket = (event) => {
      if (event.detail?.page !== "support" || event.detail?.entityId == null) return;
      const id = String(event.detail.entityId);
      setTargetTicketId(id);
      setSearchField("ticket_id");
      setSearch(id);
      setPage(1);
    };
    window.addEventListener("admin:navigate", navigateToTicket);
    return () => window.removeEventListener("admin:navigate", navigateToTicket);
  }, []);
  const [result, loading] = useRemoteList("/admin/api/tickets", {
    status, search, search_field: searchField, page, per_page: 25,
  }, { refreshInterval: 4000 });
  return <SupportInbox result={result} loading={loading} search={search}
    setSearch={(value) => { setSearch(value); setPage(1); }}
    searchField={searchField} setSearchField={(value) => { setSearchField(value); setPage(1); }}
    status={status} setStatus={(value) => { setStatus(value); setPage(1); }}
    targetTicketId={targetTicketId}
    pagination={<Pagination value={result} onChange={setPage} />} onAction={onAction}
    onNavigate={onNavigate}
    writeToken={data?.dashboard_write_token || ""} />;
}

function ProductRequestsPage({ onAction, onNavigate, data }) {
  const initialRequest = new URLSearchParams(window.location.search).get("request") || "";
  const [search, setSearch] = useState(initialRequest);
  const [searchField, setSearchField] = useState(initialRequest ? "ticket_id" : "all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [targetTicketId, setTargetTicketId] = useState(initialRequest);
  useEffect(() => {
    const navigateToRequest = (event) => {
      if (event.detail?.page !== "product-requests" || event.detail?.entityId == null) return;
      const id = String(event.detail.entityId);
      setTargetTicketId(id);
      setSearchField("ticket_id");
      setSearch(id);
      setPage(1);
    };
    window.addEventListener("admin:navigate", navigateToRequest);
    return () => window.removeEventListener("admin:navigate", navigateToRequest);
  }, []);
  const [result, loading] = useRemoteList("/admin/api/tickets", {
    category: "catalog_request", status, search, search_field: searchField, page, per_page: 25,
  }, { refreshInterval: 4000 });
  const summary = result.summary || {};
  return <div className="product-requests-page">
    <PageHeader
      eyebrow="Veille catalogue"
      title="Demandes de produits"
      description="Centralisez les produits recherchés par vos clients, échangez avec eux dans Telegram et repérez les prochaines offres à ajouter au bot."
    />
    <OperationsSummary items={[
      ["Total demandes", summary.total || 0, "accent"],
      ["À traiter", summary.actionable || 0, "warning"],
      ["Réponse client", summary.waiting_customer || 0, "info"],
      ["Terminées", summary.completed || 0, "success"],
    ]} />
    <SupportInbox result={result} loading={loading} search={search}
      setSearch={(value) => { setSearch(value); setPage(1); }}
      searchField={searchField} setSearchField={(value) => { setSearchField(value); setPage(1); }}
      status={status} setStatus={(value) => { setStatus(value); setPage(1); }}
      targetTicketId={targetTicketId}
      pagination={<Pagination value={result} onChange={setPage} />} onAction={onAction}
      onNavigate={onNavigate}
      writeToken={data?.dashboard_write_token || ""}
      variant="product-requests"
      showBulkActions={false} />
  </div>;
}

function InteractionsPage({ data }) {
  const analytics = data.interactions || {};
  const summary = analytics.summary || {};
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [type, setType] = useState("");
  const events = (analytics.events || []).filter(
    (event) => {
      const searchable = {
        user: `${event.full_name || ""} ${event.username || ""} ${event.user_id || ""}`,
        action: event.action || "",
        content: `${event.content || ""} ${event.screen || ""}`,
      };
      const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
      return (!type || event.interaction_type === type) && (!search || haystack.toLowerCase().includes(search.toLowerCase()));
    },
  );
  const max = Math.max(
    ...(analytics.daily || []).map((point) => point.count),
    1,
  );
  return (
    <>
      <PageHeader
        eyebrow="Analyse"
        title="Interactions"
        description="Messages, commandes et clics enregistrés dans le bot."
      />
      <div className="mini-kpi-grid">
        <div>
          <span>Total</span>
          <strong>{summary.total || 0}</strong>
        </div>
        <div>
          <span>Aujourd’hui</span>
          <strong>{summary.today || 0}</strong>
        </div>
        <div>
          <span>Utilisateurs actifs</span>
          <strong>{summary.active_today || 0}</strong>
        </div>
        <div>
          <span>Clics boutons</span>
          <strong>{summary.button_clicks || 0}</strong>
        </div>
      </div>
      <section className="data-panel analytics-panel">
        <header>
          <h3>Interactions sur 30 jours</h3>
        </header>
        <div className="bar-chart">
          {(analytics.daily || []).map((point) => (
            <div key={point.date} title={`${point.date}: ${point.count}`}>
              <i
                style={{ height: `${Math.max(4, (point.count / max) * 100)}%` }}
              />
              <span>{point.date.slice(8)}</span>
            </div>
          ))}
        </div>
      </section>
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["user", "Utilisateur"], ["action", "Action"], ["content", "Message / écran"]]}
        resultCount={events.length}
        placeholder="Nom, utilisateur, message ou action…"
      >
        <select value={type} onChange={(event) => setType(event.target.value)}>
          <option value="">Tous les types</option>
          {["button", "message", "command", "media", "other"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Utilisateur</th>
                <th>Type</th>
                <th>Action</th>
                <th>Contenu / écran</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => (
                <tr key={event.id || index}>
                  <td>{date(event.created_at)}</td>
                  <td>
                    <strong>
                      {event.full_name || event.first_name || event.user_id}
                    </strong>
                    <small>
                      {event.username ? `@${event.username}` : event.user_id}
                    </small>
                  </td>
                  <td>
                    <span className="status">{event.interaction_type}</span>
                  </td>
                  <td>
                    <code>{event.action || "—"}</code>
                  </td>
                  <td>{event.content || event.screen || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.length && <Empty icon={Activity} title="Aucune interaction" />}
      </section>
    </>
  );
}

function ActivityPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [undoTarget, setUndoTarget] = useState(null);
  const events = (data.audits || []).filter(
    (item) => {
      const searchable = {
        action: item.action || "",
        actor: `${item.actor_id || ""} ${item.user_id || ""}`,
        details: JSON.stringify(item.details || {}),
      };
      const haystack = searchField === "all" ? Object.values(searchable).join(" ") : searchable[searchField] || "";
      return !search || haystack.toLowerCase().includes(search.toLowerCase());
    },
  );
  return (
    <>
      <PageHeader
        eyebrow="Sécurité"
        title="Journal d’activité"
        description="Historique des actions administratives et événements système."
      />
      <FilterBar
        search={search}
        setSearch={setSearch}
        searchField={searchField}
        setSearchField={setSearchField}
        options={[["all", "Tout"], ["action", "Action"], ["actor", "Acteur / utilisateur"], ["details", "Détails"]]}
        resultCount={events.length}
        placeholder="Action, acteur, utilisateur ou détail…"
      />
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Action</th>
                <th>Acteur</th>
                <th>Détails</th>
                <th>Restauration</th>
              </tr>
            </thead>
            <tbody>
              {events.map((item, index) => (
                <tr key={item.id || index}>
                  <td>{date(item.created_at)}</td>
                  <td>
                    <strong>{item.action}</strong>
                  </td>
                  <td>{item.actor_id || item.user_id || "Système"}</td>
                  <td>
                    <code className="audit-details">
                      {typeof item.details === "string"
                        ? item.details
                        : JSON.stringify(item.details || {})}
                    </code>
                  </td>
                  <td>{item.details?.undone ? <span className="status delivered">Restauré</span> : item.id && item.details?.reversible ? <button className="audit-undo-button" onClick={() => setUndoTarget(item)}><RefreshCw size={13} />Annuler</button> : <span className="audit-not-reversible">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.length && <Empty icon={Activity} title="Aucun événement" />}
      </section>
      {undoTarget && <Modal title="Restaurer cette modification ?" onClose={() => setUndoTarget(null)}><div className="undo-confirm"><span><RefreshCw size={27} /></span><strong>{undoTarget.action}</strong><p>La restauration fonctionne pendant 24 heures. Les éléments modifiés depuis cet événement seront ignorés afin de ne pas écraser un changement plus récent.</p><code>Événement #{undoTarget.id}</code><div><ActionButton secondary onClick={() => setUndoTarget(null)}>Conserver</ActionButton><ActionButton icon={RefreshCw} onClick={async () => { await onAction({ action: "undo_audit_event", event_id: undoTarget.id }); setUndoTarget(null); }}>Restaurer</ActionButton></div></div></Modal>}
    </>
  );
}

function SettingsPage({ data, onAction, onHealthCheck }) {
  const [form, setForm] = useState({
    shop_name: data.shop_name || "BlackMarket",
    currency: data.currency || "USDT",
    low_stock_threshold: data.low_stock_threshold || 5,
    order_expiry_seconds: data.order_expiry_seconds || 1800,
    payment_recipient: data.payment_recipient || "",
    affiliate_enabled: data.affiliate_enabled !== false,
    affiliate_target: data.affiliate_target || 10,
    affiliate_reward_cents: data.affiliate_reward_cents || 100,
    maintenance_enabled: data.maintenance_enabled === true,
    maintenance_message: data.maintenance_message || "",
    welcome_message: data.welcome_message || "",
    help_message: data.help_message || "",
    terms_message: data.terms_message || "",
    privacy_message: data.privacy_message || "",
    active_languages: data.active_languages || "en,ar",
    announcement_new_stock: data.announcement_new_stock || "",
    announcement_flash_sale: data.announcement_flash_sale || "",
    announcement_restock: data.announcement_restock || "",
  });
  const set = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Paramètres"
        description="Personnalisez la boutique, le paiement, l’affiliation et les messages."
        actions={
          <>
            <ActionButton
              secondary
              icon={ShieldCheck}
              onClick={() => onHealthCheck("telegram")}
            >
              Telegram
            </ActionButton>
            <ActionButton secondary icon={RefreshCw} onClick={() => onHealthCheck("telegram-repair")}>Réparer le webhook</ActionButton>
            <ActionButton
              secondary
              icon={Cloud}
              onClick={() => onHealthCheck("binance")}
            >
              Binance
            </ActionButton>
          </>
        }
      />
      <form
        className="settings-layout"
        onSubmit={(event) => {
          event.preventDefault();
          onAction({
            action: "save_settings",
            ...form,
            affiliate_enabled: form.affiliate_enabled ? "on" : "",
            maintenance_enabled: form.maintenance_enabled ? "on" : "",
          });
        }}
      >
        <section className="settings-card">
          <header>
            <Settings size={18} />
            <div>
              <h3>Boutique</h3>
              <p>Identité et règles commerciales.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Nom">
              <input
                value={form.shop_name}
                onChange={(event) => set("shop_name", event.target.value)}
              />
            </Field>
            <Field label="Devise">
              <input
                value={form.currency}
                onChange={(event) => set("currency", event.target.value)}
              />
            </Field>
            <Field label="Seuil stock faible">
              <input
                type="number"
                value={form.low_stock_threshold}
                onChange={(event) =>
                  set("low_stock_threshold", event.target.value)
                }
              />
            </Field>
            <Field label="Expiration commande (secondes)">
              <input
                type="number"
                value={form.order_expiry_seconds}
                onChange={(event) =>
                  set("order_expiry_seconds", event.target.value)
                }
              />
            </Field>
            <Field label="Identifiant de paiement" wide>
              <input
                value={form.payment_recipient}
                onChange={(event) =>
                  set("payment_recipient", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <section className="settings-card">
          <header>
            <Users size={18} />
            <div>
              <h3>Affiliation et maintenance</h3>
              <p>Contrôlez les récompenses et la disponibilité.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Affiliation">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={form.affiliate_enabled}
                  onChange={(event) =>
                    set("affiliate_enabled", event.target.checked)
                  }
                />
                <span />
                Activée
              </label>
            </Field>
            <Field label="Objectif">
              <input
                type="number"
                value={form.affiliate_target}
                onChange={(event) =>
                  set("affiliate_target", event.target.value)
                }
              />
            </Field>
            <Field label="Récompense (centimes)">
              <input
                type="number"
                value={form.affiliate_reward_cents}
                onChange={(event) =>
                  set("affiliate_reward_cents", event.target.value)
                }
              />
            </Field>
            <Field label="Maintenance">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={form.maintenance_enabled}
                  onChange={(event) =>
                    set("maintenance_enabled", event.target.checked)
                  }
                />
                <span />
                Activée
              </label>
            </Field>
            <Field label="Message maintenance" wide>
              <textarea
                value={form.maintenance_message}
                onChange={(event) =>
                  set("maintenance_message", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <section className="settings-card full">
          <header>
            <MessageSquareText size={18} />
            <div>
              <h3>Contenu du bot</h3>
              <p>Messages personnalisés affichés aux clients.</p>
            </div>
          </header>
          <div className="form-grid">
            <Field label="Accueil">
              <textarea
                value={form.welcome_message}
                onChange={(event) => set("welcome_message", event.target.value)}
              />
            </Field>
            <Field label="Aide">
              <textarea
                value={form.help_message}
                onChange={(event) => set("help_message", event.target.value)}
              />
            </Field>
            <Field label="Conditions">
              <textarea
                value={form.terms_message}
                onChange={(event) => set("terms_message", event.target.value)}
              />
            </Field>
            <Field label="Confidentialité">
              <textarea
                value={form.privacy_message}
                onChange={(event) => set("privacy_message", event.target.value)}
              />
            </Field>
            <Field label="Langues actives" wide>
              <input
                value={form.active_languages}
                onChange={(event) => {
                  const languages = event.target.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter((value) => ["en", "ar"].includes(value));
                  set("active_languages", [...new Set(languages)].join(",") || "en");
                }}
                placeholder="en,ar"
              />
            </Field>
            <Field label="Annonce Nouveau Stock" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock}, {added}" wide>
              <textarea
                rows={5}
                value={form.announcement_new_stock}
                onChange={(event) =>
                  set("announcement_new_stock", event.target.value)
                }
              />
            </Field>
            <Field label="Annonce Vente Flash" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {old_price}, {price}, {cur}, {discount}, {remaining}" wide>
              <textarea
                rows={5}
                value={form.announcement_flash_sale}
                onChange={(event) =>
                  set("announcement_flash_sale", event.target.value)
                }
              />
            </Field>
            <Field label="Annonce Restock / Produit disponible" help="Variables: {emoji}, {service}, {offer}, {period}, {warranty}, {price}, {cur}, {stock}" wide>
              <textarea
                rows={5}
                value={form.announcement_restock}
                onChange={(event) =>
                  set("announcement_restock", event.target.value)
                }
              />
            </Field>
          </div>
        </section>
        <div className="settings-submit">
          <ActionButton icon={Check} type="submit">
            Enregistrer les paramètres
          </ActionButton>
        </div>
      </form>
    </>
  );
}

const AI_QUICK_PROMPTS = [
  ["Bot overview", "Give me an operational overview of the bot and the top three priorities right now."],
  ["Orders to review", "Analyze recent orders and identify those that need administrator attention."],
  ["Critical stock", "Analyze inventory and propose the most urgent actions without executing them."],
  ["Optimize sales", "Analyze sales, pricing, and the catalog, then suggest concrete improvements."],
  ["Urgent support", "Summarize support tickets and alerts that need a fast response."],
];

function AiManagerPage({ data, onAction, setToast }) {
  const [config, setConfig] = useState({ configured: false, models: [] });
  const [model, setModel] = useState(window.localStorage.getItem("ai-manager-model") || "");
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: "Hello. I can answer questions across the bot database, analyze operations, and propose administrative actions for your confirmation.",
  }]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  useEffect(() => {
    let active = true;
    fetch("/admin/api/ai-manager/config", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "AI configuration is unavailable.");
        if (!active) return;
        setConfig(payload);
        const selected = payload.models?.includes(model) ? model : payload.models?.[0] || "";
        setModel(selected);
      })
      .catch((error) => active && setToast({ type: "error", title: "AI Bot Manager", message: error.message }));
    return () => { active = false; };
  }, []);

  const selectModel = (value) => {
    setModel(value);
    window.localStorage.setItem("ai-manager-model", value);
  };

  const send = async (preset) => {
    const content = String(preset || input).trim();
    if (!content || sending || !model) return;
    const userMessage = { role: "user", content };
    const history = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setSending(true);
    try {
      const response = await fetch("/admin/api/ai-manager/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Dashboard-Write-Token": data?.dashboard_write_token || "",
        },
        body: JSON.stringify({
          model,
          messages: history.map(({ role, content: messageContent }) => ({ role, content: messageContent })),
        }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "The AI response is unavailable.");
      setMessages((current) => [...current, {
        role: "assistant",
        content: payload.reply,
        actions: payload.suggested_actions || [],
        model: payload.model,
      }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", error: true, content: error.message }]);
    } finally {
      setSending(false);
    }
  };

  const executeAction = async () => {
    if (!pendingAction) return;
    const completed = await onAction(pendingAction.parameters);
    if (completed) {
      setMessages((current) => [...current, {
        role: "assistant",
        content: `Action “${pendingAction.label}” was executed and the bot data was refreshed.`,
      }]);
    }
    setPendingAction(null);
  };

  return (
    <>
      <PageHeader
        eyebrow="Administrator copilot"
        title="AI Bot Manager"
        description="Ask questions across the bot database and manage operations by conversation. Every change requires your confirmation."
        actions={(
          <div className={`ai-manager-status ${config.configured ? "ready" : ""}`}>
            <span />{config.configured ? "OpenAI configured" : "OpenAI key required"}
          </div>
        )}
      />
      <section className="ai-manager-layout">
        <aside className="ai-manager-sidebar">
          <div className="ai-manager-brand"><Sparkles size={21} /><div><strong>Full admin assistant</strong><span>Database context refreshed for every question</span></div></div>
          <label className="ai-model-select"><span>Active model</span><select value={model} onChange={(event) => selectModel(event.target.value)}>{config.models?.map((item) => <option key={item} value={item}>{item}</option>)}</select>{config.endpoint_host && <small>API: {config.provider || config.endpoint_host}</small>}</label>
          <div className="ai-quick-list"><span>Quick questions</span>{AI_QUICK_PROMPTS.map(([label, prompt]) => <button key={label} disabled={sending || !config.configured} onClick={() => send(prompt)}><Sparkles size={13} />{label}</button>)}</div>
          <div className="ai-safety-note"><ShieldCheck size={17} /><div><strong>Human control</strong><span>The AI proposes. You confirm every action before execution.</span></div></div>
        </aside>
        <div className="ai-chat-panel">
          <div className="ai-chat-messages">
            {messages.map((message, index) => (
              <article className={`ai-message ${message.role} ${message.error ? "error" : ""}`} key={`${message.role}-${index}`}>
                <div className="ai-message-avatar">{message.role === "assistant" ? <Sparkles size={15} /> : "A"}</div>
                <div className="ai-message-body"><div className="ai-message-meta"><strong>{message.role === "assistant" ? "AI Bot Manager" : "You"}</strong>{message.model && <span>{message.model}</span>}</div><p>{message.content}</p>
                  {!!message.actions?.length && <div className="ai-proposals">{message.actions.map((action, actionIndex) => <div className={`ai-proposal risk-${action.risk}`} key={`${action.action}-${actionIndex}`}><div><span>{action.risk === "high" ? "High risk" : action.risk === "medium" ? "Confirmation required" : "Low risk"}</span><strong>{action.label}</strong><p>{action.description}</p></div><button onClick={() => setPendingAction(action)}>Review and execute</button></div>)}</div>}
                </div>
              </article>
            ))}
            {sending && <article className="ai-message assistant"><div className="ai-message-avatar"><RefreshCw className="spin" size={15} /></div><div className="ai-message-body"><p>Analyzing the current bot database…</p></div></article>}
          </div>
          <form className="ai-chat-composer" onSubmit={(event) => { event.preventDefault(); send(); }}><textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={config.configured ? "Ask about any database record, analysis, or admin action…" : "Add HP_OPENAI_API_KEY in Railway first"} disabled={!config.configured || sending} rows={2} /><button type="submit" disabled={!input.trim() || sending || !config.configured}><Send size={17} /></button></form>
        </div>
      </section>
      {pendingAction && <Modal title="Confirm AI action" onClose={() => setPendingAction(null)}><div className="ai-confirm"><ShieldCheck size={30} /><strong>{pendingAction.label}</strong><p>{pendingAction.confirmation}</p><pre>{JSON.stringify(pendingAction.parameters, null, 2)}</pre><div><ActionButton secondary onClick={() => setPendingAction(null)}>Cancel</ActionButton><ActionButton danger={pendingAction.risk === "high"} icon={Check} onClick={executeAction}>Confirm and execute</ActionButton></div></div></Modal>}
    </>
  );
}

export default function AdminPage({
  page,
  data,
  onAction,
  onHealthCheck,
  onNavigate,
  setToast,
}) {
  const props = { data, onAction, onHealthCheck, onNavigate, setToast };
  if (page === "ai-manager") return <AiManagerPage {...props} />;
  if (page === "orders") return <OrdersPage {...props} />;
  if (page === "catalog") return <CatalogPage {...props} />;
  if (page === "api-products") return <ApiProductsPage {...props} />;
  if (page === "api-clients") return <ResellerClientsPage {...props} />;
  if (page === "inventory") return <InventoryPage {...props} />;
  if (page === "customers") return <CustomersPage {...props} />;
  if (page === "deposits") return <DepositsPage {...props} />;
  if (page === "withdrawals") return <WithdrawalsPage {...props} />;
  if (page === "warranties") return <WarrantiesPage {...props} />;
  if (page === "finance") return <FinancePage {...props} />;
  if (page === "support") return <SupportPage {...props} />;
  if (page === "product-requests") return <ProductRequestsPage {...props} />;
  if (page === "interactions") return <InteractionsPage {...props} />;
  if (page === "activity") return <ActivityPage {...props} />;
  if (page === "settings") return <SettingsPage {...props} />;
  return null;
}
