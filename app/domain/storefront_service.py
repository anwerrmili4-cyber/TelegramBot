"""MongoDB-backed public catalog and manual cart checkout for Tunisia.

The storefront sells from the very same live catalog as the Telegram bot. A
customer cart is stored as one order document per line rather than a single
document holding an item array: that is what lets the admin dashboard, the
delivery pipeline, inventory and warranty treat a site sale exactly like a bot
sale. A shared ``cart_reference`` is the only thing grouping the lines back
together in the customer's account and the admin panel.

Buying needs an account. A cart paid from the wallet is debited at once and
delivered from inventory straight away; a cart paid by transfer is created in
``MANUAL_REVIEW`` with its receipt, and only an administrator can confirm it.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import secrets
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from pymongo.errors import DuplicateKeyError

import database as db
from app.constants import OrderStatus
from app.core.cache import CATALOG_PREFIX, cache
from app.domain import (
    email_service,
    site_logo_service,
    site_orders_service,
    site_requests_service,
    site_settings_service,
    storefront_invoice_service,
    storefront_receipt_service,
    storefront_wallet_service,
)

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

# A cart is a human hand-off on WhatsApp, so it stays small enough for an
# administrator to verify one receipt against it.
MAX_CART_LINES = 12

# Ambiguous glyphs are excluded so a customer can read the reference out loud.
_REFERENCE_ALPHABET = "ACDEFGHJKLMNPQRSTUVWXYZ2345679"
_REFERENCE_PATTERN = re.compile(r"^TN-[A-Z0-9]{6}$")
_CHECKOUT_KEY = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
# A wallet click that already took the money is finished, not charged again.
_WALLET_RESUME_SECONDS = 7 * 24 * 3600

log = logging.getLogger(__name__)


class StorefrontError(ValueError):
    """Validation error safe to return from the public storefront API."""


def site_enabled(row: dict[str, Any]) -> bool:
    """Whether this record is switched on for the storefront.

    An explicit ``site_enabled`` flag wins, so the bot's ``active`` state stays
    independent. Older rows without the flag follow the bot flag they used
    before the two channels were split.
    """
    if "site_enabled" in row:
        return row.get("site_enabled") is not False
    return bool(row.get("active", 1))


def _site_visible(row: dict[str, Any]) -> bool:
    return site_enabled(row) and row.get("archived") != 1


def _price_millimes(offer: dict[str, Any]) -> int:
    """Return the admin-set dinar price, or 0 when the offer has none yet.

    Converting the USDT bot price produced absurd dinar amounts for cheap bulk
    offers, so an offer without its own dinar price is not sold on the site.
    """
    try:
        return max(0, int(offer.get("tn_price_millimes") or 0))
    except (TypeError, ValueError):
        return 0


def _bulk_deal(_offer: dict[str, Any]) -> tuple[int, int]:
    """A group price only exists when the offer stores one in dinars.

    ``bulk_unit_price`` belongs to the bot and is in USDT. Turning that
    discount into dinars invented a unit price the catalogue never saved and
    that checkout never charges. The homepage was advertising that invention.
    """
    return 0, 0


def suggested_price_millimes(offer: dict[str, Any], rate: float | None = None) -> int:
    """Convert the bot's USDT price at the configured rate, rounded to 100 millimes."""
    if rate is None:
        rate = site_settings_service.tnd_per_usdt()
    try:
        price = Decimal(str(offer.get("price") or 0))
        converted = price * Decimal(str(rate)) * 10
        return max(0, int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100)
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _offer_on_sale(offer: dict[str, Any]) -> bool:
    return _site_visible(offer) and _price_millimes(offer) > 0


def _plain_text(value: Any, *, limit: int = 700, keep_breaks: bool = False) -> str:
    text = str(value or "").replace("[[HTML]]", " ")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    if keep_breaks:
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\n+", "\n", text)
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
    words = set(re.findall(r"[a-z0-9]+", name))
    rules = (
        ("ai", ("chatgpt", "openai", "gemini", "claude", "manus")),
        ("streaming", ("netflix", "spotify", "youtube", "stream")),
        ("design", ("adobe", "canva", "capcut", "framer", "design")),
        ("cloud", ("supabase", "cloud", "hosting", "developer")),
        ("communication", ("telegram", "discord", "linkedin", "mail")),
        ("security", ("vpn", "security", "number", "otp")),
        ("productivity", ("office", "microsoft", "notion", "quillbot")),
    )
    if words & {"ai", "ia"}:
        return "ai"
    return next((key for key, terms in rules if any(term in name for term in terms)), "other")


