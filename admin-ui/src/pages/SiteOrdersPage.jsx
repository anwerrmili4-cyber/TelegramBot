import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  Globe2,
  PackageCheck,
  RefreshCw,
  UserRound,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import { date, PageHeader, ActionButton, Modal, Field, Empty, FilterBar, Pagination, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { LINE_STATUS, Receipt, dinars, refreshLists, CartStatus, formatDeliveryNote, useSiteQuery } from "../site-format.jsx";

const DELIVERY_SUGGESTIONS = ["Adresse", "Mot de passe", "Email", "Lien"];

function DeliveryForm({ cart, waiting, sending, onClose, onSubmit }) {
  const [fields, setFields] = useState([{ label: "", value: "" }]);
  const [error, setError] = useState("");
  const update = (index, key, value) => setFields((current) => current.map((field, item) => item === index ? { ...field, [key]: value } : field));
  const add = (label = "") => setFields((current) => [...current, { label, value: "" }]);
  const remove = (index) => setFields((current) => current.length === 1 ? [{ label: "", value: "" }] : current.filter((_, item) => item !== index));
  const submit = (event) => {
    event.preventDefault();
    const note = formatDeliveryNote(fields);
    if (!note) {
      setError("Donne un nom et une valeur à au moins un champ. Exemple : Adresse et Mot de passe.");
      return;
    }
    setError("");
    onSubmit(note);
  };
  return <form className="operation-form" onSubmit={submit}>
    <p>Ces accès seront envoyés par email à <strong>{cart.customer_email || "le client"}</strong> et dans son espace, pour : {waiting.map((item) => `${item.quantity} × ${item.offer_name}`).join(", ") || "les lignes en attente"}.</p>
    <div className="site-delivery-fields">
      {fields.map((field, index) => <div className="site-delivery-field" key={index}>
        <input aria-label="Nom du champ" value={field.label} placeholder="Ex. Adresse" maxLength={80} onChange={(event) => update(index, "label", event.target.value)} autoFocus={index === 0} />
        <input aria-label="Valeur du champ" value={field.value} placeholder="À remplir pour le client" maxLength={500} onChange={(event) => update(index, "value", event.target.value)} />
        <button type="button" onClick={() => remove(index)} aria-label="Retirer ce champ">Retirer</button>
      </div>)}
    </div>
    <div className="site-delivery-suggestions">
      {DELIVERY_SUGGESTIONS.map((label) => <button key={label} type="button" onClick={() => add(label)}>+ {label}</button>)}
      <button type="button" onClick={() => add()}>Ajouter un champ</button>
    </div>
    {error && <p className="site-field-help" role="alert">{error}</p>}
    <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={onClose}>Retour</ActionButton><ActionButton type="submit" icon={PackageCheck} disabled={sending}>Envoyer et marquer livré</ActionButton></div>
  </form>;
}

function CartDetail({ reference, onAction, onBack, onNavigate }) {
  const [cart, setCart] = useState(null);
  const [missing, setMissing] = useState(false);
  const [editor, setEditor] = useState(null);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let controller = new AbortController();
    const pull = () => {
      controller.abort();
      controller = new AbortController();
      fetch(`/admin/api/site-orders?search=${encodeURIComponent(reference)}&status=all&per_page=5`, {
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok) throw new Error("unavailable");
        const payload = await response.json();
        if (cancelled) return;
        const found = (payload.items || []).find((item) => item.reference === reference) || null;
        setCart(found);
        setMissing(!found);
      }).catch((error) => {
        if (error.name !== "AbortError" && !cancelled) setMissing(true);
      });
    };
    pull();
    window.addEventListener("admin:data-synced", pull);
    return () => {
      cancelled = true;
      controller.abort();
      window.removeEventListener("admin:data-synced", pull);
    };
  }, [reference]);
  const run = async (payload) => {
    setSending(true);
    try {
      const completed = await onAction(payload);
      if (completed) {
        setEditor(null);
        setNote("");
        refreshLists();
      }
    } finally {
      setSending(false);
    }
  };
  if (!cart && !missing) return <div className="operation-loading"><RefreshCw className="spin" />Ouverture de la commande…</div>;
  if (!cart) return <div className="site-record-page">
    <button type="button" className="site-back" onClick={onBack}><ArrowLeft size={18} />Toutes les commandes</button>
    <Empty icon={Globe2} title="Commande introuvable" text={`Aucun panier ${reference} dans les résultats de l’API.`} />
  </div>;
  const waiting = cart.items.filter((item) => ["payment_confirmed", "paid"].includes(item.status));
  const paidTotal = waiting.reduce((sum, item) => sum + item.total_millimes, 0);
  return <div className="site-record-page">
    <button type="button" className="site-back" onClick={onBack}><ArrowLeft size={18} />Toutes les commandes</button>
    <header className="site-record-head">
      <div>
        <span className="eyebrow">Dossier de commande</span>
        <h2>{cart.reference}</h2>
        <p>{cart.customer_name || "Client"}{cart.customer_email ? ` · ${cart.customer_email}` : ""}</p>
      </div>
      <CartStatus status={cart.status} />
    </header>
    <section className="workspace-scoreboard" aria-label="Résumé de la commande">
      <div><span>Montant</span><strong>{dinars(cart.total_millimes)}</strong><small>{cart.payment_label || "Paiement"}</small></div>
      <div><span>Paiement</span><strong>{cart.payment_label || "—"}</strong><small>{cart.transaction_reference ? `Réf. ${cart.transaction_reference}` : "Sans référence"}</small></div>
      <div><span>Livraison</span><strong>{cart.delivered_at ? "Effectuée" : "En attente"}</strong><small>{cart.delivered_at ? date(cart.delivered_at) : "À traiter"}</small></div>
      <div><span>Client</span><strong>{cart.customer_name || "Client"}</strong><small>{cart.customer_phone || cart.customer_email || "—"}</small></div>
    </section>
    <div className="site-record-layout">
      <div className="site-record-panel">
        <h3>Lignes</h3>
        <ul className="site-recent">{cart.items.map((item) => <li key={item.order_id}>
          <div>
            <strong>{item.quantity} × {item.service_name ? `${item.service_name} — ` : ""}{item.offer_name}</strong>
            <small>{dinars(item.total_millimes)} · {LINE_STATUS[item.status] || item.status}{item.automatic ? " automatiquement" : ""}</small>
            {item.site_remark ? <small className="site-line-note">Remarque : {item.site_remark}</small> : null}
            {item.customer_info ? <small className="site-line-note">Informations du client : {item.customer_info}</small> : null}
          </div>
          {item.automatic && <em className="site-chip"><Zap size={11} />Stock</em>}
        </li>)}</ul>
        <dl className="site-facts">
          <div><dt>Commandé le</dt><dd>{date(cart.created_at)}</dd></div>
          {cart.paid_at ? <div><dt>Payé le</dt><dd>{date(cart.paid_at)}</dd></div> : null}
          {cart.customer_note ? <div><dt>Note client</dt><dd>{cart.customer_note}</dd></div> : null}
          {cart.delivery_note ? <div><dt>Accès envoyés</dt><dd className="site-delivery">{cart.delivery_note}</dd></div> : null}
          {cart.admin_note ? <div><dt>Motif d’annulation</dt><dd>{cart.admin_note}</dd></div> : null}
          {cart.refunded_millimes > 0 ? <div><dt>Remboursé</dt><dd>{dinars(cart.refunded_millimes)} sur le portefeuille</dd></div> : null}
          <div><dt>Reçu</dt><dd><Receipt id={cart.receipt_id} /></dd></div>
          <div><dt>Facture</dt><dd>{cart.invoice_number ? <a href={`/admin/api/site-invoice?ref=${encodeURIComponent(cart.reference)}`} target="_blank" rel="noreferrer"><ExternalLink size={12} /> {cart.invoice_number}</a> : "Pas encore émise"}</dd></div>
        </dl>
      </div>
      <aside className="site-record-panel">
        <span className="eyebrow">Pilotage</span>
        <h3>Traiter le panier</h3>
        {cart.customer_id ? <button type="button" className="site-link" onClick={() => onNavigate("site-customers", cart.customer_id, { search: cart.customer_email || cart.customer_name || "" })}><UserRound size={14} /> Ouvrir le client</button> : null}
        <div className="site-actions">
          {cart.status === "to_verify" && <>
            <ActionButton icon={CheckCircle2} disabled={sending} onClick={() => run({ action: "site_cart_confirm", reference: cart.reference })}>Reçu valide : confirmer</ActionButton>
            <ActionButton icon={X} danger disabled={sending} onClick={() => { setEditor("cancel"); setNote(""); }}>Refuser</ActionButton>
          </>}
          {["confirmed", "partial"].includes(cart.status) && <>
            <ActionButton icon={PackageCheck} disabled={sending} onClick={() => { setEditor("deliver"); setNote(""); }}>Envoyer les accès</ActionButton>
            <ActionButton icon={X} danger disabled={sending} onClick={() => { setEditor("cancel"); setNote(""); }}>Annuler et rembourser</ActionButton>
          </>}
        </div>
        {cart.payment_method === "wallet" && <p className="site-field-help"><Wallet size={14} /> Paiement déjà confirmé par le portefeuille.</p>}
      </aside>
    </div>
    {editor === "deliver" && <Modal title={`Livrer le panier ${cart.reference}`} onClose={() => !sending && setEditor(null)}><DeliveryForm cart={cart} waiting={waiting} sending={sending} onClose={() => setEditor(null)} onSubmit={(note) => run({ action: "site_cart_deliver", reference: cart.reference, note })} /></Modal>}
    {editor === "cancel" && <Modal title={`Annuler le panier ${cart.reference}`} onClose={() => !sending && setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_cancel", reference: cart.reference, reason: note }); }}>
      <p>{cart.status === "to_verify" ? "Le reçu est refusé et la commande retirée de la file. Rien n’est débité ni remboursé." : <>Les articles non livrés sont annulés et le stock remis en vente. <strong>{dinars(paidTotal)}</strong> seront remboursés sur le portefeuille du client.</>} Le client recevra ce motif par email.</p>
      <Field label="Motif" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={4} required autoFocus placeholder={cart.status === "to_verify" ? "Ex. Reçu illisible, montant incorrect…" : "Ex. Produit en rupture"} /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X} disabled={sending}>{cart.status === "to_verify" ? "Refuser la commande" : "Annuler et rembourser"}</ActionButton></div>
    </form></Modal>}
  </div>;
}

