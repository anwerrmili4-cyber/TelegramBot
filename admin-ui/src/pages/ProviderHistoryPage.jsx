import { useState } from "react";
import { AlertTriangle, CircleDollarSign, Cloud, Database, Layers } from "lucide-react";
import { date, PageHeader, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";

export const PROVIDER_TRANSACTION_STATUS_LABELS = {
  purchasing: "Achat en cours",
  completed: "Terminé",
  delivery_pending: "Livraison en attente",
  not_created: "Non créée",
  review_required: "À vérifier",
};

const STATUS_ORDER = ["completed", "delivery_pending", "review_required", "purchasing", "not_created"];
const NAMED_PROVIDER_SLOTS = 5;
const DONUT_RADIUS = 60;
const DONUT_LENGTH = 2 * Math.PI * DONUT_RADIUS;

const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const precise = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 });

function cost(value, currency) {
  if (value === null || value === undefined || value === "") return "—";
  return `${precise.format(Number(value))} ${currency || "USDT"}`;
}

function costSummary(costs = {}) {
  const entries = Object.entries(costs);
  if (!entries.length) return "—";
  return entries.map(([currency, amount]) => `${number.format(amount)} ${currency}`).join(" · ");
}

const costTotal = (costs = {}) => Object.values(costs).reduce((sum, amount) => sum + Number(amount || 0), 0);
const percent = (part, total) => (total ? Math.round((part / total) * 1000) / 10 : 0);
const providerColor = (index) => `var(--ph-${Math.min(index, NAMED_PROVIDER_SLOTS) + 1})`;

function groupProviders(breakdown) {
  const named = breakdown.slice(0, NAMED_PROVIDER_SLOTS).map((entry, index) => ({ ...entry, color: providerColor(index) }));
  const rest = breakdown.slice(NAMED_PROVIDER_SLOTS);
  if (!rest.length) return named;
  const costs = {};
  rest.forEach((entry) => Object.entries(entry.costs).forEach(([currency, amount]) => { costs[currency] = (costs[currency] || 0) + amount; }));
  return [...named, {
    id: "__others",
    name: `Autres (${rest.length})`,
    count: rest.reduce((sum, entry) => sum + entry.count, 0),
    costs,
    color: providerColor(NAMED_PROVIDER_SLOTS),
  }];
}

function CostSplit({ groups, summary }) {
  const total = costTotal(summary.costs);
  return (
    <article className="ph-card ph-rise" style={{ "--i": 4 }}>
      <header className="ph-card-head">
        <div><h3>Répartition du coût par fournisseur</h3><p>Part de chaque fournisseur dans le coût d’achat filtré</p></div>
        <div className="ph-total"><strong>{costSummary(summary.costs)}</strong><small>{summary.count || 0} achats</small></div>
      </header>
      <div className="ph-stack" role="img" aria-label="Répartition du coût par fournisseur">
        {groups.map((group, index) => {
          const share = percent(costTotal(group.costs), total);
          return share > 0 && <span key={group.id} className="ph-grow" title={`${group.name} · ${share} %`} style={{ width: `${share}%`, background: group.color, "--i": index }} />;
        })}
      </div>
      <ul className="ph-legend">
        {groups.map((group, index) => {
          const share = percent(costTotal(group.costs), total);
          return (
            <li key={group.id}>
              <i style={{ background: group.color }} />
              <strong>{group.name}</strong>
              <small>{group.count} achats</small>
              <span className="ph-track"><b className="ph-grow" style={{ width: `${share}%`, background: group.color, "--i": index + 3 }} /></span>
              <em>{costSummary(group.costs)}</em>
              <small className="ph-share">{number.format(share)} %</small>
            </li>
          );
        })}
      </ul>
    </article>
  );
}

