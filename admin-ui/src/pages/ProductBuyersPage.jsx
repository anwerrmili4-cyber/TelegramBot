import { Fragment, useMemo, useState } from "react";
import { ArrowUpRight, CalendarDays, CheckCircle2, ChevronDown, Search, ShieldCheck, ShoppingBag, UserRound } from "lucide-react";
import { STATUS_LABELS, money, date, PageHeader, Empty, providerLabel } from "../admin-kit.jsx";
import { dinars, LINE_STATUS, useSiteQuery } from "../site-format.jsx";
import { buildAdminQuery } from "../admin-routes.js";
import { BUYER_PERIODS, FW_FILTERS, buyerDateRange, buyerOrderTarget, fwStatusText } from "../product-buyers-utils.js";
import { useProductBuyers } from "./use-product-buyers.js";
import "../product-buyers.css";

const STATE_CLASS = {
  active: "delivered",
  archived: "manual_review",
  inactive: "cancelled",
  product_off: "rejected",
  out_of_stock: "stock_issue",
  deleted: "expired",
};

const FILTERS = [
  { id: "all", label: "Tous", match: () => true },
  { id: "active", label: "Actifs", match: (item) => item.catalog_state === "active" },
  { id: "archived", label: "Archivés", match: (item) => item.catalog_state === "archived" },
  { id: "inactive", label: "Désactivés", match: (item) => item.catalog_state === "inactive" || item.catalog_state === "product_off" },
  { id: "out_of_stock", label: "Hors stock", match: (item) => item.catalog_state === "out_of_stock" },
  { id: "deleted", label: "Supprimés", match: (item) => item.catalog_state === "deleted" },
];

const CATALOG_FACTS = ["État dans le catalogue", "Produit", "Stock", "Fournisseur", "Canaux", "Identifiant"];
const OFFER_FACTS = ["Prix catalogue", "Garantie", "Durée", "Livraison"];

function spentLabel(channel, value, currency) {
  return channel === "site" ? dinars(value) : money(value, currency || "USDT");
}

function orderStatus(channel, status) {
  if (channel === "site") return LINE_STATUS[status] || STATUS_LABELS[status] || status || "—";
  return STATUS_LABELS[status] || status || "—";
}

function factText(fact) {
  if (!fact) return "—";
  return fact.label === "Fournisseur" ? providerLabel(fact.value) : (fact.value || "—");
}

function factMap(facts) {
  return new Map((facts || []).filter((fact) => fact.label !== "Icône du service").map((fact) => [fact.label, fact]));
}

function buyerContact(buyer) {
  const details = new Map((buyer.details || []).map((fact) => [fact.label, fact.value]));
  return [
    details.get("Nom d’utilisateur"),
    details.get("Email"),
    details.get("Téléphone"),
    details.get("Identifiant Telegram") ? `ID ${details.get("Identifiant Telegram")}` : "",
  ].filter((value) => value && value !== "—");
}

function FullWarrantyStatus({ order, compact = false }) {
  const label = fwStatusText(order);
  if (!label) return compact ? null : <span className="fw-status none">Sans FW</span>;
  return <span className={`fw-status ${order.fw_status}`} title={order.expires_at ? `Fin : ${date(order.expires_at)}` : undefined}>
    {order.fw_status === "finished" ? <CheckCircle2 size={13} /> : <ShieldCheck size={13} />}
    {compact ? (order.fw_status === "finished" ? "FW terminé" : "FW en cours") : label}
  </span>;
}

