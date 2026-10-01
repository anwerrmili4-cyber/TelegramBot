import { useEffect, useState } from "react";
import {
  Check,
  CircleDollarSign,
  PackageCheck,
  RefreshCw,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";
import { STATUS_LABELS, money, date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";

export default function WarrantiesPage({ onAction, data, channel = "" }) {
  const initial = new URLSearchParams(window.location.search).get("warranty") || "";
  const [search, setSearch] = useState(initial);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState(null);
  const [value, setValue] = useState("");
  const site = channel === "tn_site";
  useEffect(() => {
    const navigateToWarranty = (event) => {
      const pageId = site ? "site-warranties" : "warranties";
      if (event.detail?.page !== pageId || event.detail?.entityId == null) return;
      setSearch(String(event.detail.entityId));
      setStatus("");
      setPage(1);
    };
    window.addEventListener("admin:navigate", navigateToWarranty);
    return () => window.removeEventListener("admin:navigate", navigateToWarranty);
  }, [site]);
  const [result, loading] = useRemoteList("/admin/api/warranties", { search, status, page, per_page: 25, ...(site ? { channel: "tn_site" } : {}) }, { refreshInterval: 10000 });
  const refresh = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));
  const run = async (payload) => {
    const completed = await onAction({ ...payload, channel: site ? "tn_site" : "bot" });
    if (completed) { setEditor(null); setValue(""); refresh(); }
  };
  const openEditor = (type, item) => { setEditor({ type, item }); setValue(""); };
  return <div className="operations-page warranty-page">
    <PageHeader title="Garanties" description={site ? "Demandes ouvertes sur ourblackmarket. Un remboursement crédite le portefeuille en dinars du client." : "Examinez les demandes du bot, remboursez le portefeuille ou livrez un remplacement."} />
    <OperationsSummary items={[["À traiter", result.summary?.actionable || 0, "warning"], ["Nouvelles", result.summary?.pending || 0, "accent"], ["Acceptées", result.summary?.accepted || 0, "info"], ["Terminées", result.summary?.completed || 0, "success"]]} />
    <FilterBar search={search} setSearch={(next) => { setSearch(next); setPage(1); }} placeholder="Demande, commande, client ou motif…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut de garantie"><option value="">Tous les statuts</option><option value="pending_admin_check">Contrôle admin</option><option value="accepted">Acceptées</option><option value="replacement_pending">Remplacement requis</option><option value="replacement_delivered">Remplacements livrés</option><option value="refunded">Remboursées</option><option value="refused">Refusées</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des garanties…</div> : !result.items.length ? <Empty icon={ShieldCheck} title="Aucune garantie" text="Les demandes créées dans le bot apparaîtront ici." /> : <div className="operation-list warranty-list">{result.items.map((item) => <article key={item.id} className="operation-card">
        <header><span className="operation-icon"><ShieldCheck size={20} /></span><div><small>Garantie #{item.id} · Commande #{item.order_id}</small><strong>{item.product}</strong></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span></header>
        <div className="warranty-customer"><span>{item.username ? `@${item.username}` : item.full_name || `Client ${item.user_id}`}</span><b>{item.days_used || 0} jour(s) utilisé(s)</b></div>
        <p>{item.reason || "Aucun motif communiqué."}</p>
        <dl><div><dt>Garantie produit</dt><dd>{item.warranty}</dd></div><div><dt>Remboursement calculé</dt><dd>{site ? `${Number(item.refund_amount || 0).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT` : money(item.refund_amount, data.currency)}</dd></div><div><dt>Mise à jour</dt><dd>{date(item.updated_at || item.created_at)}</dd></div>{item.admin_note && <div><dt>Note admin</dt><dd>{item.admin_note}</dd></div>}</dl>
        <footer>{item.status === "pending_admin_check" && <><ActionButton icon={Check} onClick={() => run({ action: "warranty_accept", warranty_id: item.id })}>Accepter</ActionButton><ActionButton danger icon={X} onClick={() => openEditor("refuse", item)}>Refuser</ActionButton></>}{item.status === "accepted" && <><ActionButton icon={PackageCheck} onClick={() => openEditor("replacement", item)}>Remplacement</ActionButton><ActionButton secondary icon={CircleDollarSign} onClick={() => run({ action: "warranty_refund", warranty_id: item.id })}>Rembourser</ActionButton></>}{item.status === "replacement_pending" && <ActionButton icon={Send} onClick={() => openEditor("replacement", item)}>Envoyer le remplacement</ActionButton>}</footer>
      </article>)}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor && <Modal title={editor.type === "refuse" ? `Refuser la garantie #${editor.item.id}` : `Remplacement pour la garantie #${editor.item.id}`} onClose={() => setEditor(null)} wide={editor.type === "replacement"}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run(editor.type === "refuse" ? { action: "warranty_refuse", warranty_id: editor.item.id, admin_note: value } : { action: "warranty_replacement", warranty_id: editor.item.id, replacement: value }); }}><p>{editor.type === "refuse" ? (site ? "Le client verra ce motif dans son compte sur le site." : "Le client recevra ce motif dans Telegram.") : (site ? "Ce contenu apparaîtra dans le compte du client, à la place de la livraison." : "Ce contenu sera envoyé directement au client comme nouvelle livraison.")}</p><Field label={editor.type === "refuse" ? "Motif du refus" : "Compte ou contenu de remplacement"} wide><textarea value={value} onChange={(event) => setValue(event.target.value)} maxLength={editor.type === "refuse" ? 1000 : 3600} rows={editor.type === "refuse" ? 5 : 9} required autoFocus /></Field><div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Annuler</ActionButton><ActionButton type="submit" danger={editor.type === "refuse"} icon={editor.type === "refuse" ? X : Send}>{editor.type === "refuse" ? "Refuser" : "Envoyer au client"}</ActionButton></div></form></Modal>}
  </div>;
}
