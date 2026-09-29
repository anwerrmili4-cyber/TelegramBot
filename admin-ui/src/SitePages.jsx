import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Coins,
  Edit3,
  ExternalLink,
  Globe2,
  Image as ImageIcon,
  PackageCheck,
  RefreshCw,
  Save,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Users,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import { ActionButton, Empty, Field, FilterBar, Modal, OperationsSummary, PageHeader, Pagination, date, useRemoteList } from "./AdminPages";

const SITE_URL = "https://www.ourblackmarket.com";

const SITE_CART_STATUS = {
  to_verify: ["À vérifier", "manual_review"],
  confirmed: ["Paiement confirmé", "payment_confirmed"],
  partial: ["Livraison partielle", "payment_confirmed"],
  delivered: ["Livré", "delivered"],
  cancelled: ["Annulé", "cancelled"],
  mixed: ["Statuts mixtes", "stock_issue"],
};

const LINE_STATUS = {
  manual_review: "à vérifier",
  payment_confirmed: "à livrer",
  paid: "à livrer",
  preparing_delivery: "en livraison",
  delivered: "livré",
  cancelled: "annulé",
};

const DEPOSIT_STATUS = {
  pending: ["À vérifier", "manual_review"],
  approved: ["Créditée", "delivered"],
  rejected: ["Refusée", "cancelled"],
};

const receiptUrl = (id) => `/admin/api/site-receipt?id=${encodeURIComponent(id)}`;

function Receipt({ id }) {
  if (!id) return <span>—</span>;
  return <a className="site-receipt" href={receiptUrl(id)} target="_blank" rel="noreferrer" title="Ouvrir le reçu en grand">
    <img src={receiptUrl(id)} alt="Reçu du client" loading="lazy" />
    <span><ImageIcon size={13} />Voir le reçu</span>
  </a>;
}

const CATALOG_STATUS = {
  on_sale: ["En vente", "delivered"],
  no_price: ["Sans prix DT", "manual_review"],
  hidden: ["Masqué", "cancelled"],
};

function dinars(millimes) {
  return `${(Number(millimes || 0) / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT`;
}

function dinarInput(millimes) {
  return millimes ? String(Number(millimes) / 1000).replace(".", ",") : "";
}

function catalogStatus(row) {
  if (row.on_sale) return "on_sale";
  if (!row.site_enabled || !row.service_visible) return "hidden";
  return "no_price";
}

const refreshLists = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));

function CartStatus({ status }) {
  const [label, className] = SITE_CART_STATUS[status] || [status, ""];
  return <span className={`status ${className}`}>{label}</span>;
}

