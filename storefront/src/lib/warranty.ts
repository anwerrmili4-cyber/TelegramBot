import type { Offer } from "@/types";
import { frenchDuration } from "@/lib/format";

const NONE = new Set(["NW", "NO WARRANTY", "SANS GARANTIE", "NON GARANTI", "0"]);
const FULL = new Set(["FW", "FULL WARRANTY", "GARANTIE COMPLETE", "GARANTIE COMPLÈTE"]);

export type WarrantyView = {
  covered: boolean;
  label: string;
  /** French month count, empty when the product has no duration to show. */
  duration: string;
};

/** Customer-facing warranty. FW is a full warranty, NW is none. Durations are in months. */
export function warrantyView(offer: Pick<Offer, "warranty" | "warranty_days" | "period_days">): WarrantyView {
  const raw = offer.warranty.trim();
  const code = raw.toLocaleUpperCase("fr");
  const days = Number(offer.warranty_days ?? 0);
  const period = Number(offer.period_days ?? 0);
  const fromText = frenchDuration(raw);
  const duration = fromText || (days > 0 ? frenchDuration("", days) : "");
  const full = FULL.has(code) || (days > 0 && period > 0 && days === period);
  if (full && !NONE.has(code)) return { covered: true, label: "Garantie complète", duration };
  const missingDays = offer.warranty_days !== undefined && days <= 0 && !fromText;
  if (!raw || NONE.has(code) || missingDays) return { covered: false, label: "Non garanti", duration: "" };
  return { covered: true, label: duration || raw, duration };
}
