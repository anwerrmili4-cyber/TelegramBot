import { useEffect, useState } from "react";
import {
  CircleDollarSign,
  ExternalLink,
  RefreshCw,
  Save,
  ShoppingBag,
  Users,
  Wallet,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";
import { DEPOSIT_STATUS, dinars, refreshLists, CartStatus, useSiteQuery } from "../site-format.jsx";

function CustomerDetail({ customer, onAction, onClose, onNavigate }) {
  const [tab, setTab] = useState("orders");
  const [deposits, setDeposits] = useState(null);
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
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des clients…</div>
        : !result.items.length ? <Empty icon={Users} title="Aucun client" text="Les comptes créés sur le site apparaîtront ici." />
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Client</th><th>Portefeuille</th><th>Paniers</th><th>Total dépensé</th><th>Dernière commande</th></tr></thead>
          <tbody>{result.items.map((customer) => <tr key={customer.id} className={`site-click-row${String(customer.id) === String(query.customer || "") ? " is-selected" : ""}`} onClick={() => replace({ customer: customer.id }, { push: true })}>
            <td><strong>{customer.name || "Client"}</strong><small>{customer.email}{customer.phone ? ` · ${customer.phone}` : ""}</small></td>
            <td><strong>{dinars(customer.balance_millimes)}</strong></td>
            <td>{customer.carts_count}{customer.pending_count > 0 && <small>{customer.pending_count} à vérifier</small>}</td>
            <td><strong>{dinars(customer.total_spent_millimes)}</strong></td>
            <td>{customer.last_order_at ? date(customer.last_order_at) : "—"}</td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination value={result} onChange={(next) => replace({ page: next === 1 ? "" : next, customer: "" })} />
    </section>
    {query.customer && !selected && !loading && <Empty icon={Users} title="Client introuvable" text="Ce compte n’est pas dans les résultats de cette recherche." />}
    {selected && <CustomerDetail customer={selected} onAction={onAction} onNavigate={onNavigate} onClose={() => replace({ customer: "" })} />}
  </div>;
}