def _product_category_label(offer: dict[str, Any]) -> str:
    """Name a catalog category after the product, without its duration.

    An admin-set ``site_category_name`` wins, so the panel can rename the
    category without renaming the product itself.
    """
    custom = str(offer.get("site_category_name") or "").strip()
    if custom:
        return custom[:120]
    raw = _display_name(offer, "Offre")
    label = re.split(r"\s*[|·]\s*", raw, maxsplit=1)[0].strip()
    label = re.sub(
        r"\s+\d+\s*(?:years?|months?|days?|mois|ans?|jours?)\s*$",
        "",
        label,
        flags=re.I,
    ).strip()
    return (label or raw)[:120]


def _display_name(row: dict[str, Any], fallback: str) -> str:
    site_name = str(row.get("site_name") or "").strip()
    if site_name:
        return site_name[:160]
    if "site_name" in row:
        return str(row.get("name") or fallback)[:160]
    return str(row.get("name") or fallback)[:160]


def _site_period_days(offer: dict[str, Any]) -> int:
    if "site_period_days" in offer or "site_period_value" in offer:
        return max(0, int(offer.get("site_period_days") or 0))
    return max(0, int(offer.get("period_days") or 0))


def _site_warranty_days(offer: dict[str, Any]) -> int:
    if "site_warranty_days" in offer or "site_warranty_value" in offer:
        return max(0, int(offer.get("site_warranty_days") or 0))
    return 0


def _months_label(days: int) -> str:
    if days <= 0:
        return ""
    months = days // 30 if days % 30 == 0 else max(1, round(days / 30))
    return f"{months} mois"


def _site_warranty_label(offer: dict[str, Any]) -> str:
    days = _site_warranty_days(offer)
    period = _site_period_days(offer)
    note = str(offer.get("site_note") or "").strip()
    code = note.upper()
    if days <= 0:
        return "Non garanti"
    if code == "FW" or (period > 0 and days == period):
        return "Garantie complète"
    months = _months_label(days)
    if months:
        return f"Garantie {months}"
    return _plain_text(note, limit=160)


