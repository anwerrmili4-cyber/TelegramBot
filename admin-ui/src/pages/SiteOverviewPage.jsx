import {
  AlertTriangle,
  ClipboardList,
  ExternalLink,
  Globe2,
  RefreshCw,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { date, PageHeader, Empty, useRemoteList, OperationsSummary } from "../admin-kit.jsx";
import { SITE_URL, dinars, CartStatus } from "../site-format.jsx";

export default function SiteOverviewPage({ onNavigate }) {
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
