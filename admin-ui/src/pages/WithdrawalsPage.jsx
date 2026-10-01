import { useState } from "react";
import {
  CheckCircle2,
  CircleDollarSign,
  RefreshCw,
  X,
} from "lucide-react";
import { STATUS_LABELS, money, date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";

export default function WithdrawalsPage({ onAction, data }) {
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
    <PageHeader title="Retraits" description="Traitez les demandes créées dans le bot et suivez les paiements déjà terminés." />
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