def _public_offer(service: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    category = _category(service, offer)
    methods = db.is_methods_service(service)
    price_millimes = _price_millimes(offer)
    unlimited = bool(offer.get("unlimited_stock"))
    stock = max(0, int(offer.get("stock") or 0))
    minimum = max(1, int(offer.get("min_quantity") or 1))
    delay = offer.get("site_delivery_delay") if "site_delivery_delay" in offer else ""
    bulk_quantity, bulk_unit_millimes = _bulk_deal(offer)
    return {
        "id": int(offer["id"]),
        "package_number": str(offer.get("package_number") or offer["id"]),
        "name": _display_name(offer, "Offre"),
        "description": _plain_text(offer.get("site_description_fr"), limit=8000, keep_breaks=True),
        "price_millimes": price_millimes,
        "currency": "TND",
        "available": unlimited or stock > 0,
        "stock": -1 if unlimited else stock,
        "min_quantity": minimum,
        "max_quantity": max(minimum, int(offer.get("max_quantity") or 10)),
        "delivery_delay": _plain_text(delay, limit=120),
        "period_days": 0 if methods else _site_period_days(offer),
        "warranty": "" if methods else _site_warranty_label(offer),
        "warranty_days": 0 if methods else _site_warranty_days(offer),
        "show_terms": not methods,
        "featured": bool(offer.get("site_featured")),
        "badge": str(offer.get("site_badge") or "").strip()[:48],
        "image_url": _safe_image_url(offer.get("site_image_url")),
        "video_url": _safe_image_url(offer.get("site_video_url")),
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "service_id": int(service["id"]),
        "service_name": _display_name(service, "Service")[:120],
        "service_emoji": str(service.get("emoji") or "✦")[:8],
        "service_logo_url": site_logo_service.logo_url(service),
        "bulk_quantity": bulk_quantity,
        "bulk_unit_millimes": bulk_unit_millimes,
        "remark": _plain_text(offer.get("site_remark"), limit=400),
        "requires_info": offer.get("site_requires_info") is True,
    }


# Fields the public catalog actually reads. Leaving the rest on the server
# avoids shipping bot notes, Arabic copy, and supplier data over the network.
_CATALOG_OFFER_FIELDS = {
    "id": 1,
    "service_id": 1,
    "archived": 1,
    "active": 1,
    "site_enabled": 1,
    "name": 1,
    "site_name": 1,
    "emoji": 1,
    "package_number": 1,
    "price": 1,
    "tn_price_millimes": 1,
    "stock": 1,
    "unlimited_stock": 1,
    "min_quantity": 1,
    "max_quantity": 1,
    "period_days": 1,
    "site_period_days": 1,
    "site_period_value": 1,
    "site_warranty_days": 1,
    "site_warranty_value": 1,
    "site_note": 1,
    "site_delivery_delay": 1,
    "site_featured": 1,
    "site_badge": 1,
    "site_image_url": 1,
    "site_video_url": 1,
    "site_description_fr": 1,
    "site_category": 1,
    "site_category_name": 1,
    "site_category_logo_id": 1,
    "site_category_logo_version": 1,
    "site_remark": 1,
    "site_requires_info": 1,
    "flash_sale_active": 1,
    "flash_sale_ends_at": 1,
    "flash_sale_original_price": 1,
    "flash_sale_price": 1,
}


CATALOG_CACHE_SECONDS = 5.0


def catalog() -> dict[str, Any]:
    """Project the bot's live MongoDB catalog into a customer-safe response.

    Supplier stock is refreshed off the request path; the stock writes it
    makes invalidate the cached catalog, so the next view shows them.
    """
    from app.domain import reseller_service

    reseller_service.refresh_supplier_stock_in_background()
    return cache.get_or_set(CATALOG_PREFIX + "storefront", CATALOG_CACHE_SECONDS, _build_catalog)


def _build_catalog() -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    flat_groups: dict[str, dict[str, Any]] = {}
    visible = [
        service
        for service in db.sort_for_site(db.list_services(active_only=False))
        if _site_visible(service)
    ]
    # One offer query for the whole shop. A query per category made the first
    # page wait on a round trip for every service.
    offers_by_service = db.list_offers_for_services(
        visible,
        active_only=False,
        include_archived=True,
        projection=_CATALOG_OFFER_FIELDS,
    )
    for service in visible:
        # Official subscriptions is only a bot folder. On the site each product
        # is its own category, named like the product (ChatGPT, Google AI Pro).
        flat = db.is_official_subscriptions_service(service)
        offers = []
        # Bot ``active`` is ignored: the site sells whatever it has switched on.
        for offer in offers_by_service.get(int(service["id"]), []):
            if not _offer_on_sale(offer):
                continue
            public = _public_offer(service, offer)
            used_categories.add(public["category"])
            if not flat:
                offers.append(public)
                continue
            label = _product_category_label(offer)
            public["service_name"] = label
            emoji = str(offer.get("emoji") or public["service_emoji"] or "✦").strip()[:8]
            public["service_emoji"] = emoji
            category_logo = site_logo_service.category_logo_url(
                offer.get("site_category_logo_id"),
                offer.get("site_category_logo_version"),
            )
            if category_logo:
                public["service_logo_url"] = category_logo
            group = flat_groups.get(label.casefold())
            if group is None:
                group = {
                    "id": -int(offer["id"]),
                    "name": label,
                    "emoji": emoji,
                    "logo_url": category_logo or public["service_logo_url"],
                    "offers": [],
                }
                flat_groups[label.casefold()] = group
                services.append(group)
            elif category_logo:
                group["logo_url"] = category_logo
            public["service_id"] = group["id"]
            group["offers"].append(public)
        if offers:
            services.append({
                "id": int(service["id"]),
                "name": _display_name(service, "Service")[:120],
                "emoji": str(service.get("emoji") or "✦")[:8],
                "logo_url": site_logo_service.logo_url(service),
                "offers": offers,
            })
    return {
        "ok": True,
        "currency": "TND",
        "max_cart_lines": MAX_CART_LINES,
        "services": services,
        "categories": [
            {"id": key, "label": label}
            for key, label in CATEGORY_LABELS.items()
            if key in used_categories
        ],
        "payment_methods": site_settings_service.public_payment_methods(),
    }


def public_offer(offer_id: int) -> dict[str, Any] | None:
    """One customer-safe product, without building the whole catalog."""
    try:
        offer_id = int(offer_id)
    except (TypeError, ValueError):
        return None
    offer = db.get_offer(offer_id)
    if not offer:
        return None
    service = db.get_service(int(offer.get("service_id") or 0))
    if not service or not _site_visible(service) or not _offer_on_sale(offer):
        return None
    public = _public_offer(service, offer)
    if not db.is_official_subscriptions_service(service):
        return public
    public["service_name"] = _product_category_label(offer)
    public["service_emoji"] = str(offer.get("emoji") or public["service_emoji"] or "✦").strip()[:8]
    category_logo = site_logo_service.category_logo_url(
        offer.get("site_category_logo_id"),
        offer.get("site_category_logo_version"),
    )
    if category_logo:
        public["service_logo_url"] = category_logo
    return public


def _requested_lines(payload: dict[str, Any]) -> list[tuple[int, int, str]]:
    """Normalise a cart payload into merged ``(offer_id, quantity, info)`` rows.

    A single ``offer_id``/``quantity`` pair is still accepted so a cached copy
    of an older frontend keeps working against this endpoint. ``info`` is the
    customer's answer when the product asks for one. A cart-wide note is ignored:
    the remark itself is written by the administrator on the product.
    """
    raw = payload.get("items")
    if raw is None and payload.get("offer_id") is not None:
        raw = [{"offer_id": payload.get("offer_id"), "quantity": payload.get("quantity")}]
    if not isinstance(raw, list) or not raw:
        raise StorefrontError("Ton panier est vide.")
    if len(raw) > MAX_CART_LINES:
        raise StorefrontError(f"Un panier accepte au maximum {MAX_CART_LINES} produits différents.")

    merged: dict[int, tuple[int, str]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise StorefrontError("Panier invalide.")
        try:
            offer_id = int(entry.get("offer_id"))
            quantity = int(entry.get("quantity") or 1)
        except (TypeError, ValueError) as exc:
            raise StorefrontError("Offre ou quantité invalide.") from exc
        if quantity < 1:
            raise StorefrontError("Choisis au moins une unité par produit.")
        info = _plain_text(entry.get("info"), limit=2000, keep_breaks=True)
        previous = merged.get(offer_id)
        if previous:
            quantity += previous[0]
            info = info or previous[1]
        merged[offer_id] = (quantity, info)
    return [(offer_id, quantity, info) for offer_id, (quantity, info) in merged.items()]


def _resolved_line(offer_id: int, quantity: int, info: str = "") -> dict[str, Any]:
    """Validate one cart line against the live catalog and price it in TND."""
    from app.domain import reseller_service

    offer = db.get_offer(offer_id)
    if offer and offer.get("supplier_provider"):
        reseller_service.refresh_supplier_stock([offer])
        offer = db.get_offer(offer_id)
    service = db.get_service(int(offer.get("service_id"))) if offer else None
    if not offer or not service or offer.get("archived") == 1:
        raise StorefrontError("Cette offre n'est plus disponible.")
    if not _offer_on_sale(offer) or not _site_visible(service):
        raise StorefrontError("Cette offre n'est pas disponible sur le site tunisien.")

    name = _display_name(offer, "Offre")[:200]
    minimum = max(1, int(offer.get("min_quantity") or 1))
    maximum = max(minimum, int(offer.get("max_quantity") or 10))
    if quantity < minimum or quantity > maximum:
        raise StorefrontError(f"« {name} » : choisis une quantité entre {minimum} et {maximum}.")
    if not offer.get("unlimited_stock") and int(offer.get("stock") or 0) < quantity:
        raise StorefrontError(f"« {name} » : le stock disponible est insuffisant.")

    remark = _plain_text(offer.get("site_remark"), limit=400)
    requires_info = offer.get("site_requires_info") is True
    customer_info = _plain_text(info, limit=2000, keep_breaks=True) if requires_info else ""
    if requires_info and not customer_info:
        raise StorefrontError(f"« {name} » : envoie les informations demandées.")

    unit_millimes = _price_millimes(offer)
    methods = db.is_methods_service(service)
    return {
        "offer_id": int(offer["id"]),
        "offer_name": name,
        "service_name": _display_name(service, "Service")[:120],
        "quantity": quantity,
        "unit_millimes": unit_millimes,
        "total_millimes": unit_millimes * quantity,
        "period_days": 0 if methods else _site_period_days(offer),
        "warranty_days": 0 if methods else _site_warranty_days(offer),
        "warranty": "" if methods else _site_warranty_label(offer),
        "customer_info": customer_info,
        "site_remark": remark,
    }


def _cart_reference() -> str:
    return "TN-" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(6))


def _normalized_reference(value: Any) -> str:
    reference = str(value or "").strip().upper()
    if not reference.startswith("TN-"):
        reference = f"TN-{reference}"
    if not _REFERENCE_PATTERN.fullmatch(reference):
        raise StorefrontError("Référence de commande invalide.")
    return reference


def _token_hash(token: Any) -> str:
    return hashlib.sha256(str(token or "").encode()).hexdigest()


def _insert_cart(documents: list[dict[str, Any]]) -> str:
    """Write the cart lines under a reference no other cart holds.

    Line 1 exists in every cart, so inserting it first claims the reference
    through the unique index before any sibling line is written.
    """
    orders = db.get_conn().orders
    for _ in range(5):
        reference = _cart_reference()
        for document in documents:
            document["cart_reference"] = reference
        try:
            orders.insert_one(documents[0])
        except DuplicateKeyError:
            documents[0].pop("_id", None)
            continue
        if len(documents) > 1:
            orders.insert_many(documents[1:])
        return reference
    raise StorefrontError("Impossible de générer une référence. Réessaie dans un instant.")


def _payment_method(value: Any) -> str:
    method = str(value or "").strip().lower()
    if method == site_orders_service.WALLET_METHOD:
        return method
    try:
        return site_settings_service.normalize_method(method)
    except ValueError as exc:
        raise StorefrontError(str(exc)) from exc


def transfer_reference_in_use(method: str, key: str) -> bool:
    """True while a live site order or deposit already declared this reference."""
    conn = db.get_conn()
    return bool(conn.orders.find_one({
        "sales_channel": "tn_site",
        "payment_method": method,
        "payment_reference_key": key,
        "status": {"$ne": OrderStatus.CANCELLED},
    }, {"_id": 1}) or conn.storefront_deposits.find_one({
        "method": method,
        "transaction_reference_key": key,
        "status": {"$ne": storefront_wallet_service.DEPOSIT_REJECTED},
    }, {"_id": 1}))


def _transfer_reference(method: str, value: Any) -> tuple[str, str | None]:
    """Validate and claim a transfer reference; return it with its release token."""
    reference = re.sub(r"\s+", " ", str(value or "").strip())[:64]
    if not reference:
        return "", None
    if len(reference) < 3:
        raise StorefrontError("Saisis la référence de la transaction indiquée sur ton reçu.")
    key = reference.lower()
    if transfer_reference_in_use(method, key):
        raise StorefrontError("Cette référence de transaction a déjà été utilisée.")
    token = db.claim_payment_reference(method, key, lambda: transfer_reference_in_use(method, key))
    if token is None:
        raise StorefrontError("Cette référence de transaction a déjà été utilisée.")
    return reference, token


def _checkout_key(value: Any) -> str:
    key = str(value or "").strip()
    return key if _CHECKOUT_KEY.fullmatch(key) else ""


def _line_signature(lines: list[dict[str, Any]]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(
        (int(line.get("offer_id") or 0), int(line.get("quantity") or line.get("qty") or 1))
        for line in lines
    ))


def _cart_rows(reference: str) -> list[dict[str, Any]]:
    rows = list(db.get_conn().orders.find({"sales_channel": "tn_site", "cart_reference": reference}))
    rows.sort(key=lambda row: int(row.get("cart_position") or 0))
    return rows


def _existing_checkout(customer_id: int, checkout_key: str) -> str:
    if not checkout_key:
        return ""
    row = db.get_conn().orders.find_one({
        "sales_channel": "tn_site",
        "customer_id": int(customer_id),
        "checkout_key": checkout_key,
        "cart_position": 1,
    })
    return str(row["cart_reference"]) if row else ""


def _supplier_charge_never_sent(row: dict[str, Any]) -> bool:
    """A paid supplier line whose purchase never left this server."""
    if str(row.get("status") or "") in {str(OrderStatus.DELIVERED), str(OrderStatus.CANCELLED)}:
        return False
    offer = db.get_offer(int(row.get("offer_id") or 0)) or {}
    if not offer.get("supplier_provider"):
        return False
    fulfillment = db.get_conn().reseller_fulfillments.find_one({"order_id": int(row["id"])})
    if not fulfillment:
        return str(row.get("status") or "") in {
            str(OrderStatus.PAYMENT_CONFIRMED),
            str(OrderStatus.PAID),
            str(OrderStatus.MANUAL_REVIEW),
        }
    return fulfillment.get("status") == "purchasing" and not fulfillment.get("supplier_requested")


def _open_wallet_carts(customer_id: int, signature: tuple[tuple[int, int], ...]) -> list[str]:
    """Wallet carts of these items, already paid, whose supplier was never called."""
    since = int(time.time()) - _WALLET_RESUME_SECONDS
    rows = list(db.get_conn().orders.find({
        "sales_channel": "tn_site",
        "customer_id": int(customer_id),
        "payment_method": site_orders_service.WALLET_METHOD,
        "created_at": {"$gte": since},
    }))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("cart_reference") or ""), []).append(row)
    found: list[tuple[int, str]] = []
    for reference, group in grouped.items():
        if not reference or _line_signature(group) != signature:
            continue
        if not storefront_wallet_service.purchase_recorded(customer_id, reference):
            continue
        if any(_supplier_charge_never_sent(row) for row in group):
            found.append((max(int(row.get("created_at") or 0) for row in group), reference))
    found.sort()
    return [reference for _, reference in found]


