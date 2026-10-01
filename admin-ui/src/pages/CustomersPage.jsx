import { useEffect, useState } from "react";
import {
  Activity,
  Ban,
  ChevronRight,
  CircleDollarSign,
  Database,
  Edit3,
  Eye,
  Headphones,
  MessageSquareText,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  SlidersHorizontal,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { STATUS_LABELS, money, orderAmount, date, PageHeader, ActionButton, Modal, Field, Empty, Pagination, useRemoteList } from "../admin-kit.jsx";
import { PendingWalletTopups, DEPOSIT_PROVIDER_LABELS } from "./wallet-topups.jsx";

function CustomerDetail({ customer, onAction, onClose, onNavigate, currency }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [loadingOrder, setLoadingOrder] = useState(null);
  const [customerTab, setCustomerTab] = useState("timeline");
  const openOrder = async (order) => {
    setLoadingOrder(order.id);
    try {
      const response = await fetch(`/admin/api/orders?detail=1&order_id=${order.id}`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      setSelectedOrder(response.ok ? await response.json() : order);
    } finally {
      setLoadingOrder(null);
    }
  };
  const displayName = [customer.first_name, customer.last_name].filter(Boolean).join(" ")
    || customer.full_name
    || (customer.username ? `@${customer.username}` : `Client ${customer.telegram_id}`);
  const tabs = [
    ["timeline", Activity, "Chronologie", customer.timeline?.length || 0],
    ["orders", ShoppingBag, "Achats", (customer.orders?.length || 0) + (customer.api_purchases?.length || 0)],
    ["finance", CircleDollarSign, "Finances", (customer.topups?.length || 0) + (customer.withdrawals?.length || 0)],
    ["support", Headphones, "Support", customer.tickets?.length || 0],
    ["warranties", ShieldCheck, "Garanties", customer.warranties?.length || 0],
  ];
  return (
    <>
      <Modal
        title={
          customer.username
            ? `@${customer.username}`
            : `Client ${customer.telegram_id}`
        }
        onClose={onClose}
        fullScreen
      >
      <div className="customer-profile-head customer-profile-hero">
        <span>{(customer.first_name || customer.username || "C").slice(0, 1).toUpperCase()}</span>
        <div><strong>{displayName}</strong><small>{customer.username ? `@${customer.username} · ` : ""}ID {customer.telegram_id} · {String(customer.lang || customer.language || "en").toUpperCase()}</small></div>
        <div className="customer-profile-actions">
          <button type="button" onClick={() => {
            const firstTicket = customer.tickets?.[0];
            onClose();
            onNavigate("support", firstTicket?.id || null);
          }}><MessageSquareText size={16} />Messages support</button>
          <i className={customer.banned ? "blocked" : "active"}>{customer.banned ? "Bloqué" : "Actif"}</i>
        </div>
      </div>
      <div className="customer-profile-layout">
        <div className="customer-profile-main">
          <div className="customer-profile-kpis">
            <article><span>Portefeuille</span><strong>{money(customer.wallet_balance, currency)}</strong><small>solde disponible</small></article>
            <article><span>Dépensé</span><strong>{money(customer.total_spent, currency)}</strong><small>{customer.paid_order_count || 0} achat(s) payé(s)</small></article>
            <article><span>Dépôts</span><strong>{money(customer.deposit_total, currency)}</strong><small>{customer.topups?.length || 0} opération(s)</small></article>
            <article><span>Affiliation</span><strong>{customer.referral_count || 0}</strong><small>{money(customer.affiliate_earned, currency)} gagné</small></article>
          </div>
          <div className="customer-facts">
            <div><span>Inscription</span><strong>{date(customer.created_at)}</strong></div>
            <div><span>Dernière activité</span><strong>{date(customer.last_active_at || customer.last_order_at)}</strong></div>
            <div><span>Niveau fidélité</span><strong>{customer.loyalty?.level || "Standard"}</strong></div>
            <div><span>Interactions</span><strong>{customer.interaction_total || customer.interaction_count || 0}</strong></div>
          </div>
        </div>
        <aside className="customer-wallet-control">
          <span className="eyebrow">Contrôle administrateur</span>
          <h4>Portefeuille et accès</h4>
          <div className="form-grid">
            <Field label="Montant"><input type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="+10 ou -5" /></Field>
            <Field label="Motif"><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Correction, bonus…" /></Field>
          </div>
          <div className="dialog-actions wrap">
            <ActionButton icon={CircleDollarSign} disabled={!amount || !reason.trim()} onClick={() => onAction({ action: "adjust_user_wallet", user_id: customer.telegram_id, amount, reason })}>Ajuster</ActionButton>
            <ActionButton danger icon={Ban} onClick={() => onAction({ action: "toggle_ban", user_id: customer.telegram_id, banned: customer.banned ? "0" : "1" })}>{customer.banned ? "Débloquer" : "Bloquer"}</ActionButton>
          </div>
        </aside>
      </div>
      <div className="customer-detail-tabs" role="tablist">
        {tabs.map(([key, Icon, label, count]) => <button key={key} type="button" role="tab" aria-selected={customerTab === key} className={customerTab === key ? "active" : ""} onClick={() => setCustomerTab(key)}><Icon size={14} />{label}<span>{count}</span></button>)}
      </div>
      {customerTab === "timeline" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Vue à 360°</span><h4>Chronologie du client</h4></div><strong>{customer.timeline?.length || 0}</strong></header>
        {customer.timeline?.length ? <div className="customer-timeline">{customer.timeline.map((event, index) => {
          const EventIcon = { order: ShoppingBag, topup: CircleDollarSign, withdrawal: Database, ticket: Headphones, warranty: ShieldCheck, reward: Sparkles, adjustment: Edit3 }[event.type] || Activity;
          return <article key={`${event.type}-${event.id}-${index}`}><span className={`timeline-icon ${event.type}`}><EventIcon size={15} /></span><div><strong>{event.title}</strong><p>{event.description}</p><small>{date(event.created_at)}</small></div><aside>{event.status && <span className={`status ${event.status}`}>{STATUS_LABELS[event.status] || event.status}</span>}{event.amount !== undefined && event.amount !== null && <b className={Number(event.amount) < 0 ? "negative" : ""}>{Number(event.amount) > 0 ? "+" : ""}{money(event.amount, currency)}</b>}</aside></article>;
        })}</div> : <Empty icon={Activity} title="Aucune activité" text="Les futures opérations apparaîtront ici." />}
        <div className="customer-profile-split">
          <div><h5>Programme fidélité</h5><dl><div><dt>Niveau</dt><dd>{customer.loyalty?.level || "Standard"}</dd></div><div><dt>Réduction</dt><dd>{customer.loyalty?.discount_percent || 0}%</dd></div><div><dt>Total reconnu</dt><dd>{money(customer.loyalty?.total_spend, currency)}</dd></div></dl></div>
          <div><h5>Dernières interactions</h5>{customer.interactions?.length ? <ul>{customer.interactions.slice(0, 6).map((event, index) => <li key={`${event.created_at}-${index}`}><span>{event.action || event.interaction_type || "Interaction"}</span><small>{date(event.created_at)}</small></li>)}</ul> : <p>Aucune interaction enregistrée.</p>}</div>
        </div>
        {!!customer.referrals?.length && <div className="customer-subsection"><h5>Profils parrainés</h5><div className="compact-history">{customer.referrals.map((referral, index) => <article key={referral.referred_id || index}><div><strong>{referral.customer?.username ? `@${referral.customer.username}` : referral.customer?.first_name || `Client ${referral.referred_id}`}</strong><small>Telegram ID {referral.referred_id}{referral.qualified_order_id ? ` · commande #${referral.qualified_order_id}` : ""}</small></div><span className={`status ${referral.valid === false ? "pending" : "confirmed"}`}>{referral.valid === false ? "À qualifier" : "Qualifié"}</span><time>{date(referral.qualified_at || referral.created_at)}</time></article>)}</div></div>}
      </section>}
      {customerTab === "orders" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Historique complet</span><h4>Produits achetés</h4></div><strong>{customer.orders?.length || 0}</strong></header>
        {customer.orders?.length ? <div className="customer-purchase-grid">{customer.orders.map((order) => <button type="button" key={order.id} onClick={() => openOrder(order)}>
          <header><span>Commande #{order.id}</span><span className={`status ${order.status}`}>{STATUS_LABELS[order.status] || order.status}</span></header>
          <h5>{order.offer_name || order.service_name || "Produit supprimé"}</h5>
          <dl><div><dt>Montant</dt><dd>{money(orderAmount(order), currency)}</dd></div><div><dt>Quantité</dt><dd>{order.qty || 1}</dd></div><div><dt>Garantie</dt><dd>{order.warranty || order.warranty_days ? `${order.warranty || order.warranty_days} j` : "—"}</dd></div></dl>
          <footer><span>{date(order.created_at)}</span><span>Voir tous les détails <Eye size={14} /></span></footer>
        </button>)}</div> : <Empty icon={ShoppingBag} title="Aucun achat" text="Ce client n’a encore passé aucune commande." />}
        {!!customer.api_purchases?.length && <div className="customer-subsection"><h5>Achats via API</h5><div className="compact-history">{customer.api_purchases.map((purchase, index) => <article key={purchase.idempotency_key || index}><div><strong>{purchase.response?.productType || purchase.status || "Achat API"}</strong><small>{purchase.idempotency_key || `Opération ${index + 1}`}</small></div><span className={`status ${purchase.response?.success ? "delivered" : "rejected"}`}>{purchase.response?.success ? "Réussi" : "Échec"}</span><b>{money(purchase.response?.amount, currency)}</b><time>{date(purchase.created_at)}</time></article>)}</div></div>}
        {loadingOrder && <div className="table-loading">Chargement de la commande #{loadingOrder}…</div>}
      </section>}
      {customerTab === "finance" && <section className="customer-profile-section">
        <header><div><span className="eyebrow">Traçabilité financière</span><h4>Dépôts, retraits et ajustements</h4></div><strong>{(customer.topups?.length || 0) + (customer.withdrawals?.length || 0)}</strong></header>
        <div className="customer-finance-columns">
          <div><h5>Dépôts</h5>{customer.topups?.length ? <div className="compact-history">{customer.topups.map((item, index) => <article key={item.id || item.txid || index}><div><strong>{DEPOSIT_PROVIDER_LABELS[item.provider] || item.provider || "Dépôt"}</strong><small>{item.txid || `Dépôt #${item.id}`}</small></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b>+{money(item.amount, item.currency || currency)}</b><time>{date(item.created_at)}</time></article>)}</div> : <p>Aucun dépôt.</p>}</div>
          <div><h5>Retraits</h5>{customer.withdrawals?.length ? <div className="compact-history">{customer.withdrawals.map((item, index) => <article key={item.id || index}><div><strong>{item.method || "Retrait"}</strong><small>{item.destination || `Retrait #${item.id}`}</small></div><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span><b className="negative">-{money(item.amount, currency)}</b><time>{date(item.created_at)}</time></article>)}</div> : <p>Aucun retrait.</p>}</div>
        </div>
        {!!customer.wallet_adjustments?.length && <div className="customer-subsection"><h5>Ajustements administrateur</h5><div className="compact-history">{customer.wallet_adjustments.map((item) => <article key={item.id}><div><strong>{item.details?.reason || "Ajustement"}</strong><small>Admin {item.actor_id || "système"} · solde après {money(item.details?.balance, currency)}</small></div><b className={Number(item.details?.amount) < 0 ? "negative" : ""}>{Number(item.details?.amount) > 0 ? "+" : ""}{money(item.details?.amount, currency)}</b><time>{date(item.created_at)}</time></article>)}</div></div>}
      </section>}
      {customerTab === "support" && <section className="customer-profile-section"><header><div><span className="eyebrow">Support client</span><h4>Tous les tickets</h4></div><strong>{customer.tickets?.length || 0}</strong></header>{customer.tickets?.length ? <div className="customer-ticket-list">{customer.tickets.map((ticket) => <button type="button" key={ticket.id} onClick={() => { onClose(); onNavigate("support", ticket.id); }}><div><strong>Ticket #{ticket.id}</strong><span className={`status ${ticket.status}`}>{STATUS_LABELS[ticket.status] || ticket.status}</span></div><p>{ticket.subject || ticket.category || ticket.message || "Demande de support"}</p><small>Mis à jour {date(ticket.updated_at || ticket.created_at)}</small><span className="customer-ticket-open">Ouvrir les messages <ChevronRight size={15} /></span></button>)}</div> : <Empty icon={Headphones} title="Aucun ticket" text="Ce client n’a aucune demande de support." />}</section>}
      {customerTab === "warranties" && <section className="customer-profile-section"><header><div><span className="eyebrow">Après-vente</span><h4>Demandes de garantie</h4></div><strong>{customer.warranties?.length || 0}</strong></header>{customer.warranties?.length ? <div className="customer-warranty-grid">{customer.warranties.map((item) => <article key={item.id}><header><strong>Garantie #{item.id}</strong><span className={`status ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span></header><h5>Commande #{item.order_id}</h5><p>{item.reason || "Aucun motif communiqué."}</p><footer><span>{item.days_used || 0} jour(s) utilisé(s)</span><b>{money(item.refund_amount, currency)}</b><time>{date(item.updated_at || item.created_at)}</time></footer></article>)}</div> : <Empty icon={ShieldCheck} title="Aucune garantie" text="Aucune demande après-vente pour ce client." />}</section>}
      </Modal>
      {selectedOrder && (
        <OrderEditor
          order={selectedOrder}
          currency={currency}
          onAction={onAction}
          onClose={() => setSelectedOrder(null)}
        />
      )}
    </>
  );
}

export default function CustomersPage({ data, onAction, onNavigate }) {
  const [search, setSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [walletFilter, setWalletFilter] = useState("all");
  const [ordersFilter, setOrdersFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkAmount, setBulkAmount] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [revision, setRevision] = useState(0);
  const [result, loading] = useRemoteList("/admin/api/customers", {
    search,
    search_field: searchField,
    status: statusFilter,
    wallet: walletFilter,
    orders: ordersFilter,
    sort,
    page,
    per_page: 25,
    revision,
  });
  const open = async (user) => {
    const response = await fetch(
      `/admin/api/customers?user_id=${user.telegram_id}`,
      { credentials: "same-origin", cache: "no-store" },
    );
    if (response.ok) setSelected(await response.json());
  };
  const closeCustomer = () => {
    setSelected(null);
    if (new URLSearchParams(window.location.search).has("user")) window.history.replaceState({}, "", "/admin/customers");
  };
  useEffect(() => {
    const openRequestedCustomer = (userId) => {
      if (userId != null && /^\d+$/.test(String(userId))) open({ telegram_id: Number(userId) });
    };
    openRequestedCustomer(new URLSearchParams(window.location.search).get("user"));
    const navigateToCustomer = (event) => {
      if (event.detail?.page === "customers") openRequestedCustomer(event.detail.entityId);
    };
    const restoreCustomerRoute = () => {
      const requested = new URLSearchParams(window.location.search).get("user");
      if (requested) openRequestedCustomer(requested);
      else setSelected(null);
    };
    window.addEventListener("admin:navigate", navigateToCustomer);
    window.addEventListener("popstate", restoreCustomerRoute);
    return () => {
      window.removeEventListener("admin:navigate", navigateToCustomer);
      window.removeEventListener("popstate", restoreCustomerRoute);
    };
  }, []);
  const customerAction = async (payload) => {
    const result = await onAction(payload);
    if (result) {
      setRevision((value) => value + 1);
      if (selected) await open(selected);
    }
    return result;
  };
  const visible = result.items || [];
  const visibleWallets = visible.reduce((sum, user) => sum + Number(user.wallet_balance || 0), 0);
  const visibleSpent = visible.reduce((sum, user) => sum + Number(user.total_spent || 0), 0);
  const activeVisible = visible.filter((user) => !user.banned).length;
  const hasCustomerFilters = Boolean(
    search
      || searchField !== "all"
      || statusFilter !== "all"
      || walletFilter !== "all"
      || ordersFilter !== "all"
      || sort !== "newest",
  );
  const resetCustomerFilters = () => {
    setSearch("");
    setSearchField("all");
    setStatusFilter("all");
    setWalletFilter("all");
    setOrdersFilter("all");
    setSort("newest");
    setPage(1);
  };
  return (
    <>
      <PageHeader
        title="Clients"
        description="Identité, portefeuille, achats, dépôts, affiliation et support de chaque client."
        actions={
          <ActionButton
            icon={CircleDollarSign}
            onClick={() => setBulkOpen(true)}
          >
            Crédit collectif
          </ActionButton>
        }
      />
      <PendingWalletTopups onAction={onAction} />
      <div className="customer-directory-kpis">
        <article><span><Users size={17} /></span><div><small>Clients trouvés</small><strong>{result.total || 0}</strong><em>{activeVisible} actifs sur cette page</em></div></article>
        <article><span><CircleDollarSign size={17} /></span><div><small>Soldes affichés</small><strong>{money(visibleWallets, data.currency)}</strong><em>portefeuilles disponibles</em></div></article>
        <article><span><ShoppingBag size={17} /></span><div><small>Achats affichés</small><strong>{money(visibleSpent, data.currency)}</strong><em>dépenses cumulées</em></div></article>
      </div>
      <section className={`customer-filter-shell ${hasCustomerFilters ? "is-filtered" : ""}`} aria-label="Recherche et filtres clients">
        <header className="customer-filter-heading">
          <div><span><SlidersHorizontal size={16} /></span><div><strong>Affiner les clients</strong><small>Recherchez un profil ou combinez plusieurs critères.</small></div></div>
          <div><strong>{result.total || 0}</strong><span>profil{result.total === 1 ? "" : "s"}</span></div>
        </header>
        <div className="customer-filter-search-row">
          <label className="customer-search-box">
            <Search size={19} aria-hidden="true" />
            <span className="sr-only">Rechercher un client</span>
            <input
              type="search"
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(1); }}
              placeholder="Nom, username ou Telegram ID…"
              aria-label="Rechercher un client par nom, username ou Telegram ID"
            />
            {search && <button type="button" onClick={() => { setSearch(""); setPage(1); }} title="Effacer la recherche" aria-label="Effacer la recherche"><X size={15} /></button>}
          </label>
          <label className="customer-filter-field customer-filter-scope">
            <span>Rechercher dans</span>
            <select value={searchField} onChange={(event) => { setSearchField(event.target.value); setPage(1); }}>
              <option value="all">Tous les champs</option>
              <option value="name">Nom / prénom</option>
              <option value="username">Username</option>
              <option value="telegram_id">Telegram ID</option>
            </select>
          </label>
        </div>
        <div className="customer-filter-controls">
          <label className="customer-filter-field">
            <span>Statut</span>
            <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les statuts</option>
              <option value="active">Clients actifs</option>
              <option value="banned">Clients bloqués</option>
            </select>
          </label>
          <label className="customer-filter-field">
            <span>Portefeuille</span>
            <select value={walletFilter} onChange={(event) => { setWalletFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les soldes</option>
              <option value="funded">Solde positif</option>
              <option value="empty">Solde vide</option>
            </select>
          </label>
          <label className="customer-filter-field">
            <span>Commandes</span>
            <select value={ordersFilter} onChange={(event) => { setOrdersFilter(event.target.value); setPage(1); }}>
              <option value="all">Tous les clients</option>
              <option value="with_orders">Avec commandes</option>
              <option value="without_orders">Sans commande</option>
            </select>
          </label>
          <label className="customer-filter-field customer-filter-sort">
            <span>Trier par</span>
            <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
              <option value="newest">Plus récents</option>
              <option value="oldest">Plus anciens</option>
              <option value="balance">Solde le plus élevé</option>
              <option value="spent">Dépenses les plus élevées</option>
              <option value="orders">Plus de commandes</option>
            </select>
          </label>
          <button className="customer-filter-reset" type="button" onClick={resetCustomerFilters} disabled={!hasCustomerFilters}>
            <X size={15} /> Réinitialiser
          </button>
        </div>
      </section>
      <section className="data-panel customer-directory">
        <header className="customer-directory-head"><div><span className="eyebrow">Répertoire CRM</span><h3>Cartes clients</h3></div><span>{result.total || 0} profil(s)</span></header>
        <div className="customer-card-grid">
          {visible.map((user) => {
            const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.full_name || (user.username ? `@${user.username}` : `Client ${user.telegram_id}`);
            return <button type="button" className="customer-card" key={user.telegram_id} onClick={() => open(user)}>
              <header><span className="customer-card-avatar">{(user.first_name || user.username || "C").slice(0, 1).toUpperCase()}</span><div><strong>{name}</strong><small>{user.username ? `@${user.username} · ` : ""}ID {user.telegram_id}</small></div><i className={user.banned ? "blocked" : "active"}>{user.banned ? "Bloqué" : "Actif"}</i></header>
              <div className="customer-card-money"><span><small>Portefeuille</small><strong>{money(user.wallet_balance, data.currency)}</strong></span><span><small>Total dépensé</small><strong>{money(user.total_spent, data.currency)}</strong></span></div>
              <div className="customer-card-metrics"><span><ShoppingBag size={14} /><strong>{user.order_count || 0}</strong><small>achats</small></span><span><Database size={14} /><strong>{user.deposit_count || 0}</strong><small>dépôts</small></span><span><Users size={14} /><strong>{user.referral_count || 0}</strong><small>filleuls</small></span><span><Headphones size={14} /><strong>{user.ticket_count || 0}</strong><small>tickets</small></span></div>
              <footer><div><small>Dernier achat</small><strong>{user.last_order_name || "Aucun achat"}</strong><span>{user.last_order_at ? date(user.last_order_at) : `Inscrit ${date(user.created_at)}`}</span></div><span className="customer-card-open">Profil complet <ChevronRight size={15} /></span></footer>
            </button>;
          })}
        </div>
        {loading ? (
          <div className="table-loading">Chargement des profils…</div>
        ) : (
          !visible.length && <Empty icon={Users} title="Aucun client" text="Aucun profil ne correspond aux filtres sélectionnés." />
        )}
        <Pagination value={result} onChange={setPage} />
      </section>
      {selected && (
        <CustomerDetail
          customer={selected}
          onAction={customerAction}
          onNavigate={onNavigate}
          currency={data.currency}
          onClose={closeCustomer}
        />
      )}
      {bulkOpen && (
        <Modal
          title="Créditer tous les portefeuilles"
          onClose={() => setBulkOpen(false)}
        >
          <div className="warning-box">
            Cette action crédite chaque utilisateur actif. Elle est idempotente
            grâce à un identifiant d’opération unique.
          </div>
          <div className="form-grid">
            <Field label={`Montant (${data.currency})`}>
              <input
                type="number"
                step="0.01"
                value={bulkAmount}
                onChange={(event) => setBulkAmount(event.target.value)}
              />
            </Field>
            <Field label="Confirmation">
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="CREDIT ALL"
              />
            </Field>
          </div>
          <div className="dialog-actions">
            <ActionButton
              danger
              icon={CircleDollarSign}
              disabled={!bulkAmount || confirmation !== "CREDIT ALL"}
              onClick={async () => {
                if (
                  await onAction({
                    action: "bulk_credit_wallets",
                    amount: bulkAmount,
                    confirmation,
                    operation_id: `react-${Date.now()}`,
                  })
                )
                  setBulkOpen(false);
              }}
            >
              Créditer tous
            </ActionButton>
          </div>
        </Modal>
      )}
    </>
  );
}
