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
import re
import secrets
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from pymongo.errors import DuplicateKeyError

import database as db
from app.constants import OrderStatus
from app.domain import (
    email_service,
    site_logo_service,
    site_orders_service,
    site_requests_service,
    site_settings_service,
    storefront_invoice_service,
    storefront_receipt_service,
    storefront_wallet_service,
    warranty_service,
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


def _bulk_deal(offer: dict[str, Any]) -> tuple[int, int]:
    """Project a real USDT bulk discount onto the dinar price.

    The site never invents a dinar amount from the bot price. It only keeps the
    discount ratio when buying the bulk quantity is actually cheaper.
    """
    regular_tn = _price_millimes(offer)
    try:
        quantity = int(offer.get("bulk_quantity") or 0)
        regular_usdt = Decimal(str(offer.get("price") or 0))
        bulk_usdt = Decimal(str(offer.get("bulk_unit_price")))
    except (InvalidOperation, TypeError, ValueError):
        return 0, 0
    if quantity < 2 or regular_tn <= 0 or regular_usdt <= 0 or not (0 <= bulk_usdt < regular_usdt):
        return 0, 0
    bulk_tn = int((Decimal(regular_tn) * bulk_usdt / regular_usdt).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if bulk_tn <= 0 or bulk_tn >= regular_tn:
        return 0, 0
    return quantity, bulk_tn


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
    return months or _plain_text(note, limit=160)


def _public_offer(service: dict[str, Any], offer: dict[str, Any]) -> dict[str, Any]:
    category = _category(service, offer)
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
        "period_days": _site_period_days(offer),
        "warranty": _site_warranty_label(offer),
        "warranty_days": _site_warranty_days(offer),
        "featured": bool(offer.get("site_featured")),
        "badge": str(offer.get("site_badge") or "").strip()[:48],
        "image_url": _safe_image_url(offer.get("site_image_url")),
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


def catalog() -> dict[str, Any]:
    """Project the bot's live MongoDB catalog into a customer-safe response."""
    services: list[dict[str, Any]] = []
    used_categories: set[str] = set()
    flat_groups: dict[str, dict[str, Any]] = {}
    for service in db.sort_for_site(db.list_services(active_only=False)):
        if not _site_visible(service):
            continue
        # Official subscriptions is only a bot folder. On the site each product
        # is its own category, named like the product (ChatGPT, Google AI Pro).
        flat = db.is_official_subscriptions_service(service)
        offers = []
        # list_offers already resolves expired sales and the OTP price rules.
        # Re-reading each offer adds two database round trips per product.
        # Bot ``active`` is ignored: the site sells whatever it has switched on.
        for offer in db.list_offers(int(service["id"]), active_only=False):
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
            group = flat_groups.get(label.casefold())
            if group is None:
                group = {
                    "id": -int(offer["id"]),
                    "name": label,
                    "emoji": emoji,
                    "logo_url": public["service_logo_url"],
                    "offers": [],
                }
                flat_groups[label.casefold()] = group
                services.append(group)
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
        info = _plain_text(entry.get("info"), limit=400)
        previous = merged.get(offer_id)
        if previous:
            quantity += previous[0]
            info = info or previous[1]
        merged[offer_id] = (quantity, info)
    return [(offer_id, quantity, info) for offer_id, (quantity, info) in merged.items()]


def _resolved_line(offer_id: int, quantity: int, info: str = "") -> dict[str, Any]:
    """Validate one cart line against the live catalog and price it in TND."""
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
    customer_info = _plain_text(info, limit=400) if requires_info else ""
    if requires_info and not customer_info:
        raise StorefrontError(f"« {name} » : envoie les informations demandées.")

    unit_millimes = _price_millimes(offer)
    return {
        "offer_id": int(offer["id"]),
        "offer_name": name,
        "service_name": _display_name(service, "Service")[:120],
        "quantity": quantity,
        "unit_millimes": unit_millimes,
        "total_millimes": unit_millimes * quantity,
        "period_days": _site_period_days(offer),
        "warranty_days": _site_warranty_days(offer),
        "warranty": _site_warranty_label(offer),
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


def _transfer_reference(method: str, value: Any) -> str:
    reference = re.sub(r"\s+", " ", str(value or "").strip())[:64]
    if len(reference) < 3:
        raise StorefrontError("Saisis la référence de la transaction indiquée sur ton reçu.")
    key = reference.lower()
    conn = db.get_conn()
    reused = conn.orders.find_one({
        "sales_channel": "tn_site",
        "payment_method": method,
        "payment_reference_key": key,
        "status": {"$ne": OrderStatus.CANCELLED},
    }) or conn.storefront_deposits.find_one({
        "method": method,
        "transaction_reference_key": key,
        "status": {"$ne": storefront_wallet_service.DEPOSIT_REJECTED},
    })
    if reused:
        raise StorefrontError("Cette référence de transaction a déjà été utilisée.")
    return reference


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

    payment_reference = ""
    receipt_id = None
    if by_wallet:
        if storefront_wallet_service.balance(customer_id) < cart_total:
            raise StorefrontError("Solde insuffisant. Recharge ton portefeuille ou paie par virement.")
    else:
        payment_reference = _transfer_reference(method, payload.get("transaction_reference"))
        try:
            receipt_id = storefront_receipt_service.store(
                payload.get("receipt"), customer_id=customer_id, purpose="order"
            )
        except storefront_receipt_service.ReceiptError as exc:
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
            "payment_reference_key": payment_reference.lower(),
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
            "cart_token_hash": _token_hash(tracking_token),
            "txid": "",
            "verify_method": "",
            "created_at": now,
            "updated_at": now,
            "paid_at": None,
            "delivered_at": None,
        })

    reference = _insert_cart(documents)
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
    else:
        status = "to_verify"
        email_service.send_order_received(
            email, name, reference, items, cart_total, site_orders_service.method_label(method)
        )
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
    return {
        "ok": True,
        "reference": reference,
        "order_ids": order_ids,
        "tracking_token": tracking_token,
        "status": status,
        "payment_method": method,
        "total_millimes": cart_total,
        "currency": "TND",
        "items": items,
        "balance_millimes": storefront_wallet_service.balance(customer_id),
    }


def _pay_from_wallet(customer_id: int, reference: str, documents: list[dict[str, Any]], total: int) -> str:
    """Debit the wallet for a freshly stored cart, then deliver what is in stock."""
    with db.coalesce_admin_notifications():
        return _pay_from_wallet_now(customer_id, reference, documents, total)


def _pay_from_wallet_now(customer_id: int, reference: str, documents: list[dict[str, Any]], total: int) -> str:
    conn = db.get_conn()
    if storefront_wallet_service.debit(customer_id, total, kind="purchase", reference=reference) is None:
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
    site_orders_service.fulfill_cart(reference)
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
