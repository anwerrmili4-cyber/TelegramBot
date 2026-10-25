"""Resolve warranty and product-period state for bot order views."""

from __future__ import annotations

import time
from datetime import datetime

import database as db


def order_delivery_timestamp(order):
    delivered_at = order.get("delivered_at") or order.get("created_at") or time.time()
    if isinstance(delivered_at, datetime):
        return delivered_at.timestamp()
    try:
        return float(delivered_at)
    except (TypeError, ValueError, OverflowError):
        return time.time()


def warranty_days_used(order):
    return max(0, int((time.time() - order_delivery_timestamp(order)) // 86400))


def product_warranty_days(order):
    """Resolve warranty duration from the product with order snapshot fallback."""
    offer_id = order.get("offer_id")
    if offer_id:
        offer = db.get_offer(int(offer_id))
        if offer and offer.get("warranty_days") is not None:
            return max(0, int(offer.get("warranty_days") or 0))
    return max(0, int(order.get("warranty_days") or 0))


def product_period_days(order):
    offer_id = order.get("offer_id")
    if offer_id:
        offer = db.get_offer(int(offer_id))
        if offer and offer.get("period_days") is not None:
            return max(0, int(offer.get("period_days") or 0))
    return max(0, int(order.get("period_days") or 0))


__all__ = [
    "order_delivery_timestamp",
    "product_period_days",
    "product_warranty_days",
    "warranty_days_used",
]
