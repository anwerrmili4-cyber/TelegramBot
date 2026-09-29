const dinars = new Intl.NumberFormat("fr-TN", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

/** Millimes are the storage unit: 1 dinar = 1000 millimes. */
export function money(millimes: number): string {
  return `${dinars.format((Number(millimes) || 0) / 1000)} DT`;
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

/** Display a period as the customer thinks of it rather than in raw days. */
export function periodLabel(days: number): string {
  if (days <= 0) return "";
  if (days % 365 === 0) {
    const years = days / 365;
    return `${years} ${plural(years, "an", "ans")}`;
  }
  if (days % 30 === 0) return `${days / 30} mois`;
  return `${days} ${plural(days, "jour", "jours")}`;
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
