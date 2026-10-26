export const BUYER_PERIODS = [
  ["all", "Toute la période"],
  ["today", "Aujourd’hui"],
  ["7d", "7 derniers jours"],
  ["30d", "30 derniers jours"],
  ["month", "Ce mois"],
  ["custom", "Personnalisée"],
];

export const FW_FILTERS = [
  ["all", "Tous les achats"],
  ["fw", "Tous les FW"],
  ["fw_active", "FW en cours"],
  ["fw_finished", "FW terminés"],
];

export function fwStatusText(order) {
  if (order?.fw_status === "finished") return "Terminé";
  if (order?.fw_status !== "active") return "";
  const days = order.remaining_days;
  if (days == null) return "En cours · fin inconnue";
  return `En cours · ${days} j restant${days > 1 ? "s" : ""}`;
}

function localDay(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

export function buyerDateRange(period, from, to, now = new Date()) {
  if (period === "all") return { from_ts: "", to_ts: "" };
  let start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  if (period === "custom") {
    start = localDay(from);
    end = localDay(to);
    if (!start || !end) return { error: "Choisissez une date de début et une date de fin." };
    if (start > end) return { error: "La date de fin doit être égale ou postérieure à la date de début." };
    end.setDate(end.getDate() + 1);
  } else if (period === "7d") start.setDate(start.getDate() - 6);
  else if (period === "30d") start.setDate(start.getDate() - 29);
  else if (period === "month") start.setDate(1);
  return { from_ts: Math.floor(start.getTime() / 1000), to_ts: Math.floor(end.getTime() / 1000) };
}

export function buyerOrderTarget(channel, order) {
  if (channel === "site") {
    return order.cart_reference ? { page: "site-orders", id: order.cart_reference } : null;
  }
  return order.order_id != null ? { page: "orders", id: order.order_id } : null;
}
