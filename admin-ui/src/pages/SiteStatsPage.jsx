import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, BellRing, CreditCard, Download, Eye, Flame, Gauge, Heart, Layers, Minus, MousePointerClick,
  PackageCheck, Repeat, Search, Share2, ShoppingBag, ShoppingCart, Smartphone, Sparkles, Target,
  TrendingDown, TrendingUp, UserCheck, Users,
} from "lucide-react";
import { Empty, PageHeader, useRemoteList } from "../admin-kit.jsx";
import { csvDocument } from "../control-utils.js";
import {
  DAILY_CSV_COLUMNS, dayLabel, delta, formatCount, formatDelta, formatPercent, insights, niceMax, peakSlot,
  percent, relativeTime,
} from "../site-stats-utils.js";
import "../site-stats.css";

const PERIODS = [7, 30, 90];
const DONUT_COLORS = ["var(--accent)", "var(--green)", "var(--amber)", "var(--muted)"];
const ACTION_ICONS = {
  page: Eye, cart_add: ShoppingCart, checkout: CreditCard, order: PackageCheck,
  favorite: Heart, search: Search, stock_alert: BellRing,
};
const INSIGHT_ICONS = { "best-day": Sparkles, peak: Flame, source: Share2, conversion: Target, device: Smartphone };

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function useCountUp(target, duration = 900) {
  const [value, setValue] = useState(0);
  const shown = useRef(0);
  useEffect(() => {
    const end = Number(target) || 0;
    if (prefersReducedMotion()) { shown.current = end; setValue(end); return undefined; }
    const start = shown.current;
    const began = performance.now();
    let frame = 0;
    const step = (now) => {
      const progress = Math.min(1, (now - began) / duration);
      shown.current = start + (end - start) * (1 - (1 - progress) ** 3);
      setValue(shown.current);
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return value;
}

function AnimatedNumber({ value, format = formatCount }) {
  return <>{format(useCountUp(value))}</>;
}

function DeltaBadge({ change, period }) {
  if (!change) return null;
  const Icon = change.kind === "up" ? TrendingUp : change.kind === "down" ? TrendingDown : change.kind === "new" ? Sparkles : Minus;
  return <span className={`stats-delta is-${change.kind}`} title={`Comparé aux ${period} jours précédents`}>
    <Icon size={12} />{formatDelta(change)}
  </span>;
}

function Sparkline({ values }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => [(index / (values.length - 1)) * 100, 30 - (value / max) * 26]);
  const line = points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  return <svg className="stats-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
    <path d={`${line} L100,32 L0,32 Z`} className="stats-spark-area" />
    <path d={line} pathLength="1" className="stats-spark-line" />
  </svg>;
}

function KpiCard({ icon: Icon, label, value, format, hint, change, period, spark = [], tone = "" }) {
  return <article className={`stats-kpi ${tone}`}>
    <header><span className="stats-kpi-icon"><Icon size={16} /></span><span>{label}</span></header>
    <div className="stats-kpi-value"><strong><AnimatedNumber value={value} format={format} /></strong><DeltaBadge change={change} period={period} /></div>
    <small>{hint}</small>
    <Sparkline values={spark} />
  </article>;
}

function smoothPath(points, floor) {
  if (!points.length) return "";
  if (points.length === 1) return `M${points[0][0]},${points[0][1]}`;
  let path = `M${points[0][0]},${points[0][1]}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const [x0, y0] = points[index - 1] || points[index];
    const [x1, y1] = points[index];
    const [x2, y2] = points[index + 1];
    const [x3, y3] = points[index + 2] || points[index + 1];
    const clamp = (y) => Math.min(floor, y);
    path += ` C${x1 + (x2 - x0) / 6},${clamp(y1 + (y2 - y0) / 6)} ${x2 - (x3 - x1) / 6},${clamp(y2 - (y3 - y1) / 6)} ${x2},${y2}`;
  }
  return path;
}

function TrafficChart({ daily, period }) {
  const [hovered, setHovered] = useState(null);
  const width = 760;
  const height = 260;
  const box = { left: 40, right: 14, top: 16, bottom: 30 };
  const plotWidth = width - box.left - box.right;
  const plotHeight = height - box.top - box.bottom;
  const floor = box.top + plotHeight;
  const max = niceMax(Math.max(0, ...daily.flatMap((point) => [point.visits, point.visitors, point.interactions].map(Number))));
  const band = plotWidth / Math.max(daily.length, 1);
  const x = (index) => box.left + band * index + band / 2;
  const y = (value) => floor - ((Number(value) || 0) / max) * plotHeight;
  const visits = daily.map((point, index) => [x(index), y(point.visits)]);
  const visitors = daily.map((point, index) => [x(index), y(point.visitors)]);
  const visitsLine = smoothPath(visits, floor);
  const labelEvery = Math.ceil(daily.length / 10);
  const barWidth = Math.max(3, Math.min(14, band * 0.42));
  const active = hovered == null ? null : daily[hovered];

  return <div className="stats-chart" onMouseLeave={() => setHovered(null)}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Visites, visiteurs et interactions sur ${period} jours`}>
      <defs>
        <linearGradient id="stats-visits-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity=".32" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => <g key={ratio} className="stats-grid-line">
        <line x1={box.left} x2={width - box.right} y1={floor - ratio * plotHeight} y2={floor - ratio * plotHeight} />
        <text x={box.left - 8} y={floor - ratio * plotHeight + 4}>{formatCount(max * ratio)}</text>
      </g>)}
      {daily.map((point, index) => <rect key={`bar-${point.date}`} className="stats-bar" style={{ animationDelay: `${Math.min(index * 18, 500)}ms` }}
        x={x(index) - barWidth / 2} width={barWidth} y={y(point.interactions)} height={floor - y(point.interactions)} rx={Math.min(4, barWidth / 2)} />)}
      {visits.length > 1 && <path className="stats-area" d={`${visitsLine} L${visits.at(-1)[0]},${floor} L${visits[0][0]},${floor} Z`} />}
      <path className="stats-line" pathLength="1" d={visitsLine} />
      <path className="stats-line is-secondary" pathLength="1" d={smoothPath(visitors, floor)} />
      {daily.map((point, index) => index % labelEvery === 0 || index === daily.length - 1
        ? <text key={`label-${point.date}`} className="stats-axis" x={x(index)} y={height - 8}>{dayLabel(point.date)}</text> : null)}
      {active && <g className="stats-hover">
        <line x1={x(hovered)} x2={x(hovered)} y1={box.top} y2={floor} />
        <circle cx={x(hovered)} cy={y(active.visits)} r="5" />
        <circle cx={x(hovered)} cy={y(active.visitors)} r="4" className="is-secondary" />
      </g>}
      {daily.map((point, index) => <rect key={`hit-${point.date}`} className="stats-hit" x={box.left + band * index} y={box.top} width={band} height={plotHeight}
        onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)} tabIndex={0}
        aria-label={`${dayLabel(point.date, "long")} : ${point.visits} visites`} />)}
    </svg>
    {active && <div className="stats-tooltip" aria-live="polite" style={{ left: `${(x(hovered) / width) * 100}%` }} data-side={hovered > daily.length / 2 ? "left" : "right"}>
      <strong>{dayLabel(active.date, "long")}</strong>
      <span><i className="is-visits" />Visites<b>{formatCount(active.visits)}</b></span>
      <span><i className="is-visitors" />Visiteurs<b>{formatCount(active.visitors)}</b></span>
      <span><i className="is-interactions" />Interactions<b>{formatCount(active.interactions)}</b></span>
    </div>}
  </div>;
}

