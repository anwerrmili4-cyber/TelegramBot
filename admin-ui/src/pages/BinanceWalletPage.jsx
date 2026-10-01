import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Copy,
  RefreshCw,
  Search,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import { BINANCE_STATUS_LABELS, PageHeader, ActionButton, Empty } from "../admin-kit.jsx";

function binanceDate(value) {
  if (!value) return "—";
  const numeric = Number(value);
  const parsed = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(parsed);
}

function cryptoAmount(value) {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 }).format(Number(value || 0));
}

export default function BinanceWalletPage({ setToast }) {
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [days, setDays] = useState(90);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(`/admin/api/binance-wallet?days=${days}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json();
        if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
        if (!response.ok || payload.ok === false) throw new Error(payload.error || "Portefeuille Binance indisponible.");
        return payload;
      })
      .then((payload) => active && setWallet(payload))
      .catch((requestError) => {
        if (active && requestError.name !== "AbortError") setError(requestError.message);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; controller.abort(); };
  }, [days, refreshVersion]);

  const permissions = wallet?.permissions;
  const unsafeKey = permissions && (permissions.withdrawals || permissions.trading);
  const normalizedSearch = search.trim().toLowerCase();
  const balances = (wallet?.balances || []).filter((item) => !normalizedSearch || item.asset.toLowerCase().includes(normalizedSearch));
  const transactions = (wallet?.transactions || []).filter((item) => {
    if (filter !== "all" && item.type !== filter) return false;
    if (!normalizedSearch) return true;
    return `${item.asset} ${item.network} ${item.status} ${item.txid} ${item.address}`.toLowerCase().includes(normalizedSearch);
  });

  const copyValue = async (value, label) => {
    if (!value || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(value);
    setToast({ type: "success", title: "Copié", message: `${label} copié.` });
  };

  return (
    <>
      <PageHeader
        title="Portefeuille Binance"
        description="Soldes et mouvements récents, en lecture seule : aucun trading, envoi ni retrait possible."
        actions={<ActionButton icon={RefreshCw} secondary disabled={loading} onClick={() => setRefreshVersion((value) => value + 1)}>{loading ? "Synchronisation…" : "Actualiser"}</ActionButton>}
      />

      {error && <section className="binance-alert danger"><AlertTriangle size={20} /><div><strong>Connexion Binance impossible</strong><p>{error}</p></div></section>}
      {unsafeKey && <section className="binance-alert danger"><AlertTriangle size={20} /><div><strong>Permissions dangereuses détectées</strong><p>Désactivez immédiatement le trading et les retraits pour cette clé dans Binance.</p></div></section>}
      {permissions && !unsafeKey && <section className="binance-alert safe"><ShieldCheck size={20} /><div><strong>Clé API en lecture seule</strong><p>Trading et retraits désactivés. Les secrets ne sont jamais transmis au navigateur.</p></div></section>}
      {!!wallet?.warnings?.length && <section className="binance-alert warning"><AlertTriangle size={20} /><div><strong>Données partielles</strong>{wallet.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></section>}

      <div className="binance-kpis">
        <article><span>État du compte</span><strong>{wallet?.account_status || (loading ? "…" : "Inconnu")}</strong><small>{wallet?.endpoint ? new URL(wallet.endpoint).host : "API Binance"}</small></article>
        <article><span>Actifs détenus</span><strong>{wallet?.summary?.assets ?? "—"}</strong><small>{wallet ? `≈ ${cryptoAmount(wallet.summary?.btc_value)} BTC` : "Soldes non nuls"}</small></article>
        <article><span>Dépôts</span><strong>{wallet?.summary?.deposits ?? "—"}</strong><small>{wallet ? `${wallet.period_days} derniers jours` : "Historique"}</small></article>
        <article><span>Retraits</span><strong>{wallet?.summary?.withdrawals ?? "—"}</strong><small>{permissions?.withdrawals ? "API autorisée — à désactiver" : "API de retrait désactivée"}</small></article>
      </div>
      <section className="binance-permissions panel">
        <header><div><span className="eyebrow">Sécurité de la clé</span><h3>Permissions Binance</h3></div><span className={`binance-readonly-badge ${unsafeKey ? "unsafe" : ""}`}>{unsafeKey ? "Action requise" : "Lecture seule"}</span></header>
        <div>
          {[["Lecture", permissions?.read], ["Retraits", permissions?.withdrawals], ["Trading Spot", permissions?.trading], ["Transferts internes", permissions?.internal_transfer], ["Restriction IP", permissions?.ip_restricted]].map(([label, enabled]) => <article key={label}><span>{label}</span><strong className={enabled ? "enabled" : "disabled"}>{permissions == null ? "Inconnu" : enabled ? "Activé" : "Désactivé"}</strong></article>)}
        </div>
      </section>

      <section className="binance-panel panel">
        <header><div><span className="eyebrow">Portefeuille Spot</span><h3>Soldes disponibles</h3></div><span>{balances.length} actif(s)</span></header>
        {loading && !wallet ? <div className="binance-loading"><RefreshCw className="spin" size={20} />Synchronisation sécurisée…</div> : balances.length ? <div className="binance-balance-grid">{balances.map((item) => <article key={item.asset}><div className="binance-asset-icon">{item.asset.slice(0, 3)}</div><div><strong>{item.asset}</strong><span>Total</span></div><div><strong>{cryptoAmount(item.total)}</strong><span>{item.locked > 0 ? `${cryptoAmount(item.locked)} verrouillé` : "Disponible"}</span></div></article>)}</div> : <Empty icon={WalletCards} title="Aucun solde" text={error ? "Réessayez après avoir corrigé la connexion." : "Aucun actif non nul pour ce filtre."} />}
      </section>

      <section className="binance-panel panel">
        <header className="binance-history-header"><div><span className="eyebrow">Historique</span><h3>Mouvements Binance</h3></div><label>Période<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>7 jours</option><option value={30}>30 jours</option><option value={90}>90 jours</option></select></label></header>
        <div className="binance-toolbar">
          <label><Search size={16} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Actif, réseau, statut ou TXID…" /></label>
          <div role="group" aria-label="Filtrer les mouvements">{[["all", "Tous"], ["deposit", "Dépôts"], ["withdrawal", "Retraits"]].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
        </div>
        {transactions.length ? <div className="table-scroll"><table className="binance-table"><thead><tr><th>Type</th><th>Actif</th><th>Montant</th><th>Réseau</th><th>Statut</th><th>Identifiant</th><th>Date</th></tr></thead><tbody>{transactions.map((item, index) => <tr key={`${item.type}-${item.id}-${index}`}><td><span className={`binance-kind ${item.type}`}>{item.type === "deposit" ? "Dépôt" : "Retrait"}</span></td><td><strong>{item.asset || "—"}</strong></td><td>{cryptoAmount(item.amount)}{item.fee > 0 && <small>Frais {cryptoAmount(item.fee)}</small>}</td><td>{item.network || "—"}</td><td><span className={`status-pill ${item.status}`}>{BINANCE_STATUS_LABELS[item.status] || item.status}</span></td><td><button className="binance-copy" onClick={() => copyValue(item.txid, "TXID")} disabled={!item.txid} title="Copier le TXID">{item.txid || item.address || "—"}<Copy size={13} /></button></td><td>{binanceDate(item.timestamp)}</td></tr>)}</tbody></table></div> : !loading && <Empty icon={Activity} title="Aucun mouvement" text="Aucune transaction ne correspond à ces filtres pendant la période sélectionnée." />}
      </section>
      <p className="binance-footnote">Dernière synchronisation : {binanceDate(wallet?.fetched_at)} · Ce panneau ne contient aucune action d’envoi, de trading ou de retrait.</p>
    </>
  );
}