def _release_duplicate_wallet_charges(
    customer_id: int, keep: str, signature: tuple[tuple[int, int], ...]
) -> None:
    """Give back every earlier wallet click that never reached the supplier."""
    for reference in _open_wallet_carts(customer_id, signature):
        if reference == keep:
            continue
        try:
            site_orders_service.cancel_cart(
                reference,
                "Paiement en double annulé : un seul achat a été conservé.",
            )
        except Exception:
            log.exception("Duplicate wallet cart %s could not be refunded", reference)


def _checkout_response(
    customer_id: int, reference: str, tracking_token: str, status: str
) -> dict[str, Any]:
    rows = _cart_rows(reference)
    first = rows[0]
    items = [
        {
            "offer_id": int(row.get("offer_id") or 0),
            "offer_name": row.get("offer_name", ""),
            "service_name": row.get("service_name", ""),
            "quantity": int(row.get("qty") or 1),
            "unit_millimes": int(row.get("unit_price_millimes") or 0),
            "total_millimes": int(row.get("total_millimes") or 0),
        }
        for row in rows
    ]
    return {
        "ok": True,
        "reference": reference,
        "order_ids": [int(row["id"]) for row in rows],
        "tracking_token": tracking_token,
        "status": status,
        "payment_method": first.get("payment_method", ""),
        "total_millimes": int(first.get("cart_total_millimes") or 0) or sum(item["total_millimes"] for item in items),
        "currency": "TND",
        "items": items,
        "balance_millimes": storefront_wallet_service.balance(customer_id),
    }


