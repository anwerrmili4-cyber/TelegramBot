"""MongoDB-backed public catalog and manual storefront orders for Tunisia."""

from __future__ import annotations

import hashlib
import html
import re
import secrets
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import database as db
from app.constants import OrderStatus
from app.domain import manual_payment_service
from config import TN_MANUAL_PAYMENT_METHODS, TN_TND_PER_USDT, TN_WHATSAPP_NUMBER

CATEGORY_LABELS = {
    "ai": "Intelligence artificielle",
    "streaming": "Streaming",
    "design": "Design & création",
    "productivity": "Productivité",
    "cloud": "Cloud & développement",
    "communication": "Communication",
    "security": "Sécurité",
    "other": "Autres services",
}


class StorefrontError(ValueError):
    """Validation error safe to return from the public storefront API."""


def _site_visible(row: dict[str, Any]) -> bool:
    # The storefront and Telegram bot intentionally share the complete active
    # catalog. A record is hidden only by an explicit site opt-out or archive.
    return row.get("site_enabled") is not False and row.get("archived") != 1


def _price_millimes(offer: dict[str, Any]) -> int:
    configured = offer.get("tn_price_millimes")
    if configured is not None:
        try:
            return max(0, int(configured))
        except (TypeError, ValueError):
            pass
    try:
        price = Decimal(str(offer.get("price") or 0))
        converted = price * Decimal(str(TN_TND_PER_USDT)) * 1000
        return max(0, int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _plain_text(value: Any, *, limit: int = 700) -> str:
    text = str(value or "").replace("[[HTML]]", " ")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:limit]


def _safe_image_url(value: Any) -> str:
    value = str(value or "").strip()[:1000]
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if value.startswith("/api/storefront/"):
        return value
    return ""


def _category(service: dict[str, Any], offer: dict[str, Any]) -> str:
    configured = str(offer.get("site_category") or "").strip().lower()
    if configured in CATEGORY_LABELS:
        return configured
    name = f"{service.get('name', '')} {offer.get('name', '')}".lower()
    rules = (
        ("ai", ("chatgpt", "openai", "gemini", "claude", "manus", "ai", " ia ")),
        ("streaming", ("netflix", "spotify", "youtube", "stream")),
        ("design", ("adobe", "canva", "capcut", "framer", "design")),
        ("cloud", ("supabase", "cloud", "hosting", "developer")),
        ("communication", ("telegram", "discord", "linkedin", "mail")),
        ("security", ("vpn", "security", "number", "otp")),
        ("productivity", ("office", "microsoft", "notion", "quillbot")),
    )
    return next((key for key, terms in rules if any(term in name for term in terms)), "other")


def catalog() -> dict[str, Any]:
    """Project the bot's live MongoDB catalog into a customer-safe response."""
    services: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    for service in db.list_services(active_only=True):
        if not _site_visible(service):
            continue
        offers = []
        for raw_offer in db.list_offers(int(service["id"]), active_only=True):
            if not _site_visible(raw_offer):
                continue
            offer = db.get_offer(int(raw_offer["id"])) or raw_offer
            category = _category(service, offer)
            used_categories.add(category)
            price_millimes = _price_millimes(offer)
            available = bool(
                offer.get("unlimited_stock") or int(offer.get("stock") or 0) > 0
            )
            offers.append({
                "id": int(offer["id"]),
                "package_number": str(offer.get("package_number") or offer["id"]),
                "name": str(offer.get("name") or "Offre")[:160],
                "description": _plain_text(
                    offer.get("site_description_fr") or offer.get("description") or offer.get("note")
                ),
                "price_millimes": price_millimes,
                "price": price_millimes / 1000,
                "currency": "TND",
                "available": available,
                "stock": -1 if offer.get("unlimited_stock") else max(0, int(offer.get("stock") or 0)),
                "min_quantity": max(1, int(offer.get("min_quantity") or 1)),
                "max_quantity": max(1, int(offer.get("max_quantity") or 10)),
                "delivery_delay": _plain_text(offer.get("delivery_delay"), limit=120),
                "period_days": int(offer.get("period_days") or 0),
                "warranty": _plain_text(offer.get("note"), limit=160),
                "featured": bool(offer.get("site_featured")),
                "badge": str(offer.get("site_badge") or "").strip()[:48],
                "image_url": _safe_image_url(offer.get("site_image_url")),
                "category": category,
                "category_label": CATEGORY_LABELS[category],
            })
        if offers:
            services.append({
                "id": int(service["id"]),
                "name": str(service.get("name") or "Service")[:120],
                "emoji": str(service.get("emoji") or "✦")[:8],
                "offers": offers,
            })
    return {
        "ok": True,
        "currency": "TND",
        "whatsapp": TN_WHATSAPP_NUMBER,
        "services": services,
        "categories": [
            {"id": key, "label": label}
            for key, label in CATEGORY_LABELS.items()
            if key in used_categories
        ],
        "payment_methods": [
            {"id": method, "label": method.upper() if method == "d17" else "Flouci"}
            for method in sorted(TN_MANUAL_PAYMENT_METHODS)
        ],
    }