function Funnel({ steps }) {
  const top = Math.max(Number(steps[0]?.visitors) || 0, 1);
  return <ol className="stats-funnel">
    {steps.map((step, index) => {
      const share = (Number(step.visitors) || 0) / top;
      const fromPrevious = index ? percent(step.visitors, steps[index - 1].visitors) : null;
      return <li key={step.key} style={{ "--share": share, animationDelay: `${index * 90}ms` }}>
        {index > 0 && <em>{formatPercent(fromPrevious)} de l’étape précédente</em>}
        <div><span>{step.label}</span><b>{formatCount(step.visitors)}</b></div>
        <i><span /></i>
        <small>{index ? `${formatPercent(percent(step.visitors, steps[0].visitors))} des visiteurs` : "Point de départ"}</small>
      </li>;
    })}
  </ol>;
}

function Donut({ title, rows, unit }) {
  const total = rows.reduce((sum, row) => sum + (Number(row.count) || 0), 0);
  let offset = 0;
  return <figure className="stats-donut">
    <figcaption>{title}</figcaption>
    <div>
      <svg viewBox="0 0 42 42" role="img" aria-label={`${title} : ${rows.map((row) => `${row.label} ${row.count}`).join(", ")}`}>
        <circle cx="21" cy="21" r="15.915" className="stats-donut-track" />
        {total > 0 && rows.map((row, index) => {
          const size = (row.count / total) * 100;
          const segment = <circle key={row.key} cx="21" cy="21" r="15.915" pathLength="100" className="stats-donut-segment"
            style={{ stroke: DONUT_COLORS[index % DONUT_COLORS.length], strokeDasharray: `${Math.max(size - 0.6, 0)} ${100 - Math.max(size - 0.6, 0)}`, strokeDashoffset: 25 - offset, animationDelay: `${index * 120}ms` }} />;
          offset += size;
          return segment;
        })}
      </svg>
      <span><strong><AnimatedNumber value={total} /></strong><small>{unit}</small></span>
    </div>
    <ul>{rows.map((row, index) => <li key={row.key}>
      <i style={{ background: DONUT_COLORS[index % DONUT_COLORS.length] }} />
      <span>{row.label}</span>
      <b>{total ? formatPercent(percent(row.count, total)) : "—"}</b>
    </li>)}</ul>
  </figure>;
}