export default function ProductBuyersPage({ channel = "bot", data, onNavigate }) {
  const [query, replace] = useSiteQuery();
  const search = query.search || "";
  const selected = query.product || "";
  const stateFilter = query.state || "all";
  const sort = query.sort || "recent";
  const buyerSearch = query.buyer || "";
  const period = BUYER_PERIODS.some(([id]) => id === query.period) ? query.period : "all";
  const coverage = FW_FILTERS.some(([id]) => id === query.coverage) ? query.coverage : "all";
  const range = buyerDateRange(period, query.from, query.to);
  const view = query.view === "orders" ? "orders" : "clients";
  const [openBuyerKey, setOpenBuyerKey] = useState("");
  const { result, loading, error, refresh } = useProductBuyers({
    channel, search, product: selected, coverage: coverage === "all" ? "" : coverage, from_ts: range.from_ts ?? "", to_ts: range.to_ts ?? "",
  }, !range.error);
  const products = result.products || [];
  const product = result.product && result.product.key === selected ? result.product : null;
  const currency = data?.currency || result.currency || "USDT";
  const visibleProducts = useMemo(() => {
    const filter = FILTERS.find((item) => item.id === stateFilter) || FILTERS[0];
    const rows = products.filter(filter.match);
    const spent = (item) => Number(item.spent || 0);
    rows.sort((left, right) => {
      if (sort === "name") return left.name.localeCompare(right.name, "fr", { sensitivity: "base" });
      if (sort === "sales") return right.sales_count - left.sales_count || left.name.localeCompare(right.name, "fr");
      if (sort === "spent") return spent(right) - spent(left) || left.name.localeCompare(right.name, "fr");
      return Number(right.last_sale_at || 0) - Number(left.last_sale_at || 0);
    });
    return rows;
  }, [products, stateFilter, sort]);
  const counts = useMemo(() => Object.fromEntries(FILTERS.map((filter) => [filter.id, products.filter(filter.match).length])), [products]);
  const facts = factMap(product?.facts);
  const description = facts.get("Description");
  const buyers = (product?.buyers || []).filter((buyer) => {
    const needle = buyerSearch.trim().toLocaleLowerCase("fr");
    if (!needle) return true;
    return `${buyer.name} ${buyerContact(buyer).join(" ")}`.toLocaleLowerCase("fr").includes(needle);
  });
  const routeLink = (target, children, label) => {
    if (!target || target.id == null) return <span>{children}</span>;
    const params = buildAdminQuery(target.page, target.id, target.extra);
    return <a href={`/admin/${target.page}?${params}`} aria-label={label} onClick={(event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      event.stopPropagation();
      onNavigate(target.page, target.id, target.extra);
    }}>{children}</a>;
  };
  const buyerTarget = (buyer) => ({ page: buyer.page, id: buyer.entity_id, extra: channel === "site" ? { search: buyer.email || buyer.name } : null });
  const transactions = buyers.flatMap((buyer) => (buyer.orders || []).map((order) => ({ ...order, buyer })))
    .sort((a, b) => (b.paid_at || b.created_at || 0) - (a.paid_at || a.created_at || 0));

  return (
    <div className="buyer-workspace">
      <PageHeader
        title="Acheteurs par produit"
        description="Explorez les ventes d’un produit et accédez à ses clients et à leurs commandes."
      />
      <section className="buyer-period" aria-label="Période des ventes">
        <div><CalendarDays size={18} /><strong>Période des ventes</strong></div>
        <label><span className="sr-only">Filtrer par période</span><select aria-label="Filtrer par période" value={period} onChange={(event) => replace({ period: event.target.value, from: "", to: "" })}>
          {BUYER_PERIODS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select></label>
        {period === "custom" && <div className="buyer-date-inputs">
          <label>Du<input type="date" aria-label="Date de début" value={query.from || ""} max={query.to || undefined} onChange={(event) => replace({ from: event.target.value })} /></label>
          <label>Au<input type="date" aria-label="Date de fin" value={query.to || ""} min={query.from || undefined} onChange={(event) => replace({ to: event.target.value })} /></label>
        </div>}
        <label className="buyer-fw-filter"><ShieldCheck size={16} /><span>Suivi FW</span><select aria-label="Filtrer le suivi Full Warranty" value={coverage} onChange={(event) => replace({ coverage: event.target.value })}>
          {FW_FILTERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select></label>
        <small>Date de paiement · heure locale</small>
        {(period !== "all" || coverage !== "all" || search || stateFilter !== "all" || buyerSearch) && <button type="button" className="buyer-reset" onClick={() => replace({ period: "", from: "", to: "", coverage: "", search: "", state: "", buyer: "" })}>Réinitialiser les filtres</button>}
      </section>
      {range.error && <p className="buyer-feedback" role="alert">{range.error}</p>}
      {error && <div className="buyer-feedback" role="alert"><span>{error}</span><button type="button" onClick={refresh}>Réessayer</button></div>}
      <div className="buyer-layout">
        <section className="buyer-directory" aria-label="Produits vendus" aria-busy={loading}>
          <header>
            <strong>Produits vendus <span className="buyer-count">{visibleProducts.length}</span></strong>
            <label>
              Trier
              <select value={sort} onChange={(event) => replace({ sort: event.target.value })} aria-label="Trier les produits">
                <option value="recent">Plus récents</option>
                <option value="sales">Plus vendus</option>
                <option value="spent">Plus encaissés</option>
                <option value="name">Nom A–Z</option>
              </select>
            </label>
          </header>
          <label className="buyer-search">
            <Search size={16} />
            <input type="search" value={search} onChange={(event) => replace({ search: event.target.value })} placeholder="Rechercher un produit" aria-label="Rechercher un produit vendu" />
          </label>
          <div className="buyer-filters" role="toolbar" aria-label="Filtrer par état du catalogue">
            {FILTERS.filter((filter) => filter.id === "all" || counts[filter.id]).map((filter) => (
              <button key={filter.id} type="button" aria-pressed={stateFilter === filter.id} onClick={() => replace({ state: filter.id })}>
                {filter.label}<b>{counts[filter.id] || 0}</b>
              </button>
            ))}
          </div>
          {loading ? <p className="control-caption" role="status">Actualisation des ventes…</p> : null}
          {!loading && !error && !range.error && !visibleProducts.length ? <Empty icon={ShoppingBag} title="Aucun produit vendu" text="Aucune vente ne correspond à cette période et à ces filtres." /> : null}
          <div className="buyer-options" aria-label="Produits déjà vendus">
            {visibleProducts.map((item) => (
              <button key={item.key} type="button" aria-pressed={selected === item.key} onClick={() => { replace({ product: item.key, buyer: "" }, { push: true }); setOpenBuyerKey(""); }}>
                <span><strong>{item.name}</strong><em className={`status ${STATE_CLASS[item.catalog_state] || "delivered"}`}>{item.catalog_label}</em></span>
                <small>{[item.service_name, item.period, item.warranty].filter(Boolean).join(" · ") || "Sans service"}</small>
                <small>{item.sales_count} vente{item.sales_count > 1 ? "s" : ""} · {item.buyer_count} client{item.buyer_count > 1 ? "s" : ""} · {spentLabel(channel, item.spent, currency)}</small>
                {item.fw_total > 0 && <span className="buyer-option-fw">
                  {item.fw_active > 0 && <span className="fw-dot active"><ShieldCheck size={11} />{item.fw_active} en cours</span>}
                  {item.fw_finished > 0 && <span className="fw-dot finished"><CheckCircle2 size={11} />{item.fw_finished} terminé{item.fw_finished > 1 ? "s" : ""}</span>}
                </span>}
              </button>
            ))}
          </div>
          <p className="buyer-directory-note">Les produits archivés, désactivés et supprimés restent consultables.</p>
        </section>

        <section className="buyer-dossier" aria-busy={loading}>
          {loading ? <div className="buyer-loading" role="status"><span className="buyer-skeleton" /><span className="buyer-skeleton" /><p>Chargement des ventes…</p></div> : error || range.error ? null : !product ? <Empty icon={UserRound} title={selected ? "Aucune vente sur cette période" : "Sélectionnez un produit"} text={selected ? "Élargissez la période ou choisissez un autre produit pour voir ses acheteurs." : "Choisissez un produit à gauche pour consulter ses clients et ses commandes."} /> : (
            <>
              <header className="buyer-title">
                <div>
                  <span className="eyebrow">{product.service_name || "Produit"}</span>
                  <h2>{product.name}</h2>
                  <p>{[product.period, product.warranty].filter(Boolean).join(" · ") || "Durée et garantie non enregistrées"}</p>
                </div>
                <em className={`status ${STATE_CLASS[product.catalog_state] || "delivered"}`}>{product.catalog_label}</em>
              </header>
              <div className="buyer-metrics" aria-label="Résumé des ventes">
                <article><span>Ventes</span><strong>{product.sales_count}</strong><small>{product.quantity} unité{product.quantity > 1 ? "s" : ""}</small></article>
                <article><span>Clients</span><strong>{product.buyer_count}</strong><small>Acheteurs distincts</small></article>
                <article className="accent"><span>Montant des ventes</span><strong>{spentLabel(channel, product.spent, currency)}</strong><small>Sur la période sélectionnée</small></article>
                <article><span>Dernière vente</span><strong>{date(product.last_sale_at)}</strong><small>Première : {date(product.first_sale_at)}</small></article>
              </div>

              <section className="buyer-fw-summary" aria-label="Suivi Full Warranty">
                <header><div><ShieldCheck size={18} /><span><strong>Suivi Full Warranty</strong><small>État calculé depuis la livraison et la durée du produit.</small></span></div></header>
                <div>
                  <article><span>Tous les FW</span><strong>{product.fw_total || 0}</strong></article>
                  <article className="active"><span>En cours</span><strong>{product.fw_active || 0}</strong><small>Encore utilisés</small></article>
                  <article className="finished"><span>Terminés</span><strong>{product.fw_finished || 0}</strong><small>Durée écoulée</small></article>
                </div>
              </section>

              <section className="buyer-panel">
                <header>
                  <div className="buyer-views" role="group" aria-label="Afficher les clients ou les commandes">
                    <button type="button" aria-pressed={view === "clients"} onClick={() => replace({ view: "" })}><UserRound size={15} />Clients <b>{buyers.length}</b></button>
                    <button type="button" aria-pressed={view === "orders"} onClick={() => replace({ view: "orders" })}><ShoppingBag size={15} />Commandes <b>{transactions.length}</b></button>
                  </div>
                  <label className="buyer-search">
                    <Search size={15} />
                    <input type="search" value={buyerSearch} onChange={(event) => replace({ buyer: event.target.value })} placeholder="Nom, email, identifiant" aria-label="Rechercher un client" />
                  </label>
                </header>
                {view === "orders" ? (transactions.length ? <div className="table-scroll"><table className="buyer-table">
                  <thead><tr><th>Commande</th><th>Client</th><th>Statut</th><th>Suivi FW</th><th>Quantité</th><th>Total</th><th>Date de paiement</th></tr></thead>
                  <tbody>{transactions.map((order) => <tr key={order.order_id}>
                    <td>{routeLink(buyerOrderTarget(channel, order), <>{order.cart_reference || `#${order.order_id}`}<ArrowUpRight size={13} /></>, `Ouvrir la commande ${order.cart_reference || order.order_id}`)}</td>
                    <td>{routeLink(buyerTarget(order.buyer), order.buyer.name)}</td>
                    <td><span className={`status ${order.status}`}>{orderStatus(channel, order.status)}</span></td>
                    <td><FullWarrantyStatus order={order} /></td>
                    <td>{order.quantity}</td><td>{spentLabel(channel, order.spent, currency)}</td><td>{date(order.paid_at || order.created_at)}</td>
                  </tr>)}</tbody>
                </table></div> : <Empty icon={ShoppingBag} title="Aucune commande" text="Aucune commande ne correspond à cette recherche." />) : buyers.length ? (
                  <div className="table-scroll">
                    <table className="buyer-table">
                      <thead><tr><th>Client</th><th>Contact</th><th>Achats</th><th>Montant</th><th>Dernier achat</th><th>Actions</th></tr></thead>
                      <tbody>
                        {buyers.map((buyer) => {
                          const open = openBuyerKey === buyer.key;
                          const account = (buyer.details || []).find((fact) => fact.label === "Compte")?.value;
                          return (
                            <Fragment key={buyer.key}>
                              <tr className={open ? "open" : ""}>
                                <td><strong>{routeLink(buyerTarget(buyer), buyer.name)}</strong><small>{account || "Compte"}</small></td>
                                <td>{buyerContact(buyer).join(" · ") || "—"}</td>
                                <td>{buyer.orders_count} · {buyer.quantity} unité{buyer.quantity > 1 ? "s" : ""}</td>
                                <td>{spentLabel(channel, buyer.spent, currency)}</td>
                                <td>{date(buyer.last_purchase_at)}</td>
                                <td>
                                  <button type="button" aria-expanded={open} aria-label={`${open ? "Masquer" : "Afficher"} les achats de ${buyer.name}`} onClick={() => setOpenBuyerKey(open ? "" : buyer.key)}><ChevronDown size={15} />{open ? "Masquer" : "Achats"}</button>
                                  {buyer.entity_id != null ? routeLink(buyerTarget(buyer), <>Fiche<ArrowUpRight size={13} /></>, `Ouvrir la fiche de ${buyer.name}`) : null}
                                </td>
                              </tr>
                              {open ? <tr className="buyer-orders-row"><td colSpan={6}>
                                <ul>
                                  {(buyer.orders || []).map((order) => (
                                    <li key={order.order_id}>
                                      {routeLink(buyerOrderTarget(channel, order), order.cart_reference || `Commande #${order.order_id}`)}
                                      <span className={`status ${order.status}`}>{orderStatus(channel, order.status)}</span>
                                      <FullWarrantyStatus order={order} compact />
                                      <span>{order.quantity} unité{order.quantity > 1 ? "s" : ""} · Total {spentLabel(channel, order.spent, currency)}</span>
                                      <span>{[order.period, order.warranty].filter(Boolean).join(" · ")}</span>
                                      <time>{date(order.paid_at || order.created_at)}</time>
                                    </li>
                                  ))}
                                </ul>
                              </td></tr> : null}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : <Empty icon={UserRound} title="Aucun client" text="Aucun acheteur ne correspond à cette recherche." />}
              </section>

              <details className="buyer-panel buyer-product-file" key={product.key}>
                <summary><span><strong>Fiche produit</strong><small>Catalogue, offre et description</small></span><ChevronDown size={18} /></summary>
                <div className="buyer-file">
                  <article>
                    <h4>Catalogue</h4>
                    <dl>{CATALOG_FACTS.map((label) => <div key={label}><dt>{label}</dt><dd>{factText(facts.get(label))}</dd></div>)}</dl>
                  </article>
                  <article>
                    <h4>Offre</h4>
                    <dl>{OFFER_FACTS.map((label) => <div key={label}><dt>{label}</dt><dd>{factText(facts.get(label))}</dd></div>)}</dl>
                  </article>
                </div>
                <article className="buyer-description">
                  <h4>Description</h4>
                  <p>{description?.value || "Aucune description enregistrée pour ce produit."}</p>
                </article>
              </details>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