def _finish_saved_cart(customer_id: int, reference: str, tracking_token: str = "") -> dict[str, Any]:
    """Finish a cart that was already stored, without taking the money twice."""
    rows = _cart_rows(reference)
    if not rows:
        raise StorefrontError("Commande introuvable.")
    total = int(rows[0].get("cart_total_millimes") or 0)
    if str(rows[0].get("payment_method") or "") == site_orders_service.WALLET_METHOD:
        status = _pay_from_wallet(customer_id, reference, rows, total)
        _release_duplicate_wallet_charges(customer_id, reference, _line_signature(rows))
    else:
        status = site_orders_service.cart_status(rows)
    return _checkout_response(customer_id, reference, tracking_token, status)


def create_order(payload: dict[str, Any], customer: dict[str, Any]) -> dict[str, Any]:
    """Store a signed-in customer's cart and pay it from the wallet or by transfer."""
    customer_id = int(customer["id"])
    name = str(customer.get("name") or "")
    email = str(customer.get("email") or "")
    method = _payment_method(payload.get("payment_method"))
    lines = [
        _resolved_line(offer_id, quantity, info)
        for offer_id, quantity, info in _requested_lines(payload)
    ]
    cart_total = sum(line["total_millimes"] for line in lines)
    by_wallet = method == site_orders_service.WALLET_METHOD
    checkout_key = _checkout_key(payload.get("idempotency_key") or payload.get("checkout_key"))
    signature = _line_signature(lines)

    existing = _existing_checkout(customer_id, checkout_key)
    if existing:
        return _finish_saved_cart(customer_id, existing)
    if by_wallet:
        open_carts = _open_wallet_carts(customer_id, signature)
        if open_carts:
            return _finish_saved_cart(customer_id, open_carts[-1])

    payment_reference = ""
    reference_claim = None
    receipt_id = None
    if by_wallet:
        if storefront_wallet_service.balance(customer_id) < cart_total:
            raise StorefrontError("Solde insuffisant. Recharge ton portefeuille ou paie par virement.")
    else:
        payment_reference, reference_claim = _transfer_reference(
            method, payload.get("transaction_reference")
        )
        try:
            receipt_id = storefront_receipt_service.store(
                payload.get("receipt"), customer_id=customer_id, purpose="order"
            )
        except storefront_receipt_service.ReceiptError as exc:
            db.release_payment_reference(method, payment_reference.lower(), reference_claim)
            raise StorefrontError(str(exc)) from exc

    tracking_token = secrets.token_urlsafe(24)
    now = int(time.time())

    documents = []
    for position, line in enumerate(lines, start=1):
        documents.append({
            "id": db._next_id("orders"),
            "sales_channel": "tn_site",
            "source": "customer_site",
            "user_id": None,
            "customer_id": customer_id,
            "customer_name": name,
            "customer_email": email,
            "customer_phone": str(customer.get("phone") or ""),
            "customer_note": "",
            "customer_info": line["customer_info"],
            "site_remark": line["site_remark"],
            "payment_reference": payment_reference,
            **({"payment_reference_key": payment_reference.lower()} if payment_reference else {}),
            "receipt_id": receipt_id,
            "cart_position": position,
            "cart_size": len(lines),
            "cart_total_millimes": cart_total,
            "offer_id": line["offer_id"],
            "offer_name": line["offer_name"],
            "service_name": line["service_name"],
            "period_days": line["period_days"],
            "warranty_days": line["warranty_days"],
            "warranty": line["warranty"],
            "qty": line["quantity"],
            "quantity": line["quantity"],
            "unit_price_millimes": line["unit_millimes"],
            "total_millimes": line["total_millimes"],
            "total_price": line["total_millimes"] / 1000,
            "currency": "TND",
            "payment_method": method,
            "status": OrderStatus.MANUAL_REVIEW,
            "verification_channel": "wallet" if by_wallet else "receipt",
            "checkout_key": checkout_key,
            "cart_token_hash": _token_hash(tracking_token),
            "txid": "",
            "verify_method": "",
            "created_at": now,
            "updated_at": now,
            "paid_at": None,
            "delivered_at": None,
        })

    try:
        reference = _insert_cart(documents)
    except Exception:
        if reference_claim:
            db.release_payment_reference(method, payment_reference.lower(), reference_claim)
        raise
    db.bind_payment_reference(method, payment_reference.lower(), reference_claim)
    order_ids = [document["id"] for document in documents]
    items = [
        {
            "offer_id": line["offer_id"],
            "offer_name": line["offer_name"],
            "service_name": line["service_name"],
            "quantity": line["quantity"],
            "unit_millimes": line["unit_millimes"],
            "total_millimes": line["total_millimes"],
        }
        for line in lines
    ]

    if by_wallet:
        status = _pay_from_wallet(customer_id, reference, documents, cart_total)
        _release_duplicate_wallet_charges(customer_id, reference, signature)
    else:
        status = "to_verify"
        try:
            email_service.send_order_received(
                email, name, reference, items, cart_total, site_orders_service.method_label(method)
            )
        except Exception:
            log.exception("Order received email failed for cart %s", reference)
    try:
        db.audit_event(
            "storefront.cart_created",
            details={
                "cart_reference": reference,
                "order_ids": order_ids,
                "payment_method": method,
                "total_millimes": cart_total,
                "status": status,
            },
        )
    except Exception:
        log.exception("Checkout audit failed for cart %s", reference)
    return _checkout_response(customer_id, reference, tracking_token, status)


