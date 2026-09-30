import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Coins,
  Copy,
  Edit3,
  ExternalLink,
  Globe2,
  Image as ImageIcon,
  PackageCheck,
  PackagePlus,
  Plus,
  RefreshCw,
  Save,
  ShoppingBag,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Trash2,
  TrendingUp,
  Upload,
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
  disabled: ["Désactivé", "cancelled"],
};

function dinars(millimes) {
  return `${(Number(millimes || 0) / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT`;
}

function dinarInput(millimes) {
  return millimes ? String(Number(millimes) / 1000).replace(".", ",") : "";
}

function catalogStatus(row) {
  if (!row.active || !row.service_active) return "disabled";
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

const DURATION_UNITS = [["days", "Jours"], ["months", "Mois"], ["years", "Années"]];

function decimalInput(value) {
  return value || value === 0 ? String(value).replace(".", ",") : "";
}

function parseDecimal(value) {
  const number = Number(String(value || "").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(number) ? number : 0;
}

function productForm(row, defaultServiceId) {
  return {
    service_id: String(row?.service_id || defaultServiceId || ""),
    name: row?.name || "",
    tn_price: dinarInput(row?.tn_price_millimes),
    price: row ? decimalInput(row.bot_price_usdt) : "",
    site_category: row?.site_category || "",
    site_badge: row?.site_badge || "",
    site_enabled: row ? row.site_enabled : true,
    site_featured: row?.site_featured || false,
    site_description_fr: row?.site_description_fr || "",
    site_image_url: row?.site_image_url || "",
    delivery_delay: row?.delivery_delay || "Instantané après confirmation",
    period_value: String(row?.period_value || 30),
    period_unit: row?.period_unit || "days",
    warranty_value: String(row?.warranty_value ?? 0),
    warranty_unit: row?.warranty_unit || "days",
    stock_mode: row?.unlimited_stock ? "unlimited" : "inventory",
    auto_delivery: row ? row.auto_delivery : true,
    initial_inventory: "",
  };
}

function DurationInput({ value, unit, min, onValue, onUnit }) {
  return <div className="duration-input">
    <input type="number" min={min} value={value} onChange={(event) => onValue(event.target.value)} required />
    <select value={unit} onChange={(event) => onUnit(event.target.value)}>{DURATION_UNITS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
  </div>;
}

function ProductEditor({ row, services, categories, rate, defaultServiceId, onClose, onSave }) {
  const [form, setForm] = useState(() => productForm(row, defaultServiceId || services[0]?.id));
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const creating = !row;
  const externallyStocked = Boolean(row?.supplier_provider || row?.manual_stock);
  const autoLabel = row ? categories.find((item) => item.id === row.effective_category)?.label || "Autres services" : "selon le nom";
  const suggestedMillimes = Math.round((parseDecimal(form.price) * rate * 10)) * 100;
  const derivedUsdt = !form.price && form.tn_price && rate ? (parseDecimal(form.tn_price) / rate).toFixed(2) : "";
  const [image, setImage] = useState("");
  const [removeImage, setRemoveImage] = useState(false);
  const [imageError, setImageError] = useState("");
  const uploadedUrl = form.site_image_url.startsWith(OFFER_IMAGE_PATH) ? form.site_image_url : "";
  const serviceLogo = services.find((service) => String(service.id) === String(form.service_id))?.logo_url || "";
  const imagePreview = image || form.site_image_url;
  const pickImage = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) { setImageError("Format accepté : PNG, JPEG ou WebP."); return; }
    if (file.size > MAX_OFFER_IMAGE_BYTES) { setImageError("L’image doit peser moins de 1 Mo."); return; }
    setImageError("");
    const reader = new FileReader();
    reader.onload = () => { setImage(String(reader.result || "")); setRemoveImage(false); };
    reader.onerror = () => setImageError("Impossible de lire ce fichier.");
    reader.readAsDataURL(file);
  };
  const clearImage = () => { setImage(""); set("site_image_url", ""); setRemoveImage(true); };
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_offer_save",
      ...(row ? { offer_id: row.id } : {}),
      ...form,
      image,
      remove_image: removeImage ? "1" : "0",
      site_enabled: form.site_enabled ? "1" : "0",
      site_featured: form.site_featured ? "1" : "0",
      auto_delivery: form.auto_delivery ? "1" : "0",
    });
  };
  return <Modal title={creating ? "Nouveau produit" : `${row.service_name} — ${row.name}`} onClose={onClose} wide>
    <form className="operation-form" onSubmit={submit}>
      <p>Le site et le bot Telegram partagent le même catalogue : {creating ? "ce produit sera aussi proposé dans le bot" : "les modifications s’appliquent aussi au bot"}. Le prix en dinars et les réglages d’affichage ne concernent que le site.</p>
      <h3 className="site-section-title">Produit</h3>
      <div className="form-grid">
        <Field label="Service">
          <select value={form.service_id} onChange={(event) => set("service_id", event.target.value)} required>
            {services.map((service) => <option key={service.id} value={service.id}>{service.emoji} {service.name}{service.active ? "" : " (désactivé)"}</option>)}
          </select>
        </Field>
        <Field label="Nom du produit">
          <input value={form.name} onChange={(event) => set("name", event.target.value)} maxLength={120} required autoFocus={creating} placeholder="Ex. Netflix Premium 1 mois" />
        </Field>
        <Field label="Description en français" wide>
          <textarea value={form.site_description_fr} onChange={(event) => set("site_description_fr", event.target.value)} maxLength={700} rows={4} placeholder={creating ? "Ce que reçoit le client, conditions d’utilisation…" : "Laissez vide pour reprendre la description du bot."} />
        </Field>
        <Field label="Image du produit (site, optionnel)" wide>
          <div className="site-logo-picker">
            <span className="site-logo-preview">{imagePreview || serviceLogo ? <img src={imagePreview || serviceLogo} alt="Image du produit" /> : <ImageIcon size={18} />}</span>
            <label className="action-button secondary site-logo-upload"><Upload size={15} />{imagePreview ? "Remplacer" : "Importer une image"}<input type="file" accept={LOGO_TYPES.join(",")} onChange={pickImage} /></label>
            {imagePreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearImage}>Retirer</ActionButton>}
          </div>
          {!image && !uploadedUrl && <input value={form.site_image_url} onChange={(event) => { set("site_image_url", event.target.value); setRemoveImage(false); }} type="url" maxLength={1000} placeholder="…ou collez un lien https://…/image.png" aria-label="Lien de l’image" />}
          {imageError ? <small className="site-hint"><AlertTriangle size={13} />{imageError}</small>
            : <small className="site-field-help">PNG, JPEG ou WebP, 1 Mo max. {imagePreview ? "Remplace le logo du service pour ce produit." : serviceLogo ? "Sans image, le logo du service est affiché." : "Sans image, l’emoji du service est affiché."}</small>}
        </Field>
      </div>
      <h3 className="site-section-title">Prix</h3>
      <div className="form-grid">
        <Field label="Prix sur le site (DT)">
          <input value={form.tn_price} onChange={(event) => set("tn_price", event.target.value)} inputMode="decimal" placeholder="Ex. 25,500" autoFocus={!creating} />
          {suggestedMillimes > 0 && <button type="button" className="site-link" onClick={() => set("tn_price", dinarInput(suggestedMillimes))}>Utiliser la conversion du prix bot : {dinars(suggestedMillimes)}</button>}
        </Field>
        <Field label="Prix dans le bot (USDT)">
          <input value={form.price} onChange={(event) => set("price", event.target.value)} inputMode="decimal" placeholder={creating ? "Calculé depuis le prix DT si vide" : ""} required={!creating} />
          {derivedUsdt && <small className="site-field-help">Sera fixé à {derivedUsdt.replace(".", ",")} USDT (taux {decimalInput(rate)} DT).</small>}
        </Field>
      </div>
      <h3 className="site-section-title">Affichage sur le site</h3>
      <div className="form-grid">
        <Field label="Catégorie">
          <select value={form.site_category} onChange={(event) => set("site_category", event.target.value)}>
            <option value="">Automatique ({autoLabel})</option>
            {categories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="Badge (optionnel)">
          <input value={form.site_badge} onChange={(event) => set("site_badge", event.target.value)} maxLength={48} placeholder="Ex. Promo, Nouveau, -20 %" />
        </Field>
        <Field label="Affichage">
          <label className="switch"><input type="checkbox" checked={form.site_enabled} onChange={(event) => set("site_enabled", event.target.checked)} /><span />Afficher sur le site</label>
        </Field>
        <Field label="Mise en avant">
          <label className="switch"><input type="checkbox" checked={form.site_featured} onChange={(event) => set("site_featured", event.target.checked)} /><span />Produit vedette</label>
        </Field>
      </div>
      <h3 className="site-section-title">Livraison, durée et garantie</h3>
      <div className="form-grid">
        <Field label="Délai de livraison affiché">
          <input value={form.delivery_delay} onChange={(event) => set("delivery_delay", event.target.value)} maxLength={120} />
        </Field>
        <Field label="Livraison">
          <label className="switch"><input type="checkbox" checked={form.auto_delivery} onChange={(event) => set("auto_delivery", event.target.checked)} /><span />Livraison automatique depuis le stock</label>
        </Field>
        <Field label="Durée de l’abonnement">
          <DurationInput value={form.period_value} unit={form.period_unit} min={1} onValue={(value) => set("period_value", value)} onUnit={(value) => set("period_unit", value)} />
        </Field>
        <Field label="Garantie (0 = sans garantie)">
          <DurationInput value={form.warranty_value} unit={form.warranty_unit} min={0} onValue={(value) => set("warranty_value", value)} onUnit={(value) => set("warranty_unit", value)} />
        </Field>
      </div>
      <h3 className="site-section-title">Stock</h3>
      <div className="form-grid">
        <Field label="Gestion du stock">
          {externallyStocked
            ? <input value={row.supplier_provider ? "Géré par le fournisseur API" : "Stock manuel (bot)"} disabled />
            : <select value={form.stock_mode} onChange={(event) => set("stock_mode", event.target.value)}>
              <option value="inventory">Comptes en stock (livrés un par un)</option>
              <option value="unlimited">Illimité (livraison manuelle)</option>
            </select>}
        </Field>
        {!creating && <Field label="Stock actuel"><input value={row.stock < 0 ? "Illimité" : String(row.stock)} disabled /></Field>}
        {creating && form.stock_mode === "inventory" && <Field label="Stock initial (optionnel)" wide>
          <textarea value={form.initial_inventory} onChange={(event) => set("initial_inventory", event.target.value)} rows={5} placeholder={"###\nEmail : compte1@exemple.com\nMot de passe : ••••\n###\nEmail : compte2@exemple.com\nMot de passe : ••••"} />
          <small className="site-field-help">Commencez chaque compte par une ligne ###. Vous pourrez en ajouter plus tard avec le bouton Stock.</small>
        </Field>}
      </div>
      {!form.tn_price && <p className="site-hint"><AlertTriangle size={14} />Sans prix en dinars, le produit reste masqué du site (il reste vendu dans le bot).</p>}
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={creating ? Plus : Save}>{creating ? "Créer le produit" : "Enregistrer"}</ActionButton></div>
    </form>
  </Modal>;
}

