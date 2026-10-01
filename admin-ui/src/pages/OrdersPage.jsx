import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Boxes,
  Check,
  CheckCircle2,
  CircleDollarSign,
  ClipboardList,
  Clock3,
  Columns3,
  Copy,
  CreditCard,
  Edit3,
  ExternalLink,
  PackageCheck,
  PackagePlus,
  Plus,
  RefreshCw,
  Send,
  TrendingUp,
  UserRound,
  X,
} from "lucide-react";
import { STATUS_LABELS, money, orderAmount, orderCustomerName, orderCustomerReference, date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";

function DeliveredProductDescription({ order }) {
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
    <div className="delivered-product-description">
      <header><span>Description du produit</span>{order.product_description && <button type="button" onClick={copyDescription} aria-label="Copier la description du produit"><Copy size={14} />{copied ? "Copié" : "Copier"}</button>}</header>
      <p>{description}</p>
      <small className="copy-description-status" aria-live="polite">{copied ? "Description copiée dans le presse-papiers." : ""}</small>
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
          {confirmation && <div className="order-confirmation" role="alertdialog" aria-label={confirmation.label}><div><strong>{confirmation.label} ?</strong><span>{confirmation.action === "refund_order" ? `${money(order.charged_total, currency)} seront crédités une seule fois sur le portefeuille du client, qui sera notifié.` : "Cette action peut notifier le client."}</span></div><button type="button" onClick={() => setConfirmation(null)}>Retour</button><button type="button" className="danger" onClick={() => submit(confirmation.action, confirmation.extra)}>Confirmer</button></div>}
        </aside>
      </div>
    </div>
  );
}

export default function OrdersPage({ data, onAction, onNavigate }) {
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
        title="Commandes"
        description="Suivez les paiements, les livraisons et les interventions manuelles."
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
        {viewMode === "cards" ? <div className="mobile-order-cards">{result.items.map((order) => <button className={order.needs_attention ? "needs-attention" : ""} key={order.id} onClick={() => openOrder(order)}><header><strong>#{order.id}</strong><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></header>{order.attention_reason && <em className="order-attention">{order.attention_reason}</em>}<h3>{order.offer_name || order.service_name || "Produit"}</h3><span className="order-customer-display"><strong>{orderCustomerName(order)}</strong><small>{orderCustomerReference(order)}</small></span><footer><strong>{money(orderAmount(order), data.currency)}</strong><span>{date(order.created_at)}</span></footer><small>Ouvrir la fiche et les actions →</small></button>)}</div> : viewMode === "table" ? <div className="responsive-table">
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
                  {visibleColumns.includes("product") && <td><div className="order-table-product"><strong>{order.offer_name || order.service_name || "—"}</strong></div></td>}
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
        </div> : <div className="orders-kanban">{kanbanColumns.map((column) => <section className={`kanban-column ${column.id}`} key={column.id}><header><div><span>{column.label}</span><small>{column.items.length} sur cette page</small></div><strong>{column.total}</strong></header><div className="kanban-cards">{column.items.map((order) => <button className={`kanban-order ${order.needs_attention ? "needs-attention" : ""}`} onClick={() => openOrder(order)} key={order.id}><div><strong>#{order.id}</strong><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></div>{order.attention_reason && <em className="order-attention">{order.attention_reason}</em>}<h4>{order.offer_name || order.service_name || "Produit"}</h4><span className="order-customer-display"><strong>{orderCustomerName(order)}</strong><small>{orderCustomerReference(order)}</small></span><footer><b>{money(orderAmount(order), data.currency)}</b><small>{date(order.created_at)}</small></footer></button>)}{!column.items.length && <div className="kanban-empty">Aucune commande sur cette page</div>}</div></section>)}</div>}
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
