import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Archive,
  Ban,
  Boxes,
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
  Database,
  Download,
  Edit3,
  Eye,
  Globe2,
  Headphones,
  KeyRound,
  MessageSquareText,
  PackagePlus,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  ToggleLeft,
  ToggleRight,
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

function Modal({ title, children, onClose, wide = false }) {
  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <section
        className={`form-dialog ${wide ? "wide" : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <h3>{title}</h3>
          <button onClick={onClose}>
            <X size={19} />
          </button>
        </header>
        <div className="form-dialog-body">{children}</div>
      </section>
    </div>
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

function useRemoteList(endpoint, filters) {
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
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    fetch(`${endpoint}?${debouncedQuery}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    })
      .then((response) => {
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
      .catch(() => undefined)
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      controller.abort();
    };
  }, [endpoint, debouncedQuery, syncVersion]);
  return [result, loading];
}

function OrderEditor({ order, onAction, onClose, currency }) {
  const [status, setStatus] = useState(order.status || "pending_payment");
  const [note, setNote] = useState(order.admin_note || "");
  const [message, setMessage] = useState("");
  const [delivery, setDelivery] = useState(
    order.delivery_content ||
      (order.delivery_text === "[encrypted automatic delivery]"
        ? ""
        : order.delivery_text || ""),
  );
  const customer = order.customer || {};
  const submit = async (action, extra = {}) => {
    if (await onAction({ action, order_id: order.id, ...extra })) onClose();
  };
  return (
    <Modal title={`Commande #${order.id}`} onClose={onClose} wide>
      <div className="detail-grid">
        <div>
          <span>Client</span>
          <strong>
            {order.username ? `@${order.username}` : order.user_id}
          </strong>
        </div>
        <div>
          <span>Produit</span>
          <strong>{order.offer_name || order.service_name || "—"}</strong>
        </div>
        <div>
          <span>Montant</span>
          <strong>{money(orderAmount(order), currency)}</strong>
        </div>
        <div>
          <span>Créée</span>
          <strong>{date(order.created_at)}</strong>
        </div>
        <div>
          <span>ID client</span>
          <strong>{order.user_id || customer.telegram_id || "—"}</strong>
        </div>
        <div>
          <span>Quantité</span>
          <strong>{order.qty || 1}</strong>
        </div>
        <div>
          <span>Prix unitaire</span>
          <strong>{money(order.unit_price, currency)}</strong>
        </div>
        <div>
          <span>Statut</span>
          <strong>{STATUS_LABELS[order.status] || order.status || "—"}</strong>
        </div>
        <div>
          <span>ID offre</span>
          <strong>{order.offer_id || "—"}</strong>
        </div>
        <div>
          <span>TXID</span>
          <strong title={order.txid || ""}>{order.txid || "—"}</strong>
        </div>
        <div>
          <span>Vérification</span>
          <strong>{order.verify_method || "—"}</strong>
        </div>
        <div>
          <span>Livrée</span>
          <strong>{date(order.delivered_at)}</strong>
        </div>
      </div>
      <section className="delivery-detail">
        <header>
          <div>
            <span>Contenu livré au client</span>
            <small>{delivery ? "Contenu complet de la livraison" : "Aucun contenu livré pour cette commande"}</small>
          </div>
          {delivery && (
            <button type="button" onClick={() => navigator.clipboard?.writeText(delivery)} title="Copier le contenu">
              <Copy size={15} /> Copier
            </button>
          )}
        </header>
        <pre>{delivery || "—"}</pre>
      </section>
      <div className="form-grid">
        <Field label="Statut">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {Object.entries(STATUS_LABELS)
              .slice(0, 11)
              .map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Note administrateur">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        <Field label="Message au client">
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Message Telegram…"
          />
        </Field>
        <Field label="Contenu de livraison">
          <textarea
            value={delivery}
            onChange={(event) => setDelivery(event.target.value)}
            placeholder="Identifiants ou code…"
          />
        </Field>
      </div>
      <div className="dialog-actions wrap">
        <ActionButton
          icon={Check}
          onClick={() =>
            submit("update_order_admin", { status, admin_note: note })
          }
        >
          Enregistrer
        </ActionButton>
        <ActionButton
          secondary
          icon={Send}
          disabled={!message.trim()}
          onClick={() => submit("message_customer", { message })}
        >
          Envoyer
        </ActionButton>
        <ActionButton
          secondary
          icon={PackagePlus}
          disabled={!delivery.trim()}
          onClick={() =>
            submit("manual_deliver_order", { delivery_text: delivery })
          }
        >
          Livrer
        </ActionButton>
        <ActionButton
          secondary
          icon={RefreshCw}
          onClick={() => submit("reset_order")}
        >
          Réinitialiser
        </ActionButton>
        <ActionButton
          secondary
          icon={Send}
          onClick={() => submit("resend_delivery")}
        >
          Renvoyer
        </ActionButton>
        <ActionButton
          danger
          icon={CircleDollarSign}
          onClick={() =>
            submit("refund_order", {
              reason: note || "Remboursement depuis le dashboard React",
            })
          }
        >
          Rembourser
        </ActionButton>
        <ActionButton
          danger
          icon={X}
          onClick={() =>
            submit("cancel_order", {
              reason: note || "Annulée depuis le dashboard React",
            })
          }
        >
          Annuler
        </ActionButton>
      </div>
    </Modal>
  );
}

function OrdersPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("date");
  const [direction, setDirection] = useState("desc");
  const [selected, setSelected] = useState(null);
  const [viewMode, setViewMode] = useState(window.localStorage.getItem("admin-orders-view") || "table");
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
    page,
    per_page: 25,
    sort,
    direction,
  });
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
  const statusSegments = useMemo(() => {
    const colors = {
      delivered: "#34d399",
      paid: "#22d3ee",
      payment_confirmed: "#60a5fa",
      cancelled: "#fb7185",
      refunded: "#f97316",
      pending_payment: "#fbbf24",
      manual_review: "#a78bfa",
    };
    return Object.entries(analytics.statuses || {})
      .map(([key, value]) => ({ key, value, color: colors[key] || "#64748b" }))
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
  const totalStatuses = statusSegments.reduce((sum, item) => sum + item.value, 0);
  let donutCursor = 0;
  const donutBackground = statusSegments.length
    ? `conic-gradient(${statusSegments.map((item) => {
        const start = donutCursor;
        donutCursor += (item.value / totalStatuses) * 100;
        return `${item.color} ${start}% ${donutCursor}%`;
      }).join(", ")})`
    : "conic-gradient(#1c2b3d 0 100%)";
  const toggleSort = (nextSort) => {
    if (sort === nextSort) setDirection((value) => (value === "desc" ? "asc" : "desc"));
    else {
      setSort(nextSort);
      setDirection("desc");
    }
    setPage(1);
  };
  const openOrder = async (order) => {
    const response = await fetch(`/admin/api/orders?detail=1&order_id=${order.id}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    setSelected(response.ok ? await response.json() : order);
  };
  return (
    <>
      <PageHeader
        eyebrow="Ventes"
        title="Commandes"
        description="Suivez les paiements, livraisons et interventions manuelles."
      />
      <section className="order-kpis" aria-label="Statistiques des commandes">
        <article><span className="order-kpi-icon violet"><ClipboardList size={19} /></span><div><small>Total commandes</small><strong>{analytics.total || 0}</strong><em>Volume global</em></div></article>
        <article><span className="order-kpi-icon cyan"><CircleDollarSign size={19} /></span><div><small>Chiffre d'affaires</small><strong>{money(analytics.revenue, data.currency)}</strong><em>Commandes encaissées</em></div></article>
        <article><span className="order-kpi-icon green"><CheckCircle2 size={19} /></span><div><small>Taux de livraison</small><strong>{analytics.success_rate || 0}%</strong><em>{analytics.delivered || 0} livrée(s)</em></div></article>
        <article><span className="order-kpi-icon amber"><Clock3 size={19} /></span><div><small>À traiter</small><strong>{analytics.pending || 0}</strong><em>Action requise</em></div></article>
      </section>
      <section className="order-analytics-grid">
        <article className="data-panel order-trend-card">
          <header><div><span className="eyebrow">Activité</span><h3>Commandes sur 7 jours</h3></div><TrendingUp size={19} /></header>
          <div className="order-line-chart">
            <svg viewBox="0 0 600 160" preserveAspectRatio="none" role="img" aria-label="Courbe des commandes sur 7 jours">
              {[30, 86, 142].map((y) => <line key={y} x1="0" x2="600" y1={y} y2={y} className="order-grid-line" />)}
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
      </section>
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
        <div className="order-view-switch" aria-label="Mode d’affichage"><button className={viewMode === "table" ? "active" : ""} onClick={() => { setViewMode("table"); window.localStorage.setItem("admin-orders-view", "table"); }} type="button"><ClipboardList size={14} />Tableau</button><button className={viewMode === "kanban" ? "active" : ""} onClick={() => { setViewMode("kanban"); window.localStorage.setItem("admin-orders-view", "kanban"); }} type="button"><Boxes size={14} />Kanban</button></div>
        {viewMode === "table" && <button className="column-picker-trigger" type="button" onClick={() => setColumnsOpen(true)}><Columns3 size={14} />Colonnes</button>}
      </FilterBar>
      <section className="data-panel">
        {viewMode === "table" ? <div className="responsive-table">
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
                <tr key={order.id} onClick={() => openOrder(order)}>
                  <td>
                    <strong>#{order.id}</strong>
                  </td>
                  {visibleColumns.includes("customer") && <td>
                    {order.username ? `@${order.username}` : order.user_id}
                  </td>}
                  {visibleColumns.includes("product") && <td>{order.offer_name || order.service_name || "—"}</td>}
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
        </div> : <div className="orders-kanban">{kanbanColumns.map((column) => <section className={`kanban-column ${column.id}`} key={column.id}><header><div><span>{column.label}</span><small>{column.items.length} sur cette page</small></div><strong>{column.total}</strong></header><div className="kanban-cards">{column.items.map((order) => <button className="kanban-order" onClick={() => openOrder(order)} key={order.id}><div><strong>#{order.id}</strong><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></div><h4>{order.offer_name || order.service_name || "Produit"}</h4><p>{order.username ? `@${order.username}` : `Client ${order.user_id}`}</p><footer><b>{money(orderAmount(order), data.currency)}</b><small>{date(order.created_at)}</small></footer></button>)}{!column.items.length && <div className="kanban-empty">Aucune commande sur cette page</div>}</div></section>)}</div>}
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !result.items.length && (
            <Empty icon={ClipboardList} title="Aucune commande" />
          )
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {selected && (
        <OrderEditor
          order={selected}
          currency={data.currency}
          onAction={onAction}
          onClose={() => setSelected(null)}
        />
      )}
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
  const visibleServices = (data.services || []).map((service) => {
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
        eyebrow="Bot Telegram"
        title="Catalogue du bot"
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
  const [provider, setProvider] = useState("mailreader");
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
    const startedAt = performance.now();
    if (selectCatalog) setLoading(true);
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
      if (selectCatalog) setCatalog(payload);
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
      if (selectCatalog) setCatalog(null);
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
      if (selectCatalog) setLoading(false);
    }
  };
  const load = () => loadProvider(provider, { showToast: true, selectCatalog: true });
  useEffect(() => {
    fetch("/admin/api/reseller-providers", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Configuration fournisseurs indisponible");
        setProviderMeta(payload.providers || []);
      })
      .catch((error) => setToast({ type: "error", title: "Centre API indisponible", message: error.message }));
  }, []);
  useEffect(() => {
    load();
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
        eyebrow="Automatisation"
        title="Produits API"
        description="Connectez les fournisseurs et publiez leurs produits dans votre boutique."
        actions={
          <div className="inline-actions">
            <ActionButton icon={Sparkles} onClick={comparePrices} disabled={comparisonLoading}>
              {comparisonLoading ? "Analyse IA…" : "Comparer les prix avec l’IA"}
            </ActionButton>
            <ActionButton secondary icon={RefreshCw} onClick={load}>
              Synchroniser
            </ActionButton>
          </div>
        }
      />
      <section className="provider-health-center">
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
      </section>
      {comparison && (
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
      <div className="provider-tabs">
        {PROVIDERS.map(([id, label]) => (
          <button
            className={provider === id ? "active" : ""}
            onClick={() => setProvider(id)}
            key={id}
          >
            <Cloud size={16} />
            {label}
          </button>
        ))}
      </div>
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
                <button onClick={() => setEditing(product)}>
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
      <BuyerKeys setToast={setToast} writeToken={data.dashboard_write_token} />
      <CustomExternalApis setToast={setToast} writeToken={data.dashboard_write_token} />
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

function CustomerDetail({ customer, onAction, onClose, currency }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [loadingOrder, setLoadingOrder] = useState(null);
  const [customerTab, setCustomerTab] = useState("orders");
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
  return (
    <>
      <Modal
        title={
          customer.username
            ? `@${customer.username}`
            : `Client ${customer.telegram_id}`
        }
        onClose={onClose}
        wide
      >
      <div className="customer-profile-head"><span>{(customer.first_name || customer.username || "C").slice(0, 1).toUpperCase()}</span><div><strong>{[customer.first_name, customer.last_name].filter(Boolean).join(" ") || (customer.username ? `@${customer.username}` : `Client ${customer.telegram_id}`)}</strong><small>{customer.username ? `@${customer.username} · ` : ""}{customer.banned ? "Compte bloqué" : "Compte actif"}</small></div><i className={customer.banned ? "blocked" : "active"}>{customer.banned ? "Bloqué" : "Actif"}</i></div>
      <div className="detail-grid">
        <div>
          <span>Telegram ID</span>
          <strong>{customer.telegram_id}</strong>
        </div>
        <div>
          <span>Portefeuille</span>
          <strong>{money(customer.wallet_balance, currency)}</strong>
        </div>
        <div>
          <span>Commandes</span>
          <strong>{customer.order_count || 0}</strong>
        </div>
        <div>
          <span>Total dépensé</span>
          <strong>{money(customer.total_spent, currency)}</strong>
        </div>
        <div><span>Affiliés</span><strong>{customer.referrals || 0}</strong></div>
        <div><span>Tickets</span><strong>{customer.tickets?.length || 0}</strong></div>
        <div><span>Langue</span><strong>{String(customer.lang || "en").toUpperCase()}</strong></div>
        <div><span>Inscription</span><strong>{date(customer.created_at)}</strong></div>
      </div>
      <div className="form-grid">
        <Field label="Ajustement du solde">
          <input
            type="number"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="+10 ou -5"
          />
        </Field>
        <Field label="Motif">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
      </div>
      <div className="dialog-actions wrap">
        <ActionButton
          icon={CircleDollarSign}
          disabled={!amount}
          onClick={() =>
            onAction({
              action: "adjust_user_wallet",
              user_id: customer.telegram_id,
              amount,
              reason,
            })
          }
        >
          Ajuster
        </ActionButton>
        <ActionButton
          danger
          icon={Ban}
          onClick={() =>
            onAction({
              action: "toggle_ban",
              user_id: customer.telegram_id,
              banned: customer.banned ? "0" : "1",
            })
          }
        >
          {customer.banned ? "Débloquer" : "Bloquer"}
        </ActionButton>
      </div>
      <div className="customer-detail-tabs"><button className={customerTab === "orders" ? "active" : ""} onClick={() => setCustomerTab("orders")}><ShoppingBag size={14} />Commandes <span>{customer.orders?.length || 0}</span></button><button className={customerTab === "tickets" ? "active" : ""} onClick={() => setCustomerTab("tickets")}><Headphones size={14} />Support <span>{customer.tickets?.length || 0}</span></button></div>
      {customerTab === "orders" ? <section className="customer-orders">
        <header>
          <div>
            <span className="eyebrow">Historique complet</span>
            <h4>Commandes de ce client</h4>
          </div>
          <strong>{customer.orders?.length || 0}</strong>
        </header>
        {customer.orders?.length ? (
          <div className="responsive-table">
            <table>
              <thead>
                <tr><th>Commande</th><th>Produit</th><th>Montant</th><th>Statut</th><th>Date</th><th>Détails</th></tr>
              </thead>
              <tbody>
                {customer.orders.map((order) => (
                  <tr key={order.id} onClick={() => openOrder(order)}>
                    <td><strong>#{order.id}</strong></td>
                    <td>{order.offer_name || order.service_name || "—"}</td>
                    <td>{money(orderAmount(order), currency)}</td>
                    <td><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></td>
                    <td>{date(order.created_at)}</td>
                    <td><button className="row-action" type="button" aria-label={`Voir la commande ${order.id}`}><Eye size={15} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={ShoppingBag} title="Aucune commande" text="Ce client n’a encore passé aucune commande." />
        )}
        {loadingOrder && <div className="table-loading">Chargement de la commande #{loadingOrder}…</div>}
      </section> : <section className="customer-orders customer-tickets"><header><div><span className="eyebrow">Support client</span><h4>Tickets récents</h4></div><strong>{customer.tickets?.length || 0}</strong></header>{customer.tickets?.length ? <div className="customer-ticket-list">{customer.tickets.map((ticket) => <article key={ticket.id}><div><strong>Ticket #{ticket.id}</strong><span className={`status ${ticket.status}`}>{STATUS_LABELS[ticket.status] || ticket.status}</span></div><p>{ticket.subject || ticket.category || ticket.message || "Demande de support"}</p><small>Mis à jour {date(ticket.updated_at || ticket.created_at)}</small></article>)}</div> : <Empty icon={Headphones} title="Aucun ticket" text="Ce client n’a aucune demande de support." />}</section>}
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

function CustomersPage({ data, onAction }) {
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
  const [result, loading] = useRemoteList("/admin/api/customers", {
    search,
    search_field: searchField,
    status: statusFilter,
    wallet: walletFilter,
    orders: ordersFilter,
    sort,
    page,
    per_page: 25,
  });
  const open = async (user) => {
    const response = await fetch(
      `/admin/api/customers?user_id=${user.telegram_id}`,
      { credentials: "same-origin" },
    );
    if (response.ok) setSelected(await response.json());
  };
  return (
    <>
      <PageHeader
        eyebrow="CRM"
        title="Clients"
        description="Portefeuilles, achats, affiliation et accès au bot."
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
      <FilterBar
        search={search}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["name", "Nom / prénom"], ["username", "Username"], ["telegram_id", "Telegram ID"]]}
        resultCount={result.total}
        setSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
        placeholder="Nom, username ou Telegram ID…"
      >
        <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }} aria-label="Filtrer par statut">
          <option value="all">Tous les statuts</option>
          <option value="active">Clients actifs</option>
          <option value="banned">Clients bloqués</option>
        </select>
        <select value={walletFilter} onChange={(event) => { setWalletFilter(event.target.value); setPage(1); }} aria-label="Filtrer par portefeuille">
          <option value="all">Tous les portefeuilles</option>
          <option value="funded">Solde positif</option>
          <option value="empty">Solde vide</option>
        </select>
        <select value={ordersFilter} onChange={(event) => { setOrdersFilter(event.target.value); setPage(1); }} aria-label="Filtrer par commandes">
          <option value="all">Tous les clients</option>
          <option value="with_orders">Avec commandes</option>
          <option value="without_orders">Sans commande</option>
        </select>
        <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }} aria-label="Trier les clients">
          <option value="newest">Plus récents</option>
          <option value="oldest">Plus anciens</option>
          <option value="balance">Solde le plus élevé</option>
          <option value="spent">Dépenses les plus élevées</option>
          <option value="orders">Plus de commandes</option>
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Telegram ID</th>
                <th>Portefeuille</th>
                <th>Commandes</th>
                <th>Dépensé</th>
                <th>Affiliés</th>
                <th>Statut</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.items.map((user) => (
                <tr key={user.telegram_id} onClick={() => open(user)}>
                  <td>
                    <strong>
                      {user.username
                        ? `@${user.username}`
                        : user.first_name || "Client"}
                    </strong>
                  </td>
                  <td>{user.telegram_id}</td>
                  <td>{money(user.wallet_balance, data.currency)}</td>
                  <td>{user.order_count || 0}</td>
                  <td>{money(user.total_spent, data.currency)}</td>
                  <td>{user.referral_count || 0}</td>
                  <td>
                    <span
                      className={`status ${user.banned ? "cancelled" : "delivered"}`}
                    >
                      {user.banned ? "Bloqué" : "Actif"}
                    </span>
                  </td>
                  <td>
                    <button className="row-action">
                      <UserRound size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !result.items.length && <Empty icon={Users} title="Aucun client" />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {selected && (
        <CustomerDetail
          customer={selected}
          onAction={onAction}
          currency={data.currency}
          onClose={() => setSelected(null)}
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

function TicketDialog({ ticket, onAction, onClose }) {
  const [messages, setMessages] = useState([]);
  const [reply, setReply] = useState("");
  const load = () =>
    fetch(`/admin/api/ticket-messages?ticket_id=${ticket.id}`, {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((payload) =>
        setMessages(Array.isArray(payload) ? payload : payload.messages || []),
      );
  useEffect(load, [ticket.id]);
  return (
    <Modal title={`Ticket #${ticket.id}`} onClose={onClose} wide>
      <div className="ticket-thread">
        {messages.map((message, index) => (
          <div
            className={`ticket-message ${message.sender_type === "admin" ? "admin" : ""}`}
            key={message.id || index}
          >
            <strong>
              {message.sender_type === "admin" ? "Admin" : "Client"}
            </strong>
            <p>{message.message || message.content}</p>
            <span>{date(message.created_at)}</span>
          </div>
        ))}
        {!messages.length && (
          <Empty icon={MessageSquareText} title="Conversation vide" />
        )}
      </div>
      <Field label="Réponse">
        <textarea
          value={reply}
          onChange={(event) => setReply(event.target.value)}
          placeholder="Votre réponse…"
        />
      </Field>
      <div className="dialog-actions wrap">
        <ActionButton
          icon={Send}
          disabled={!reply.trim()}
          onClick={async () => {
            if (
              await onAction({
                action: "reply_ticket",
                ticket_id: ticket.id,
                message: reply,
              })
            ) {
              setReply("");
              load();
            }
          }}
        >
          Répondre
        </ActionButton>
        <ActionButton
          secondary
          icon={Archive}
          onClick={async () => {
            if (
              await onAction({ action: "close_ticket", ticket_id: ticket.id })
            )
              onClose();
          }}
        >
          Fermer le ticket
        </ActionButton>
      </div>
    </Modal>
  );
}

function SupportPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [ticket, setTicket] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/tickets", {
    status,
    search,
    search_field: searchField,
    page,
    per_page: 25,
  });
  const items = result.items;
  return (
    <>
      <PageHeader
        eyebrow="Assistance"
        title="Support"
        description="Consultez les conversations et répondez directement aux clients."
      />
      <FilterBar
        search={search}
        setSearch={(value) => { setSearch(value); setPage(1); }}
        searchField={searchField}
        setSearchField={(value) => { setSearchField(value); setPage(1); }}
        options={[["all", "Tout"], ["ticket_id", "ID ticket"], ["user_id", "ID client"], ["category", "Catégorie"], ["message", "Message"]]}
        resultCount={result.total}
        placeholder="Ticket, client, catégorie ou message…"
      >
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Tous les statuts</option>
          {Object.entries(STATUS_LABELS)
            .slice(11)
            .map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Client</th>
                <th>Catégorie</th>
                <th>Statut</th>
                <th>Mis à jour</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} onClick={() => setTicket(item)}>
                  <td>
                    <strong>#{item.id}</strong>
                  </td>
                  <td>{item.user_id}</td>
                  <td>{item.category || "Général"}</td>
                  <td>
                    <span className={`status ${item.status}`}>
                      {STATUS_LABELS[item.status] || item.status}
                    </span>
                  </td>
                  <td>{date(item.updated_at || item.created_at)}</td>
                  <td>
                    <button className="row-action">
                      <MessageSquareText size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? (
          <div className="table-loading">Chargement…</div>
        ) : (
          !items.length && <Empty icon={Headphones} title="Aucun ticket" />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {ticket && (
        <TicketDialog
          ticket={ticket}
          onAction={onAction}
          onClose={() => setTicket(null)}
        />
      )}
    </>
  );
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
  ["Résumé du bot", "Donne-moi un résumé opérationnel du bot et les 3 priorités du moment."],
  ["Commandes à surveiller", "Analyse les commandes récentes et indique celles qui demandent une intervention."],
  ["Stock critique", "Analyse le stock et propose les actions les plus urgentes, sans les exécuter."],
  ["Optimiser les ventes", "Analyse les ventes, les prix et le catalogue puis propose des optimisations concrètes."],
  ["Support urgent", "Résume les tickets et alertes support qui nécessitent une réponse rapide."],
];

