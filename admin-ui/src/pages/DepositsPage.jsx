import { useState } from "react";
import {
  Check,
  CircleDollarSign,
  Clock3,
  Database,
  Plus,
  X,
} from "lucide-react";
import { STATUS_LABELS, money, date, PageHeader, Empty, FilterBar, Pagination, useRemoteList } from "../admin-kit.jsx";
import { shortTxid, topupCustomerName, TopupDecisionModal, DEPOSIT_PROVIDER_LABELS } from "./wallet-topups.jsx";

export default function DepositsPage({ data, onAction }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [status, setStatus] = useState("all");
  const [provider, setProvider] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState(null);
  const [decision, setDecision] = useState(null);
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
      setDecision(null);
    }
  };
  return (
    <>
      <PageHeader
        title="Dépôts & paiements"
        description="Tous les dépôts des clients, quel que soit le moyen de paiement."
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
                  <td><strong>{topupCustomerName(topup)}</strong><small>{topup.user_id}</small></td>
                  <td><span className="deposit-provider">{DEPOSIT_PROVIDER_LABELS[topup.provider] || topup.provider}</span></td>
                  <td><strong>{money(topup.amount, topup.currency || data.currency || "USDT")}</strong></td>
                  <td>{topup.source_amount ? `${topup.source_amount} ${topup.source_currency || ""}` : "—"}</td>
                  <td>{topup.explorer_url && topup.txid ? <a className="txid-link" href={topup.explorer_url} target="_blank" rel="noreferrer" title={topup.txid}>{shortTxid(topup.txid)}</a> : <span className="txid-text" title={topup.txid || ""}>{shortTxid(topup.txid)}</span>}</td>
                  <td><span className={`status ${topup.status}`}>{STATUS_LABELS[topup.status] || topup.status}</span></td>
                  <td>{date(topup.created_at)}</td>
                  <td>{topup.status === "manual_review" && <div className="topup-actions"><button className="row-action approve" disabled={busyId === topup.id} onClick={() => setDecision({ topup, approved: true })} title="Accepter" aria-label={`Accepter le dépôt #${topup.id}`}><Check size={15} /></button><button className="row-action reject" disabled={busyId === topup.id} onClick={() => setDecision({ topup, approved: false })} title="Refuser" aria-label={`Refuser le dépôt #${topup.id}`}><X size={15} /></button></div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading ? <div className="table-loading">Chargement de l’historique…</div> : !result.items.length && <Empty icon={CircleDollarSign} title="Aucun dépôt" text="Aucun dépôt ne correspond aux filtres sélectionnés." />}
        <Pagination value={result} onChange={setPage} />
      </section>
      {decision && <TopupDecisionModal decision={decision} busy={busyId === decision.topup.id} onCancel={() => setDecision(null)} onConfirm={() => decide(decision.topup, decision.approved)} />}
    </>
  );
}