def _pay_from_wallet(customer_id: int, reference: str, documents: list[dict[str, Any]], total: int) -> str:
    """Debit the wallet for a freshly stored cart, then deliver what is in stock."""
    with db.coalesce_admin_notifications():
        return _pay_from_wallet_now(customer_id, reference, documents, total)


def _pay_from_wallet_now(customer_id: int, reference: str, documents: list[dict[str, Any]], total: int) -> str:
    conn = db.get_conn()
    already_paid = storefront_wallet_service.purchase_recorded(customer_id, reference)
    if not already_paid and storefront_wallet_service.debit(
        customer_id, total, kind="purchase", reference=reference,
    ) is None:
        conn.orders.delete_many({"cart_reference": reference, "status": OrderStatus.MANUAL_REVIEW})
        raise StorefrontError("Solde insuffisant. Recharge ton portefeuille ou paie par virement.")

    # Stock was checked when pricing the cart; a line sold out in the meantime
    # is cancelled and refunded rather than failing the whole purchase.
    for line in site_orders_service.mark_cart_paid(documents, "wallet"):
        now = int(time.time())
        conn.orders.update_one(
            {"id": line["id"]},
            {"$set": {
                "status": OrderStatus.CANCELLED,
                "admin_note": "Rupture de stock pendant le paiement",
                "refunded_millimes": line["total_millimes"],
                "cancelled_at": now,
                "updated_at": now,
            }},
        )
        storefront_wallet_service.credit(
            customer_id, line["total_millimes"], kind="refund", reference=reference, note=line["offer_name"]
        )
    try:
        site_orders_service.fulfill_cart(reference)
    except Exception:
        log.exception("Wallet cart %s stayed paid but delivery did not finish", reference)
    lines = list(conn.orders.find({"cart_reference": reference}))
    return site_orders_service.cart_status(lines)


