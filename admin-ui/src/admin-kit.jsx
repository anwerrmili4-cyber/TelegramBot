import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Database,
  Search,
  X,
} from "lucide-react";

export const STATUS_LABELS = {
  pending_payment: "Paiement en attente",
  awaiting_verification: "À vérifier",
  payment_confirmed: "Paiement confirmé",
  preparing_delivery: "Préparation",
  delivered: "Livrée",
  verification_failed: "Échec de vérification",
  manual_review: "Révision manuelle",
  cancelled: "Annulée",
  refunded: "Remboursée",
  expired: "Expirée",
  paid: "Payée",
  stock_issue: "Problème de stock",
  confirmed: "Confirmé",
  rejected: "Refusée",
  open: "Ouvert",
  waiting_admin: "Attente admin",
  waiting_customer: "Attente client",
  resolved: "Résolu",
  closed: "Fermé",
  pending: "En attente",
  approved: "Approuvé",
  completed: "Terminé",
  pending_admin_check: "Contrôle admin",
  accepted: "Acceptée",
  replacement_pending: "Remplacement requis",
  replacement_delivered: "Remplacement livré",
  refused: "Refusée",
  replacement_sent: "Remplacement envoyé",
  refund_approved: "Remboursement approuvé",
};

export const PROVIDERS = [
  ["mailreader", "MailReader"],
  ["shamekh", "Shamekh’s bot"],
  ["kakao", "Kakao Shop"],
  ["vex", "VEX Reseller"],
  ["canboso", "Piggy AI"],
  ["gpt_cheap", "GPT Cheap"],
  ["shop_cron", "Shop Cron"],
  ["upibot", "UPIBot Shop"],
  ["toolorax", "ToolOraX Store Bot"],
  ["cgpt_active", "Rich AI Store"],
  ["safwantiger", "Safwan Tiger"],
];

export const PROVIDER_LABELS = Object.fromEntries(PROVIDERS);
export const SERVICE_COLORS = ["#a78bfa", "#22d3ee", "#34d399", "#f59e0b", "#fb7185", "#60a5fa"];

export const BINANCE_STATUS_LABELS = {
  completed: "Terminée",
  pending: "En attente",
  credited_locked: "Créditée · verrouillée",
  wrong_deposit: "Dépôt incorrect",
  awaiting_confirmation: "Confirmation requise",
  email_sent: "E-mail envoyé",
  awaiting_approval: "Approbation requise",
  rejected: "Refusée",
  processing: "Traitement",
  unknown: "Inconnu",
};

export function providerLabel(value) {
  return PROVIDER_LABELS[value] || value || "Stock interne";
}

export function supplierMonogram(value) {
  const letters = String(value || "").replace(/[^A-Za-z0-9]/g, "");
  return (letters.slice(0, 2) || "AP").toUpperCase();
}