function SiteOverviewPage({ onNavigate }) {
  const [result, loading] = useRemoteList("/admin/api/site-overview", {}, { refreshInterval: 30000 });
  const carts = result.carts || {};
  const catalog = result.catalog || {};
  const topProducts = result.top_products || [];
  const recent = result.recent_carts || [];
  return <div className="operations-page site-page">
    <PageHeader
      title="Tableau de bord du site"
      description="ourblackmarket.com : commandes à traiter, chiffre d’affaires en dinars et produits les plus vendus."
      actions={<a className="action-button secondary" href={SITE_URL} target="_blank" rel="noreferrer"><ExternalLink size={16} />Ouvrir le site</a>}
    />
    <OperationsSummary items={[
      ["Commandes à vérifier", carts.to_verify || 0, "warning"],
      ["À livrer", carts.confirmed || 0, "accent"],
      ["Recharges à vérifier", result.deposits_pending || 0, "warning"],
      ["CA aujourd’hui", dinars(result.revenue_today_millimes), "success"],
      ["CA ce mois", dinars(result.revenue_month_millimes), "info"],
    ]} />
    {result.deposits_pending > 0 && <button type="button" className="site-alert" onClick={() => onNavigate("site-deposits")}>
      <Wallet size={18} />
      <span><strong>{result.deposits_pending} recharge(s) de portefeuille</strong> attendent la vérification de leur reçu.</span>
    </button>}
    {catalog.no_price > 0 && <button type="button" className="site-alert" onClick={() => onNavigate("site-catalog")}>
      <AlertTriangle size={18} />
      <span><strong>{catalog.no_price} offre(s) sans prix en dinars</strong> sont masquées du site. Fixez leur prix dans le catalogue pour les mettre en vente.</span>
    </button>}
    <div className="site-overview-grid">
      <section className="site-panel">
        <header><h3><TrendingUp size={17} />Produits les plus vendus</h3><small>Paniers confirmés et livrés</small></header>
        {loading && !topProducts.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement…</div>
          : !topProducts.length ? <Empty icon={TrendingUp} title="Aucune vente confirmée" text="Les ventes apparaîtront après la confirmation d’un premier paiement." />
          : <ol className="site-rank">{topProducts.map((item) => <li key={item.offer_name}>
            <div><strong>{item.offer_name}</strong><small>{item.service_name} · {item.quantity} vendu(s)</small></div>
            <b>{dinars(item.revenue_millimes)}</b>
          </li>)}</ol>}
      </section>
      <section className="site-panel">
        <header><h3><ClipboardList size={17} />Dernières commandes</h3><button type="button" className="site-link" onClick={() => onNavigate("site-orders")}>Tout voir</button></header>
        {!recent.length ? <Empty icon={Globe2} title="Aucune commande" text="Les paniers validés sur le site apparaîtront ici." />
          : <ul className="site-recent">{recent.map((cart) => <li key={cart.reference}>
            <div><strong>{cart.customer_name || "Client"}</strong><small>{cart.reference} · {date(cart.created_at)}</small></div>
            <b>{dinars(cart.total_millimes)}</b>
            <CartStatus status={cart.status} />
          </li>)}</ul>}
      </section>
    </div>
    <OperationsSummary items={[
      ["Offres en vente", catalog.on_sale || 0, "success"],
      ["Sans prix DT", catalog.no_price || 0, "warning"],
      ["Masquées", catalog.hidden || 0, "danger"],
      ["Clients", result.customers || 0, "info"],
    ]} />
  </div>;
}

function SiteOrdersPage({ onAction }) {
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
            {item.automatic && <em className="site-chip"><Zap size={11} />Stock</em>}
          </span>)}</dd></div>
          <div><dt>Paiement</dt><dd>{cart.payment_label}{cart.transaction_reference ? <> · réf. <strong>{cart.transaction_reference}</strong></> : ""}</dd></div>
          {cart.receipt_id && <div><dt>Reçu</dt><dd><Receipt id={cart.receipt_id} /></dd></div>}
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

function SiteDepositsPage({ onAction }) {
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

function OfferEditor({ row, categories, onClose, onSave }) {
  const [form, setForm] = useState({
    tn_price: dinarInput(row.tn_price_millimes),
    site_enabled: row.site_enabled,
    site_featured: row.site_featured,
    site_badge: row.site_badge,
    site_category: row.site_category,
    site_description_fr: row.site_description_fr,
  });
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const autoLabel = categories.find((item) => item.id === row.effective_category)?.label || "Autres services";
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_offer_update",
      offer_id: row.id,
      ...form,
      site_enabled: form.site_enabled ? "1" : "0",
      site_featured: form.site_featured ? "1" : "0",
    });
  };
  return <Modal title={`${row.service_name} — ${row.name}`} onClose={onClose} wide>
    <form className="operation-form" onSubmit={submit}>
      <p>Ces réglages ne concernent que le site tunisien : le bot Telegram garde son prix de {row.bot_price_usdt} USDT.</p>
      <div className="form-grid">
        <Field label="Prix sur le site (DT)">
          <input value={form.tn_price} onChange={(event) => set("tn_price", event.target.value)} inputMode="decimal" placeholder="Ex. 25,500" autoFocus />
          {row.suggested_price_millimes > 0 && <button type="button" className="site-link" onClick={() => set("tn_price", dinarInput(row.suggested_price_millimes))}>Utiliser la suggestion : {dinars(row.suggested_price_millimes)}</button>}
        </Field>
        <Field label="Catégorie">
          <select value={form.site_category} onChange={(event) => set("site_category", event.target.value)}>
            <option value="">Automatique ({autoLabel})</option>
            {categories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="Affichage">
          <label className="switch"><input type="checkbox" checked={form.site_enabled} onChange={(event) => set("site_enabled", event.target.checked)} /><span />Afficher sur le site</label>
        </Field>
        <Field label="Mise en avant">
          <label className="switch"><input type="checkbox" checked={form.site_featured} onChange={(event) => set("site_featured", event.target.checked)} /><span />Produit vedette</label>
        </Field>
        <Field label="Badge (optionnel)">
          <input value={form.site_badge} onChange={(event) => set("site_badge", event.target.value)} maxLength={48} placeholder="Ex. Promo, Nouveau, -20 %" />
        </Field>
        <Field label="Stock">
          <input value={row.stock < 0 ? "Illimité" : String(row.stock)} disabled />
        </Field>
        <Field label="Description en français (optionnel)" wide>
          <textarea value={form.site_description_fr} onChange={(event) => set("site_description_fr", event.target.value)} maxLength={700} rows={4} placeholder="Laissez vide pour reprendre la description du bot." />
        </Field>
      </div>
      {!form.tn_price && <p className="site-hint"><AlertTriangle size={14} />Sans prix en dinars, l’offre reste masquée du site.</p>}
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={Save}>Enregistrer</ActionButton></div>
    </form>
  </Modal>;
}

function SiteCatalogPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [serviceId, setServiceId] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/site-catalog", { search, status, service_id: serviceId, page, per_page: 30 });
  const counts = result.counts || {};
  const services = result.services || [];
  const categories = result.categories || [];
  const save = async (payload) => {
    if (await onAction(payload)) { setEditing(null); refreshLists(); }
  };
  const toggleService = async (service) => {
    if (await onAction({ action: "site_service_visibility", service_id: service.id, site_enabled: service.site_enabled ? "0" : "1" })) refreshLists();
  };
  const tabs = [["all", "Toutes"], ["on_sale", "En vente"], ["no_price", "Sans prix DT"], ["hidden", "Masquées"]];
  return <div className="operations-page site-page">
    <PageHeader title="Catalogue du site" description="Choisissez ce qui est vendu sur ourblackmarket.com et à quel prix en dinars. Une offre sans prix DT reste masquée." />
    <div className="site-tabs" role="tablist" aria-label="Filtrer les offres">
      {tabs.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={status === value} onClick={() => { setStatus(value); setPage(1); }}>{label}<small>{counts[value] ?? 0}</small></button>)}
    </div>
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Rechercher une offre ou un service…" resultCount={result.total}>
      <select value={serviceId} onChange={(event) => { setServiceId(event.target.value); setPage(1); }} aria-label="Service">
        <option value="">Tous les services</option>
        {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
      </select>
    </FilterBar>
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement du catalogue…</div>
        : !result.items.length ? <Empty icon={ShoppingBag} title="Aucune offre" text="Aucune offre ne correspond à ce filtre." />
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Offre</th><th>Prix bot</th><th>Prix site</th><th>Stock</th><th>Statut</th><th /></tr></thead>
          <tbody>{result.items.map((row) => {
            const [label, className] = CATALOG_STATUS[catalogStatus(row)];
            return <tr key={row.id}>
              <td><strong>{row.name}</strong><small>{row.service_emoji} {row.service_name}{row.site_featured && <em className="site-chip"><Sparkles size={11} />Vedette</em>}{row.site_badge && <em className="site-chip">{row.site_badge}</em>}</small></td>
              <td>{row.bot_price_usdt} USDT</td>
              <td>{row.tn_price_millimes ? <strong>{dinars(row.tn_price_millimes)}</strong> : <small>Suggestion {dinars(row.suggested_price_millimes)}</small>}</td>
              <td>{row.stock < 0 ? "∞" : row.stock}</td>
              <td><span className={`status ${className}`}>{label}</span>{!row.service_visible && <small>Service masqué</small>}</td>
              <td><ActionButton secondary icon={Edit3} onClick={() => setEditing(row)}>{row.tn_price_millimes ? "Modifier" : "Fixer le prix"}</ActionButton></td>
            </tr>;
          })}</tbody>
        </table></div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    <section className="site-panel">
      <header><h3><Globe2 size={17} />Services affichés sur le site</h3><small>Masquer un service retire toutes ses offres du site, sans toucher au bot.</small></header>
      <div className="site-service-grid">{services.map((service) => <label key={service.id} className="site-service">
        <span><strong>{service.emoji} {service.name}</strong><small>{service.on_sale}/{service.offers} offre(s) en vente</small></span>
        <span className="switch"><input type="checkbox" checked={service.site_enabled} onChange={() => toggleService(service)} /><span /></span>
      </label>)}</div>
    </section>
    {editing && <OfferEditor row={editing} categories={categories} onClose={() => setEditing(null)} onSave={save} />}
  </div>;
}

function SiteCustomersPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [adjusting, setAdjusting] = useState(null);
  const [adjustment, setAdjustment] = useState({ amount: "", note: "" });
  const [result, loading] = useRemoteList("/admin/api/site-customers", { search, page, per_page: 25 });
  const openAdjust = (customer) => { setAdjusting(customer); setAdjustment({ amount: "", note: "" }); };
  const submitAdjust = async (event) => {
    event.preventDefault();
    if (await onAction({ action: "site_wallet_adjust", customer_id: adjusting.id, ...adjustment })) {
      setAdjusting(null);
      setSelected(null);
      refreshLists();
    }
  };
  return <div className="operations-page site-page">
    <PageHeader title="Clients du site" description="Comptes clients avec leur solde de portefeuille, leurs achats et le total dépensé." />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Nom, email ou téléphone…" resultCount={result.total} />
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des clients…</div>
        : !result.items.length ? <Empty icon={Users} title="Aucun client" text="Les comptes créés sur le site apparaîtront ici." />
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Client</th><th>Portefeuille</th><th>Paniers</th><th>Total dépensé</th><th>Dernière commande</th><th /></tr></thead>
          <tbody>{result.items.map((customer) => <tr key={customer.id}>
            <td><strong>{customer.name || "Client"}</strong><small>{customer.email}{customer.phone ? ` · ${customer.phone}` : ""}</small></td>
            <td><strong>{dinars(customer.balance_millimes)}</strong></td>
            <td>{customer.carts_count}{customer.pending_count > 0 && <small>{customer.pending_count} à vérifier</small>}</td>
            <td><strong>{dinars(customer.total_spent_millimes)}</strong></td>
            <td>{customer.last_order_at ? date(customer.last_order_at) : "—"}</td>
            <td><ActionButton secondary onClick={() => setSelected(customer)}>Détails</ActionButton></td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {selected && <Modal title={`${selected.name || "Client"} · ${selected.email}`} onClose={() => setSelected(null)} wide>
      <OperationsSummary items={[["Portefeuille", dinars(selected.balance_millimes), "accent"], ["Paniers", selected.carts_count, "info"], ["Total dépensé", dinars(selected.total_spent_millimes), "success"], ["Client depuis", date(selected.created_at), ""]]} />
      {!selected.carts.length ? <Empty icon={ShoppingBag} title="Aucun achat" text="Ce client n’a pas encore commandé." />
        : <ul className="site-recent site-history">{selected.carts.map((cart) => <li key={cart.reference}>
          <div><strong>{cart.reference}</strong><small>{date(cart.created_at)} · {cart.payment_label}</small><small>{cart.items.map((item) => `${item.quantity} × ${item.offer_name}`).join(", ")}</small></div>
          <b>{dinars(cart.total_millimes)}</b>
          <CartStatus status={cart.status} />
        </li>)}</ul>}
      <div className="dialog-actions">
        {selected.email && <a className="action-button secondary" href={`mailto:${selected.email}`}><ExternalLink size={16} />Écrire un email</a>}
        <ActionButton icon={Wallet} onClick={() => openAdjust(selected)}>Ajuster le solde</ActionButton>
      </div>
    </Modal>}
    {adjusting && <Modal title={`Ajuster le portefeuille de ${adjusting.name || adjusting.email}`} onClose={() => setAdjusting(null)}><form className="operation-form" onSubmit={submitAdjust}>
      <p>Solde actuel : <strong>{dinars(adjusting.balance_millimes)}</strong>. Saisissez un montant positif pour créditer (ex. 10) ou négatif pour débiter (ex. -5). L’opération apparaît dans l’historique du client.</p>
      <div className="form-grid">
        <Field label="Montant (DT)"><input value={adjustment.amount} onChange={(event) => setAdjustment({ ...adjustment, amount: event.target.value })} inputMode="decimal" placeholder="Ex. 10 ou -5" required autoFocus /></Field>
        <Field label="Motif visible par le client"><input value={adjustment.note} onChange={(event) => setAdjustment({ ...adjustment, note: event.target.value })} maxLength={200} placeholder="Ex. Geste commercial" required /></Field>
      </div>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setAdjusting(null)}>Retour</ActionButton><ActionButton type="submit" icon={Save}>Appliquer</ActionButton></div>
    </form></Modal>}
  </div>;
}

function SiteSettingsPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-settings", {});
  const [form, setForm] = useState(null);
  useEffect(() => {
    if (form || !result.available_payment_methods) return;
    setForm({
      tnd_per_usdt: String(result.tnd_per_usdt).replace(".", ","),
      methods: new Set(result.payment_methods || []),
      details: { ...(result.payment_details || {}) },
    });
  }, [form, result]);
  const methods = result.available_payment_methods || [];
  const toggleMethod = (id) => setForm((current) => {
    const next = new Set(current.methods);
    if (next.has(id)) next.delete(id); else next.add(id);
    return { ...current, methods: next };
  });
  const setDetails = (id, value) => setForm((current) => ({ ...current, details: { ...current.details, [id]: value } }));
  const submit = async (event) => {
    event.preventDefault();
    const payload = { action: "site_settings_save", tnd_per_usdt: form.tnd_per_usdt };
    methods.forEach(({ id }) => {
      payload[`payment_${id}`] = form.methods.has(id) ? "1" : "0";
      payload[`details_${id}`] = form.details[id] || "";
    });
    await onAction(payload);
  };
  return <div className="operations-page site-page">
    <PageHeader title="Paramètres du site" description="Appliqués sur ourblackmarket.com en moins d’une minute, sans redéploiement." />
    <section className="site-panel">
      {loading && !form ? <div className="operation-loading"><RefreshCw className="spin" />Chargement…</div> : form && <form className="operation-form" onSubmit={submit}>
        <div className="form-grid">
          <Field label="Taux TND pour 1 USDT">
            <input value={form.tnd_per_usdt} onChange={(event) => setForm({ ...form, tnd_per_usdt: event.target.value })} inputMode="decimal" required />
            <small className="site-field-help">Sert uniquement à suggérer un prix en dinars dans le catalogue.</small>
          </Field>
        </div>
        <h3 className="site-section-title">Moyens de paiement</h3>
        <p className="site-field-help">Les coordonnées sont affichées au client au moment de payer une commande ou de recharger son portefeuille. Il joint ensuite la référence et la capture du reçu.</p>
        <div className="site-method-grid">{methods.map(({ id, label }) => <div key={id} className={`site-method-card${form.methods.has(id) ? " active" : ""}`}>
          <label className="switch"><input type="checkbox" checked={form.methods.has(id)} onChange={() => toggleMethod(id)} /><span />{label}</label>
          <textarea value={form.details[id] || ""} onChange={(event) => setDetails(id, event.target.value)} maxLength={300} rows={3} required={form.methods.has(id)} placeholder={`Où envoyer l’argent par ${label} (numéro, nom du bénéficiaire…)`} aria-label={`Coordonnées ${label}`} />
        </div>)}</div>
        <div className="dialog-actions"><ActionButton type="submit" icon={Save}>Enregistrer</ActionButton></div>
      </form>}
    </section>
  </div>;
}

export const SITE_PAGE_IDS = new Set(["site-overview", "site-orders", "site-deposits", "site-catalog", "site-customers", "site-settings"]);

export default function SitePage({ page, ...props }) {
  if (page === "site-overview") return <SiteOverviewPage {...props} />;
  if (page === "site-orders") return <SiteOrdersPage {...props} />;
  if (page === "site-deposits") return <SiteDepositsPage {...props} />;
  if (page === "site-catalog") return <SiteCatalogPage {...props} />;
  if (page === "site-customers") return <SiteCustomersPage {...props} />;
  if (page === "site-settings") return <SiteSettingsPage {...props} />;
  return null;
}