const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_LOGO_BYTES = 500_000;
const MAX_OFFER_IMAGE_BYTES = 1_000_000;
const OFFER_IMAGE_PATH = "/api/storefront/offer-image";

function ServiceEditor({ service, onClose, onSave }) {
  const [form, setForm] = useState({
    name: service?.name || "",
    emoji: service?.emoji || "",
    name_ar: service?.name_ar || "",
    site_enabled: service ? service.site_enabled : true,
    logo: "",
    remove_logo: false,
  });
  const [logoError, setLogoError] = useState("");
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const logoPreview = form.logo || (!form.remove_logo && service?.logo_url) || "";
  const pickLogo = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) { setLogoError("Format accepté : PNG, JPEG ou WebP."); return; }
    if (file.size > MAX_LOGO_BYTES) { setLogoError("Le logo doit peser moins de 500 Ko."); return; }
    setLogoError("");
    const reader = new FileReader();
    reader.onload = () => setForm((current) => ({ ...current, logo: String(reader.result || ""), remove_logo: false }));
    reader.onerror = () => setLogoError("Impossible de lire ce fichier.");
    reader.readAsDataURL(file);
  };
  const clearLogo = () => setForm((current) => ({ ...current, logo: "", remove_logo: Boolean(service?.logo_url) }));
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_service_save",
      ...(service ? { service_id: service.id } : {}),
      ...form,
      site_enabled: form.site_enabled ? "1" : "0",
      remove_logo: form.remove_logo ? "1" : "0",
    });
  };
  return <Modal title={service ? `Modifier le service · ${service.name}` : "Nouveau service"} onClose={onClose}>
    <form className="operation-form" onSubmit={submit}>
      <p>Un service regroupe plusieurs produits (ex. Netflix, ChatGPT, Canva). Il apparaît aussi dans le bot Telegram.</p>
      <div className="form-grid">
        <Field label="Nom"><input value={form.name} onChange={(event) => set("name", event.target.value)} maxLength={80} required autoFocus placeholder="Ex. Netflix" /></Field>
        <Field label="Emoji"><input value={form.emoji} onChange={(event) => set("emoji", event.target.value)} maxLength={12} placeholder="📦" /></Field>
        <Field label="Nom arabe (bot, optionnel)" wide><input dir="rtl" value={form.name_ar} onChange={(event) => set("name_ar", event.target.value)} maxLength={120} /></Field>
        <Field label="Logo du service (site, optionnel)" wide>
          <div className="site-logo-picker">
            <span className="site-logo-preview">{logoPreview ? <img src={logoPreview} alt="Logo du service" /> : form.emoji || <ImageIcon size={18} />}</span>
            <label className="action-button secondary site-logo-upload"><Upload size={15} />{logoPreview ? "Remplacer" : "Importer un logo"}<input type="file" accept={LOGO_TYPES.join(",")} onChange={pickLogo} /></label>
            {logoPreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearLogo}>Retirer</ActionButton>}
          </div>
          {logoError ? <small className="site-hint"><AlertTriangle size={13} />{logoError}</small> : <small className="site-field-help">PNG, JPEG ou WebP, 500 Ko max. Idéalement carré (256 × 256 px). Remplace l’emoji sur le site.</small>}
        </Field>
        <Field label="Affichage" wide><label className="switch"><input type="checkbox" checked={form.site_enabled} onChange={(event) => set("site_enabled", event.target.checked)} /><span />Afficher ce service sur le site</label></Field>
      </div>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={service ? Save : Plus}>{service ? "Enregistrer" : "Créer le service"}</ActionButton></div>
    </form>
  </Modal>;
}

