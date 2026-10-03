import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Check,
  ChevronDown,
  Copy,
  FileDown,
  Bell,
  Headphones,
  Heart,
  KeyRound,
  LogOut,
  Package,
  PackageSearch,
  RotateCcw,
  ShieldCheck,
  UserRound,
  Wallet as WalletIcon,
} from "lucide-react";
import { noteFavorite } from "@/components/FavoriteButton";
import { MethodPicker, PaymentInstructions, ReceiptField } from "@/components/PaymentFields";
import { useAuth } from "@/hooks/useAuth";
import { assetUrl, createDeposit, downloadInvoice, errorMessage, fetchFavorites, fetchNotifications, fetchMyReviews, fetchOrders, fetchProductRequests, fetchTickets, fetchWarranties, markAllNotificationsRead, markNotificationRead, openProductRequest, openTicket, openWarranty, replyToTicket, fetchWallet, requestStockAlert, resendVerificationCode, setFavorite, submitReview } from "@/lib/api";
import { accessLabel, clampQuantity, dateTime, displayPhone, isValidPhone, money, normalizePhoneInput, periodLabel, plural } from "@/lib/format";
import { accountPath } from "@/lib/accountPath";
import { Link, navigate, ROUTES, withNext } from "@/lib/router";
import { MIN_PASSWORD_LENGTH, PasswordField } from "@/pages/AuthLayout";
import { verifyEmailPath } from "@/pages/VerifyEmailPage";
import type { AccountOrder, AccountOrderItem, AccountOrders, AccountReview, AccountTicket, AccountWarranty, CartStatus, Deposit, Favorite, Offer, SiteNotification, Wallet } from "@/types";

export { accountPath };

const TABS = [
  { id: "commandes", label: "Mes achats", short: "Achats", icon: Package },
  { id: "favoris", label: "Favoris", short: "Favoris", icon: Heart },
  { id: "notifications", label: "Notifications", short: "Notifs", icon: Bell },
  { id: "portefeuille", label: "Portefeuille", short: "Solde", icon: WalletIcon },
  { id: "support", label: "Support", short: "Support", icon: Headphones },
  { id: "garanties", label: "Garanties", short: "Garanties", icon: ShieldCheck },
  { id: "demande", label: "Demande produit", short: "Demande", icon: PackageSearch },
  { id: "profil", label: "Profil & sécurité", short: "Profil", icon: UserRound },
] as const;

type Tab = (typeof TABS)[number]["id"];


function initialTab(): Tab {
  const requested = new URLSearchParams(window.location.search).get("onglet");
  return TABS.find((tab) => tab.id === requested)?.id ?? "commandes";
}

const CART_STATUS: Record<CartStatus, [string, string]> = {
  to_verify: ["Reçu en vérification", "pending"],
  confirmed: ["Paiement confirmé", "progress"],
  partial: ["Livraison partielle", "progress"],
  delivered: ["Livrée", "done"],
  cancelled: ["Annulée", "failed"],
  mixed: ["En cours", "progress"],
};

const LINE_STATUS: Record<string, [string, string]> = {
  to_verify: ["En vérification", "pending"],
  confirmed: ["En préparation", "progress"],
  delivered: ["Livré", "done"],
  cancelled: ["Annulé", "failed"],
};

const DEPOSIT_STATUS: Record<Deposit["status"], [string, string]> = {
  pending: ["En vérification", "pending"],
  approved: ["Créditée", "done"],
  rejected: ["Refusée", "failed"],
};

function StatusChip({ label, tone }: { label: string; tone: string }) {
  return <span className={`status-chip status-${tone}`}>{label}</span>;
}

function AccountSkeleton({ label }: { label: string }) {
  return (
    <div className="account-skeleton" role="status" aria-label={label}>
      <span className="account-skeleton-row" />
      <span className="account-skeleton-row" />
    </div>
  );
}

type AccountRenewal = {
  offers: Offer[];
  catalogLoading: boolean;
  catalogError: string;
  reloadCatalog: () => void;
  maxLines: number;
  place: (offer: Offer, quantity: number) => boolean;
};

