import { useState } from "react";
import { Search, ShoppingBag, UserRound } from "lucide-react";
import { STATUS_LABELS, money, date, PageHeader, Empty, useRemoteList, providerLabel } from "../admin-kit.jsx";
import { dinars, LINE_STATUS } from "../site-format.jsx";

const STATE_CLASS = {
  active: "delivered",
  archived: "manual_review",
  inactive: "cancelled",
  product_off: "rejected",
  out_of_stock: "stock_issue",
  deleted: "expired",
};

function spentLabel(channel, value, currency) {
  return channel === "site" ? dinars(value) : money(value, currency || "USDT");
}

function orderStatus(channel, status) {
  if (channel === "site") return LINE_STATUS[status] || STATUS_LABELS[status] || status || "—";
  return STATUS_LABELS[status] || status || "—";
}

function factText(fact) {
  return fact.label === "Fournisseur" ? providerLabel(fact.value) : fact.value;
}

export default function ProductBuyersPage({ channel = "bot", data, onNavigate }) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [result, loading] = useRemoteList("/admin/api/product-buyers", {
    channel,
    search,
    product: selected,
  });
  const products = result.products || [];
  const product = result.product && result.product.key === selected ? result.product : null;
  const currency = data?.currency || result.currency || "USDT";
  const openBuyer = (buyer) => {
    if (buyer.entity_id == null) return;
    onNavigate(buyer.page, buyer.entity_id, channel === "site" ? { search: buyer.email || buyer.name } : null);
  };
  const openOrder = (order) => {
    if (channel === "site" && order.cart_reference) {
      onNavigate("site-orders", order.cart_reference, { search: order.cart_reference, status: "all" });
      return;
    }
    if (order.order_id != null) onNavigate("orders", order.order_id);
  };

  return (
    <>
      <PageHeader
        title="Acheteurs par produit"
        description="Choisissez un produit déjà vendu. Les produits désactivés, archivés ou supprimés restent dans la liste, avec les clients qui les ont achetés."
      />
      <div className="product-buyers">
        <section className="product-buyer-picker" aria-label="Produits vendus">
          <label className="product-buyer-search">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher un produit vendu"
              aria-label="Rechercher un produit vendu"
            />
          </label>
          {loading && !products.length ? <p className="control-caption">Chargement des ventes…</p> : null}
          {!loading && !products.length ? <Empty icon={ShoppingBag} title={search ? "Aucun produit" : "Aucun produit vendu"} text={search ? "Aucun produit vendu ne correspond à cette recherche." : "Les ventes déjà encaissées apparaissent ici, même si le produit est ensuite désactivé ou supprimé."} /> : null}
          <div className="product-buyer-options" role="listbox" aria-label="Produits déjà vendus">
            {products.map((item) => (
              <button
                key={item.key}
                type="button"
                role="option"
                aria-selected={selected === item.key}
                onClick={() => setSelected(item.key)}
              >
                <span>
                  <strong>{item.name}</strong>
                  <em className={`status ${STATE_CLASS[item.catalog_state] || "delivered"}`}>{item.catalog_label}</em>
                </span>
                <small>{[item.service_name, item.period, item.warranty].filter(Boolean).join(" · ") || "Sans service"}</small>
                <small>{item.sales_count} vente(s) · {item.buyer_count} client(s) · {spentLabel(channel, item.spent, currency)}</small>
              </button>
            ))}
          </div>
        </section>
        <section className="product-buyer-detail" aria-live="polite">
          {!product ? <Empty icon={UserRound} title="Sélectionnez un produit" text="La fiche du produit et tous les clients qui l’ont acheté s’affichent ici." /> : (
            <>
              <header className="product-buyer-heading">
                <div>
                  <span className="eyebrow">{product.service_name || "Produit"}</span>
                  <h3>{product.name}</h3>
                </div>
                <em className={`status ${STATE_CLASS[product.catalog_state] || "delivered"}`}>{product.catalog_label}</em>
              </header>
              <div className="order-kpis product-buyer-kpis" aria-label="Résumé des ventes">
                <article><div><small>Ventes</small><strong>{product.sales_count}</strong><em>{product.quantity} unité(s)</em></div></article>
                <article><div><small>Clients</small><strong>{product.buyer_count}</strong><em>Acheteurs distincts</em></div></article>
                <article><div><small>Encaissé</small><strong>{spentLabel(channel, product.spent, currency)}</strong><em>Sur les ventes payées</em></div></article>
                <article><div><small>Dernière vente</small><strong>{date(product.last_sale_at)}</strong><em>Première : {date(product.first_sale_at)}</em></div></article>
              </div>
              <div className="product-buyer-facts">
                {(product.facts || []).map((fact) => (
                  <div key={fact.label} className={fact.label === "Description" ? "wide" : ""}>
                    <span>{fact.label}</span>
                    <strong>{factText(fact)}</strong>
                  </div>
                ))}
              </div>
              <div className="product-buyer-clients">
                <h3>Clients</h3>
                {(product.buyers || []).map((buyer) => (
                  <article key={buyer.key} className="product-buyer-card">
                    <header>
                      <div>
                        <strong>{buyer.name}</strong>
                        <small>{buyer.orders_count} achat(s) · {buyer.quantity} unité(s) · {spentLabel(channel, buyer.spent, currency)}</small>
                      </div>
                      {buyer.entity_id != null ? <button type="button" onClick={() => openBuyer(buyer)}>Ouvrir le client</button> : null}
                    </header>
                    <div className="product-buyer-facts compact">
                      {(buyer.details || []).map((fact) => (
                        <div key={fact.label}><span>{fact.label}</span><strong>{fact.value}</strong></div>
                      ))}
                    </div>
                    <div className="product-buyer-orders">
                      {(buyer.orders || []).map((order) => (
                        <article key={order.order_id}>
                          <button type="button" onClick={() => openOrder(order)}>
                            {channel === "site" && order.cart_reference ? order.cart_reference : `Commande #${order.order_id}`}
                          </button>
                          <span>{orderStatus(channel, order.status)}</span>
                          <span>{order.quantity} × {spentLabel(channel, order.spent, currency)}</span>
                          <time>{date(order.paid_at || order.created_at)}</time>
                        </article>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
