import { useState } from "react";
import { Activity, Eye, MousePointerClick, Search, ShoppingBag, Users } from "lucide-react";
import { date, Empty, PageHeader, useRemoteList } from "../admin-kit.jsx";

function formatCount(value) {
  return new Intl.NumberFormat("fr-FR").format(Number(value) || 0);
}

export default function SiteStatsPage() {
  const [days, setDays] = useState(30);
  const [result, loading] = useRemoteList("/admin/api/site-stats", { days }, { refreshInterval: 30000 });
  const ready = result.ok === true;
  const summary = result.summary || {};
  const daily = result.daily || [];
  const pages = result.popular_pages || [];
  const products = result.popular_products || [];
  const actions = result.actions || [];
  const searches = result.searches || [];
  const recent = result.recent || [];
  const max = Math.max(...daily.map((point) => Number(point.visits) || 0), 1);
  const shown = (value) => (ready ? formatCount(value) : "—");
  const period = ready ? summary.days || days : days;
  const hasActivity = ready && ((summary.visits || 0) > 0 || (summary.interactions || 0) > 0);

  return <div className="operations-page site-page">
    <PageHeader
      title="Statistiques du site"
      description="Visites, visiteurs uniques et interactions enregistrées sur ourblackmarket.com. Les chiffres viennent du site, sans outil externe."
      actions={<div className="site-tabs" role="group" aria-label="Période">
        <button type="button" aria-selected={days === 7} onClick={() => setDays(7)}>7 jours</button>
        <button type="button" aria-selected={days === 30} onClick={() => setDays(30)}>30 jours</button>
      </div>}
    />
    <section className="workspace-scoreboard" aria-label="Chiffres de fréquentation">
      <div><span>Visites aujourd’hui</span><strong>{shown(summary.visits_today)}</strong><small>{ready ? `${formatCount(summary.visits)} sur ${period} jours` : "Pages vues"}</small></div>
      <div><span>Visiteurs uniques</span><strong>{shown(summary.unique_today)}</strong><small>{ready ? `${formatCount(summary.unique)} sur ${period} jours` : "Navigateurs distincts"}</small></div>
      <div><span>Interactions</span><strong>{shown(summary.interactions_today)}</strong><small>{ready ? `${formatCount(summary.interactions)} sur ${period} jours` : "Paniers, recherches, favoris"}</small></div>
      <div><span>En ligne</span><strong>{shown(summary.live_visitors)}</strong><small>5 dernières minutes</small></div>
    </section>
    <section className="site-panel site-stats-chart">
      <header>
        <h3><Eye size={16} />Visites sur {period} jours</h3>
        <small>{loading && !ready ? "Chargement…" : "Heure de Tunis"}</small>
      </header>
      {!hasActivity ? <Empty icon={Activity} title="Aucune visite pour le moment" text="Les pages vues et les actions sur le site apparaîtront ici dès qu’un visiteur navigue." />
        : <div className="bar-chart" role="img" aria-label={`Visites sur ${period} jours`}>
          {daily.map((point) => <div key={point.date} title={`${point.date} : ${formatCount(point.visits)} visite(s), ${formatCount(point.visitors)} visiteur(s), ${formatCount(point.interactions)} interaction(s)`}>
            <i style={{ height: `${Math.max(point.visits ? 4 : 0, (point.visits / max) * 100)}%` }} />
            <span>{String(point.date).slice(8)}</span>
          </div>)}
        </div>}
    </section>
    <div className="site-stats-grid">
      <section className="site-panel">
        <header><h3><Eye size={16} />Pages les plus vues</h3><small>{period} jours</small></header>
        {!pages.length ? <Empty icon={Eye} title="Aucune page" text="Le classement s’affiche après les premières visites." />
          : <ol className="site-rank">{pages.map((page) => <li key={page.path}>
            <div><strong>{page.label}</strong><small>{page.path}</small></div>
            <b>{formatCount(page.visits)}</b>
          </li>)}</ol>}
      </section>
      <section className="site-panel">
        <header><h3><ShoppingBag size={16} />Produits les plus consultés</h3><small>Vues de fiche</small></header>
        {!products.length ? <Empty icon={ShoppingBag} title="Aucune fiche produit" text="Les consultations de fiches produit apparaîtront ici." />
          : <ol className="site-rank">{products.map((product) => <li key={product.offer_id}>
            <div><strong>{product.name}</strong><small>{formatCount(product.cart_adds)} ajout(s) au panier</small></div>
            <b>{formatCount(product.views)}</b>
          </li>)}</ol>}
      </section>
      <section className="site-panel">
        <header><h3><MousePointerClick size={16} />Interactions</h3><small>{period} jours</small></header>
        <ol className="site-rank">{actions.map((item) => <li key={item.action}>
          <div><strong>{item.label}</strong></div>
          <b>{ready ? formatCount(item.count) : "—"}</b>
        </li>)}</ol>
        {searches.length > 0 && <>
          <h3><Search size={16} />Recherches</h3>
          <ol className="site-rank">{searches.map((item) => <li key={item.label}>
            <div><strong>{item.label}</strong></div>
            <b>{formatCount(item.count)}</b>
          </li>)}</ol>
        </>}
      </section>
      <section className="site-panel">
        <header><h3><Users size={16} />Activité récente</h3><small>12 derniers événements</small></header>
        {!recent.length ? <Empty icon={Users} title="Aucune activité" text="Les visites et les interactions récentes s’affichent ici." />
          : <ul className="site-recent">{recent.map((event, index) => <li key={`${event.created_at}-${index}`}>
            <div>
              <strong>{event.action_label}{event.label ? ` · ${event.label}` : ""}</strong>
              <small>{[event.page_label, event.customer_name].filter(Boolean).join(" · ")}</small>
            </div>
            <b>{date(event.created_at)}</b>
          </li>)}</ul>}
      </section>
    </div>
  </div>;
}
