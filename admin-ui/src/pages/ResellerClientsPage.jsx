import { useState } from "react";
import {
  CircleDollarSign,
  ClipboardList,
  Eye,
  KeyRound,
  Plus,
  RefreshCw,
  Users,
} from "lucide-react";
import { money, date, PageHeader, ActionButton, Modal, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";

export default function ResellerClientsPage({ data }) {
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
