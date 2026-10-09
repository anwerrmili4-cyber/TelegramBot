const COUNT = new Intl.NumberFormat("fr-FR");
const PERCENT = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const WEEKDAYS = { Lun: "le lundi", Mar: "le mardi", Mer: "le mercredi", Jeu: "le jeudi", Ven: "le vendredi", Sam: "le samedi", Dim: "le dimanche" };

export function formatCount(value) {
  return COUNT.format(Math.round(Number(value) || 0));
}

export function percent(part, whole) {
  const total = Number(whole) || 0;
  if (total <= 0) return null;
  return ((Number(part) || 0) / total) * 100;
}

export function formatPercent(value) {
  return value == null ? "—" : `${PERCENT.format(value)} %`;
}

/** Change against the previous period of the same length. */
export function delta(current, previous) {
  if (previous == null) return null;
  const now = Number(current) || 0;
  const before = Number(previous) || 0;
  if (before === 0) return now === 0 ? { kind: "flat", value: 0 } : { kind: "new", value: null };
  const change = ((now - before) / before) * 100;
  if (Math.abs(change) < 0.5) return { kind: "flat", value: 0 };
  return { kind: change > 0 ? "up" : "down", value: change };
}

export function formatDelta(change) {
  if (!change) return "";
  if (change.kind === "new") return "Nouveau";
  if (change.kind === "flat") return "Stable";
  return `${change.value > 0 ? "+" : "−"}${PERCENT.format(Math.abs(change.value))} %`;
}

/** Round an axis maximum up to 1, 2, 2.5 or 5 times a power of ten. */
export function niceMax(value) {
  const max = Number(value) || 0;
  if (max <= 4) return 4;
  const power = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * power >= max);
  return step * power;
}

export function dayLabel(isoDate, style = "short") {
  const [year, month, day] = String(isoDate || "").split("-").map(Number);
  if (!year || !month || !day) return String(isoDate || "");
  const value = new Date(Date.UTC(year, month - 1, day, 12));
  const options = style === "long"
    ? { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }
    : { day: "numeric", month: "short", timeZone: "UTC" };
  return new Intl.DateTimeFormat("fr-FR", options).format(value);
}

export function relativeTime(unixSeconds, nowMs = Date.now()) {
  const seconds = Math.round((Number(unixSeconds) || 0) - nowMs / 1000);
  const format = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
  const steps = [[60, "second"], [3600, "minute"], [86400, "hour"], [Infinity, "day"]];
  const size = { second: 1, minute: 60, hour: 3600, day: 86400 };
  for (const [limit, unit] of steps) {
    if (Math.abs(seconds) < limit) return format.format(Math.round(seconds / size[unit]), unit);
  }
  return "";
}

export function peakSlot(heatmap = []) {
  let best = null;
  heatmap.forEach((row) => (row.hours || []).forEach((count, hour) => {
    if (count > 0 && (!best || count > best.count)) best = { day: row.day, hour, count };
  }));
  return best;
}

export function bestDay(daily = []) {
  return daily.reduce((best, point) => (Number(point.visits) > Number(best?.visits || 0) ? point : best), null);
}

/** Short French sentences shown above the charts. Empty when there is nothing to say. */
export function insights(result = {}) {
  const summary = result.summary || {};
  const items = [];
  const top = bestDay(result.daily);
  if (top) {
    items.push({ key: "best-day", title: "Meilleur jour", text: `${dayLabel(top.date, "long")} avec ${formatCount(top.visits)} visite(s).` });
  }
  const peak = peakSlot(result.heatmap);
  if (peak) {
    items.push({ key: "peak", title: "Heure de pointe", text: `${WEEKDAYS[peak.day] || peak.day} entre ${peak.hour} h et ${peak.hour + 1} h.` });
  }
  const sources = (result.sources || []).filter((row) => row.count > 0);
  const entries = sources.reduce((sum, row) => sum + row.count, 0);
  if (sources.length) {
    items.push({ key: "source", title: "Première source", text: `${sources[0].label} : ${formatPercent(percent(sources[0].count, entries))} des entrées.` });
  }
  const conversion = percent(summary.orders, summary.unique);
  if (conversion != null && summary.orders > 0) {
    items.push({ key: "conversion", title: "Conversion", text: `${formatPercent(conversion)} des visiteurs ont envoyé une commande.` });
  }
  const devices = (result.devices || []).filter((row) => row.count > 0);
  const deviceTotal = devices.reduce((sum, row) => sum + row.count, 0);
  if (devices.length) {
    items.push({ key: "device", title: "Appareil principal", text: `${devices[0].label} pour ${formatPercent(percent(devices[0].count, deviceTotal))} des visiteurs.` });
  }
  return items;
}

export const DAILY_CSV_COLUMNS = [
  ["date", "Date"],
  ["visits", "Visites"],
  ["visitors", "Visiteurs uniques"],
  ["interactions", "Interactions"],
  ["cart_adds", "Ajouts au panier"],
  ["checkouts", "Paiements ouverts"],
  ["orders", "Commandes envoyées"],
];
