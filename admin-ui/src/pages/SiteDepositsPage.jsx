import { useState } from "react";
import {
  CheckCircle2,
  Coins,
  RefreshCw,
  Wallet,
  X,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { DEPOSIT_STATUS, Receipt, dinars, dinarInput, refreshLists } from "../site-format.jsx";

export default function SiteDepositsPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState(null);
  const [value, setValue] = useState("");
  const [result, loading] = useRemoteList("/admin/api/site-deposits", { search, status, page, per_page: 20 }, { refreshInterval: 15000 });
  const counts = result.counts || {};
  const open = (type, deposit) => { setEditor({ type, deposit }); setValue(type === "approve" ? dinarInput(deposit.amount_millimes) : ""); };
  const run = async (payload) => {
    if (await onAction(payload)) { setEditor(null); setValue(""); refreshLists(); }
  };
  return <div className="operations-page site-page">
    <PageHeader title="Recharges du portefeuille" description="Comparez le reçu au montant et à la référence déclarés, puis créditez le portefeuille du client. Vous pouvez corriger le montant si le virement reçu est différent." />
    <OperationsSummary items={[["À vérifier", counts.pending || 0, "warning"], ["Créditées", counts.approved || 0, "success"], ["Refusées", counts.rejected || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(next) => { setSearch(next); setPage(1); }} placeholder="Nom, email ou référence de transaction…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut de la recharge"><option value="pending">À vérifier</option><option value="approved">Créditées</option><option value="rejected">Refusées</option><option value="all">Toutes</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des recharges…</div>
        : !result.items.length ? <Empty icon={Wallet} title="Aucune recharge" text="Les demandes de recharge envoyées depuis l’espace client apparaîtront ici." />
        : <div className="operation-list">{result.items.map((deposit) => {
          const [label, className] = DEPOSIT_STATUS[deposit.status] || [deposit.status, ""];
          return <article key={deposit.id} className="operation-card">
            <header><span className="operation-icon"><Coins size={20} /></span><div><small>Recharge #{deposit.id}</small><strong>{deposit.customer_name || "Client"}</strong></div><span className={`status ${className}`}>{label}</span></header>
            <div className="operation-amount"><strong>{dinars(deposit.status === "approved" ? deposit.credited_millimes : deposit.amount_millimes)}</strong><span>{deposit.method_label}</span></div>
            <dl>
              <div><dt>Email</dt><dd>{deposit.customer_email ? <a href={`mailto:${deposit.customer_email}`}>{deposit.customer_email}</a> : "—"}</dd></div>
              <div><dt>Référence</dt><dd><strong>{deposit.transaction_reference}</strong></dd></div>
              <div><dt>Montant déclaré</dt><dd>{dinars(deposit.amount_millimes)}</dd></div>
              <div><dt>Reçu</dt><dd><Receipt id={deposit.receipt_id} /></dd></div>
              <div><dt>Solde actuel</dt><dd>{dinars(deposit.balance_millimes)}</dd></div>
              <div><dt>Envoyée le</dt><dd>{date(deposit.created_at)}</dd></div>
              {deposit.reviewed_at && <div><dt>Traitée le</dt><dd>{date(deposit.reviewed_at)}</dd></div>}
              {deposit.reason && <div><dt>Motif du refus</dt><dd>{deposit.reason}</dd></div>}
            </dl>
            {deposit.status === "pending" && <footer><ActionButton icon={CheckCircle2} onClick={() => open("approve", deposit)}>Créditer</ActionButton><ActionButton icon={X} danger onClick={() => open("reject", deposit)}>Refuser</ActionButton></footer>}
          </article>;
        })}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor?.type === "approve" && <Modal title={`Créditer la recharge #${editor.deposit.id}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_deposit_approve", deposit_id: editor.deposit.id, amount: value }); }}>
      <p>{editor.deposit.customer_name} a déclaré <strong>{dinars(editor.deposit.amount_millimes)}</strong> par {editor.deposit.method_label} (réf. {editor.deposit.transaction_reference}). Indiquez le montant réellement reçu.</p>
      <Field label="Montant à créditer (DT)"><input value={value} onChange={(event) => setValue(event.target.value)} inputMode="decimal" required autoFocus /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" icon={CheckCircle2}>Créditer le portefeuille</ActionButton></div>
    </form></Modal>}
    {editor?.type === "reject" && <Modal title={`Refuser la recharge #${editor.deposit.id}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_deposit_reject", deposit_id: editor.deposit.id, reason: value }); }}>
      <p>Le client recevra ce motif par email et pourra envoyer une nouvelle demande.</p>
      <Field label="Motif" wide><textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={500} rows={4} required autoFocus placeholder="Ex. Aucun virement reçu avec cette référence" /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X}>Refuser</ActionButton></div>
    </form></Modal>}
  </div>;
}
