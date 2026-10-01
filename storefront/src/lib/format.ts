const dinars = new Intl.NumberFormat("fr-TN", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

/** Millimes are the storage unit: 1 dinar = 1000 millimes. */
export function money(millimes: number): string {
  return `${dinars.format((Number(millimes) || 0) / 1000)} DT`;
}

const dateTimes = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** API timestamps are Unix seconds. */
export function dateTime(seconds: number | null | undefined): string {
  return seconds ? dateTimes.format(new Date(seconds * 1000)) : "—";
}

export function plural(count: number, one: string, many: string): string {
  return count > 1 ? many : one;
}

/** Highest quantity a customer may order, respecting both the cap and stock. */
export function maxOrderable(offer: { max_quantity: number; stock: number }): number {
  if (offer.stock < 0) return offer.max_quantity;
  return Math.max(0, Math.min(offer.max_quantity, offer.stock));
}

export function clampQuantity(
  offer: { min_quantity: number; max_quantity: number; stock: number },
  quantity: number,
): number {
  const ceiling = maxOrderable(offer);
  if (ceiling < offer.min_quantity) return 0;
  return Math.min(ceiling, Math.max(offer.min_quantity, Math.round(quantity) || offer.min_quantity));
}

/** A duration the customer reads in months: 30 days and 1 month are both "1 mois". */
export function monthsLabel(days: number): string {
  if (days <= 0) return "";
  const months = days % 30 === 0 ? days / 30 : Math.max(1, Math.round(days / 30));
  return `${months} mois`;
}

/** Display a period in French months, never in days. */
export function periodLabel(days: number): string {
  return monthsLabel(days);
}

const DURATION_TEXT = /^(\d+)\s*(day|days|jour|jours|j|month|months|mois|year|years|an|ans)$/i;

/** Turn "30 days", "1 month" or "1 year" into a French month count. */
export function frenchDuration(value: string, fallbackDays = 0): string {
  const match = value.trim().toLowerCase().match(DURATION_TEXT);
  let days = fallbackDays;
  if (match) {
    const amount = Number(match[1]);
    const unit = match[2];
    if (unit === "j" || unit.startsWith("day") || unit.startsWith("jour")) days = amount;
    else if (unit === "mois" || unit.startsWith("month")) days = amount * 30;
    else days = amount * 365;
  }
  return monthsLabel(days);
}

/** Strip anything that is not part of a local Tunisian 8-digit number. */
export function normalizePhoneInput(value: string): string {
  return value.replace(/[^\d]/g, "").replace(/^00216/, "").replace(/^216/, "").slice(0, 8);
}

export function isValidPhone(value: string): boolean {
  return /^[2459]\d{7}$/.test(normalizePhoneInput(value));
}

/** Group digits as `12 345 678` while typing. */
export function displayPhone(value: string): string {
  const digits = normalizePhoneInput(value);
  return digits.replace(/(\d{2})(\d{0,3})(\d{0,3})/, (_, a, b, c) =>
    [a, b, c].filter(Boolean).join(" "),
  );
}

const accents = /[\u0300-\u036f]/g;

export function searchable(value: string): string {
  return value.normalize("NFD").replace(accents, "").toLowerCase();
}