export function money(value, currency = "USDT") {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(Number(value || 0))} ${currency}`;
}

export function orderAmount(order = {}) {
  return order.charged_total ?? Number(order.total_price || 0) + Number(order.wallet_amount || 0);
}

export function orderCustomerName(order = {}) {
  const customer = order.customer || {};
  return order.customer_name
    || customer.full_name
    || [order.first_name || customer.first_name, order.last_name || customer.last_name].filter(Boolean).join(" ")
    || (order.username || customer.username ? `@${order.username || customer.username}` : `Client ${order.user_id || customer.telegram_id || "—"}`);
}

export function orderCustomerReference(order = {}) {
  const customer = order.customer || {};
  const username = order.username || customer.username;
  const userId = order.user_id || customer.telegram_id || "—";
  return `${username ? `@${username} · ` : ""}ID ${userId}`;
}

export function date(value) {
  if (!value) return "—";
  const parsed =
    typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(parsed);
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="page-heading">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function ActionButton({
  children,
  icon: Icon,
  secondary = false,
  danger = false,
  ...props
}) {
  return (
    <button
      className={`action-button ${secondary ? "secondary" : ""} ${danger ? "danger" : ""}`}
      {...props}
    >
      {Icon && <Icon size={16} />}
      {children}
    </button>
  );
}

export function Modal({ title, children, onClose, wide = false, fullScreen = false }) {
  const dialog = useRef(null);
  useEffect(() => {
    const node = dialog.current;
    const previous = document.body.style.overflow;
    node.showModal();
    document.body.style.overflow = "hidden";
    return () => { node.close(); document.body.style.overflow = previous; };
  }, []);
  return (
      <dialog ref={dialog} aria-label={title}
        className={`form-dialog ${wide ? "wide" : ""} ${fullScreen ? "full-screen" : ""}`}
        onCancel={(event) => { event.preventDefault(); onClose(); }}
      >
        <header>
          <h3>{title}</h3>
          <button type="button" onClick={onClose} aria-label="Fermer la fenêtre">
            <X size={19} />
          </button>
        </header>
        <div className="form-dialog-body">{children}</div>
      </dialog>
  );
}

export function Field({ label, children, wide = false }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Empty({
  icon: Icon = Database,
  title = "Aucune donnée",
  text = "Les éléments apparaîtront ici.",
}) {
  return (
    <div className="page-empty">
      <Icon size={28} />
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

export function FilterBar({
  search,
  setSearch,
  children,
  placeholder = "Rechercher…",
  options = [],
  searchField = "all",
  setSearchField,
  resultCount,
}) {
  return (
    <div className={`filter-bar ${search ? "has-search" : ""}`}>
      <label className="smart-search">
        <Search size={17} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
        />
        {search && <button type="button" onClick={() => setSearch("")} title="Effacer la recherche" aria-label="Effacer la recherche"><X size={15} /></button>}
      </label>
      {options.length > 0 && (
        <label className="search-field-select">
          <span>Rechercher par</span>
          <select value={searchField} onChange={(event) => setSearchField?.(event.target.value)}>
            {options.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
        </label>
      )}
      {children}
      {search && resultCount !== undefined && <span className="search-result-count">{resultCount} résultat(s)</span>}
    </div>
  );
}

export function Pagination({ value, onChange }) {
  if (!value || value.pages <= 1) return null;
  return (
    <div className="pagination">
      <button
        disabled={value.page <= 1}
        onClick={() => onChange(value.page - 1)}
      >
        <ChevronLeft size={16} /> Précédent
      </button>
      <span>
        Page {value.page} sur {value.pages} · {value.total} résultat(s)
      </span>
      <button
        disabled={value.page >= value.pages}
        onClick={() => onChange(value.page + 1)}
      >
        Suivant <ChevronRight size={16} />
      </button>
    </div>
  );
}

export function useRemoteList(endpoint, filters, { refreshInterval = 0 } = {}) {
  const [result, setResult] = useState({
    items: [],
    page: 1,
    pages: 1,
    total: 0,
  });
  const [loading, setLoading] = useState(true);
  const [syncVersion, setSyncVersion] = useState(0);
  const query = new URLSearchParams(
    Object.entries(filters)
      .filter(([, value]) => value !== "" && value != null)
      .map(([key, value]) => [key, String(value)]),
  ).toString();
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    const synchronize = () => setSyncVersion((value) => value + 1);
    window.addEventListener("admin:data-synced", synchronize);
    return () => window.removeEventListener("admin:data-synced", synchronize);
  }, []);
  useEffect(() => {
    if (!refreshInterval) return undefined;
    const refresh = () => {
      if (document.visibilityState === "visible" && navigator.onLine) setSyncVersion((value) => value + 1);
    };
    const timer = window.setInterval(refresh, refreshInterval);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [refreshInterval]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    fetch(`${endpoint}?${debouncedQuery}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    })
      .then((response) => {
        if (response.status === 401) window.dispatchEvent(new Event("admin:session-expired"));
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        setResult({
          ...payload,
          items: Array.isArray(payload?.items) ? payload.items : [],
          page: Number(payload?.page) || 1,
          pages: Math.max(1, Number(payload?.pages) || 1),
          total: Math.max(0, Number(payload?.total) || 0),
        });
      })
      .catch((error) => {
        if (active && error.name !== "AbortError") window.dispatchEvent(new CustomEvent("admin:read-error", { detail: "La liste n’a pas pu être actualisée. Réessayez avant d’agir." }));
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      controller.abort();
    };
  }, [endpoint, debouncedQuery, syncVersion]);
  return [result, loading];
}

export function OperationsSummary({ items }) {
  return <div className="operations-summary">{items.map(([label, value, tone]) => <article key={label} className={tone || ""}><span>{label}</span><strong>{value}</strong></article>)}</div>;
}