function Heatmap({ rows }) {
  const max = Math.max(1, ...rows.flatMap((row) => row.hours));
  const peak = peakSlot(rows);
  return <div className="stats-heatmap">
    <div className="stats-heatmap-grid" role="img"
      aria-label={peak ? `Visites par jour et par heure. Pic le ${peak.day} à ${peak.hour} h avec ${peak.count} visite(s).` : "Visites par jour et par heure."}>
      <span />
      {Array.from({ length: 24 }, (_, hour) => <span key={`h-${hour}`} className="stats-heatmap-hour">{hour % 3 === 0 ? `${hour}h` : ""}</span>)}
      {rows.map((row, rowIndex) => <div key={row.day} className="stats-heatmap-row">
        <span>{row.day}</span>
        {row.hours.map((count, hour) => {
          const level = count / max;
          const isPeak = peak && peak.day === row.day && peak.hour === hour;
          return <i key={hour} title={`${row.day} ${hour} h – ${hour + 1} h : ${count} visite(s)`}
            className={isPeak ? "is-peak" : ""}
            style={{ background: count ? `color-mix(in srgb, var(--accent) ${Math.round(18 + level * 82)}%, var(--panel-soft))` : undefined, animationDelay: `${(rowIndex * 24 + hour) * 4}ms` }} />;
        })}
      </div>)}
    </div>
    <footer>
      <span>Moins</span>
      {[0, 0.25, 0.5, 0.75, 1].map((level) => <i key={level} style={{ background: level ? `color-mix(in srgb, var(--accent) ${Math.round(18 + level * 82)}%, var(--panel-soft))` : undefined }} />)}
      <span>Plus</span>
      {peak && <b><Flame size={13} />Pic : {peak.day} {peak.hour} h ({formatCount(peak.count)})</b>}
    </footer>
  </div>;
}

function RankList({ rows, value, label, detail, emptyIcon, emptyTitle, emptyText }) {
  if (!rows.length) return <Empty icon={emptyIcon} title={emptyTitle} text={emptyText} />;
  const max = Math.max(1, ...rows.map((row) => Number(value(row)) || 0));
  return <ol className="stats-rank">{rows.map((row, index) => <li key={label(row)} style={{ "--share": (Number(value(row)) || 0) / max, animationDelay: `${index * 45}ms` }}>
    <span className="stats-rank-index">{index + 1}</span>
    <div><strong>{label(row)}</strong>{detail && <small>{detail(row)}</small>}</div>
    <b>{formatCount(value(row))}</b>
  </li>)}</ol>;
}