function StockEditor({ row, onClose, onSave }) {
  const [items, setItems] = useState("");
  return <Modal title={`Ajouter du stock · ${row.name}`} onClose={onClose}>
    <form className="operation-form" onSubmit={(event) => { event.preventDefault(); onSave({ action: "add_inventory", offer_id: row.id, items }); }}>
      <p>Stock actuel : <strong>{row.stock < 0 ? "illimité" : row.stock}</strong>. Chaque compte ajouté est livré automatiquement à un client (site ou bot), une seule fois.</p>
      <Field label="Comptes à ajouter" wide>
        <textarea value={items} onChange={(event) => setItems(event.target.value)} rows={9} required autoFocus placeholder={"###\nEmail : compte1@exemple.com\nMot de passe : ••••\n###\nEmail : compte2@exemple.com\nMot de passe : ••••"} />
        <small className="site-field-help">Commencez chaque compte par une ligne contenant uniquement ###. Le contenu est chiffré à l’enregistrement.</small>
      </Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={PackagePlus}>Ajouter au stock</ActionButton></div>
    </form>
  </Modal>;
}

function DeleteConfirm({ target, onClose, onConfirm }) {
  const isService = target.type === "service";
  return <Modal title={isService ? "Supprimer le service" : "Supprimer le produit"} onClose={onClose}>
    <div className="operation-form">
      <p>Supprimer « <strong>{target.item.name}</strong> » ? {isService ? `Le service et ses ${target.item.offers} produit(s) disparaîtront du site et du bot.` : "Le produit disparaîtra du site et du bot."} Les commandes passées sont conservées.</p>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton danger icon={Trash2} onClick={() => onConfirm(isService ? { action: "archive_service", service_id: target.item.id } : { action: "archive_offer", offer_id: target.item.id })}>Supprimer</ActionButton></div>
    </div>
  </Modal>;
}

function SiteCatalogPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [serviceId, setServiceId] = useState("");
  const [category, setCategory] = useState("");
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [editor, setEditor] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/site-catalog", { search, status, service_id: serviceId });
  const counts = result.counts || {};
  const services = result.services || [];
  const categories = result.categories || [];
  const groups = result.groups || [];
  const visibleGroups = category ? groups.filter((group) => group.id === category) : groups;
  const visibleCount = visibleGroups.reduce((total, group) => total + group.count, 0);
  useEffect(() => {
    if (category && !(result.groups || []).some((group) => group.id === category)) setCategory("");
  }, [category, result.groups]);
  const close = () => setEditor(null);
  const run = async (payload) => {
    if (await onAction(payload)) { close(); refreshLists(); }
  };
  const toggleService = async (service) => {
    if (await onAction({ action: "site_service_visibility", service_id: service.id, site_enabled: service.site_enabled ? "0" : "1" })) refreshLists();
  };
  const toggleCollapse = (id) => setCollapsed((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const newProduct = () => setEditor(services.length ? { type: "product" } : { type: "service" });
  const tabs = [["all", "Toutes"], ["on_sale", "En vente"], ["no_price", "Sans prix DT"], ["hidden", "Masquées"], ["disabled", "Désactivées"]];
  return <div className="operations-page site-page">
    <PageHeader
      title="Catalogue du site"
      description="Créez vos services et produits, fixez leur prix en dinars, gérez le stock et l’affichage sur ourblackmarket.com. Une offre sans prix DT reste masquée."
      actions={<>
        <ActionButton secondary icon={Plus} onClick={() => setEditor({ type: "service" })}>Nouveau service</ActionButton>
        <ActionButton icon={PackagePlus} onClick={newProduct}>Nouveau produit</ActionButton>
      </>}
    />
    <div className="site-tabs" role="tablist" aria-label="Filtrer les offres">
      {tabs.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={status === value} onClick={() => setStatus(value)}>{label}<small>{counts[value] ?? 0}</small></button>)}
    </div>
    <div className="workspace-tabs" role="group" aria-label="Catégories du catalogue">
      <button type="button" aria-pressed={!category} onClick={() => setCategory("")}>Toutes les catégories</button>
      {groups.map((group) => <button key={group.id} type="button" aria-pressed={category === group.id} onClick={() => setCategory(group.id)}>{group.label}<small> {group.count}</small></button>)}
    </div>
    <FilterBar search={search} setSearch={setSearch} placeholder="Rechercher une offre ou un service…" resultCount={visibleCount}>
      <select value={serviceId} onChange={(event) => setServiceId(event.target.value)} aria-label="Service">
        <option value="">Tous les services</option>
        {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
      </select>
    </FilterBar>
    {loading && !groups.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement du catalogue…</div>
      : !visibleGroups.length ? <Empty icon={ShoppingBag} title="Aucune offre" text={counts.all ? "Aucune offre ne correspond à ce filtre." : "Créez un service puis ajoutez votre premier produit."} />
      : <div className="catalog-react-grid catalog-table-template catalog-list-view site-catalog-groups" aria-busy={loading}>
        {visibleGroups.map((group) => {
          const folded = collapsed.has(group.id);
          return <section key={group.id} className={`data-panel catalog-collection ${folded ? "collapsed" : ""}`}>
            <header className="panel-heading catalog-collection-heading">
              <div className="catalog-collection-title">
                <button type="button" className="catalog-collection-toggle" onClick={() => toggleCollapse(group.id)} aria-expanded={!folded} aria-label={`${folded ? "Déplier" : "Replier"} ${group.label}`}><ChevronRight size={16} /></button>
                <div>
                  <span className="eyebrow">Catégorie · {group.count} produit(s) · {group.on_sale} en vente</span>
                  <h2>{group.label}</h2>
                </div>
              </div>
            </header>
            <div className="catalog-offers">
              <div className="catalog-offers-content">
                <div className="responsive-table">
                  <table className="catalog-offer-table site-catalog-table">
                    <thead><tr><th>Produit</th><th>Prix bot</th><th>Prix site</th><th>Stock</th><th>Statut</th><th>Actif</th><th className="catalog-col-actions" aria-label="Actions" /></tr></thead>
                    <tbody>{group.items.map((row) => {
                      const [label, className] = CATALOG_STATUS[catalogStatus(row)];
                      const enabled = row.active && row.service_active;
                      const canStock = !row.unlimited_stock && !row.supplier_provider && !row.manual_stock;
                      return <tr key={row.id} className={`offer-row ${enabled ? "" : "inactive"}`}>
                        <td className="catalog-col-name"><div className="site-offer-cell">
                          {row.site_image_url || row.service_logo_url ? <img className="site-thumb" src={row.site_image_url || row.service_logo_url} alt="" loading="lazy" /> : <span className="site-thumb">{row.service_emoji || <ShoppingBag size={15} />}</span>}
                          <div><strong>{row.name}</strong><small>{row.service_name}{row.site_featured && <em className="site-chip"><Sparkles size={11} />Vedette</em>}{row.site_badge && <em className="site-chip">{row.site_badge}</em>}</small></div>
                        </div></td>
                        <td>{row.bot_price_usdt} USDT</td>
                        <td className="catalog-col-price">{row.tn_price_millimes ? <strong>{dinars(row.tn_price_millimes)}</strong> : <small>Suggestion {dinars(row.suggested_price_millimes)}</small>}</td>
                        <td>{row.stock < 0 ? "∞" : row.stock}</td>
                        <td><span className={`status ${className}`}>{label}</span>{!row.service_active ? <small>Service désactivé</small> : !row.service_visible && <small>Service masqué</small>}</td>
                        <td><span className={`status ${enabled ? "delivered" : "cancelled"}`}>{enabled ? "Actif" : "Désactivé"}</span></td>
                        <td className="catalog-col-actions"><div className="site-row-actions">
                          <ActionButton secondary icon={Edit3} onClick={() => setEditor({ type: "product", row })}>{row.tn_price_millimes ? "Modifier" : "Fixer le prix"}</ActionButton>
                          {canStock && <button type="button" title="Ajouter du stock" aria-label={`Ajouter du stock à ${row.name}`} onClick={() => setEditor({ type: "stock", row })}><Boxes size={15} /></button>}
                          <button type="button" title="Dupliquer" aria-label={`Dupliquer ${row.name}`} onClick={() => run({ action: "duplicate_offer", offer_id: row.id })}><Copy size={15} /></button>
                          <button type="button" title={row.active ? "Désactiver (site et bot)" : "Réactiver"} aria-label={`${row.active ? "Désactiver" : "Réactiver"} ${row.name}`} onClick={() => run({ action: "toggle_offer", offer_id: row.id })}>{row.active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}</button>
                          <button type="button" className="danger" title="Supprimer" aria-label={`Supprimer ${row.name}`} onClick={() => setEditor({ type: "delete", target: { type: "offer", item: row } })}><Trash2 size={15} /></button>
                        </div></td>
                      </tr>;
                    })}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>;
        })}
      </div>}
    <section className="site-panel">
      <header><h3><Globe2 size={17} />Services</h3><small>Masquer un service retire ses offres du site sans toucher au bot. Le désactiver le retire des deux.</small></header>
      {!services.length ? <Empty icon={Globe2} title="Aucun service" text="Créez un premier service pour y ranger vos produits." />
        : <div className="site-service-grid">{services.map((service) => <div key={service.id} className={`site-service${service.active ? "" : " site-row-disabled"}`}>
          {service.logo_url ? <img className="site-thumb" src={service.logo_url} alt="" loading="lazy" /> : <span className="site-thumb">{service.emoji || <Globe2 size={15} />}</span>}
          <span><strong>{service.name}</strong><small>{service.active ? `${service.on_sale}/${service.offers} offre(s) en vente` : "Désactivé (site et bot)"}</small></span>
          <span className="site-row-actions">
            <button type="button" title="Ajouter un produit" aria-label={`Ajouter un produit à ${service.name}`} onClick={() => setEditor({ type: "product", serviceId: service.id })}><Plus size={15} /></button>
            <button type="button" title="Modifier" aria-label={`Modifier ${service.name}`} onClick={() => setEditor({ type: "service", service })}><Edit3 size={15} /></button>
            <button type="button" title={service.active ? "Désactiver (site et bot)" : "Réactiver"} aria-label={`${service.active ? "Désactiver" : "Réactiver"} ${service.name}`} onClick={() => run({ action: "toggle_service", service_id: service.id })}>{service.active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}</button>
            <button type="button" className="danger" title="Supprimer" aria-label={`Supprimer ${service.name}`} onClick={() => setEditor({ type: "delete", target: { type: "service", item: service } })}><Trash2 size={15} /></button>
            <label className="switch" title="Afficher sur le site"><input type="checkbox" checked={service.site_enabled} onChange={() => toggleService(service)} aria-label={`Afficher ${service.name} sur le site`} /><span /></label>
          </span>
        </div>)}</div>}
    </section>
    {editor?.type === "product" && <ProductEditor row={editor.row} services={services} categories={categories} rate={Number(result.tnd_per_usdt) || 0} defaultServiceId={editor.serviceId || (serviceId ? Number(serviceId) : null)} onClose={close} onSave={run} />}
    {editor?.type === "service" && <ServiceEditor service={editor.service} onClose={close} onSave={run} />}
    {editor?.type === "stock" && <StockEditor row={editor.row} onClose={close} onSave={run} />}
    {editor?.type === "delete" && <DeleteConfirm target={editor.target} onClose={close} onConfirm={run} />}
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