function CartActions({ cart, onAction, onOpen }) {
  const [editor, setEditor] = useState(null);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const waiting = cart.items.filter((item) => ["payment_confirmed", "paid"].includes(item.status));
  const paidTotal = waiting.reduce((sum, item) => sum + item.total_millimes, 0);
  const run = async (payload) => {
    setSending(true);
    try {
      if (await onAction(payload)) {
        setEditor(null);
        setNote("");
        refreshLists();
      }
    } finally {
      setSending(false);
    }
  };
  return <>
    <div className="site-actions" onClick={(event) => event.stopPropagation()}>
      <ActionButton secondary onClick={onOpen}>Ouvrir</ActionButton>
      {cart.status === "to_verify" && <>
        <ActionButton icon={CheckCircle2} disabled={sending} onClick={() => run({ action: "site_cart_confirm", reference: cart.reference })}>Confirmer</ActionButton>
        <ActionButton icon={X} danger disabled={sending} onClick={() => { setEditor("cancel"); setNote(""); }}>Refuser</ActionButton>
      </>}
      {["confirmed", "partial"].includes(cart.status) && <>
        <ActionButton icon={PackageCheck} disabled={sending} onClick={() => { setEditor("deliver"); setNote(""); }}>Livrer</ActionButton>
        <ActionButton icon={X} danger disabled={sending} onClick={() => { setEditor("cancel"); setNote(""); }}>Rembourser</ActionButton>
      </>}
    </div>
    {editor === "deliver" && <Modal title={`Livrer le panier ${cart.reference}`} onClose={() => !sending && setEditor(null)}><DeliveryForm cart={cart} waiting={waiting} sending={sending} onClose={() => setEditor(null)} onSubmit={(note) => run({ action: "site_cart_deliver", reference: cart.reference, note })} /></Modal>}
    {editor === "cancel" && <Modal title={`Annuler le panier ${cart.reference}`} onClose={() => !sending && setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_cancel", reference: cart.reference, reason: note }); }}>
      <p>{cart.status === "to_verify" ? "Le reçu est refusé. Rien n’est débité ni remboursé." : <><strong>{dinars(paidTotal)}</strong> seront remboursés sur le portefeuille.</>} Le client reçoit ce motif par email.</p>
      <Field label="Motif" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={4} required autoFocus /></Field>
      <div className="dialog-actions"><ActionButton type="button" secondary disabled={sending} onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X} disabled={sending}>{cart.status === "to_verify" ? "Refuser" : "Annuler et rembourser"}</ActionButton></div>
    </form></Modal>}
  </>;
}

