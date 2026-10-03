import { useState } from "react";
import {
  CheckCircle2,
  RefreshCw,
  Wallet,
  X,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { DEPOSIT_STATUS, Receipt, dinars, dinarInput, refreshLists, useSiteQuery } from "../site-format.jsx";

function DepositDetail({ deposit, onAction, onDone, compact = false }) {
  const [editor, setEditor] = useState(null);
  const [value, setValue] = useState("");
  const [sending, setSending] = useState(false);
  const [label, className] = DEPOSIT_STATUS[deposit.status] || [deposit.status, ""];
  const open = (type) => {
    setEditor(type);
    setValue(type === "approve" ? dinarInput(deposit.amount_millimes) : "");
  };
  const run = async (payload) => {
    setSending(true);
    try {
      if (await onAction(payload)) {
        setEditor(null);
        setValue("");
        refreshLists();
        onDone?.();
      }
    } finally {
      setSending(false);
    }
  };
  const actions = deposit.status === "pending" ? <div className="site-actions">
    <ActionButton icon={CheckCircle2} disabled={sending} onClick={() => open("approve")}>Créditer</ActionButton>
    <ActionButton icon={X} danger disabled={sending} onClick={() => open("reject")}>Refuser</ActionButton>
  </div> : null;
  const dialogs = <>
    {editor === "approve" && <Modal title={`Créditer la recharge #${deposit.id}`} onClose={() => !sending && setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_deposit_approve", deposit_id: deposit.id, amount: value }); }}>
      <p>{deposit.customer_name} a déclaré <strong>{dinars(deposit.amount_millimes)}</strong> par {deposit.method_label} (réf. {deposit.transaction_reference || "—"}). Indiquez le montant réellement reçu.</p>
      <Field label="Montant à créditer (DT)"><input value={value} onChange={(event) => setValue(event.target.value)} inputMode="decimal" required autoFocus /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" icon={CheckCircle2} disabled={sending}>Créditer le portefeuille</ActionButton></div>
    </form></Modal>}
    {editor === "reject" && <Modal title={`Refuser la recharge #${deposit.id}`} onClose={() => !sending && setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_deposit_reject", deposit_id: deposit.id, reason: value }); }}>
      <p>Le client recevra ce motif par email et pourra envoyer une nouvelle demande.</p>
      <Field label="Motif" wide><textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={500} rows={4} required autoFocus placeholder="Ex. Aucun virement reçu avec cette référence" /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X} disabled={sending}>Refuser</ActionButton></div>
    </form></Modal>}
  </>;
  if (compact) return <>{actions}{dialogs}</>;
  return <aside className="site-record-panel">
    <header className="site-record-head">
      <div>
        <span className="eyebrow">Détail</span>
        <h2>Recharge #{deposit.id}</h2>
        <p>{deposit.customer_name || "Client"}</p>
      </div>
      <span className={`status ${className}`}>{label}</span>
    </header>
    <dl className="site-facts">
      <div><dt>Email</dt><dd>{deposit.customer_email ? <a href={`mailto:${deposit.customer_email}`}>{deposit.customer_email}</a> : "—"}</dd></div>
      <div><dt>Référence</dt><dd><strong>{deposit.transaction_reference || "—"}</strong></dd></div>
      <div><dt>Moyen</dt><dd>{deposit.method_label || deposit.method || "—"}</dd></div>
      <div><dt>Montant déclaré</dt><dd>{dinars(deposit.amount_millimes)}</dd></div>
      {deposit.status === "approved" ? <div><dt>Montant crédité</dt><dd>{dinars(deposit.credited_millimes)}</dd></div> : null}
      <div><dt>Solde actuel</dt><dd>{dinars(deposit.balance_millimes)}</dd></div>
      <div><dt>Envoyée le</dt><dd>{date(deposit.created_at)}</dd></div>
      {deposit.reviewed_at ? <div><dt>Traitée le</dt><dd>{date(deposit.reviewed_at)}</dd></div> : null}
      {deposit.reason ? <div><dt>Motif du refus</dt><dd>{deposit.reason}</dd></div> : null}
      <div><dt>Reçu</dt><dd><Receipt id={deposit.receipt_id} /></dd></div>
    </dl>
    {actions}
    {dialogs}
  </aside>;
}

export default function SiteDepositsPage({ onAction }) {
  const [query, replace] = useSiteQuery();
  const search = query.search || "";
  const status = query.status || "pending";
  const page = Number(query.page || 1);
  const [result, loading] = useRemoteList("/admin/api/site-deposits", { search, status, page, per_page: 20 }, { refreshInterval: 15000 });
  const counts = result.counts || {};
  const selected = (result.items || []).find((deposit) => String(deposit.id) === String(query.deposit || ""));
  return <div className="operations-page site-page">
    <PageHeader title="Recharges du portefeuille" description="Comparez le reçu au montant et à la référence déclarés, puis créditez le portefeuille du client. Vous pouvez corriger le montant si le virement reçu est différent." />
    <OperationsSummary items={[["À vérifier", counts.pending || 0, "warning"], ["Créditées", counts.approved || 0, "success"], ["Refusées", counts.rejected || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(value) => replace({ search: value, page: "", deposit: "" })} placeholder="Nom, email ou référence de transaction…" resultCount={result.total}>
      <select value={status} onChange={(event) => replace({ status: event.target.value === "pending" ? "" : event.target.value, page: "", deposit: "" })} aria-label="Statut de la recharge">
        <option value="pending">À vérifier</option>
        <option value="approved">Créditées</option>
        <option value="rejected">Refusées</option>
        <option value="all">Toutes</option>
      </select>
    </FilterBar>
    <div className={selected ? "site-split" : undefined}>
      <section className="data-panel" aria-busy={loading}>
        {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des recharges…</div>
          : !result.items.length ? <Empty icon={Wallet} title="Aucune recharge" text="Les demandes de recharge envoyées depuis l’espace client apparaîtront ici." />
          : <div className="responsive-table"><table className="site-catalog-table">
            <thead><tr><th>Recharge</th><th>Client</th><th>Montant</th><th>Référence</th><th>Statut</th><th>Date</th><th>Actions</th></tr></thead>
            <tbody>{result.items.map((deposit) => {
              const [label, className] = DEPOSIT_STATUS[deposit.status] || [deposit.status, ""];
              return <tr key={deposit.id} className={`site-click-row${selected?.id === deposit.id ? " is-selected" : ""}`} onClick={() => replace({ deposit: deposit.id }, { push: true })}>
                <td><strong>#{deposit.id}</strong><small>{deposit.method_label}</small></td>
                <td><strong>{deposit.customer_name || "Client"}</strong><small>{deposit.customer_email || "—"}</small></td>
                <td><strong>{dinars(deposit.status === "approved" ? deposit.credited_millimes : deposit.amount_millimes)}</strong></td>
                <td>{deposit.transaction_reference || "—"}</td>
                <td><span className={`status ${className}`}>{label}</span></td>
                <td>{date(deposit.created_at)}</td>
                <td className="site-ops-cell" onClick={(event) => event.stopPropagation()}>
                  {deposit.status === "pending"
                    ? <DepositDetail deposit={deposit} onAction={onAction} onDone={() => replace({ deposit: "" })} compact />
                    : <ActionButton secondary onClick={() => replace({ deposit: deposit.id }, { push: true })}>Ouvrir</ActionButton>}
                </td>
              </tr>;
            })}</tbody>
          </table></div>}
        <Pagination value={result} onChange={(next) => replace({ page: next === 1 ? "" : next, deposit: "" })} />
      </section>
      {query.deposit && selected && <DepositDetail key={selected.id} deposit={selected} onAction={onAction} onDone={() => replace({ deposit: "" })} />}
      {query.deposit && !selected && !loading && <aside className="site-record-panel"><Empty icon={Wallet} title="Recharge introuvable" text="Cette demande n’est pas dans les résultats filtrés." /></aside>}
    </div>
  </div>;
}