def _public_line(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(order["id"]),
        "offer_name": order.get("offer_name", ""),
        "service_name": order.get("service_name", ""),
        "quantity": int(order.get("qty") or 1),
        "total_millimes": int(order.get("total_millimes") or 0),
        "status": str(order.get("status") or OrderStatus.MANUAL_REVIEW),
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at"),
    }


def cart_status(reference: Any, tracking_token: Any) -> dict[str, Any]:
    """Return every line of a cart, authenticated by its tracking token."""
    reference = _normalized_reference(reference)
    orders = list(db.get_conn().orders.find({
        "sales_channel": "tn_site",
        "cart_reference": reference,
        "cart_token_hash": _token_hash(tracking_token),
    }))
    if not orders:
        raise StorefrontError("Commande introuvable.")
    orders.sort(key=lambda order: int(order.get("cart_position") or 0))
    lines = [_public_line(order) for order in orders]
    return {
        "ok": True,
        "reference": reference,
        "currency": "TND",
        "payment_method": orders[0].get("payment_method", ""),
        "total_millimes": int(orders[0].get("cart_total_millimes") or 0)
        or sum(line["total_millimes"] for line in lines),
        "created_at": orders[0].get("created_at"),
        "items": lines,
    }


MAX_ACCOUNT_CARTS = 50

