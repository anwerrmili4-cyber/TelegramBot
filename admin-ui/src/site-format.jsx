import { useEffect, useState } from "react";
import {
  Image as ImageIcon,
} from "lucide-react";

export const SITE_URL = "https://www.ourblackmarket.com";

export const SITE_CART_STATUS = {
  to_verify: ["À vérifier", "manual_review"],
  confirmed: ["Paiement confirmé", "payment_confirmed"],
  partial: ["Livraison partielle", "payment_confirmed"],
  delivered: ["Livré", "delivered"],
  cancelled: ["Annulé", "cancelled"],
  mixed: ["Statuts mixtes", "stock_issue"],
};

export const LINE_STATUS = {
  manual_review: "à vérifier",
  payment_confirmed: "à livrer",
  paid: "à livrer",
  preparing_delivery: "en livraison",
  delivered: "livré",
  cancelled: "annulé",
};

export const DEPOSIT_STATUS = {
  pending: ["À vérifier", "manual_review"],
  approved: ["Créditée", "delivered"],
  rejected: ["Refusée", "cancelled"],
};

export const receiptUrl = (id) => `/admin/api/site-receipt?id=${encodeURIComponent(id)}`;

export function Receipt({ id }) {
  if (!id) return <span>—</span>;
  return <a className="site-receipt" href={receiptUrl(id)} target="_blank" rel="noreferrer" title="Ouvrir le reçu en grand">
    <img src={receiptUrl(id)} alt="Reçu du client" loading="lazy" />
    <span><ImageIcon size={13} />Voir le reçu</span>
  </a>;
}

export const CATALOG_STATUS = {
  on_sale: ["En vente", "delivered"],
  no_price: ["Sans prix DT", "manual_review"],
  hidden: ["Masqué", "cancelled"],
  disabled: ["Désactivé", "cancelled"],
};

export function dinars(millimes) {
  return `${(Number(millimes || 0) / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} DT`;
}

export function dinarInput(millimes) {
  return millimes ? String(Number(millimes) / 1000).replace(".", ",") : "";
}

export function catalogStatus(row) {
  if (!row.site_enabled) return "disabled";
  if (!row.service_visible) return "hidden";
  if (row.on_sale) return "on_sale";
  return "no_price";
}

export const refreshLists = () => window.dispatchEvent(new CustomEvent("admin:data-synced"));

export function formatDeliveryNote(fields = []) {
  return fields
    .map((field) => ({
      label: String(field.label || "").trim().replace(/[:\n]/g, " ").replace(/\s+/g, " ").slice(0, 80),
      value: String(field.value || "").trim().replace(/\s+/g, " ").slice(0, 500),
    }))
    .filter((field) => field.label && field.value)
    .map((field) => `${field.label} : ${field.value}`)
    .join("\n")
    .slice(0, 4000);
}

export function CartStatus({ status }) {
  const [label, className] = SITE_CART_STATUS[status] || [status, ""];
  return <span className={`status ${className}`}>{label}</span>;
}

export function useSiteQuery() {
  const read = () => Object.fromEntries(new URLSearchParams(window.location.search));
  const [query, setQuery] = useState(read);
  useEffect(() => {
    const sync = () => setQuery(read());
    window.addEventListener("popstate", sync);
    window.addEventListener("admin:navigate", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("admin:navigate", sync);
    };
  }, []);
  const replace = (patch, { push = false } = {}) => {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || value === "") params.delete(key);
      else params.set(key, String(value));
    }
    const search = params.toString();
    const url = `${window.location.pathname}${search ? `?${search}` : ""}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (url !== current) window.history[push ? "pushState" : "replaceState"]({}, "", url);
    setQuery(Object.fromEntries(params));
  };
  return [query, replace];
}
