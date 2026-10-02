import type { Offer } from "@/types";
import { frenchDuration } from "@/lib/format";

const NONE = new Set(["NW", "NO WARRANTY", "SANS GARANTIE", "NON GARANTI", "0"]);
const FULL = new Set(["FW", "FULL WARRANTY", "GARANTIE COMPLETE", "GARANTIE COMPLÈTE"]);

export type WarrantyTone = "full" | "months" | "none";

export type WarrantyView = {
  covered: boolean;
  /** `full` is green, `months` is yellow, `none` is red. */
  tone: WarrantyTone;
  label: string;
  /** French month count, empty when the product has no duration to show. */
  duration: string;
};

const TONE_CLASS: Record<WarrantyTone, string> = {
  full: "is-covered",
  months: "is-months",
  none: "is-open",
};

export function warrantyBadgeClass(base: string, tone: WarrantyTone): string {
  return `${base} ${TONE_CLASS[tone]}`;
}

export function warrantyTagClass(tone: WarrantyTone): string {
  if (tone === "months") return "tag tag-months";
  if (tone === "none") return "tag tag-warn";
  return "tag tag-ok";
}

/** Customer-facing warranty. FW is a full warranty, NW is none. A shorter duration is the month count. */
export function warrantyView(offer: Pick<Offer, "warranty" | "warranty_days" | "period_days">): WarrantyView {
  const raw = offer.warranty.trim();
  const code = raw.toLocaleUpperCase("fr");
  const days = Number(offer.warranty_days ?? 0);
  const period = Number(offer.period_days ?? 0);
  const fromText = frenchDuration(raw);
  const duration = fromText || (days > 0 ? frenchDuration("", days) : "");
  const full = FULL.has(code) || (days > 0 && period > 0 && days === period);
  if (full && !NONE.has(code)) return { covered: true, tone: "full", label: "Garantie complète", duration };
  const missingDays = offer.warranty_days !== undefined && days <= 0 && !fromText;
  if (!raw || NONE.has(code) || missingDays) return { covered: false, tone: "none", label: "Non garanti", duration: "" };
  const label = duration ? `Garantie ${duration}` : raw;
  return { covered: true, tone: "months", label, duration };
}
