import { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleDollarSign, Cloud, Database } from "lucide-react";
import { PROVIDERS, date, PageHeader, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";

export const PROVIDER_TRANSACTION_STATUS_LABELS = {
  purchasing: "Achat en cours",
  completed: "Terminé",
  delivery_pending: "Livraison en attente",
  not_created: "Non créée",
  review_required: "À vérifier",
};

const STATUS_ORDER = ["completed", "delivery_pending", "review_required", "purchasing", "not_created"];

function cost(value, currency) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(Number(value));
  return `${amount} ${currency || "USDT"}`;
}

function costSummary(costs = {}) {
  const entries = Object.entries(costs);
  if (!entries.length) return "—";
  return entries.map(([currency, amount]) => cost(amount, currency)).join(" · ");
}

export default function ProviderHistoryPage() {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [provider, setProvider] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [result, loading] = useRemoteList("/admin/api/provider-transactions", {
    search,
    search_field: searchField,
    provider,
    status,
    direction: sort === "oldest" ? "asc" : "desc",
    page,
    per_page: 25,
  });
  const summary = result.summary || {};
  const providers = result.providers || PROVIDERS.map(([id, name]) => ({ id, name }));
  const resetPage = (setter) => (value) => { setter(value); setPage(1); };
  return (
    <>
      <PageHeader
        title="Historique fournisseurs"
        description="Tous les achats envoyés aux API fournisseurs, enregistrés au moment de la commande. Lecture seule : aucune requête n’est envoyée aux fournisseurs."
      />
      <div className="order-kpis provider-history-kpis">
        <article><div className="order-kpi-icon violet"><Database size={19} /></div><div><small>Achats affichés</small><strong>{summary.count || 0}</strong><em>selon les filtres actifs</em></div></article>
        <article><div className="order-kpi-icon green"><CircleDollarSign size={19} /></div><div><small>Coût fournisseur</small><strong>{costSummary(summary.costs)}</strong><em>somme des coûts enregistrés</em></div></article>
        <article><div className="order-kpi-icon green"><CheckCircle2 size={19} /></div><div><small>Terminés</small><strong>{summary.completed || 0}</strong><em>livraison reçue du fournisseur</em></div></article>
        <article><div className="order-kpi-icon amber"><AlertTriangle size={19} /></div><div><small>À vérifier</small><strong>{summary.needs_review || 0}</strong><em>révision ou livraison en attente</em></div></article>
      </div>
      <FilterBar
        search={search}
        setSearch={resetPage(setSearch)}
        searchField={searchField}
        setSearchField={resetPage(setSearchField)}
        options={[["all", "Tout"], ["order_id", "N° commande"], ["external_order_id", "Réf. externe"], ["supplier_order_id", "Cmd fournisseur"], ["supplier_product_id", "Produit"]]}
        resultCount={result.total}
        placeholder="N° commande, référence BM-, commande fournisseur ou produit…"
      >
        <select value={provider} onChange={(event) => resetPage(setProvider)(event.target.value)} aria-label="Filtrer par fournisseur">
          <option value="all">Tous les fournisseurs</option>
          {providers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
        <select value={status} onChange={(event) => resetPage(setStatus)(event.target.value)} aria-label="Filtrer par statut">
          <option value="all">Tous les statuts</option>
          {STATUS_ORDER.map((value) => <option value={value} key={value}>{PROVIDER_TRANSACTION_STATUS_LABELS[value]}</option>)}
        </select>
        <select value={sort} onChange={(event) => resetPage(setSort)(event.target.value)} aria-label="Trier les achats">
          <option value="newest">Plus récents</option>
          <option value="oldest">Plus anciens</option>
        </select>
      </FilterBar>
      <section className="data-panel">
        <div className="responsive-table">
          <table>
            <thead><tr><th>Date</th><th>Fournisseur</th><th>Commande</th><th>Réf. externe</th><th>Cmd fournisseur</th><th>Produit</th><th>Statut</th><th>Qté</th><th>Coût d’achat</th></tr></thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={`${item.provider}-${item.external_order_id}`}>
                  <td>{date(item.created_at)}</td>
                  <td><span className="deposit-provider">{item.provider_name || item.provider}</span></td>
                  <td><strong>{item.order_exists && item.order_id != null ? `#${item.order_id}` : "—"}</strong></td>
                  <td>{item.external_order_id || "—"}</td>
                  <td>{item.supplier_order_id || "—"}</td>
                  <td><div className={`provider-history-product ${item.order_exists ? "" : "deleted"}`}><strong>{item.order_exists ? item.product_name || "—" : "Commande supprimée"}</strong><small>{item.supplier_product_id || "—"}</small></div></td>
                  <td><span className={`status ${item.status}`}>{PROVIDER_TRANSACTION_STATUS_LABELS[item.status] || item.status || "—"}</span></td>
                  <td>{item.quantity ?? "—"}</td>
                  <td><strong>{cost(item.purchase_cost_total, item.purchase_cost_currency)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? <div className="table-loading">Chargement de l’historique…</div> : !result.items.length && <Empty icon={Cloud} title="Aucun achat fournisseur" text="Aucun achat API ne correspond aux filtres sélectionnés." />}
        <Pagination value={result} onChange={setPage} />
      </section>
    </>
  );
}
