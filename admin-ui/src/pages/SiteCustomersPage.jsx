import { useEffect, useState } from "react";
import {
  ChevronRight,
  CircleDollarSign,
  ExternalLink,
  Headphones,
  PackageSearch,
  RefreshCw,
  Save,
  ShieldCheck,
  ShoppingBag,
  Users,
  Wallet,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";
import { DEPOSIT_STATUS, dinars, refreshLists, CartStatus, useSiteQuery } from "../site-format.jsx";

function CustomerDetail({ customer, onAction, onClose, onNavigate }) {
  const [tab, setTab] = useState("orders");
  const [deposits, setDeposits] = useState(null);
  const [related, setRelated] = useState(null);
  const [adjusting, setAdjusting] = useState(false);
  const [adjustment, setAdjustment] = useState({ amount: "", note: "" });
  const [sending, setSending] = useState(false);
  useEffect(() => {
    if (!customer.email && !customer.name) {
      setDeposits([]);
      return undefined;
    }
    const controller = new AbortController();
    const search = encodeURIComponent(customer.email || customer.name);
    fetch(`/admin/api/site-deposits?search=${search}&status=all&per_page=20`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    }).then(async (response) => {
      const payload = response.ok ? await response.json() : { items: [] };
      setDeposits((payload.items || []).filter((item) => item.customer_id === customer.id));
    }).catch((error) => {
      if (error.name !== "AbortError") setDeposits([]);
    });
    return () => controller.abort();
  }, [customer]);
  useEffect(() => {
    const controller = new AbortController();
    const load = async (path) => {
      const response = await fetch(path, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
      return response.ok ? response.json() : { items: [] };
    };
    const mine = (items) => (items || []).filter((item) => Number(item.customer_id) === Number(customer.id));
    Promise.all([
      load("/admin/api/tickets?channel=tn_site&per_page=100"),
      load("/admin/api/warranties?channel=tn_site&per_page=100"),
    ]).then(([tickets, warranties]) => {
      const rows = mine(tickets.items);
      setRelated({
        tickets: rows.filter((item) => item.category !== "catalog_request"),
        requests: rows.filter((item) => item.category === "catalog_request"),
        warranties: mine(warranties.items),
      });
    }).catch((error) => {
      if (error.name !== "AbortError") setRelated({ tickets: [], requests: [], warranties: [] });
    });
    return () => controller.abort();
  }, [customer.id]);
  const submitAdjust = async (event) => {
    event.preventDefault();
    setSending(true);
    try {
      if (await onAction({ action: "site_wallet_adjust", customer_id: customer.id, ...adjustment })) {
        setAdjusting(false);
        refreshLists();
        onClose();
      }
    } finally {
      setSending(false);
    }
  };
  const initial = (customer.name || customer.email || "C").slice(0, 1).toUpperCase();
  return <Modal title={customer.name || customer.email || `Client ${customer.id}`} onClose={onClose} fullScreen>
    <div className="customer-profile-head customer-profile-hero">
      <span>{initial}</span>
      <div>
        <strong>{customer.name || "Client"}</strong>
        <small>{customer.email || "Sans email"}{customer.phone ? ` · ${customer.phone}` : ""} · ID {customer.id}</small>
      </div>
      <div className="customer-profile-actions">
        {customer.email && <a href={`mailto:${customer.email}`}><ExternalLink size={16} />Écrire un email</a>}
        <button type="button" onClick={() => { setAdjusting(true); setAdjustment({ amount: "", note: "" }); }}><Wallet size={16} />Ajuster le solde</button>
      </div>
    </div>
    <div className="customer-profile-kpis">
      <article><span>Portefeuille</span><strong>{dinars(customer.balance_millimes)}</strong><small>solde disponible</small></article>
      <article><span>Dépensé</span><strong>{dinars(customer.total_spent_millimes)}</strong><small>{customer.carts_count} panier(s)</small></article>
      <article><span>À vérifier</span><strong>{customer.pending_count}</strong><small>paniers en attente</small></article>
      <article><span>Client depuis</span><strong>{date(customer.created_at)}</strong><small>{customer.last_order_at ? `Dernière commande ${date(customer.last_order_at)}` : "Aucune commande"}</small></article>
    </div>
    <div className="customer-detail-tabs" role="tablist">
      <button type="button" role="tab" aria-selected={tab === "orders"} className={tab === "orders" ? "active" : ""} onClick={() => setTab("orders")}><ShoppingBag size={14} />Commandes<span>{customer.carts?.length || 0}</span></button>
      <button type="button" role="tab" aria-selected={tab === "deposits"} className={tab === "deposits" ? "active" : ""} onClick={() => setTab("deposits")}><CircleDollarSign size={14} />Recharges<span>{deposits?.length ?? "—"}</span></button>
      {related?.tickets?.length > 0 && <button type="button" role="tab" aria-selected={tab === "support"} className={tab === "support" ? "active" : ""} onClick={() => setTab("support")}><Headphones size={14} />Support<span>{related.tickets.length}</span></button>}
      {related?.requests?.length > 0 && <button type="button" role="tab" aria-selected={tab === "requests"} className={tab === "requests" ? "active" : ""} onClick={() => setTab("requests")}><PackageSearch size={14} />Demandes<span>{related.requests.length}</span></button>}
      {related?.warranties?.length > 0 && <button type="button" role="tab" aria-selected={tab === "warranties"} className={tab === "warranties" ? "active" : ""} onClick={() => setTab("warranties")}><ShieldCheck size={14} />Garanties<span>{related.warranties.length}</span></button>}
    </div>
    {tab === "orders" && <section className="customer-profile-section">
      <header><div><span className="eyebrow">Historique</span><h4>Paniers</h4></div><strong>{customer.carts_count}</strong></header>
      {!customer.carts?.length ? <Empty icon={ShoppingBag} title="Aucun achat" text="Ce client n’a pas encore commandé." />
        : <ul className="site-recent site-history">{customer.carts.map((cart) => <li key={cart.reference}>
          <button type="button" className="site-link" onClick={() => { onClose(); onNavigate("site-orders", cart.reference); }}>
            <strong>{cart.reference}</strong>
          </button>
          <div><small>{date(cart.created_at)} · {cart.payment_label}</small><small>{cart.items.map((item) => `${item.quantity} × ${item.offer_name}`).join(", ")}</small></div>
          <b>{dinars(cart.total_millimes)}</b>
          <CartStatus status={cart.status} />
        </li>)}</ul>}
    </section>}
    {tab === "deposits" && <section className="customer-profile-section">
      <header><div><span className="eyebrow">Portefeuille</span><h4>Recharges</h4></div></header>
      {deposits == null ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des recharges…</div>
        : !deposits.length ? <Empty icon={Wallet} title="Aucune recharge" text="Les demandes de ce client apparaîtront ici." />
        : <ul className="site-recent site-history">{deposits.map((deposit) => {
          const [label, className] = DEPOSIT_STATUS[deposit.status] || [deposit.status, ""];
          return <li key={deposit.id}>
            <button type="button" className="site-link" onClick={() => { onClose(); onNavigate("site-deposits", deposit.id, { search: customer.email || deposit.transaction_reference || "", status: "all" }); }}>
              <strong>Recharge #{deposit.id}</strong>
            </button>
            <div><small>{date(deposit.created_at)} · {deposit.method_label}{deposit.transaction_reference ? ` · ${deposit.transaction_reference}` : ""}</small></div>
            <b>{dinars(deposit.status === "approved" ? deposit.credited_millimes : deposit.amount_millimes)}</b>
            <span className={`status ${className}`}>{label}</span>
          </li>;
        })}</ul>}
    </section>}
    {tab === "support" && related?.tickets?.length > 0 && <section className="customer-profile-section">
      <header><div><span className="eyebrow">Support</span><h4>Tickets de ce client</h4></div><strong>{related.tickets.length}</strong></header>
      <ul className="site-recent site-history">{related.tickets.map((ticket) => <li key={ticket.id}>
        <button type="button" className="site-link" onClick={() => { onClose(); onNavigate("site-support", ticket.id); }}><strong>Ticket #{ticket.id}</strong></button>
        <div><small>{ticket.category || "Support"} · {date(ticket.updated_at || ticket.created_at)}</small></div>
        <span className="status">{ticket.status}</span>
      </li>)}</ul>
    </section>}
    {tab === "requests" && related?.requests?.length > 0 && <section className="customer-profile-section">
      <header><div><span className="eyebrow">Catalogue</span><h4>Demandes produit</h4></div><strong>{related.requests.length}</strong></header>
      <ul className="site-recent site-history">{related.requests.map((ticket) => <li key={ticket.id}>
        <button type="button" className="site-link" onClick={() => { onClose(); onNavigate("site-product-requests", ticket.id); }}><strong>Demande #{ticket.id}</strong></button>
        <div><small>{date(ticket.updated_at || ticket.created_at)}</small></div>
        <span className="status">{ticket.status}</span>
      </li>)}</ul>
    </section>}
    {tab === "warranties" && related?.warranties?.length > 0 && <section className="customer-profile-section">
      <header><div><span className="eyebrow">Après-vente</span><h4>Garanties</h4></div><strong>{related.warranties.length}</strong></header>
      <ul className="site-recent site-history">{related.warranties.map((item) => <li key={item.id}>
        <button type="button" className="site-link" onClick={() => { onClose(); onNavigate("site-warranties", item.id); }}><strong>Garantie #{item.id}</strong></button>
        <div><small>{item.product || "Produit"} · {date(item.updated_at || item.created_at)}</small></div>
        <span className="status">{item.status}</span>
      </li>)}</ul>
    </section>}
    {adjusting && <form className="operation-form site-record-panel" onSubmit={submitAdjust}>
      <h3>Ajuster le portefeuille</h3>
      <p>Solde actuel : <strong>{dinars(customer.balance_millimes)}</strong>. Saisissez un montant positif pour créditer (ex. 10) ou négatif pour débiter (ex. -5). L’opération apparaît dans l’historique du client.</p>
      <div className="form-grid">
        <Field label="Montant (DT)"><input value={adjustment.amount} onChange={(event) => setAdjustment({ ...adjustment, amount: event.target.value })} inputMode="decimal" placeholder="Ex. 10 ou -5" required autoFocus /></Field>
        <Field label="Motif visible par le client"><input value={adjustment.note} onChange={(event) => setAdjustment({ ...adjustment, note: event.target.value })} maxLength={200} placeholder="Ex. Geste commercial" required /></Field>
      </div>
      <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={() => setAdjusting(false)}>Retour</ActionButton><ActionButton type="submit" icon={Save} disabled={sending}>Appliquer</ActionButton></div>
    </form>}
  </Modal>;
}

export default function SiteCustomersPage({ onAction, onNavigate }) {
  const [query, replace] = useSiteQuery();
  const search = query.search || "";
  const page = Number(query.page || 1);
  const [result, loading] = useRemoteList("/admin/api/site-customers", { search, page, per_page: 25 });
  const selected = (result.items || []).find((customer) => String(customer.id) === String(query.customer || ""));
  return <div className="operations-page site-page">
    <PageHeader title="Clients du site" description="Comptes clients avec leur solde de portefeuille, leurs achats et le total dépensé." />
    <FilterBar search={search} setSearch={(value) => replace({ search: value, page: "", customer: "" })} placeholder="Nom, email ou téléphone…" resultCount={result.total} />
    <section className="data-panel customer-directory" aria-busy={loading}>
      <header className="customer-directory-head"><div><span className="eyebrow">Répertoire</span><h3>Cartes clients</h3></div><span>{result.total || 0} profil(s)</span></header>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des clients…</div>
        : !result.items.length ? <Empty icon={Users} title="Aucun client" text="Les comptes créés sur le site apparaîtront ici." />
        : <div className="customer-card-grid">{result.items.map((customer) => <button type="button" className="customer-card" key={customer.id} onClick={() => replace({ customer: customer.id }, { push: true })}>
          <header><span className="customer-card-avatar">{(customer.name || customer.email || "C").slice(0, 1).toUpperCase()}</span><div><strong>{customer.name || "Client"}</strong><small>{customer.email || "Sans email"}{customer.phone ? ` · ${customer.phone}` : ""}</small></div><i className={customer.pending_count > 0 ? "blocked" : "active"}>{customer.pending_count > 0 ? "À vérifier" : "Actif"}</i></header>
          <div className="customer-card-money"><span><small>Portefeuille</small><strong>{dinars(customer.balance_millimes)}</strong></span><span><small>Total dépensé</small><strong>{dinars(customer.total_spent_millimes)}</strong></span></div>
          <div className="customer-card-metrics"><span><ShoppingBag size={14} /><strong>{customer.carts_count}</strong><small>paniers</small></span><span><Wallet size={14} /><strong>{customer.pending_count}</strong><small>à vérifier</small></span></div>
          <footer><div><small>Dernière commande</small><strong>{customer.last_order_at ? date(customer.last_order_at) : "Aucun achat"}</strong><span>{customer.created_at ? `Inscrit ${date(customer.created_at)}` : ""}</span></div><span className="customer-card-open">Profil complet <ChevronRight size={15} /></span></footer>
        </button>)}</div>}
      <Pagination value={result} onChange={(next) => replace({ page: next === 1 ? "" : next, customer: "" })} />
    </section>
    {query.customer && !selected && !loading && <Empty icon={Users} title="Client introuvable" text="Ce compte n’est pas dans les résultats de cette recherche." />}
    {selected && <CustomerDetail customer={selected} onAction={onAction} onNavigate={onNavigate} onClose={() => replace({ customer: "" })} />}
  </div>;
}