function downloadDaily(daily, period) {
  const url = URL.createObjectURL(new Blob([csvDocument(DAILY_CSV_COLUMNS, daily)], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `statistiques-site-${period}-jours.csv`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function SiteStatsPage() {
  const [days, setDays] = useState(30);
  const [result, loading] = useRemoteList("/admin/api/site-stats", { days }, { refreshInterval: 30000 });
  const [updatedAt, setUpdatedAt] = useState(null);
  const [, setTick] = useState(0);
  const ready = result.ok === true;
  const summary = result.summary || {};
  const previous = result.previous || null;
  const daily = result.daily || [];
  const period = ready ? summary.days || days : days;

  useEffect(() => { if (ready && !loading) setUpdatedAt(new Date()); }, [ready, loading, result]);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const notes = useMemo(() => (ready ? insights(result) : []), [ready, result]);
  const hasActivity = ready && ((summary.visits || 0) > 0 || (summary.interactions || 0) > 0);
  const actions = result.actions || [];
  const actionTotal = actions.reduce((sum, item) => sum + (Number(item.count) || 0), 0);
  const searches = result.searches || [];
  const searchMax = Math.max(1, ...searches.map((item) => item.count));
  const recent = result.recent || [];
  const compare = (key) => (previous ? delta(summary[key], previous[key]) : null);

  return <div className="operations-page site-page stats-page">
    <PageHeader
      title="Statistiques du site"
      description="Audience, parcours d’achat et engagement sur ourblackmarket.com, mesurés par le site lui-même, sans outil externe."
      actions={<div className="stats-actions">
        <div className="stats-period" role="group" aria-label="Période" style={{ "--index": PERIODS.indexOf(days) }}>
          <i aria-hidden="true" />
          {PERIODS.map((value) => <button key={value} type="button" aria-pressed={days === value} onClick={() => setDays(value)}>{value} j</button>)}
        </div>
        <button type="button" className="stats-export" onClick={() => downloadDaily(daily, period)} disabled={!ready || !daily.length}>
          <Download size={15} />Exporter
        </button>
      </div>}
    />

    <section className="stats-live" aria-live="polite">
      <span className="stats-live-dot" aria-hidden="true" />
      <strong>{ready ? formatCount(summary.live_visitors) : "—"} en ligne</strong>
      <span>Visiteurs actifs ces 5 dernières minutes</span>
      <small>
        {loading && !ready ? "Chargement…" : updatedAt ? `Actualisé à ${updatedAt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} · toutes les 30 s` : ""}
        {ready && (previous ? ` · comparé aux ${period} jours précédents` : " · pas de comparaison au-delà de 45 jours")}
      </small>
    </section>

    <section className="stats-kpis" aria-label="Indicateurs clés">
      <KpiCard icon={Eye} label="Visites" value={summary.visits} change={compare("visits")} period={period}
        hint={ready ? `${formatCount(summary.visits_today)} aujourd’hui` : "Pages vues"} spark={daily.map((point) => point.visits)} tone="is-accent" />
      <KpiCard icon={Users} label="Visiteurs uniques" value={summary.unique} change={compare("unique")} period={period}
        hint={ready ? `${formatCount(summary.unique_today)} aujourd’hui` : "Navigateurs distincts"} spark={daily.map((point) => point.visitors)} />
      <KpiCard icon={MousePointerClick} label="Interactions" value={summary.interactions} change={compare("interactions")} period={period}
        hint={ready ? `${formatCount(summary.interactions_today)} aujourd’hui` : "Paniers, recherches, favoris"} spark={daily.map((point) => point.interactions)} />
      <KpiCard icon={PackageCheck} label="Commandes" value={summary.orders} change={compare("orders")} period={period}
        hint={ready ? `${formatPercent(percent(summary.orders, summary.unique))} des visiteurs` : "Depuis le site"} tone="is-green" />
      <KpiCard icon={Layers} label="Pages / visiteur" value={summary.unique ? summary.visits / summary.unique : 0}
        format={(value) => value.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
        hint={ready && summary.entries ? `${formatCount(summary.entries)} entrées sur le site` : "Profondeur de visite"} />
      <KpiCard icon={Gauge} label="Engagement" value={percent(summary.engaged, summary.unique) || 0}
        format={(value) => `${Math.round(value)} %`} hint="Visiteurs ayant agi au moins une fois" />
    </section>

    {notes.length > 0 && <section className="stats-insights" aria-label="À retenir">
      {notes.map((item, index) => {
        const Icon = INSIGHT_ICONS[item.key] || Sparkles;
        return <article key={item.key} style={{ animationDelay: `${index * 70}ms` }}>
          <span><Icon size={16} /></span>
          <div><small>{item.title}</small><p>{item.text}</p></div>
        </article>;
      })}
    </section>}

    <section className="site-panel stats-panel stats-traffic">
      <header>
        <h3><Activity size={16} />Trafic sur {period} jours</h3>
        <div className="stats-legend">
          <span><i className="is-visits" />Visites</span>
          <span><i className="is-visitors" />Visiteurs</span>
          <span><i className="is-interactions" />Interactions</span>
        </div>
      </header>
      {!hasActivity
        ? <Empty icon={Activity} title={loading && !ready ? "Chargement des statistiques…" : "Aucune visite pour le moment"} text="Les pages vues et les actions sur le site apparaîtront ici dès qu’un visiteur navigue." />
        : <TrafficChart key={period} daily={daily} period={period} />}
    </section>

    <div className="stats-row">
      <section className="site-panel stats-panel stats-span-7">
        <header><h3><Target size={16} />Parcours d’achat</h3><small>Visiteurs distincts par étape</small></header>
        {hasActivity ? <Funnel steps={result.funnel || []} /> : <Empty icon={Target} title="Pas encore de parcours" text="Le tunnel se remplit avec les visites, les paniers et les commandes." />}
      </section>
      <section className="site-panel stats-panel stats-span-5">
        <header><h3><Share2 size={16} />Audience</h3><small>{period} jours</small></header>
        <div className="stats-donuts">
          <Donut title="Sources de trafic" rows={result.sources || []} unit="entrées" />
          <Donut title="Appareils" rows={result.devices || []} unit="visiteurs" />
        </div>
        <dl className="stats-audience">
          <div><dt><Repeat size={14} />Visiteurs fidèles</dt><dd><AnimatedNumber value={summary.returning} /></dd><small>revenus un autre jour</small></div>
          <div><dt><UserCheck size={14} />Clients connectés</dt><dd><AnimatedNumber value={summary.signed_in} /></dd><small>avec un compte</small></div>
        </dl>
      </section>
    </div>

    <section className="site-panel stats-panel">
      <header><h3><Flame size={16} />Affluence par jour et par heure</h3><small>Heure de Tunis</small></header>
      {hasActivity ? <Heatmap rows={result.heatmap || []} /> : <Empty icon={Flame} title="Pas encore d’affluence" text="La carte de chaleur montre les créneaux les plus fréquentés." />}
    </section>

    <div className="stats-row">
      <section className="site-panel stats-panel stats-span-6">
        <header><h3><Eye size={16} />Pages les plus vues</h3><small>{period} jours</small></header>
        <RankList rows={result.popular_pages || []} value={(row) => row.visits} label={(row) => row.label}
          detail={(row) => `${row.path} · ${formatPercent(percent(row.visits, summary.visits))}`}
          emptyIcon={Eye} emptyTitle="Aucune page" emptyText="Le classement s’affiche après les premières visites." />
      </section>
      <section className="site-panel stats-panel stats-span-6">
        <header><h3><ShoppingBag size={16} />Produits les plus consultés</h3><small>Vues et ajouts au panier</small></header>
        <RankList rows={result.popular_products || []} value={(row) => row.views} label={(row) => row.name}
          detail={(row) => `${formatCount(row.cart_adds)} ajout(s) au panier${row.views ? ` · ${formatPercent(percent(row.cart_adds, row.views))} de conversion` : ""}`}
          emptyIcon={ShoppingBag} emptyTitle="Aucune fiche produit" emptyText="Les consultations de fiches produit apparaîtront ici." />
      </section>
    </div>

    <div className="stats-row">
      <section className="site-panel stats-panel stats-span-6">
        <header><h3><MousePointerClick size={16} />Interactions</h3><small>{ready ? `${formatCount(actionTotal)} au total` : `${period} jours`}</small></header>
        <ul className="stats-actions-list">{actions.map((item, index) => {
          const Icon = ACTION_ICONS[item.action] || MousePointerClick;
          return <li key={item.action} style={{ "--share": actionTotal ? item.count / actionTotal : 0, animationDelay: `${index * 50}ms` }}>
            <span><Icon size={15} /></span>
            <div><strong>{item.label}</strong><i><span /></i></div>
            <b>{ready ? formatCount(item.count) : "—"}</b>
          </li>;
        })}</ul>
        <h4 className="stats-subtitle"><Search size={14} />Recherches fréquentes</h4>
        {searches.length
          ? <div className="stats-cloud">{searches.map((item) => <span key={item.label} style={{ "--weight": item.count / searchMax }}>{item.label}<b>{formatCount(item.count)}</b></span>)}</div>
          : <p className="stats-muted">Aucune recherche sur la période.</p>}
      </section>
      <section className="site-panel stats-panel stats-span-6">
        <header><h3><Activity size={16} />Activité en direct</h3><small>12 derniers événements</small></header>
        {!recent.length ? <Empty icon={Users} title="Aucune activité" text="Les visites et les interactions récentes s’affichent ici." />
          : <ol className="stats-timeline">{recent.map((event, index) => {
            const Icon = ACTION_ICONS[event.action] || Activity;
            return <li key={`${event.created_at}-${index}`} className={event.kind === "interaction" ? "is-interaction" : ""} style={{ animationDelay: `${index * 40}ms` }}>
              <span><Icon size={14} /></span>
              <div>
                <strong>{event.action_label}{event.label ? ` · ${event.label}` : ""}</strong>
                <small>{[event.page_label, event.customer_name].filter(Boolean).join(" · ")}</small>
              </div>
              <time dateTime={new Date(event.created_at * 1000).toISOString()} title={new Date(event.created_at * 1000).toLocaleString("fr-FR")}>{relativeTime(event.created_at)}</time>
            </li>;
          })}</ol>}
      </section>
    </div>
  </div>;
}
