import { useState } from "react";
import {
  CheckCircle2,
  Command,
  ExternalLink,
  Globe2,
  PackageCheck,
  RefreshCw,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { LINE_STATUS, Receipt, dinars, refreshLists, CartStatus } from "../site-format.jsx";

export default function SiteOrdersPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("to_verify");
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState(null);
  const [note, setNote] = useState("");
  const [result, loading] = useRemoteList("/admin/api/site-orders", { search, status, page, per_page: 20 }, { refreshInterval: 15000 });
  const counts = result.counts || {};
  const run = async (payload) => {
    const completed = await onAction(payload);
    if (completed) { setEditor(null); setNote(""); refreshLists(); }
  };
  const openEditor = (type, cart) => { setEditor({ type, cart }); setNote(""); };
  const waitingItems = (cart) => cart.items.filter((item) => ["payment_confirmed", "paid"].includes(item.status));
  const paidTotal = (cart) => cart.items.filter((item) => ["payment_confirmed", "paid"].includes(item.status)).reduce((sum, item) => sum + item.total_millimes, 0);
  return <div className="operations-page site-page">
    <PageHeader title="Commandes du site" description="Vérifiez le reçu joint par le client puis confirmez : les produits en stock sont livrés automatiquement, les autres attendent vos accès. Les paiements par portefeuille arrivent déjà confirmés." />
    <OperationsSummary items={[["À vérifier", counts.to_verify || 0, "warning"], ["À livrer", counts.confirmed || 0, "accent"], ["Livrés", counts.delivered || 0, "success"], ["Annulés", counts.cancelled || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Référence TN-…, nom, email, réf. de transaction…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut du panier"><option value="to_verify">À vérifier</option><option value="confirmed">À livrer</option><option value="delivered">Livrés</option><option value="cancelled">Annulés</option><option value="all">Tous</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des commandes du site…</div> : !result.items.length ? <Empty icon={Globe2} title="Aucune commande" text="Les paniers validés sur le site tunisien apparaîtront ici." /> : <div className="operation-list">{result.items.map((cart) => <article key={cart.reference} className="operation-card">
        <header><span className="operation-icon">{cart.payment_method === "wallet" ? <Wallet size={20} /> : <Globe2 size={20} />}</span><div><small>{cart.reference}</small><strong>{cart.customer_name || "Client"}</strong></div><CartStatus status={cart.status} /></header>
        <div className="operation-amount"><strong>{dinars(cart.total_millimes)}</strong><span>{cart.payment_label || "Paiement"}</span></div>
        <dl>
          <div><dt>Email</dt><dd>{cart.customer_email ? <a href={`mailto:${cart.customer_email}`}>{cart.customer_email}</a> : "—"}</dd></div>
          {cart.customer_phone && <div><dt>Téléphone</dt><dd>{cart.customer_phone}</dd></div>}
          <div><dt>Articles</dt><dd>{cart.items.map((item) => <span key={item.order_id} className="site-line">
            {item.quantity} × {item.service_name ? `${item.service_name} — ` : ""}{item.offer_name} <small>({dinars(item.total_millimes)} · {LINE_STATUS[item.status] || item.status}{item.automatic ? " automatiquement" : ""})</small>
            {item.site_remark ? <small className="site-line-note">Remarque : {item.site_remark}</small> : null}
            {item.customer_info ? <small className="site-line-note">Informations du client : {item.customer_info}</small> : null}
            {item.automatic && <em className="site-chip"><Zap size={11} />Stock</em>}
          </span>)}</dd></div>
          <div><dt>Paiement</dt><dd>{cart.payment_label}{cart.transaction_reference ? <> · réf. <strong>{cart.transaction_reference}</strong></> : ""}</dd></div>
          {cart.receipt_id && <div><dt>Reçu</dt><dd><Receipt id={cart.receipt_id} /></dd></div>}
          {cart.invoice_number && <div><dt>Facture</dt><dd><a href={`/admin/api/site-invoice?ref=${encodeURIComponent(cart.reference)}`} target="_blank" rel="noreferrer"><ExternalLink size={12} /> {cart.invoice_number}</a></dd></div>}
          <div><dt>Commandé le</dt><dd>{date(cart.created_at)}</dd></div>
          {cart.customer_note && <div><dt>Note client</dt><dd>{cart.customer_note}</dd></div>}
          {cart.delivery_note && <div><dt>Accès envoyés</dt><dd className="site-delivery">{cart.delivery_note}</dd></div>}
          {cart.delivered_at && <div><dt>Livré le</dt><dd>{date(cart.delivered_at)}</dd></div>}
          {cart.admin_note && <div><dt>Motif d’annulation</dt><dd>{cart.admin_note}</dd></div>}
          {cart.refunded_millimes > 0 && <div><dt>Remboursé</dt><dd>{dinars(cart.refunded_millimes)} sur le portefeuille</dd></div>}
        </dl>
        {cart.status === "to_verify" && <footer><ActionButton icon={CheckCircle2} onClick={() => run({ action: "site_cart_confirm", reference: cart.reference })}>Reçu valide : confirmer</ActionButton><ActionButton icon={X} danger onClick={() => openEditor("cancel", cart)}>Refuser</ActionButton></footer>}
        {["confirmed", "partial"].includes(cart.status) && <footer><ActionButton icon={PackageCheck} onClick={() => openEditor("deliver", cart)}>Envoyer les accès</ActionButton><ActionButton icon={X} danger onClick={() => openEditor("cancel", cart)}>Annuler et rembourser</ActionButton></footer>}
      </article>)}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor?.type === "deliver" && <Modal title={`Livrer le panier ${editor.cart.reference}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_deliver", reference: editor.cart.reference, note }); }}>
      <p>Ces accès seront envoyés par email à <strong>{editor.cart.customer_email || "le client"}</strong> et affichés dans son espace client pour : {waitingItems(editor.cart).map((item) => `${item.quantity} × ${item.offer_name}`).join(", ")}.</p>
      <Field label="Accès à livrer au client" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={4000} rows={7} required placeholder={"Ex. Email : compte@exemple.com\nMot de passe : ••••••••"} autoFocus /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" icon={PackageCheck}>Envoyer et marquer livré</ActionButton></div>
    </form></Modal>}
    {editor?.type === "cancel" && <Modal title={`Annuler le panier ${editor.cart.reference}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_cancel", reference: editor.cart.reference, reason: note }); }}>
      <p>{editor.cart.status === "to_verify" ? "Le reçu est refusé et la commande retirée de la file. Rien n’est débité ni remboursé." : <>Les articles non livrés sont annulés et le stock remis en vente. <strong>{dinars(paidTotal(editor.cart))}</strong> seront remboursés sur le portefeuille du client.</>} Le client recevra ce motif par email.</p>
      <Field label="Motif" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={4} required autoFocus placeholder={editor.cart.status === "to_verify" ? "Ex. Reçu illisible, montant incorrect…" : "Ex. Produit en rupture"} /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X}>{editor.cart.status === "to_verify" ? "Refuser la commande" : "Annuler et rembourser"}</ActionButton></div>
    </form></Modal>}
  </div>;
}