export function AccountPage({ offers, catalogLoading, catalogError, reloadCatalog, maxLines, place }: AccountRenewal) {
  const { customer, loading, logout } = useAuth();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [panelFrom, setPanelFrom] = useState("0px");
  const tabsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && !customer) navigate(withNext(ROUTES.login, accountPath(tab)), { replace: true });
  }, [loading, customer, tab]);

  useLayoutEffect(() => {
    const list = tabsRef.current;
    if (!list) return;
    const markOverflow = () => {
      const max = list.scrollWidth - list.clientWidth;
      list.toggleAttribute("data-overflow-start", list.scrollLeft > 4);
      list.toggleAttribute("data-overflow-end", max - list.scrollLeft > 4);
    };
    const place = () => {
      const active = list.querySelector<HTMLButtonElement>('[aria-selected="true"]');
      if (!active) return;
      list.style.setProperty("--pill-x", `${active.offsetLeft}px`);
      list.style.setProperty("--pill-w", `${active.offsetWidth}px`);
      const nextTab = active.nextElementSibling;
      const tail = nextTab instanceof HTMLElement ? nextTab.offsetWidth + 8 : 12;
      const start = active.offsetLeft;
      const end = start + active.offsetWidth;
      const view = list.clientWidth;
      const max = Math.max(0, list.scrollWidth - view);
      let left = list.scrollLeft;
      if (end + tail > left + view) left = end + tail - view;
      if (start - 12 < left) left = Math.max(0, start - 12);
      left = Math.min(max, Math.max(0, left));
      const first = list.dataset.pill !== "ready";
      list.dataset.pill = "ready";
      if (Math.abs(left - list.scrollLeft) > 2) {
        list.scrollTo({ left, behavior: first ? "auto" : "smooth" });
      }
      markOverflow();
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(list);
    for (const button of list.querySelectorAll("button")) observer.observe(button);
    list.addEventListener("scroll", markOverflow, { passive: true });
    return () => {
      observer.disconnect();
      list.removeEventListener("scroll", markOverflow);
    };
  }, [tab, customer]);

  function select(next: Tab) {
    if (next === tab) return;
    const current = TABS.findIndex((item) => item.id === tab);
    const target = TABS.findIndex((item) => item.id === next);
    setPanelFrom(target > current ? "8px" : "-8px");
    setTab(next);
    window.history.replaceState(null, "", accountPath(next));
  }

  if (!customer) {
    return (
      <section className="account-page">
        <p className="account-loading">Chargement de ton espace…</p>
      </section>
    );
  }

  return (
    <section className="account-page" aria-labelledby="account-title">
      <header className="account-head">
        <div>
          <span className="kicker">Mon espace</span>
          <h1 id="account-title">Bonjour {customer.name.split(" ")[0]}</h1>
          <p>{customer.email}</p>
        </div>
        <button type="button" className="button button-ghost" onClick={() => void logout().then(() => navigate(ROUTES.home))}>
          <LogOut size={16} aria-hidden="true" /> Se déconnecter
        </button>
      </header>

      <div className="account-tabs" role="tablist" aria-label="Sections du compte" ref={tabsRef}>
        <span className="account-tab-pill" aria-hidden="true" />
        {TABS.map(({ id, label, short, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`account-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="account-panel"
            aria-label={label}
            className={tab === id ? "active" : ""}
            onClick={() => select(id)}
          >
            <Icon size={16} aria-hidden="true" />
            <span className="account-tab-long">{label}</span>
            <span className="account-tab-short">{short}</span>
          </button>
        ))}
      </div>

      <div
        id="account-panel"
        role="tabpanel"
        aria-labelledby={`account-tab-${tab}`}
        className="account-panel"
        style={{ "--panel-from": panelFrom } as CSSProperties}
        key={tab}
      >
        {tab === "commandes" ? (
          <OrdersTab
            offers={offers}
            catalogLoading={catalogLoading}
            catalogError={catalogError}
            reloadCatalog={reloadCatalog}
            maxLines={maxLines}
            place={place}
          />
        ) : tab === "favoris" ? (
          <FavoritesTab />
        ) : tab === "notifications" ? (
          <NotificationsTab />
        ) : tab === "portefeuille" ? (
          <WalletTab />
        ) : tab === "support" ? (
          <RequestsTab kind="support" />
        ) : tab === "garanties" ? (
          <WarrantiesTab />
        ) : tab === "demande" ? (
          <RequestsTab kind="product" />
        ) : (
          <ProfileTab />
        )}
      </div>
    </section>
  );
}

/* ---------- Purchases ---------- */

function NotificationsTab() {
  const { token } = useAuth();
  const [items, setItems] = useState<SiteNotification[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return undefined;
    const controller = new AbortController();
    fetchNotifications(token, controller.signal)
      .then((result) => setItems(result.items))
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason, "Impossible de charger tes notifications."));
        setItems([]);
      });
    return () => controller.abort();
  }, [token]);

  async function openItem(item: SiteNotification) {
    if (!token) return;
    setError("");
    try {
      if (!item.read) {
        const result = await markNotificationRead(token, item.id);
        setItems(result.items);
      }
      if (item.href) navigate(item.href);
    } catch (reason) {
      setError(errorMessage(reason, "La notification n'a pas pu être ouverte."));
    }
  }

  async function markAll() {
    if (!token || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await markAllNotificationsRead(token);
      setItems(result.items);
    } catch (reason) {
      setError(errorMessage(reason, "Les notifications n'ont pas pu être marquées comme lues."));
    } finally {
      setBusy(false);
    }
  }

  if (!items) return <AccountSkeleton label="Chargement des notifications" />;
  const unread = items.some((item) => !item.read);

  return (
    <div className="favorites-tab">
      <header className="account-section-head">
        <h2>Notifications</h2>
        <p>Nouveautés, messages du shop et actualités.</p>
        {unread ? (
          <button type="button" className="button button-ghost" onClick={() => void markAll()} disabled={busy}>
            {busy ? "En cours…" : "Tout marquer comme lu"}
          </button>
        ) : null}
      </header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {!items.length ? (
        <div className="account-empty">
          <Bell size={28} aria-hidden="true" />
          <h3>Aucune notification pour le moment.</h3>
        </div>
      ) : (
        <ul className="notice-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={item.read ? "notice-row" : "notice-row is-new"}
                onClick={() => void openItem(item)}
              >
                <small>{item.kind_label} · {dateTime(item.created_at)}</small>
                <strong>{item.title}</strong>
                <span>{item.body}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FavoritesTab() {
  const { token } = useAuth();
  const [favorites, setFavorites] = useState<Favorite[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(0);

  useEffect(() => {
    if (!token) return undefined;
    const controller = new AbortController();
    fetchFavorites(token, controller.signal)
      .then((result) => setFavorites(result.favorites))
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason, "Impossible de charger tes favoris."));
        setFavorites([]);
      });
    return () => controller.abort();
  }, [token]);

  async function remove(offerId: number) {
    if (!token || busyId) return;
    setBusyId(offerId);
    setError("");
    try {
      await setFavorite(token, offerId, false);
      noteFavorite(token, offerId, false);
      setFavorites((current) => (current || []).filter((item) => item.offer_id !== offerId));
    } catch (reason) {
      setError(errorMessage(reason, "Le favori n'a pas pu être retiré."));
    } finally {
      setBusyId(0);
    }
  }

  if (!favorites) return <AccountSkeleton label="Chargement des favoris" />;

  return (
    <div className="favorites-tab">
      <header className="account-section-head">
        <h2>Favoris</h2>
        <p>Les produits que tu gardes de côté. Aucun email n'est envoyé.</p>
      </header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {!favorites.length ? (
        <div className="account-empty">
          <Heart size={28} aria-hidden="true" />
          <h3>Aucun favori pour le moment.</h3>
          <p>Ouvre un produit et choisis « Ajouter aux favoris ».</p>
          <Link className="button button-primary" to={ROUTES.shop}>Voir la boutique</Link>
        </div>
      ) : (
        <ul className="favorite-list">
          {favorites.map((item) => {
            const picture = item.image_url || item.service_logo_url;
            return (
              <li key={item.offer_id} className="favorite-card">
                <span className="favorite-mark">
                  {picture ? <img src={assetUrl(picture)} alt="" /> : <Heart size={18} aria-hidden="true" />}
                </span>
                <div>
                  <small>{item.service_name}</small>
                  <strong>{item.name}</strong>
                  <p>
                    {money(item.price_millimes)}
                    {item.in_catalog ? ` · ${item.available ? (item.stock < 0 ? "Illimité" : `${item.stock} en stock`) : "Indisponible"}` : " · Plus au catalogue"}
                  </p>
                </div>
                <div className="favorite-actions">
                  {item.in_catalog ? <Link to={`/produit/${item.offer_id}`}>Voir</Link> : null}
                  <button type="button" onClick={() => void remove(item.offer_id)} disabled={busyId === item.offer_id}>
                    {busyId === item.offer_id ? "Retrait…" : "Retirer"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function OrdersTab({ offers, catalogLoading, catalogError, reloadCatalog, maxLines, place }: AccountRenewal) {
  const { customer, token, handleError } = useAuth();
  const [data, setData] = useState<AccountOrders | null>(null);
  const [reviews, setReviews] = useState<AccountReview[] | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetchOrders(token, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        handleError(reason);
        setError(errorMessage(reason, "Impossible de charger tes achats."));
      });
    fetchMyReviews(token, controller.signal)
      .then((result) => setReviews(result.reviews))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setReviewError(errorMessage(reason, "Impossible de charger tes avis."));
        setReviews([]);
      });
    return () => controller.abort();
  }, [token, attempt, handleError]);

  async function confirmEmail() {
    if (!customer) return;
    await resendVerificationCode(customer.email).catch(() => undefined);
    navigate(verifyEmailPath(customer.email, accountPath("commandes")));
  }

  if (error) {
    return (
      <div className="account-empty">
        <p>{error}</p>
        <button type="button" className="button button-primary" onClick={() => setAttempt((value) => value + 1)}>
          <RotateCcw size={16} aria-hidden="true" /> Réessayer
        </button>
      </div>
    );
  }
  if (!data) return <AccountSkeleton label="Chargement de tes achats" />;

  return (
    <div className="account-section">
      {!data.email_confirmed ? (
        <p className="manual-warning">
          <BadgeCheck size={18} aria-hidden="true" />
          <span>
            <strong>Confirme ton adresse email</strong>
            Tes commandes passées sans compte avec {customer?.email} apparaîtront ici une fois l'adresse confirmée.
            <button type="button" className="auth-inline-link" onClick={() => void confirmEmail()}>
              Recevoir un code
            </button>
          </span>
        </p>
      ) : null}

      {data.orders.length ? (
        <ul className="order-list">
          {data.orders.map((order, index) => (
            <OrderCard
              key={order.reference}
              order={order}
              defaultOpen={index === 0}
              onRefresh={() => setAttempt((value) => value + 1)}
              offers={offers}
              catalogLoading={catalogLoading}
              catalogError={catalogError}
              reloadCatalog={reloadCatalog}
              maxLines={maxLines}
              place={place}
              reviews={reviews}
              reviewError={reviewError}
              onReview={() => setAttempt((value) => value + 1)}
            />
          ))}
        </ul>
      ) : (
        <div className="account-empty">
          <Package size={32} aria-hidden="true" />
          <h3>Aucun achat pour l'instant</h3>
          <p>Tes commandes, leur statut et tes accès livrés apparaîtront ici.</p>
          <Link className="button button-primary" to="/#catalogue">
            Parcourir le catalogue <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      )}
    </div>
  );
}

const WARRANTY_STATUS: Record<string, string> = {
  pending_admin_check: "En attente",
  accepted: "Acceptée",
  replacement_pending: "Remplacement en cours",
  replacement_delivered: "Remplacement livré",
  refunded: "Remboursée",
  refused: "Refusée",
};

const WARRANTY_TONE: Record<string, string> = {
  pending_admin_check: "pending",
  accepted: "progress",
  replacement_pending: "progress",
  replacement_delivered: "done",
  refunded: "done",
  refused: "failed",
};

const TICKET_STATUS: Record<string, string> = {
  open: "Ouverte",
  waiting_admin: "En attente du support",
  waiting_customer: "Réponse du support",
  resolved: "Résolue",
  closed: "Fermée",
};

const TICKET_TONE: Record<string, string> = {
  open: "progress",
  waiting_admin: "pending",
  waiting_customer: "progress",
  resolved: "done",
  closed: "failed",
};

function when(value: string | number | null): string {
  if (typeof value === "number") return dateTime(value);
  if (typeof value !== "string" || !value) return "—";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function threadClosed(status: string): boolean {
  return status === "closed" || status === "resolved";
}

type StepState = "done" | "current" | "wait" | "failed";

const STEP_WORD: Record<StepState, string> = {
  done: "terminé",
  current: "en cours",
  wait: "à venir",
  failed: "refusé",
};

function receiptSteps(order: AccountOrder): { label: string; state: StepState }[] {
  const paid = Boolean(order.paid_at) || order.status === "confirmed" || order.status === "partial" || order.status === "delivered" || order.status === "mixed";
  const cancelled = order.status === "cancelled";
  const delivered = order.items.length > 0 && order.items.every((item) => item.status === "delivered");
  const statuses = order.items.map((item) => item.warranty_status).filter((status): status is string => Boolean(status));
  const openClaim = order.items.some((item) => item.warranty_open) || statuses.some((status) => status === "pending_admin_check" || status === "replacement_pending" || status === "accepted");
  const settled = statuses.some((status) => status === "replacement_delivered" || status === "refunded");
  const refused = statuses.some((status) => status === "refused");

  const pay: StepState = paid ? "done" : cancelled ? "failed" : "current";
  const ship: StepState = delivered ? "done" : cancelled ? (paid ? "failed" : "wait") : paid ? "current" : "wait";
  let warranty: StepState = "wait";
  if (openClaim) warranty = "current";
  else if (settled) warranty = "done";
  else if (refused) warranty = "failed";

  return [
    { label: "Payé", state: pay },
    { label: "Livré", state: ship },
    { label: "Garantie", state: warranty },
  ];
}

function OrderCard({
  order,
  defaultOpen,
  onRefresh,
  offers,
  catalogLoading,
  catalogError,
  reloadCatalog,
  maxLines,
  place,
  reviews,
  reviewError,
  onReview,
}: {
  order: AccountOrder;
  defaultOpen: boolean;
  onRefresh: () => void;
  reviews: AccountReview[] | null;
  reviewError: string;
  onReview: () => void;
} & AccountRenewal) {
  const [open, setOpen] = useState(false);
  const foldRef = useRef<HTMLDivElement>(null);
  const [label, tone] = CART_STATUS[order.status] ?? CART_STATUS.mixed;
  const count = order.items.reduce((sum, item) => sum + item.quantity, 0);
  const steps = receiptSteps(order);

  useEffect(() => {
    if (!defaultOpen) return;
    const frame = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(frame);
  }, [defaultOpen]);

  useLayoutEffect(() => {
    const fold = foldRef.current;
    if (!fold) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      fold.style.height = open ? "auto" : "0px";
      return;
    }
    const current = fold.getBoundingClientRect().height;
    let frame = 0;
    let timer = 0;
    if (open) {
      const target = Math.max(fold.scrollHeight, current);
      fold.style.height = `${current}px`;
      frame = requestAnimationFrame(() => {
        if (foldRef.current) foldRef.current.style.height = `${target}px`;
      });
      timer = window.setTimeout(() => {
        if (foldRef.current) foldRef.current.style.height = "auto";
      }, 360);
    } else {
      fold.style.height = `${current}px`;
      frame = requestAnimationFrame(() => {
        if (foldRef.current) foldRef.current.style.height = "0px";
      });
    }
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [open]);

  return (
    <li className={`order-card${open ? " open" : ""}`}>
      <button type="button" className="order-summary" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="order-main">
          <strong>{order.reference}</strong>
          <small>
            {dateTime(order.created_at)} · {count} {plural(count, "article", "articles")} · {order.payment_label}
          </small>
        </span>
        <StatusChip label={label} tone={tone} />
        <b>{money(order.total_millimes)}</b>
        <ChevronDown size={18} aria-hidden="true" className="order-chevron" />
      </button>

      <div className="order-fold" ref={foldRef} inert={!open}>
        <div className="order-details">
          <ol className="order-steps" aria-label="Suivi de la commande">
            {steps.map((step) => (
              <li key={step.label} className={`is-${step.state}`}>
                <span className="step-dot" aria-hidden="true" />
                <span>{step.label}</span>
                <span className="account-live">{STEP_WORD[step.state]}</span>
              </li>
            ))}
          </ol>
          <ul className="order-items">
            {order.items.map((item) => {
              const [itemLabel, itemTone] = LINE_STATUS[item.status] ?? LINE_STATUS.to_verify;
              const period = periodLabel(item.period_days);
              return (
                <li key={item.id}>
                  <div className="order-item-head">
                    <span>
                      <strong>
                        {item.quantity} × {item.offer_name}
                      </strong>
                      <small>
                        {item.service_name}
                        {period ? ` · ${period}` : ""} · {money(item.total_millimes)}
                      </small>
                      {item.site_remark ? <small className="account-muted">Remarque : {item.site_remark}</small> : null}
                      {item.customer_info ? <small className="account-muted">Tes informations : {item.customer_info}</small> : null}
                    </span>
                    <StatusChip label={itemLabel} tone={itemTone} />
                  </div>
                  <RenewalRow
                    item={item}
                    offers={offers}
                    catalogLoading={catalogLoading}
                    catalogError={catalogError}
                    reloadCatalog={reloadCatalog}
                    maxLines={maxLines}
                    place={place}
                  />
                  {item.status === "delivered" ? (
                    <ReviewBox
                      orderId={item.id}
                      review={reviews?.find((entry) => entry.order_id === item.id) ?? null}
                      loading={reviews === null}
                      loadError={reviewError}
                      onSent={onReview}
                    />
                  ) : null}
                  {item.delivery ? <DeliveryBox content={item.delivery} deliveredAt={item.delivered_at} /> : null}
                  {item.replacement ? <DeliveryBox content={item.replacement} deliveredAt={null} heading="Remplacement sous garantie" /> : null}
                  {item.warranty_open ? <WarrantyButton item={item} onSent={onRefresh} /> : null}
                  {item.warranty_status ? <small className="account-muted">Garantie : {WARRANTY_STATUS[item.warranty_status] || item.warranty_status}</small> : null}
                  {item.warranty_status === "refused" && item.warranty_note ? <small className="account-muted">Motif du refus : {item.warranty_note}</small> : null}
                </li>
              );
            })}
          </ul>
          <dl className="order-meta">
            <div>
              <dt>Paiement</dt>
              <dd>
                {order.payment_label}
                {order.transaction_reference ? ` · réf. ${order.transaction_reference}` : ""}
              </dd>
            </div>
            {order.paid_at ? (
              <div>
                <dt>Payé le</dt>
                <dd>{dateTime(order.paid_at)}</dd>
              </div>
            ) : null}
            {order.cancel_reason ? (
              <div>
                <dt>Motif d'annulation</dt>
                <dd>{order.cancel_reason}</dd>
              </div>
            ) : null}
            {order.refunded_millimes ? (
              <div>
                <dt>Remboursé</dt>
                <dd>{money(order.refunded_millimes)} sur ton portefeuille</dd>
              </div>
            ) : null}
          </dl>
          {order.invoice_number ? <InvoiceButton reference={order.reference} number={order.invoice_number} /> : null}
        </div>
      </div>
    </li>
  );
}

function ReviewBox({
  orderId,
  review,
  loading,
  loadError,
  onSent,
}: {
  orderId: number;
  review: AccountReview | null;
  loading: boolean;
  loadError: string;
  onSent: () => void;
}) {
  const { token, handleError } = useAuth();
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || busy) return;
    if (score < 1) {
      setError("Choisis une note de 1 à 5.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await submitReview(token, { order_id: orderId, score, comment: comment.trim() });
      onSent();
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "L'avis n'a pas pu être envoyé."));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="review-wait">Chargement de l'avis…</p>;
  if (loadError && !review) return <p className="form-error">{loadError}</p>;
  if (review?.status === "pending") return <p className="review-wait">En attente de publication</p>;
  if (review?.status === "approved") {
    return (
      <p className="review-published">
        <ReviewStars value={review.score} /> {review.comment}
      </p>
    );
  }
  if (review?.status === "rejected") return <p className="review-wait">Non publié</p>;

  return (
    <form className="review-form" onSubmit={(event) => void submit(event)}>
      <span className="review-label">Noter ce service</span>
      <span className="review-stars" role="radiogroup" aria-label="Note de 1 à 5">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            className={value <= score ? "review-star is-on" : "review-star"}
            role="radio"
            aria-checked={score === value}
            aria-label={`${value} sur 5`}
            onClick={() => setScore(value)}
          >
            ★
          </button>
        ))}
      </span>
      <textarea
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        minLength={8}
        maxLength={600}
        rows={3}
        required
        placeholder="Ton commentaire"
      />
      {error ? <small className="form-error">{error}</small> : null}
      <button type="submit" className="button button-primary" disabled={busy}>
        {busy ? "Envoi…" : "Envoyer l'avis"}
      </button>
    </form>
  );
}

function ReviewStars({ value }: { value: number }) {
  return (
    <span className="review-stars" aria-label={`${value} sur 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <span key={star} className={star <= value ? "review-star is-on" : "review-star"} aria-hidden="true">
          ★
        </span>
      ))}
    </span>
  );
}

function RenewalRow({ item, offers, catalogLoading, catalogError, reloadCatalog, maxLines, place }: { item: AccountOrderItem } & AccountRenewal) {
  const [full, setFull] = useState(false);
  const offer = item.offer_id == null ? undefined : offers.find((entry) => entry.id === item.offer_id);
  const label = accessLabel(item.delivered_at, item.period_days);
  if (item.status !== "delivered" || item.offer_id == null) return null;

  function renew(target: Offer) {
    if (clampQuantity(target, item.quantity) <= 0) return;
    setFull(!place(target, item.quantity));
  }

  return (
    <div className="renew-row">
      {label ? <p className="access-date">{label}</p> : null}
      {catalogLoading ? (
        <button type="button" className="button button-primary renew-button" disabled>
          Chargement du catalogue…
        </button>
      ) : catalogError ? (
        <div className="renew-catalog-error renew-missing" role="alert">
          <span>Le catalogue est momentanément indisponible.</span>
          <button type="button" className="button button-ghost" onClick={reloadCatalog}>
            Réessayer
          </button>
        </div>
      ) : !offer ? (
        <p className="renew-missing">
          Plus au catalogue
          <Link to={ROUTES.shop}>Voir la boutique</Link>
        </p>
      ) : !offer.available ? (
        <RenewAlert offerId={offer.id} />
      ) : (
        <>
          <button type="button" className="button button-primary renew-button" onClick={() => renew(offer)}>
            Renouveler · {money(offer.price_millimes)}
          </button>
          {full ? (
            <p className="renew-full" role="alert">
              Ton panier est plein ({maxLines} {plural(maxLines, "produit", "produits")}). Retire une ligne pour renouveler celle-ci.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

function RenewAlert({ offerId }: { offerId: number }) {
  const { customer, token } = useAuth();
  const [email, setEmail] = useState(customer?.email ?? "");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await requestStockAlert(offerId, email.trim(), token || undefined);
      setDone(true);
    } catch (reason) {
      setError(errorMessage(reason, "Alerte impossible"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="renew-alert">
      <span className="renew-soldout">Épuisé</span>
      {done ? (
        <p className="renew-noted" role="status">
          C'est noté
        </p>
      ) : (
        <form onSubmit={(event) => void submit(event)}>
          <input
            required
            type="email"
            autoComplete="email"
            inputMode="email"
            aria-label="Email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "Enregistrement…" : "Me prévenir"}
          </button>
        </form>
      )}
      {error ? <small className="form-error">{error}</small> : null}
    </div>
  );
}

function InvoiceButton({ reference, number }: { reference: string; number: string }) {
  const { token, handleError } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function download() {
    setBusy(true);
    setError("");
    try {
      await downloadInvoice(token, reference, number);
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Facture indisponible pour le moment."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="order-invoice">
      <button type="button" className="button button-ghost" onClick={() => void download()} disabled={busy}>
        <FileDown size={16} aria-hidden="true" />
        {busy ? "Téléchargement…" : `Télécharger la facture ${number}`}
      </button>
      {error ? <small className="form-error">{error}</small> : null}
    </div>
  );
}

function deliveryFields(content: string) {
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  const fields = lines.map((line) => {
    const split = line.indexOf(" : ");
    if (split <= 0 || split > 80) return null;
    const label = line.slice(0, split).trim();
    const value = line.slice(split + 3).trim();
    return label && value ? { label, value } : null;
  });
  return fields.length && fields.every((field) => field) ? fields as { label: string; value: string }[] : null;
}

function DeliveryBox({ content, deliveredAt, heading }: { content: string; deliveredAt: number | null; heading?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const fields = deliveryFields(content);
  return (
    <div className="delivery-box">
      <div className="delivery-head">
        <span>{heading || `Tes accès · livrés le ${dateTime(deliveredAt)}`}</span>
        <button
          type="button"
          className={copied ? "icon-button is-copied" : "icon-button"}
          aria-label={copied ? "Accès copiés" : "Copier les accès"}
          onClick={() => void copy()}
        >
          {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
        </button>
      </div>
      {fields ? <dl className="delivery-fields">{fields.map((field, index) => <div key={`${field.label}-${index}`}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl> : <pre>{content}</pre>}
      <span className="account-live" aria-live="polite">{copied ? "Copié." : ""}</span>
    </div>
  );
}

/* ---------- Wallet ---------- */

function WarrantyButton({ item, onSent }: { item: AccountOrderItem; onSent: () => void }) {
  const { token, handleError } = useAuth();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [proofs] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await openWarranty(token, { order_id: item.id, reason, proofs });
      setOpen(false);
      onSent();
    } catch (reasonError) {
      handleError(reasonError);
      setError(errorMessage(reasonError, "La demande n'a pas pu être envoyée."));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
        <ShieldCheck size={16} aria-hidden="true" /> Demander la garantie
      </button>
    );
  }
  const length = reason.trim().length;
  return (
    <form className="warranty-form" onSubmit={(event) => void submit(event)}>
      <label>
        <span>Problème rencontré</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          minLength={8}
          maxLength={1000}
          rows={4}
          required
          autoFocus
          placeholder="Ex. Le mot de passe ne fonctionne plus, le compte est déjà utilisé…"
        />
        <small>{length < 8 ? "Décris le problème en au moins 8 caractères." : `${length} / 1000`}</small>
      </label>
      {error ? <small className="form-error">{error}</small> : null}
      <div className="warranty-form-actions">
        <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>Annuler</button>
        <button type="submit" className="button button-primary" disabled={busy || length < 8}>{busy ? "Envoi…" : "Envoyer"}</button>
      </div>
    </form>
  );
}

function WarrantiesTab() {
  const { token, handleError } = useAuth();
  const [claims, setClaims] = useState<AccountWarranty[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchWarranties(token, controller.signal)
      .then((result) => setClaims(result.warranties))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        handleError(reason);
        setError(errorMessage(reason, "Impossible de charger tes garanties."));
      });
    return () => controller.abort();
  }, [token, handleError]);

  if (error && !claims) return <p className="form-error">{error}</p>;
  if (!claims) return <AccountSkeleton label="Chargement des garanties" />;
  if (!claims.length) {
    return <p className="account-muted">Aucune demande de garantie pour le moment. Tu peux en ouvrir une depuis une commande livrée.</p>;
  }

  return (
    <ul className="order-list">
      {claims.map((claim) => (
        <li key={claim.id} className="account-card">
          <div className="ticket-card-head">
            <strong>{claim.offer_name || `Commande #${claim.order_id}`}</strong>
            <StatusChip label={WARRANTY_STATUS[claim.status] || claim.status} tone={WARRANTY_TONE[claim.status] || "pending"} />
          </div>
          <small className="account-muted">
            Garantie #{claim.id} · Commande #{claim.order_id} · {when(claim.created_at)}
          </small>
          <p>{claim.reason}</p>
          {claim.admin_note ? (
            <p className="warranty-note">
              <small>{claim.status === "refused" ? "Motif du refus" : "Message du support"}</small>
              <span>{claim.admin_note}</span>
            </p>
          ) : null}
          {claim.refund_millimes > 0 && claim.status !== "refused" && claim.status !== "replacement_delivered" ? (
            <small className="account-muted">
              {claim.status === "refunded" ? "Remboursé" : "Remboursement estimé"} : {money(claim.refund_millimes)}
            </small>
          ) : null}
          {claim.replacement ? <DeliveryBox content={claim.replacement} deliveredAt={null} heading="Remplacement sous garantie" /> : null}
        </li>
      ))}
    </ul>
  );
}

function TicketReply({ ticketId, onSent }: { ticketId: number; onSent: () => void }) {
  const { token, handleError } = useAuth();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await replyToTicket(token, { ticket_id: ticketId, message });
      setMessage("");
      onSent();
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "La réponse n'a pas pu être envoyée."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="ticket-reply" onSubmit={(event) => void submit(event)}>
      <label>
        <span>Ta réponse</span>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} minLength={1} maxLength={2000} rows={3} required placeholder="Écris ta réponse…" />
      </label>
      {error ? <small className="form-error">{error}</small> : null}
      <button type="submit" className="button button-primary" disabled={busy}>{busy ? "Envoi…" : "Répondre"}</button>
    </form>
  );
}

function RequestsTab({ kind }: { kind: "support" | "product" }) {
  const { token, handleError } = useAuth();
  const [tickets, setTickets] = useState<AccountTicket[] | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState("order");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const product = kind === "product";

  useEffect(() => {
    const controller = new AbortController();
    const load = product ? fetchProductRequests(token, controller.signal) : fetchTickets(token, controller.signal);
    load.then((result) => setTickets(result.tickets)).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      handleError(reason);
      setError(errorMessage(reason, "Impossible de charger tes demandes."));
    });
    return () => controller.abort();
  }, [token, attempt, product, handleError]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (product) await openProductRequest(token, message);
      else await openTicket(token, { message, category });
      setMessage("");
      setAttempt((value) => value + 1);
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "La demande n'a pas pu être envoyée."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="account-section">
      <form className="account-card account-form" onSubmit={(event) => void submit(event)}>
        <h2>{product ? "Demander un produit" : "Écrire au support"}</h2>
        <p className="account-muted">{product ? "Dis-nous quel service il te manque. La demande reste sur le site." : "La réponse apparaîtra ici, dans ton compte."}</p>
        {!product ? (
          <label>
            <span>Sujet</span>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="order">Commande</option>
              <option value="payment">Paiement</option>
              <option value="delivery">Livraison</option>
              <option value="other">Autre</option>
            </select>
          </label>
        ) : null}
        <label>
          <span>Message</span>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            minLength={8}
            maxLength={2000}
            rows={4}
            required
            placeholder={product ? "Netflix, ChatGPT, un jeu, un abonnement…" : "Décris le problème…"}
          />
        </label>
        {error ? <small className="form-error">{error}</small> : null}
        <button type="submit" className="button button-primary" disabled={busy}>{busy ? "Envoi…" : "Envoyer"}</button>
      </form>
      {!tickets ? <AccountSkeleton label="Chargement des demandes" /> : tickets.length ? (
        <ul className="order-list">
          {tickets.map((ticket) => (
            <li key={ticket.id} className="account-card">
              <div className="ticket-card-head">
                <strong>Demande #{ticket.id}</strong>
                <StatusChip label={TICKET_STATUS[ticket.status] || ticket.status} tone={TICKET_TONE[ticket.status] || "pending"} />
              </div>
              <ul className="ticket-thread">
                {ticket.messages.map((entry) => (
                  <li key={entry.id} className={entry.sender === "admin" ? "from-admin" : ""}>
                    <small>{entry.sender === "admin" ? "Support" : "Toi"}</small>
                    <p>{entry.content}</p>
                  </li>
                ))}
              </ul>
              {threadClosed(ticket.status) ? (
                <small className="account-muted">Cette conversation est fermée.</small>
              ) : (
                <TicketReply ticketId={ticket.id} onSent={() => setAttempt((value) => value + 1)} />
              )}
            </li>
          ))}
        </ul>
      ) : <p className="account-muted">Aucune demande pour le moment.</p>}
    </div>
  );
}

function WalletTab() {
  const { token, handleError } = useAuth();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchWallet(token, signal)
        .then(setWallet)
        .catch((reason: unknown) => {
          if (signal?.aborted) return;
          handleError(reason);
          setError(errorMessage(reason, "Impossible de charger ton portefeuille."));
        }),
    [token, handleError],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (error && !wallet) return <p className="form-error">{error}</p>;
  if (!wallet) return <AccountSkeleton label="Chargement du portefeuille" />;

  const pending = wallet.deposits.filter((deposit) => deposit.status === "pending");
  return (
    <div className="account-section wallet-layout">
      <div className="wallet-balance">
        <span>Solde disponible</span>
        <strong>{money(wallet.balance_millimes)}</strong>
        <small>
          {pending.length
            ? `${pending.length} recharge${pending.length > 1 ? "s" : ""} en vérification`
            : "Paie tes commandes en un clic, livraison immédiate quand le produit est en stock."}
        </small>
      </div>

      <DepositForm wallet={wallet} onCreated={() => void load()} />

      <section className="account-card">
        <h2>Mes recharges</h2>
        {wallet.deposits.length ? (
          <ul className="ledger">
            {wallet.deposits.map((deposit) => {
              const [label, tone] = DEPOSIT_STATUS[deposit.status];
              return (
                <li key={deposit.id}>
                  <span>
                    <strong>
                      {money(deposit.status === "approved" ? deposit.credited_millimes : deposit.amount_millimes)} ·{" "}
                      {deposit.method_label}
                    </strong>
                    <small>
                      Réf. {deposit.transaction_reference} · {dateTime(deposit.created_at)}
                      {deposit.reason ? ` · ${deposit.reason}` : ""}
                    </small>
                  </span>
                  <StatusChip label={label} tone={tone} />
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="account-muted">Aucune recharge pour l'instant.</p>
        )}
      </section>

      <section className="account-card">
        <h2>Historique du solde</h2>
        {wallet.transactions.length ? (
          <ul className="ledger">
            {wallet.transactions.map((row) => (
              <li key={row.id}>
                <span>
                  <strong>
                    {row.label}
                    {row.reference ? ` · ${row.reference}` : ""}
                  </strong>
                  <small>
                    {dateTime(row.created_at)}
                    {row.note ? ` · ${row.note}` : ""}
                  </small>
                </span>
                <b className={row.amount_millimes < 0 ? "amount-out" : "amount-in"}>
                  {row.amount_millimes > 0 ? "+" : "−"}
                  {money(Math.abs(row.amount_millimes))}
                </b>
              </li>
            ))}
          </ul>
        ) : (
          <p className="account-muted">Les recharges, achats et remboursements apparaîtront ici.</p>
        )}
      </section>
    </div>
  );
}

function DepositForm({ wallet, onCreated }: { wallet: Wallet; onCreated: () => void }) {
  const { token, handleError } = useAuth();
  const methods = wallet.payment_methods;
  const [method, setMethod] = useState(methods[0]?.id ?? "");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [receipt, setReceipt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const chosen = methods.find((option) => option.id === method) ?? methods[0];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const value = Number(amount.replace(",", "."));
    if (!value || value * 1000 < wallet.min_deposit_millimes || value * 1000 > wallet.max_deposit_millimes) {
      setError(
        `Le montant doit être compris entre ${money(wallet.min_deposit_millimes)} et ${money(wallet.max_deposit_millimes)}.`,
      );
      return;
    }
    if (reference.trim().length < 3) {
      setError("Saisis la référence de la transaction indiquée sur ton reçu.");
      return;
    }
    if (!receipt) {
      setError("Ajoute une capture de ton reçu.");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await createDeposit(token, {
        method: chosen?.id ?? "",
        amount: amount.trim(),
        transaction_reference: reference.trim(),
        receipt,
      });
      setAmount("");
      setReference("");
      setReceipt("");
      setNotice("Demande envoyée. Ton solde sera crédité dès que l'administrateur aura vérifié le reçu.");
      onCreated();
    } catch (reason) {
      handleError(reason);
      setError(errorMessage(reason, "Impossible d'envoyer la recharge."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!methods.length) {
    return (
      <section className="account-card">
        <h2>Recharger</h2>
        <p className="account-muted">Les recharges sont momentanément indisponibles.</p>
      </section>
    );
  }

  return (
    <section className="account-card">
      <h2>Recharger mon portefeuille</h2>
      <form className="checkout-form account-form" onSubmit={onSubmit} noValidate>
        <MethodPicker methods={methods} value={chosen?.id ?? ""} onChange={setMethod} name="deposit_method" />
        <PaymentInstructions method={chosen} />
        <label>
          Montant envoyé (DT)
          <input
            required
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
            placeholder="Ex. 50"
          />
        </label>
        <label>
          Référence de la transaction
          <input
            required
            value={reference}
            maxLength={64}
            onChange={(event) => setReference(event.target.value)}
            placeholder="Ex. 123456789"
          />
        </label>
        <ReceiptField value={receipt} onChange={setReceipt} onError={setError} />
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="form-success" role="status">
            {notice}
          </p>
        ) : null}
        <button type="submit" className="button button-primary button-block" disabled={submitting}>
          {submitting ? "Envoi…" : "Envoyer la demande de recharge"}
        </button>
      </form>
    </section>
  );
}

/* ---------- Profile ---------- */

function ProfileTab() {
  const { customer, updateProfile, changePassword } = useAuth();
  const [name, setName] = useState(customer?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<[string, boolean] | null>(null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<[string, boolean] | null>(null);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (name.trim().length < 2) {
      setProfileMessage(["Saisis ton nom complet.", false]);
      return;
    }
    if (phone && !isValidPhone(phone)) {
      setProfileMessage(["Saisis un numéro tunisien valide à 8 chiffres.", false]);
      return;
    }
    setSavingProfile(true);
    try {
      await updateProfile(name.trim(), normalizePhoneInput(phone));
      setProfileMessage(["Profil enregistré.", true]);
    } catch (reason) {
      setProfileMessage([errorMessage(reason, "Impossible d'enregistrer le profil."), false]);
    } finally {
      setSavingProfile(false);
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (next.length < MIN_PASSWORD_LENGTH) {
      setPasswordMessage([`Le nouveau mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`, false]);
      return;
    }
    setSavingPassword(true);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setPasswordMessage(["Mot de passe modifié. Tes autres appareils ont été déconnectés.", true]);
    } catch (reason) {
      setPasswordMessage([errorMessage(reason, "Impossible de modifier le mot de passe."), false]);
    } finally {
      setSavingPassword(false);
    }
  }

  if (!customer) return null;
  return (
    <div className="account-section profile-layout">
      <section className="account-card">
        <h2>
          <UserRound size={18} aria-hidden="true" /> Mes informations
        </h2>
        <form className="auth-form" onSubmit={saveProfile} noValidate>
          <label>
            Nom complet
            <input value={name} autoComplete="name" onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Adresse email
            <input value={customer.email} disabled />
            <small>
              {customer.email_confirmed ? "Adresse confirmée." : "Adresse pas encore confirmée."} C'est là que tes
              accès sont envoyés.
            </small>
          </label>
          <label>
            Numéro de téléphone <small>(optionnel)</small>
            <span className="phone-field">
              <i>+216</i>
              <input
                inputMode="numeric"
                autoComplete="tel-national"
                value={displayPhone(phone)}
                onChange={(event) => setPhone(normalizePhoneInput(event.target.value))}
                placeholder="21 994 132"
              />
            </span>
          </label>
          {profileMessage ? (
            <p className={profileMessage[1] ? "form-success" : "form-error"} role="status">
              {profileMessage[0]}
            </p>
          ) : null}
          <button type="submit" className="button button-primary" disabled={savingProfile}>
            {savingProfile ? "Enregistrement…" : "Enregistrer"}
          </button>
        </form>
      </section>

      <section className="account-card">
        <h2>
          <KeyRound size={18} aria-hidden="true" /> {customer.has_password ? "Mot de passe" : "Créer un mot de passe"}
        </h2>
        <form className="auth-form" onSubmit={savePassword} noValidate>
          {customer.has_password ? (
            <PasswordField
              label="Mot de passe actuel"
              name="current_password"
              value={current}
              onChange={setCurrent}
              autoComplete="current-password"
            />
          ) : (
            <p className="account-hint">
              Tu te connectes avec Google. Ajoute un mot de passe si tu veux aussi te connecter avec ton email.
            </p>
          )}
          <PasswordField
            label="Nouveau mot de passe"
            name="new_password"
            value={next}
            onChange={setNext}
            autoComplete="new-password"
            hint={`${MIN_PASSWORD_LENGTH} caractères minimum.`}
          />
          {passwordMessage ? (
            <p className={passwordMessage[1] ? "form-success" : "form-error"} role="status">
              {passwordMessage[0]}
            </p>
          ) : null}
          <button type="submit" className="button button-primary" disabled={savingPassword || (customer.has_password && !current) || !next}>
            {savingPassword ? "Enregistrement…" : customer.has_password ? "Changer le mot de passe" : "Créer le mot de passe"}
          </button>
          {customer.has_password ? (
            <Link className="auth-inline-link" to={ROUTES.forgotPassword}>
              Mot de passe oublié ?
            </Link>
          ) : null}
        </form>
      </section>
    </div>
  );
}