function StatusDonut({ summary }) {
  const counts = summary.statuses || {};
  const total = summary.count || 0;
  let offset = 0;
  return (
    <article className="ph-card ph-status-card ph-rise" style={{ "--i": 5 }}>
      <header className="ph-card-head"><div><h3>Statuts des achats</h3><p>Où en sont les commandes fournisseurs</p></div></header>
      <div className="ph-donut-row">
        <div className="ph-donut">
          <svg viewBox="0 0 150 150" aria-hidden="true">
            <circle cx="75" cy="75" r={DONUT_RADIUS} className="ph-donut-base" />
            {STATUS_ORDER.map((status, index) => {
              const length = total ? ((counts[status] || 0) / total) * DONUT_LENGTH : 0;
              const segment = length > 0 && (
                <circle key={status} cx="75" cy="75" r={DONUT_RADIUS} className={`ph-arc ${status}`}
                  style={{ "--len": `${Math.max(length - 3, 1)}px`, "--gap": `${DONUT_LENGTH}px`, "--i": index }}
                  strokeDashoffset={-offset} />
              );
              offset += length;
              return segment;
            })}
          </svg>
          <div><strong>{total}</strong><small>achats</small></div>
        </div>
        <ul className="ph-status-legend">
          {STATUS_ORDER.map((status) => (
            <li key={status}>
              <i className={`ph-dot ${status}`} />
              <span>{PROVIDER_TRANSACTION_STATUS_LABELS[status]}</span>
              <strong>{counts[status] || 0}</strong>
              <small>{Math.round(percent(counts[status] || 0, total))} %</small>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function ProviderCard({ entry, index, active, onSelect }) {
  const statuses = entry.statuses || {};
  return (
    <button type="button" className={`ph-provider ph-rise ${active ? "active" : ""}`} style={{ "--i": index + 6, "--c": providerColor(index) }}
      onClick={onSelect} aria-pressed={active}>
      <div className="ph-provider-id">
        <span className="ph-avatar">{entry.name.slice(0, 2).toUpperCase()}</span>
        <div><strong>{entry.name}</strong><small>Dernier achat {date(entry.last_created_at)}</small></div>
        <em>{Math.round(percent(entry.completed, entry.count))} % livrés</em>
      </div>
      <div className="ph-split">
        {STATUS_ORDER.map((status) => statuses[status] > 0 && (
          <span key={status} className={`ph-grow ${status}`} style={{ width: `${percent(statuses[status], entry.count)}%`, "--i": index + 6 }} />
        ))}
      </div>
      <dl>
        <div><dt>Achats</dt><dd>{entry.count}</dd></div>
        <div><dt>Coût</dt><dd>{costSummary(entry.costs)}</dd></div>
        <div><dt>À vérifier</dt><dd>{entry.needs_review}</dd></div>
      </dl>
    </button>
  );
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
  const breakdown = result.provider_breakdown || [];
  const groups = groupProviders(breakdown);
  const filteredCount = breakdown.reduce((sum, entry) => sum + entry.count, 0);
  const resetPage = (setter) => (value) => { setter(value); setPage(1); };
  const selectProvider = (value) => resetPage(setProvider)(provider === value ? "all" : value);
  const activeName = breakdown.find((entry) => entry.id === provider)?.name;
  return (
    <div className="provider-history">
      <PageHeader
        title="Historique fournisseurs"
        description="Chaque achat envoyé aux API fournisseurs, séparé par fournisseur. Lecture seule : aucune requête n’est envoyée aux fournisseurs."
      />
      <div className="order-kpis provider-history-kpis">
        <article className="ph-rise" style={{ "--i": 0 }}><div className="order-kpi-icon violet"><Database size={19} /></div><div><small>Achats affichés</small><strong>{summary.count || 0}</strong><em>selon les filtres actifs</em></div></article>
        <article className="ph-rise" style={{ "--i": 1 }}><div className="order-kpi-icon green"><CircleDollarSign size={19} /></div><div><small>Coût fournisseur</small><strong>{costSummary(summary.costs)}</strong><em>somme des coûts enregistrés</em></div></article>
        <article className="ph-rise" style={{ "--i": 2 }}><div className="order-kpi-icon cyan"><Layers size={19} /></div><div><small>Fournisseurs actifs</small><strong>{breakdown.length} / {(result.providers || []).length || "—"}</strong><em>avec au moins un achat</em></div></article>
        <article className="ph-rise" style={{ "--i": 3 }}><div className="order-kpi-icon amber"><AlertTriangle size={19} /></div><div><small>À vérifier</small><strong>{summary.needs_review || 0}</strong><em>révision ou livraison en attente</em></div></article>
      </div>
      {breakdown.length > 0 && (
        <>
          <div className="ph-charts">
            <CostSplit groups={groups} summary={summary} />
            <StatusDonut summary={summary} />
          </div>
          <section className="ph-providers">
            <header>
              <div><h3>Séparation par fournisseur</h3><p>Cliquez sur un fournisseur pour filtrer le tableau</p></div>
              <ul className="ph-keys">{STATUS_ORDER.map((value) => <li key={value}><i className={`ph-dot ${value}`} />{PROVIDER_TRANSACTION_STATUS_LABELS[value]}</li>)}</ul>
            </header>
            <div className="ph-provider-grid">
              {breakdown.map((entry, index) => (
                <ProviderCard key={entry.id} entry={entry} index={index} active={provider === entry.id} onSelect={() => selectProvider(entry.id)} />
              ))}
            </div>
          </section>
        </>
      )}
      <section className="data-panel ph-table ph-rise" style={{ "--i": 8 }}>
        <div className="ph-tabs" role="tablist" aria-label="Filtrer par fournisseur">
          <button type="button" role="tab" aria-selected={provider === "all"} className={provider === "all" ? "active" : ""} onClick={() => resetPage(setProvider)("all")}>Tous <small>{filteredCount}</small></button>
          {breakdown.map((entry) => (
            <button type="button" role="tab" key={entry.id} aria-selected={provider === entry.id} className={provider === entry.id ? "active" : ""} onClick={() => selectProvider(entry.id)}>{entry.name} <small>{entry.count}</small></button>
          ))}
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
          <select value={status} onChange={(event) => resetPage(setStatus)(event.target.value)} aria-label="Filtrer par statut">
            <option value="all">Tous les statuts</option>
            {STATUS_ORDER.map((value) => <option value={value} key={value}>{PROVIDER_TRANSACTION_STATUS_LABELS[value]}</option>)}
          </select>
          <select value={sort} onChange={(event) => resetPage(setSort)(event.target.value)} aria-label="Trier les achats">
            <option value="newest">Plus récents</option>
            <option value="oldest">Plus anciens</option>
          </select>
        </FilterBar>
        <div className="responsive-table">
          <table>
            <thead><tr><th>Date</th><th>Fournisseur</th><th>Commande</th><th>Réf. externe</th><th>Cmd fournisseur</th><th>Produit</th><th>Statut</th><th>Qté</th><th>Coût d’achat</th></tr></thead>
            <tbody>
              {result.items.map((item, index) => (
                <tr key={`${item.provider}-${item.external_order_id}`} className="ph-row" style={{ "--i": index }}>
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
        {loading ? <div className="table-loading">Chargement de l’historique…</div> : !result.items.length && <Empty icon={Cloud} title="Aucun achat fournisseur" text={activeName ? `Aucun achat ${activeName} ne correspond aux filtres sélectionnés.` : "Aucun achat API ne correspond aux filtres sélectionnés."} />}
        <Pagination value={result} onChange={setPage} />
      </section>
    </div>
  );
}
