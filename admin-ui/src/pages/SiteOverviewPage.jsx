import { useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  ClipboardList,
  ExternalLink,
  Globe2,
  Headphones,
  PackageSearch,
  RefreshCw,
  ShieldCheck,
  ShoppingBag,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";
import { date, Empty, useRemoteList } from "../admin-kit.jsx";
import { SITE_URL, dinars, CartStatus } from "../site-format.jsx";

export default function SiteOverviewPage({ data, onNavigate }) {
  const [tab, setTab] = useState("priorities");
  const [result, loading] = useRemoteList("/admin/api/site-overview", {}, { refreshInterval: 30000 });
  const ready = result.ok === true;
  const carts = result.carts || {};
  const catalog = result.catalog || {};
  const topProducts = result.top_products || [];
  const recent = result.recent_carts || [];
  const summary = data?.summary || {};
  const count = (value) => (ready || value != null ? value ?? "—" : "—");
  const queues = [
    ["site-orders", ClipboardList, "Commandes à vérifier", "Contrôler les reçus puis confirmer", ready ? carts.to_verify ?? 0 : "—", "amber"],
    ["site-deposits", Wallet, "Recharges à vérifier", "Comparer le reçu au montant déclaré", ready ? result.deposits_pending ?? 0 : "—", "amber"],
    ["site-support", Headphones, "Support", "Conversations du site en attente", summary.site_open_tickets ?? "—", "blue"],
    ["site-product-requests", PackageSearch, "Demandes produits", "Demandes envoyées depuis le site", summary.site_product_requests ?? "—", ""],
    ["site-warranties", ShieldCheck, "Garanties", "Dossiers du site à traiter", summary.site_warranties ?? "—", "rose"],
    ["site-catalog", ShoppingBag, "Catalogue", "Offres sans prix en dinars", ready ? catalog.no_price ?? 0 : "—", "amber"],
  ];
  return <div className="workspace-home">
    <div className="page-heading">
      <div>
        <h2>Tableau de bord du site</h2>
        <p>ourblackmarket.com : priorités, chiffre d’affaires en dinars et accès rapides.</p>
      </div>
      <div className="page-actions">
        <a className="primary-button" href={SITE_URL} target="_blank" rel="noreferrer"><ExternalLink size={16} />Ouvrir le site</a>
      </div>
    </div>
    <section className="workspace-scoreboard" aria-label="Chiffres du site">
      <div><span>CA aujourd’hui</span><strong>{ready ? dinars(result.revenue_today_millimes) : "—"}</strong><small>Commandes encaissées</small></div>
      <div><span>CA ce mois</span><strong>{ready ? dinars(result.revenue_month_millimes) : "—"}</strong><small>Agrégat réel</small></div>
      <div><span>Commandes du jour</span><strong>—</strong><small>Non renvoyé par l’API</small></div>
      <div><span>Clients</span><strong>{ready ? count(result.customers) : "—"}</strong><small>Comptes vérifiés</small></div>
    </section>
    {ready && catalog.no_price > 0 && <button type="button" className="site-alert" onClick={() => onNavigate("site-catalog")}>
      <AlertTriangle size={18} />
      <span><strong>{catalog.no_price} offre(s) sans prix en dinars</strong> sont masquées du site. Fixez leur prix dans le catalogue pour les mettre en vente.</span>
    </button>}
    <div className="workspace-columns">
      <div className="workspace-main">
        <div className="workspace-tabs" role="group" aria-label="Vue de l’accueil">
          <button type="button" aria-pressed={tab === "priorities"} onClick={() => setTab("priorities")}>Mes priorités</button>
          <button type="button" aria-pressed={tab === "performance"} onClick={() => setTab("performance")}>Performance</button>
          <button type="button" aria-pressed={tab === "recent"} onClick={() => setTab("recent")}>Dernières commandes</button>
        </div>
        {tab === "priorities" && <section className="workspace-inbox">
          <header><span>FILE DE TRAVAIL</span><small>{loading && !ready ? "Chargement…" : "Selon le dernier état synchronisé"}</small></header>
          {queues.map(([page, Icon, title, text, value, tone]) => <button key={page} type="button" onClick={() => onNavigate(page, null, page === "site-orders" ? { status: "to_verify" } : page === "site-deposits" ? { status: "pending" } : null)}>
            <span className={`workspace-task-icon ${tone}`}><Icon size={22} /></span>
            <span className="workspace-task-copy"><strong>{title}</strong><small>{text}</small></span>
            <b>{value}</b>
            <ArrowUpRight size={20} />
          </button>)}
          <footer><ShieldCheck size={16} />Chaque file ouvre l’outil de traitement correspondant.</footer>
        </section>}
        {tab === "performance" && <section className="workspace-inbox">
          <header><span>PERFORMANCE</span><small>Agrégats réels</small></header>
          <p className="site-performance-note">Aucune série journalière n’est renvoyée par /admin/api/site-overview. Le tableau affiche le chiffre d’affaires d’aujourd’hui et du mois, pas une courbe.</p>
          {loading && !topProducts.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement…</div>
            : !topProducts.length ? <Empty icon={TrendingUp} title="Aucune vente confirmée" text="Les ventes apparaîtront après la confirmation d’un premier paiement." />
            : <ol className="site-rank">{topProducts.map((item) => <li key={item.offer_name}>
              <div><strong>{item.offer_name}</strong><small>{item.service_name} · {item.quantity} vendu(s)</small></div>
              <b>{dinars(item.revenue_millimes)}</b>
            </li>)}</ol>}
        </section>}
        {tab === "recent" && <section className="workspace-inbox">
          <header><span>COMMANDES RÉCENTES</span><button type="button" onClick={() => onNavigate("site-orders", null, { status: "all" })}>Tout consulter →</button></header>
          {!recent.length ? <Empty icon={Globe2} title="Aucune commande" text="Les paniers validés sur le site apparaîtront ici." />
            : recent.map((cart) => <button key={cart.reference} type="button" onClick={() => onNavigate("site-orders", cart.reference)}>
              <span className="workspace-task-icon"><ClipboardList size={20} /></span>
              <span className="workspace-task-copy"><strong>{cart.reference} · {cart.customer_name || "Client"}</strong><small>{date(cart.created_at)}</small></span>
              <b>{dinars(cart.total_millimes)}</b>
              <CartStatus status={cart.status} />
            </button>)}
        </section>}
        <section className="workspace-launcher">
          <header><h3>Votre espace de travail</h3><p>Les outils du site, au même rythme que la boutique.</p></header>
          <div>{[
            ["site-catalog", ShoppingBag, "Catalogue", "Prix en dinars et visibilité"],
            ["site-orders", ClipboardList, "Commandes", "Reçus, livraisons et refus"],
            ["site-deposits", Wallet, "Recharges", "Vérification des portefeuilles"],
            ["site-customers", Users, "Clients", "Comptes, achats et soldes"],
          ].map(([page, Icon, title, text]) => <button key={page} type="button" onClick={() => onNavigate(page)}><Icon size={23} /><strong>{title}</strong><small>{text}</small><ArrowUpRight size={18} /></button>)}</div>
        </section>
      </div>
      <aside className="workspace-context">
        <div className="workspace-bot-card">
          <span>SITE TUNISIE</span>
          <div className="workspace-orbit"><span><Globe2 size={28} /></span></div>
          <h3>BlackMarket</h3>
          <p>ourblackmarket.com</p>
          <button type="button" onClick={() => onNavigate("site-settings")}>Paramètres du site <ArrowUpRight size={16} /></button>
        </div>
        <section>
          <span className="eyebrow">ACCÈS DIRECT</span>
          <h3>Le site et le bot partagent le stock.</h3>
          <p>Les prix en dinars et les reçus se traitent ici. Le catalogue bot n’est pas modifié depuis cet écran.</p>
          <button type="button" onClick={() => onNavigate("site-inventory")}>Inventaire partagé →</button>
        </section>
      </aside>
    </div>
  </div>;
}
