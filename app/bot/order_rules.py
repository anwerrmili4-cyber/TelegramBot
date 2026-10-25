"""Bot-specific order and offer predicates."""

from __future__ import annotations

import re

import database as db

CUSTOMER_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def is_otp_order(order):
    return bool(order and db.is_otp_service_name(order.get("service_name")))


def collects_customer_email(offer):
    """Return whether this internal Canva offer asks for the buyer's email."""
    if not isinstance(offer, dict):
        return False
    name = str(offer.get("name") or "").strip().casefold()
    if name != "canva pro":
        return False
    try:
        price = float(offer.get("price") or 0)
    except (TypeError, ValueError):
        return False
    if abs(price - 1) > 0.001:
        return False
    if not offer.get("unlimited_stock"):
        return False
    return not str(offer.get("supplier_provider") or "").strip()


__all__ = ["CUSTOMER_EMAIL_RE", "collects_customer_email", "is_otp_order"]
