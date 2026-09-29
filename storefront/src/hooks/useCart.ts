import { useCallback, useEffect, useMemo, useState } from "react";
import { clampQuantity } from "@/lib/format";
import type { CartLine, Offer } from "@/types";

const STORAGE_KEY = "blackmarket.tn.cart.v1";

/**
 * Only offer ids and quantities are persisted. Prices, names and stock are
 * always re-read from the live catalog, so a cart left open overnight can never
 * check out at yesterday's price.
 */
type StoredCart = Record<string, number>;

function readStored(): StoredCart {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>)
        .map(([id, quantity]) => [id, Number(quantity)] as const)
        .filter(([id, quantity]) => /^\d+$/.test(id) && Number.isFinite(quantity) && quantity > 0),
    );
  } catch {
    return {};
  }
}

export type Cart = {
  lines: CartLine[];
  count: number;
  totalMillimes: number;
  isFull: boolean;
  quantityOf: (offerId: number) => number;
  add: (offer: Offer, quantity?: number) => void;
  setQuantity: (offer: Offer, quantity: number) => void;
  remove: (offerId: number) => void;
  clear: () => void;
};

export function useCart(offers: Offer[], maxLines: number): Cart {
  const [stored, setStored] = useState<StoredCart>(readStored);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    } catch {
      // A private-browsing quota error must not break checkout.
    }
  }, [stored]);

  // Joining against the catalog drops offers that were archived or sold out
  // while the cart sat in localStorage, and clamps stale quantities to stock.
  const lines = useMemo(() => {
    const byId = new Map(offers.map((offer) => [offer.id, offer]));
    return Object.entries(stored).flatMap<CartLine>(([id, quantity]) => {
      const offer = byId.get(Number(id));
      if (!offer || !offer.available) return [];
      const clamped = clampQuantity(offer, quantity);
      return clamped > 0 ? [{ offer, quantity: clamped }] : [];
    });
  }, [offers, stored]);

  const update = useCallback((offerId: number, quantity: number) => {
    setStored((current) => {
      const next = { ...current };
      if (quantity > 0) next[String(offerId)] = quantity;
      else delete next[String(offerId)];
      return next;
    });
  }, []);

  const setQuantity = useCallback(
    (offer: Offer, quantity: number) => {
      update(offer.id, quantity <= 0 ? 0 : clampQuantity(offer, quantity));
    },
    [update],
  );

  const add = useCallback(
    (offer: Offer, quantity = offer.min_quantity) => {
      setStored((current) => {
        const existing = current[String(offer.id)] ?? 0;
        if (!existing && Object.keys(current).length >= maxLines) return current;
        const next = clampQuantity(offer, existing + quantity);
        return next > 0 ? { ...current, [String(offer.id)]: next } : current;
      });
    },
    [maxLines],
  );

  return {
    lines,
    count: lines.reduce((total, line) => total + line.quantity, 0),
    totalMillimes: lines.reduce(
      (total, line) => total + line.offer.price_millimes * line.quantity,
      0,
    ),
    isFull: lines.length >= maxLines,
    quantityOf: (offerId) => lines.find((line) => line.offer.id === offerId)?.quantity ?? 0,
    add,
    setQuantity,
    remove: (offerId) => update(offerId, 0),
    clear: () => setStored({}),
  };
}