function AiManagerPage({ data, onAction, setToast }) {
  const [config, setConfig] = useState({ configured: false, models: [] });
  const [model, setModel] = useState(window.localStorage.getItem("ai-manager-model") || "");
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: "Bonjour. Je peux analyser les commandes, le stock, les ventes, les clients, le support et proposer des actions administratives à confirmer.",
  }]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  useEffect(() => {
    let active = true;
    fetch("/admin/api/ai-manager/config", { credentials: "same-origin", cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Configuration IA indisponible.");
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
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "Réponse IA indisponible.");
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
        content: `Action « ${pendingAction.label} » exécutée et données du bot actualisées.`,
      }]);
    }
    setPendingAction(null);
  };

  return (
    <>
      <PageHeader
        eyebrow="Copilote administrateur"
        title="AI Bot Manager"
        description="Analysez et gérez le bot par conversation. Toute modification exige votre confirmation."
        actions={(
          <div className={`ai-manager-status ${config.configured ? "ready" : ""}`}>
            <span />{config.configured ? "IA configurée" : "Configuration requise"}
          </div>
        )}
      />
      <section className="ai-manager-layout">
        <aside className="ai-manager-sidebar">
          <div className="ai-manager-brand"><Sparkles size={21} /><div><strong>Assistant complet</strong><span>Contexte actualisé à chaque message</span></div></div>
          <label className="ai-model-select"><span>Modèle actif</span><select value={model} onChange={(event) => selectModel(event.target.value)}>{config.models?.map((item) => <option key={item} value={item}>{item}</option>)}</select>{config.endpoint_host && <small>API : {config.endpoint_host}</small>}</label>
          <div className="ai-quick-list"><span>Questions rapides</span>{AI_QUICK_PROMPTS.map(([label, prompt]) => <button key={label} disabled={sending || !config.configured} onClick={() => send(prompt)}><Sparkles size={13} />{label}</button>)}</div>
          <div className="ai-safety-note"><ShieldCheck size={17} /><div><strong>Contrôle humain</strong><span>L’IA propose. Vous confirmez chaque action avant exécution.</span></div></div>
        </aside>
        <div className="ai-chat-panel">
          <div className="ai-chat-messages">
            {messages.map((message, index) => (
              <article className={`ai-message ${message.role} ${message.error ? "error" : ""}`} key={`${message.role}-${index}`}>
                <div className="ai-message-avatar">{message.role === "assistant" ? <Sparkles size={15} /> : "A"}</div>
                <div className="ai-message-body"><div className="ai-message-meta"><strong>{message.role === "assistant" ? "AI Bot Manager" : "Vous"}</strong>{message.model && <span>{message.model}</span>}</div><p>{message.content}</p>
                  {!!message.actions?.length && <div className="ai-proposals">{message.actions.map((action, actionIndex) => <div className={`ai-proposal risk-${action.risk}`} key={`${action.action}-${actionIndex}`}><div><span>{action.risk === "high" ? "Risque élevé" : action.risk === "medium" ? "Confirmation" : "Action sûre"}</span><strong>{action.label}</strong><p>{action.description}</p></div><button onClick={() => setPendingAction(action)}>Vérifier et exécuter</button></div>)}</div>}
                </div>
              </article>
            ))}
            {sending && <article className="ai-message assistant"><div className="ai-message-avatar"><RefreshCw className="spin" size={15} /></div><div className="ai-message-body"><p>Analyse des données actuelles du bot…</p></div></article>}
          </div>
          <form className="ai-chat-composer" onSubmit={(event) => { event.preventDefault(); send(); }}><textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={config.configured ? "Demandez une analyse ou une action…" : "Configurez d’abord l’API IA dans Railway"} disabled={!config.configured || sending} rows={2} /><button type="submit" disabled={!input.trim() || sending || !config.configured}><Send size={17} /></button></form>
        </div>
      </section>
      {pendingAction && <Modal title="Confirmer l’action IA" onClose={() => setPendingAction(null)}><div className="ai-confirm"><ShieldCheck size={30} /><strong>{pendingAction.label}</strong><p>{pendingAction.confirmation}</p><pre>{JSON.stringify(pendingAction.parameters, null, 2)}</pre><div><ActionButton secondary onClick={() => setPendingAction(null)}>Annuler</ActionButton><ActionButton danger={pendingAction.risk === "high"} icon={Check} onClick={executeAction}>Confirmer et exécuter</ActionButton></div></div></Modal>}
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
  if (page === "support") return <SupportPage {...props} />;
  if (page === "interactions") return <InteractionsPage {...props} />;
  if (page === "activity") return <ActivityPage {...props} />;
  if (page === "settings") return <SettingsPage {...props} />;
  return null;
}