_LINE_STATUSES = {
    str(OrderStatus.MANUAL_REVIEW): "to_verify",
    str(OrderStatus.PAYMENT_CONFIRMED): "confirmed",
    str(OrderStatus.PAID): "confirmed",
    str(OrderStatus.PREPARING_DELIVERY): "confirmed",
    str(OrderStatus.DELIVERED): "delivered",
    str(OrderStatus.CANCELLED): "cancelled",
}


def customer_carts(customer_id: int, email: str = "") -> list[dict[str, Any]]:
    """The customer's site carts, newest first, with what was delivered.

    Pass ``email`` only once the customer has proven they own it: it also
    brings back carts placed as a guest with that address.
    """
    owner: dict[str, Any] = {"customer_id": int(customer_id)}
    if email:
        owner = {"$or": [owner, {"customer_email": email}]}
    rows = db.get_conn().orders.find(
        {"sales_channel": "tn_site", "cart_reference": {"$exists": True}, **owner}
    ).sort("created_at", -1).limit(MAX_ACCOUNT_CARTS * MAX_CART_LINES)
    carts: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        carts.setdefault(row["cart_reference"], []).append(row)

    result = []
    shown = list(carts.items())[:MAX_ACCOUNT_CARTS]
    invoices = storefront_invoice_service.numbers_for([reference for reference, _ in shown])
    delivered_lines = [
        line
        for _, lines in shown
        for line in lines
        if line.get("status") == OrderStatus.DELIVERED
    ]
    delivery_by_id = site_orders_service.deliveries_for(delivered_lines)
    warranty_by_id = site_requests_service.warranty_flags([line for _, lines in shown for line in lines])
    for reference, lines in shown:
        lines.sort(key=lambda line: int(line.get("cart_position") or 0))
        first = lines[0]
        method = str(first.get("payment_method") or "")
        result.append({
            "reference": reference,
            "status": site_orders_service.cart_status(lines),
            "payment_method": method,
            "payment_label": site_orders_service.method_label(method),
            "transaction_reference": first.get("payment_reference", ""),
            "total_millimes": int(first.get("cart_total_millimes") or 0)
            or sum(int(line.get("total_millimes") or 0) for line in lines),
            "refunded_millimes": sum(int(line.get("refunded_millimes") or 0) for line in lines),
            "created_at": min(int(line.get("created_at") or 0) for line in lines),
            "paid_at": first.get("paid_at"),
            "cancel_reason": next((str(line.get("admin_note") or "") for line in lines if line.get("admin_note")), ""),
            "invoice_number": invoices.get(reference, ""),
            "items": [
                {
                    "id": int(line["id"]),
                    "offer_id": line.get("offer_id"),
                    "offer_name": line.get("offer_name", ""),
                    "service_name": line.get("service_name", ""),
                    "quantity": int(line.get("qty") or 1),
                    "unit_millimes": int(line.get("unit_price_millimes") or 0),
                    "total_millimes": int(line.get("total_millimes") or 0),
                    "period_days": int(line.get("period_days") or 0),
                    "site_remark": str(line.get("site_remark") or ""),
                    "customer_info": str(line.get("customer_info") or ""),
                    "status": _LINE_STATUSES.get(str(line.get("status") or ""), "to_verify"),
                    "delivered_at": line.get("delivered_at"),
                    "delivery": delivery_by_id.get(int(line["id"]), "")
                    if line.get("status") == OrderStatus.DELIVERED
                    else "",
                    "warranty_days": int(line.get("warranty_days") or 0),
                    **warranty_by_id.get(int(line["id"]), {
                        "warranty_open": False,
                        "warranty_status": "",
                        "warranty_id": None,
                        "replacement": "",
                        "warranty_note": "",
                    }),
                }
                for line in lines
            ],
        })
    return result


def order_status(order_id: int, tracking_token: str) -> dict[str, Any]:
    """Return a single cart line, authenticated by its tracking token."""
    order = db.get_conn().orders.find_one({
        "id": int(order_id),
        "sales_channel": "tn_site",
        "cart_token_hash": _token_hash(tracking_token),
    })
    if not order:
        raise StorefrontError("Commande introuvable.")
    line = _public_line(order)
    return {
        "ok": True,
        "order": {
            **line,
            "currency": "TND",
            "payment_method": order.get("payment_method", ""),
            "reference": order.get("cart_reference", ""),
        },
    }
