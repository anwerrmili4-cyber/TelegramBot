import { useState } from "react";
import {
  ExternalLink,
  RefreshCw,
  Save,
  ShoppingBag,
  Users,
  Wallet,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { dinars, refreshLists, CartStatus } from "../site-format.jsx";

export default function SiteCustomersPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [adjusting, setAdjusting] = useState(null);
  const [adjustment, setAdjustment] = useState({ amount: "", note: "" });
  const [result, loading] = useRemoteList("/admin/api/site-customers", { search, page, per_page: 25 });
  const openAdjust = (customer) => { setAdjusting(customer); setAdjustment({ amount: "", note: "" }); };
  const submitAdjust = async (event) => {
    event.preventDefault();
    if (await onAction({ action: "site_wallet_adjust", customer_id: adjusting.id, ...adjustment })) {
      setAdjusting(null);
      setSelected(null);
      refreshLists();
    }
  };
  return <div className="operations-page site-page">
    <PageHeader title="Clients du site" description="Comptes clients avec leur solde de portefeuille, leurs achats et le total dépensé." />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Nom, email ou téléphone…" resultCount={result.total} />
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des clients…</div>
        : !result.items.length ? <Empty icon={Users} title="Aucun client" text="Les comptes créés sur le site apparaîtront ici." />
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Client</th><th>Portefeuille</th><th>Paniers</th><th>Total dépensé</th><th>Dernière commande</th><th /></tr></thead>
          <tbody>{result.items.map((customer) => <tr key={customer.id}>
            <td><strong>{customer.name || "Client"}</strong><small>{customer.email}{customer.phone ? ` · ${customer.phone}` : ""}</small></td>
            <td><strong>{dinars(customer.balance_millimes)}</strong></td>
            <td>{customer.carts_count}{customer.pending_count > 0 && <small>{customer.pending_count} à vérifier</small>}</td>
            <td><strong>{dinars(customer.total_spent_millimes)}</strong></td>
            <td>{customer.last_order_at ? date(customer.last_order_at) : "—"}</td>
            <td><ActionButton secondary onClick={() => setSelected(customer)}>Détails</ActionButton></td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {selected && <Modal title={`${selected.name || "Client"} · ${selected.email}`} onClose={() => setSelected(null)} wide>
      <OperationsSummary items={[["Portefeuille", dinars(selected.balance_millimes), "accent"], ["Paniers", selected.carts_count, "info"], ["Total dépensé", dinars(selected.total_spent_millimes), "success"], ["Client depuis", date(selected.created_at), ""]]} />
      {!selected.carts.length ? <Empty icon={ShoppingBag} title="Aucun achat" text="Ce client n’a pas encore commandé." />
        : <ul className="site-recent site-history">{selected.carts.map((cart) => <li key={cart.reference}>
          <div><strong>{cart.reference}</strong><small>{date(cart.created_at)} · {cart.payment_label}</small><small>{cart.items.map((item) => `${item.quantity} × ${item.offer_name}`).join(", ")}</small></div>
          <b>{dinars(cart.total_millimes)}</b>
          <CartStatus status={cart.status} />
        </li>)}</ul>}
      <div className="dialog-actions">
        {selected.email && <a className="action-button secondary" href={`mailto:${selected.email}`}><ExternalLink size={16} />Écrire un email</a>}
        <ActionButton icon={Wallet} onClick={() => openAdjust(selected)}>Ajuster le solde</ActionButton>
      </div>
    </Modal>}
    {adjusting && <Modal title={`Ajuster le portefeuille de ${adjusting.name || adjusting.email}`} onClose={() => setAdjusting(null)}><form className="operation-form" onSubmit={submitAdjust}>
      <p>Solde actuel : <strong>{dinars(adjusting.balance_millimes)}</strong>. Saisissez un montant positif pour créditer (ex. 10) ou négatif pour débiter (ex. -5). L’opération apparaît dans l’historique du client.</p>
      <div className="form-grid">
        <Field label="Montant (DT)"><input value={adjustment.amount} onChange={(event) => setAdjustment({ ...adjustment, amount: event.target.value })} inputMode="decimal" placeholder="Ex. 10 ou -5" required autoFocus /></Field>
        <Field label="Motif visible par le client"><input value={adjustment.note} onChange={(event) => setAdjustment({ ...adjustment, note: event.target.value })} maxLength={200} placeholder="Ex. Geste commercial" required /></Field>
      </div>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setAdjusting(null)}>Retour</ActionButton><ActionButton type="submit" icon={Save}>Appliquer</ActionButton></div>
    </form></Modal>}
  </div>;
}
