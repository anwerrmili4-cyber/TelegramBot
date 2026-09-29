import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Edit3,
  ExternalLink,
  Globe2,
  PackageCheck,
  RefreshCw,
  Save,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { ActionButton, Empty, Field, FilterBar, Modal, OperationsSummary, PageHeader, Pagination, date, useRemoteList } from "./AdminPages";

const SITE_URL = "https://www.ourblackmarket.com";

const SITE_CART_STATUS = {
  to_verify: ["À vérifier", "manual_review"],
  confirmed: ["Paiement confirmé", "payment_confirmed"],
  delivered: ["Livré", "delivered"],
  cancelled: ["Annulé", "cancelled"],
  mixed: ["Statuts mixtes", "stock_issue"],
};

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
      ["À vérifier", carts.to_verify || 0, "warning"],
      ["À livrer", carts.confirmed || 0, "accent"],
      ["CA aujourd’hui", dinars(result.revenue_today_millimes), "success"],
      ["CA ce mois", dinars(result.revenue_month_millimes), "info"],
    ]} />
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
  return <div className="operations-page site-page">
    <PageHeader title="Commandes du site" description="Vérifiez le reçu D17 ou Flouci reçu sur WhatsApp, confirmez, puis livrez." />
    <OperationsSummary items={[["À vérifier", counts.to_verify || 0, "warning"], ["À livrer", counts.confirmed || 0, "accent"], ["Livrés", counts.delivered || 0, "success"], ["Annulés", counts.cancelled || 0, "danger"]]} />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Référence TN-…, nom ou téléphone…" resultCount={result.total}>
      <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} aria-label="Statut du panier"><option value="to_verify">À vérifier</option><option value="confirmed">À livrer</option><option value="delivered">Livrés</option><option value="cancelled">Annulés</option><option value="all">Tous</option></select>
    </FilterBar>
    <section className="operations-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des commandes du site…</div> : !result.items.length ? <Empty icon={Globe2} title="Aucune commande" text="Les paniers validés sur le site tunisien apparaîtront ici." /> : <div className="operation-list">{result.items.map((cart) => <article key={cart.reference} className="operation-card">
        <header><span className="operation-icon"><Globe2 size={20} /></span><div><small>{cart.reference}</small><strong>{cart.customer_name || "Client"}</strong></div><CartStatus status={cart.status} /></header>
        <div className="operation-amount"><strong>{dinars(cart.total_millimes)}</strong><span>{String(cart.payment_method || "").toUpperCase() || "Paiement"}</span></div>
        <dl>
          <div><dt>Téléphone</dt><dd>{cart.whatsapp_url ? <a href={cart.whatsapp_url} target="_blank" rel="noreferrer">{cart.customer_phone} <ExternalLink size={12} /></a> : cart.customer_phone || "—"}</dd></div>
          <div><dt>Articles</dt><dd>{cart.items.map((item) => <span key={item.order_id} style={{ display: "block" }}>{item.quantity} × {item.service_name ? `${item.service_name} — ` : ""}{item.offer_name} <small>({dinars(item.total_millimes)})</small></span>)}</dd></div>
          <div><dt>Commandé le</dt><dd>{date(cart.created_at)}</dd></div>
          {cart.customer_note && <div><dt>Note client</dt><dd>{cart.customer_note}</dd></div>}
          {cart.status === "delivered" && <div><dt>Livraison</dt><dd>{cart.delivery_note || "—"} · {date(cart.delivered_at)}</dd></div>}
          {cart.status === "cancelled" && cart.admin_note && <div><dt>Motif d’annulation</dt><dd>{cart.admin_note}</dd></div>}
        </dl>
        {cart.status === "to_verify" && <footer><ActionButton icon={CheckCircle2} onClick={() => run({ action: "site_cart_confirm", reference: cart.reference })}>Confirmer le paiement</ActionButton><ActionButton icon={X} danger onClick={() => openEditor("cancel", cart)}>Annuler</ActionButton></footer>}
        {cart.status === "confirmed" && <footer><ActionButton icon={PackageCheck} onClick={() => openEditor("deliver", cart)}>Marquer livré</ActionButton><ActionButton icon={X} danger onClick={() => openEditor("cancel", cart)}>Annuler</ActionButton></footer>}
      </article>)}</div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {editor?.type === "deliver" && <Modal title={`Livrer le panier ${editor.cart.reference}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_deliver", reference: editor.cart.reference, note }); }}><p>Envoyez les accès au client sur WhatsApp, puis enregistrez la livraison ici.</p><Field label="Ce qui a été envoyé (optionnel)" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={4} placeholder="Ex. compte Netflix envoyé sur WhatsApp à 14h" autoFocus /></Field><div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" icon={PackageCheck}>Marquer livré</ActionButton></div></form></Modal>}
    {editor?.type === "cancel" && <Modal title={`Annuler le panier ${editor.cart.reference}`} onClose={() => setEditor(null)}><form className="operation-form" onSubmit={(event) => { event.preventDefault(); run({ action: "site_cart_cancel", reference: editor.cart.reference, reason: note }); }}><p>{editor.cart.status === "confirmed" ? "Le stock réservé sera remis en vente. Le remboursement D17/Flouci éventuel reste à faire de votre côté." : "Le panier sera retiré de la file de vérification."}</p><Field label="Motif" wide><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={4} required autoFocus /></Field><div className="dialog-actions"><ActionButton type="button" secondary onClick={() => setEditor(null)}>Retour</ActionButton><ActionButton type="submit" danger icon={X}>Annuler le panier</ActionButton></div></form></Modal>}
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

function SiteCustomersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [result, loading] = useRemoteList("/admin/api/site-customers", { search, page, per_page: 25 });
  return <div className="operations-page site-page">
    <PageHeader title="Clients du site" description="Clients identifiés par leur numéro de téléphone, avec leur historique et le total dépensé." />
    <FilterBar search={search} setSearch={(value) => { setSearch(value); setPage(1); }} placeholder="Nom ou numéro de téléphone…" resultCount={result.total} />
    <section className="data-panel" aria-busy={loading}>
      {loading && !result.items.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement des clients…</div>
        : !result.items.length ? <Empty icon={Users} title="Aucun client" text="Les clients apparaîtront après leur première commande sur le site." />
        : <div className="responsive-table"><table className="site-catalog-table">
          <thead><tr><th>Client</th><th>Paniers</th><th>Total dépensé</th><th>Dernière commande</th><th /></tr></thead>
          <tbody>{result.items.map((customer) => <tr key={customer.phone}>
            <td><strong>{customer.name || "Client"}</strong><small><a href={customer.whatsapp_url} target="_blank" rel="noreferrer">{customer.phone} <ExternalLink size={11} /></a></small></td>
            <td>{customer.carts_count}{customer.pending_count > 0 && <small>{customer.pending_count} à vérifier</small>}</td>
            <td><strong>{dinars(customer.total_spent_millimes)}</strong></td>
            <td>{date(customer.last_order_at)}</td>
            <td><ActionButton secondary onClick={() => setSelected(customer)}>Historique</ActionButton></td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination value={result} onChange={setPage} />
    </section>
    {selected && <Modal title={`${selected.name || "Client"} · ${selected.phone}`} onClose={() => setSelected(null)} wide>
      <OperationsSummary items={[["Paniers", selected.carts_count, "info"], ["À vérifier", selected.pending_count, "warning"], ["Total dépensé", dinars(selected.total_spent_millimes), "success"], ["Client depuis", date(selected.first_order_at), ""]]} />
      <ul className="site-recent site-history">{selected.carts.map((cart) => <li key={cart.reference}>
        <div><strong>{cart.reference}</strong><small>{date(cart.created_at)} · {String(cart.payment_method || "").toUpperCase()}</small><small>{cart.items.map((item) => `${item.quantity} × ${item.offer_name}`).join(", ")}</small></div>
        <b>{dinars(cart.total_millimes)}</b>
        <CartStatus status={cart.status} />
      </li>)}</ul>
      <div className="dialog-actions"><a className="action-button" href={selected.whatsapp_url} target="_blank" rel="noreferrer"><ExternalLink size={16} />Écrire sur WhatsApp</a></div>
    </Modal>}
  </div>;
}

function SiteSettingsPage({ onAction }) {
  const [result, loading] = useRemoteList("/admin/api/site-settings", {});
  const [form, setForm] = useState(null);
  useEffect(() => {
    if (form || !result.whatsapp_number) return;
    setForm({
      whatsapp_number: result.whatsapp_number,
      tnd_per_usdt: String(result.tnd_per_usdt).replace(".", ","),
      methods: new Set(result.payment_methods || []),
    });
  }, [form, result]);
  const methods = result.available_payment_methods || [];
  const toggleMethod = (id) => setForm((current) => {
    const next = new Set(current.methods);
    if (next.has(id)) next.delete(id); else next.add(id);
    return { ...current, methods: next };
  });
  const submit = async (event) => {
    event.preventDefault();
    const payload = { action: "site_settings_save", whatsapp_number: form.whatsapp_number, tnd_per_usdt: form.tnd_per_usdt };
    methods.forEach(({ id }) => { payload[`payment_${id}`] = form.methods.has(id) ? "1" : "0"; });
    await onAction(payload);
  };
  return <div className="operations-page site-page">
    <PageHeader title="Paramètres du site" description="Appliqués sur ourblackmarket.com en moins d’une minute, sans redéploiement." />
    <section className="site-panel">
      {loading && !form ? <div className="operation-loading"><RefreshCw className="spin" />Chargement…</div> : form && <form className="operation-form" onSubmit={submit}>
        <div className="form-grid">
          <Field label="Numéro WhatsApp de vérification">
            <input value={form.whatsapp_number} onChange={(event) => setForm({ ...form, whatsapp_number: event.target.value })} inputMode="tel" placeholder="216 21 994 132" required />
            <small className="site-field-help">Les clients y envoient leur reçu D17 ou Flouci.</small>
          </Field>
          <Field label="Taux TND pour 1 USDT">
            <input value={form.tnd_per_usdt} onChange={(event) => setForm({ ...form, tnd_per_usdt: event.target.value })} inputMode="decimal" required />
            <small className="site-field-help">Sert uniquement à suggérer un prix en dinars dans le catalogue.</small>
          </Field>
          <Field label="Moyens de paiement acceptés" wide>
            <div className="site-methods">{methods.map(({ id, label }) => <label key={id} className="switch"><input type="checkbox" checked={form.methods.has(id)} onChange={() => toggleMethod(id)} /><span />{label}</label>)}</div>
          </Field>
        </div>
        <div className="dialog-actions"><ActionButton type="submit" icon={Save}>Enregistrer</ActionButton></div>
      </form>}
    </section>
  </div>;
}

export const SITE_PAGE_IDS = new Set(["site-overview", "site-orders", "site-catalog", "site-customers", "site-settings"]);

export default function SitePage({ page, ...props }) {
  if (page === "site-overview") return <SiteOverviewPage {...props} />;
  if (page === "site-orders") return <SiteOrdersPage {...props} />;
  if (page === "site-catalog") return <SiteCatalogPage {...props} />;
  if (page === "site-customers") return <SiteCustomersPage {...props} />;
  if (page === "site-settings") return <SiteSettingsPage {...props} />;
  return null;
}