export default function SiteOrdersPage({ onAction, onNavigate }) {
  const [query, replace] = useSiteQuery();
  const [viewMode, setViewMode] = useState(() => (window.matchMedia("(max-width: 640px)").matches ? "cards" : "kanban"));
  const search = query.search || "";
  const status = query.status || "all";
  const page = Number(query.page || 1);
  const [result, loading] = useRemoteList("/admin/api/site-orders", { search, status, page, per_page: viewMode === "kanban" ? 40 : 20 }, { refreshInterval: 15000 });
  const counts = result.counts || {};
  const openCart = (reference) => replace({ cart: reference }, { push: true });
  const kanbanColumns = useMemo(() => [
    { id: "waiting", label: "À vérifier", statuses: ["to_verify"], total: counts.to_verify || 0 },
    { id: "confirmed", label: "À livrer", statuses: ["confirmed", "partial"], total: counts.confirmed || 0 },
    { id: "completed", label: "Livrés", statuses: ["delivered"], total: counts.delivered || 0 },
    { id: "delivery", label: "Annulés", statuses: ["cancelled"], total: counts.cancelled || 0 },
  ].map((column) => ({
    ...column,
    items: (result.items || []).filter((item) => column.statuses.includes(item.status)),
  })), [result.items, counts.to_verify, counts.confirmed, counts.delivered, counts.cancelled]);
  if (query.cart) return <CartDetail reference={query.cart} onAction={onAction} onBack={() => replace({ cart: "" })} onNavigate={onNavigate} />;
  return <div className="operations-page site-page">
    <PageHeader title="Commandes du site" description="Vérifiez le reçu joint par le client puis confirmez : les produits en stock sont livrés automatiquement, les autres attendent vos accès. Les paiements par portefeuille arrivent déjà confirmés." />
    <OperationsSummary items={[["À vérifier", counts.to_verify || 0, "warning"], ["À livrer", counts.confirmed || 0, "accent"], ["Livrés", counts.delivered || 0, "success"], ["Annulés", counts.cancelled || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(value) => replace({ search: value, page: "", cart: "" })} placeholder="Référence TN-…, nom, email, réf. de transaction…" resultCount={result.total}>
      <select value={status} onChange={(event) => replace({ status: event.target.value, page: "", cart: "" })} aria-label="Statut du panier">
        <option value="to_verify">À vérifier</option>
        <option value="confirmed">À livrer</option>
        <option value="delivered">Livrés</option>
        <option value="cancelled">Annulés</option>
        <option value="all">Tous</option>
      </select>
      <div className="order-view-switch" aria-label="Mode d’affichage">
        <button className={viewMode === "cards" ? "active" : ""} type="button" onClick={() => setViewMode("cards")}><ClipboardList size={14} />Cartes</button>
        <button className={viewMode === "table" ? "active" : ""} type="button" onClick={() => setViewMode("table")}><ClipboardList size={14} />Tableau</button>
        <button className={viewMode === "kanban" ? "active" : ""} type="button" onClick={() => { setViewMode("kanban"); if (!query.status) replace({ status: "all" }); }}><Boxes size={14} />Kanban</button>
      </div>
    </FilterBar>
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des commandes du site…</div>
        : !result.items.length ? <Empty icon={Globe2} title="Aucune commande" text="Les paniers validés sur le site tunisien apparaîtront ici." />
        : viewMode === "kanban" ? <div className="orders-kanban">{kanbanColumns.map((column) => <section className={`kanban-column ${column.id}`} key={column.id}>
          <header><div><span>{column.label}</span><small>{column.items.length} sur cette page</small></div><strong>{column.total}</strong></header>
          <div className="kanban-cards">{column.items.map((cart) => <article className="kanban-order" key={cart.reference}>
            <button type="button" onClick={() => openCart(cart.reference)}><div><strong>{cart.reference}</strong><CartStatus status={cart.status} /></div><h4>{cart.items[0] ? `${cart.items[0].quantity} × ${cart.items[0].offer_name}` : "Panier"}</h4><span className="order-customer-display"><strong>{cart.customer_name || "Client"}</strong><small>{cart.customer_email || "—"}</small></span><footer><b>{dinars(cart.total_millimes)}</b><small>{date(cart.created_at)}</small></footer></button>
            <CartActions cart={cart} onAction={onAction} onOpen={() => openCart(cart.reference)} />
          </article>)}</div>
        </section>)}</div>
        : viewMode === "cards" ? <div className="mobile-order-cards">{result.items.map((cart) => <article key={cart.reference}>
          <button type="button" onClick={() => openCart(cart.reference)}><header><strong>{cart.reference}</strong><CartStatus status={cart.status} /></header><h3>{cart.customer_name || "Client"}</h3><footer><strong>{dinars(cart.total_millimes)}</strong><span>{date(cart.created_at)}</span></footer></button>
          <CartActions cart={cart} onAction={onAction} onOpen={() => openCart(cart.reference)} />
        </article>)}</div>
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Commande</th><th>Client</th><th>Montant</th><th>Paiement</th><th>Statut</th><th>Date</th><th>Actions</th></tr></thead>
          <tbody>{result.items.map((cart) => <tr key={cart.reference} className="site-click-row" onClick={() => openCart(cart.reference)}>
            <td><strong>{cart.reference}</strong><small>{cart.items.length} article(s)</small></td>
            <td><strong>{cart.customer_name || "Client"}</strong><small>{cart.customer_email || "—"}</small></td>
            <td><strong>{dinars(cart.total_millimes)}</strong></td>
            <td>{cart.payment_method === "wallet" ? <span className="site-chip"><Wallet size={11} />Portefeuille</span> : cart.payment_label}</td>
            <td><CartStatus status={cart.status} /></td>
            <td>{date(cart.created_at)}</td>
            <td className="site-ops-cell"><CartActions cart={cart} onAction={onAction} onOpen={() => openCart(cart.reference)} /></td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination value={result} onChange={(next) => replace({ page: next === 1 ? "" : next })} />
    </section>
  </div>;
}
