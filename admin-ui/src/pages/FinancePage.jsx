import { useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { money, PageHeader, useRemoteList } from "../admin-kit.jsx";

export default function FinancePage({ data }) {
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [month, setMonth] = useState(currentMonth);
  const [selectedDate, setSelectedDate] = useState("");
  const [result, loading] = useRemoteList("/admin/api/finance", { month }, { refreshInterval: 30_000 });
  const totals = result.totals || {};
  const averages = result.averages || {};
  const days = result.month === month ? result.days || [] : [];
  const currency = result.currency || data.currency || "USDT";
  const monthDate = new Date(`${month}-01T12:00:00Z`);
  const leadingDays = (monthDate.getUTCDay() + 6) % 7;
  const selected = days.find((item) => item.date === selectedDate);
  const monthTotals = days.reduce((summary, day) => ({
    revenue: summary.revenue + Number(day.revenue || 0),
    cost: summary.cost + Number(day.cost || 0),
    profit: summary.profit + Number(day.profit || 0),
  }), { revenue: 0, cost: 0, profit: 0 });
  const changeMonth = (direction) => {
    const next = new Date(`${month}-01T12:00:00Z`);
    next.setUTCMonth(next.getUTCMonth() + direction);
    setMonth(next.toISOString().slice(0, 7));
    setSelectedDate("");
  };
  const startedAt = result.started_at
    ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" }).format(new Date(result.started_at * 1000))
    : "le lancement du bot";
  return (
    <>
      <PageHeader title="Profit & pertes" description={`Ventes et achats API reseller depuis ${startedAt}.`} />
      <section className="finance-kpis" aria-label="Résumé financier">
        <article className="income"><span><TrendingUp size={20} /></span><div><small>Argent gagné</small><strong>{money(totals.revenue, currency)}</strong><em>Ventes encaissées</em></div></article>
        <article className="expense"><span><TrendingDown size={20} /></span><div><small>Argent dépensé</small><strong>{money(totals.cost, currency)}</strong><em>Achats API reseller</em></div></article>
        <article className={Number(totals.profit || 0) < 0 ? "loss" : "profit"}><span><CircleDollarSign size={20} /></span><div><small>Profit net</small><strong>{money(totals.profit, currency)}</strong><em>Gains moins dépenses</em></div></article>
        <article><span><CalendarDays size={20} /></span><div><small>Jours gagnants / pertes</small><strong>{result.profitable_days || 0} / {result.loss_days || 0}</strong><em>Jours avec mouvement</em></div></article>
      </section>
      <section className="finance-averages">
        <article><small>Moyenne par jour</small><strong className={Number(averages.daily_profit || 0) < 0 ? "negative" : "positive"}>{money(averages.daily_profit, currency)}</strong><span>{money(averages.daily_revenue, currency)} de ventes / jour</span></article>
        <article><small>Moyenne par semaine</small><strong className={Number(averages.weekly_profit || 0) < 0 ? "negative" : "positive"}>{money(averages.weekly_profit, currency)}</strong><span>{money(averages.weekly_revenue, currency)} de ventes / semaine</span></article>
        <article><small>{new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(monthDate)}</small><strong className={monthTotals.profit < 0 ? "negative" : "positive"}>{money(monthTotals.profit, currency)}</strong><span>{money(monthTotals.revenue, currency)} gagné · {money(monthTotals.cost, currency)} dépensé</span></article>
      </section>
      <section className="finance-calendar data-panel">
        <header><div><span className="eyebrow">Calendrier du profit</span><h3>{new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric", timeZone: "UTC" }).format(monthDate)}</h3></div><div><button type="button" onClick={() => changeMonth(-1)} aria-label="Mois précédent"><ChevronLeft size={18} /></button><button type="button" onClick={() => { setMonth(currentMonth); setSelectedDate(""); }}>Aujourd’hui</button><button type="button" onClick={() => changeMonth(1)} disabled={month >= currentMonth} aria-label="Mois suivant"><ChevronRight size={18} /></button></div></header>
        {loading ? <div className="table-loading">Calcul des finances…</div> : <>
          <div className="finance-weekdays">{["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((day) => <span key={day}>{day}</span>)}</div>
          <div className="finance-days">{Array.from({ length: leadingDays }).map((_, index) => <i key={`blank-${index}`} />)}{days.map((day) => {
            const profit = Number(day.profit || 0);
            const active = Number(day.revenue || 0) !== 0 || Number(day.cost || 0) !== 0;
            return <button type="button" key={day.date} className={`${profit > 0 ? "gain" : profit < 0 ? "loss" : "neutral"} ${selectedDate === day.date ? "selected" : ""}`} onClick={() => setSelectedDate(day.date)} aria-label={`${day.date}, profit ${money(profit, currency)}`}><span>{Number(day.date.slice(-2))}</span>{active ? <><strong>{profit > 0 ? "+" : ""}{money(profit, currency)}</strong><small>{day.orders || 0} vente(s)</small></> : <small>Aucun mouvement</small>}</button>;
          })}</div>
        </>}
      </section>
      {selected && <section className="finance-day-detail"><div><span>{new Intl.DateTimeFormat("fr-FR", { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${selected.date}T12:00:00Z`))}</span><strong className={selected.profit < 0 ? "negative" : "positive"}>{money(selected.profit, currency)}</strong></div><dl><div><dt>Ventes</dt><dd>{money(selected.revenue, currency)}</dd></div><div><dt>Coût reseller</dt><dd>{money(selected.cost, currency)}</dd></div><div><dt>Commandes</dt><dd>{selected.orders || 0}</dd></div></dl></section>}
      {Number(result.cost_quality?.estimated || 0) > 0 && <p className="finance-estimate-note">{result.cost_quality.estimated} ancien(s) achat(s) utilisent le dernier prix fournisseur enregistré. Les nouveaux achats conservent automatiquement le prix au moment de l’achat.</p>}
      {Number(result.cost_quality?.unknown || 0) > 0 && <p className="finance-estimate-note">{result.cost_quality.unknown} achat(s) fournisseur n’ont pas de prix d’achat enregistré. Le profit affiché peut être surestimé.</p>}
    </>
  );
}