def _tunisian_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("00216"):
        digits = digits[5:]
    elif digits.startswith("216"):
        digits = digits[3:]
    if not re.fullmatch(r"[2459]\d{7}", digits):
        raise StorefrontError("Saisis un numéro tunisien valide à 8 chiffres.")
    return f"+216{digits}"


def create_order(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a MongoDB order awaiting receipt verification on WhatsApp."""
    name = re.sub(r"\s+", " ", str(payload.get("name") or "").strip())[:100]
    if len(name) < 2:
        raise StorefrontError("Saisis ton nom complet.")
    phone = _tunisian_phone(payload.get("phone"))
    try:
        offer_id = int(payload.get("offer_id"))
        quantity = int(payload.get("quantity") or 1)
    except (TypeError, ValueError) as exc:
        raise StorefrontError("Offre ou quantité invalide.") from exc
    method = manual_payment_service.normalize_method(str(payload.get("payment_method") or ""))
    offer = db.get_offer(offer_id)
    service = db.get_service(int(offer.get("service_id"))) if offer else None
    if not offer or not service or not offer.get("active", 1):
        raise StorefrontError("Cette offre n'est plus disponible.")
    if not _site_visible(offer) or not _site_visible(service):
        raise StorefrontError("Cette offre n'est pas disponible sur le site tunisien.")
    minimum = max(1, int(offer.get("min_quantity") or 1))
    maximum = max(minimum, int(offer.get("max_quantity") or 10))
    if quantity < minimum or quantity > maximum:
        raise StorefrontError(f"Choisis une quantité entre {minimum} et {maximum}.")
    if not offer.get("unlimited_stock") and int(offer.get("stock") or 0) < quantity:
        raise StorefrontError("Le stock disponible est insuffisant.")

    order_id = db._next_id("orders")
    now = int(time.time())
    unit_millimes = _price_millimes(offer)
    tracking_token = secrets.token_urlsafe(24)
    order = {
        "id": order_id,
        "sales_channel": "tn_site",
        "source": "customer_site",
        "user_id": None,
        "customer_name": name,
        "customer_phone": phone,
        "offer_id": offer_id,
        "offer_name": str(offer.get("name") or "")[:200],
        "service_name": str(service.get("name") or "")[:120],
        "qty": quantity,
        "quantity": quantity,
        "unit_price_millimes": unit_millimes,
        "total_millimes": unit_millimes * quantity,
        "total_price": (unit_millimes * quantity) / 1000,
        "currency": "TND",
        "payment_method": method,
        "status": OrderStatus.MANUAL_REVIEW,
        "verification_channel": "whatsapp",
        "verification_recipient": TN_WHATSAPP_NUMBER,
        "tracking_token_hash": hashlib.sha256(tracking_token.encode()).hexdigest(),
        "txid": "",
        "verify_method": "",
        "created_at": now,
        "updated_at": now,
        "paid_at": None,
        "delivered_at": None,
    }
    db.get_conn().orders.insert_one(order)
    db.audit_event(
        "storefront.order_created",
        details={"order_id": order_id, "offer_id": offer_id, "payment_method": method},
    )
    return {
        "ok": True,
        "order_id": order_id,
        "tracking_token": tracking_token,
        "status": OrderStatus.MANUAL_REVIEW,
        "total_millimes": order["total_millimes"],
        "currency": "TND",
        "automatic_confirmation": False,
        "whatsapp_url": manual_payment_service.whatsapp_url(order, method),
    }


def order_status(order_id: int, tracking_token: str) -> dict[str, Any]:
    token_hash = hashlib.sha256(str(tracking_token or "").encode()).hexdigest()
    order = db.get_conn().orders.find_one({
        "id": int(order_id),
        "sales_channel": "tn_site",
        "tracking_token_hash": token_hash,
    })
    if not order:
        raise StorefrontError("Commande introuvable.")
    return {
        "ok": True,
        "order": {
            "id": int(order["id"]),
            "offer_name": order.get("offer_name", ""),
            "service_name": order.get("service_name", ""),
            "quantity": int(order.get("qty") or 1),
            "total_millimes": int(order.get("total_millimes") or 0),
            "currency": "TND",
            "payment_method": order.get("payment_method", ""),
            "status": str(order.get("status") or OrderStatus.MANUAL_REVIEW),
            "created_at": order.get("created_at"),
            "updated_at": order.get("updated_at"),
        },
    }
