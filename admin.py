"""Vues et actions du panneau administrateur."""
import html
from datetime import UTC, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from app.domain import warranty_service
from config import ADMIN_ID, CURRENCY
from i18n import TRANSLATIONS


_BOLD_SOURCE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_BOLD_TARGET = (
    "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
    "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
)
_BOLD_TRANSLATION = str.maketrans(_BOLD_SOURCE, _BOLD_TARGET)


def _button_bold(value):
    """Simulate bold in Telegram buttons, which do not support HTML markup."""
    return str(value or "").translate(_BOLD_TRANSLATION)


def _safe_custom_emoji_id(value):
    """Ignore regular Unicode emoji accidentally stored as Premium icon IDs."""
    normalized = str(value or "").strip()
    return normalized if normalized and normalized.isascii() else None


def _service_button_text(service):
    icon_id = _safe_custom_emoji_id(service.get("custom_emoji_id"))
    left = "" if icon_id else str(service.get("emoji") or "").strip()
    name = _button_bold(service.get("name") or f"Service #{service['id']}")
    right = str(service.get("suffix_emoji") or "").strip()
    return " ".join(part for part in (left, name, right) if part)[:64]


def _two_column_rows(buttons):
    """Arrange admin products/actions in a compact two-button grid."""
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


TEXT_CATEGORIES = [
    ("menus", "🏠 Menus et navigation"),
    ("payments", "💳 Dépôts, paiements et portefeuille"),
    ("catalog", "🛍 Catalogue et produits"),
    ("orders", "📦 Commandes, livraison et garantie"),
    ("alerts", "📢 Annonces, chaîne et notifications"),
    ("support", "🎫 Support et avis"),
    ("account", "👤 Compte, fidélité et langues"),
    ("admin", "🛠 Administration et système"),
]


def text_category_for_key(key):
    if key in {
        "channel_stock_announcement", "offer_stock_announcement",
        "flash_sale_announcement",
    }:
        return "alerts"
    rules = [
        ("admin", ("admin_",)),
        ("alerts", ("channel_", "btn_channel_", "btn_join_channel", "btn_verify_join")),
        ("payments", ("payment_", "topup_", "wallet_", "ask_txid", "verifying", "copy_", "order_created", "btn_paid", "btn_pay_")),
        ("catalog", ("catalog_", "service_", "offer_", "stock_", "choose_quantity", "quantity_", "confirm_purchase", "price_", "out_of_stock", "cat_")),
        ("orders", ("orders_", "order_", "delivery_", "warranty_", "status_", "otp_", "duplicate_order", "already_paid", "cancelled_")),
        ("support", ("support_", "ticket_", "rating_")),
        ("account", ("affiliate_", "loyalty_", "profile_", "terms_", "privacy_", "help_", "welcome", "lang_")),
        ("menus", ("menu_", "btn_")),
    ]
    for category, prefixes in rules:
        if key.startswith(prefixes) or key in prefixes:
            return category
    return "admin"


def text_categories_keyboard():
    counts = {slug: 0 for slug, _label in TEXT_CATEGORIES}
    for key in TRANSLATIONS:
        counts[text_category_for_key(key)] += 1
    buttons = [InlineKeyboardButton(
        f"{label} ({counts[slug]})", callback_data=f"adm_text_cat:{slug}:0"
    ) for slug, label in TEXT_CATEGORIES if counts[slug]]
    rows = _two_column_rows(buttons)
    rows.append([InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize")])
    return InlineKeyboardMarkup(rows)


def text_entry_label(key):
    """Return a quick-to-scan button name and purpose for the text editor."""
    names = {
        "offer_card_template": "Product card",
        "menu_catalog": "Shop",
        "menu_topup": "Deposit",
        "menu_account": "My account",
        "menu_support": "Support",
        "menu_lang": "Language",
        "profile_deposit": "Deposit",
        "profile_withdraw": "Withdraw",
        "profile_orders": "My orders",
        "profile_referral": "Refer & Earn",
        "profile_shop": "Shop",
        "profile_reseller_api": "Reseller API",
        "profile_main_menu": "Main menu",
        "topup_verify_bybit": "Bybit Pay",
        "topup_verify_txid": "Binance Pay",
        "topup_onchain": "Onchain",
        "topup_bsc": "USDT - BEP20",
        "topup_polygon": "USDT - POLY",
    }
    descriptions = {
        "menus": "Menu button",
        "payments": "Payment or wallet message",
        "catalog": "Catalog or product text",
        "orders": "Order, delivery or warranty text",
        "alerts": "Announcement or notification",
        "support": "Support or ticket message",
        "account": "Account, language or loyalty text",
        "admin": "Administration or system text",
    }
    name = names.get(key) or " ".join(part.capitalize() for part in key.split("_"))
    description = descriptions.get(text_category_for_key(key), "Bot message")
    return f"{name} — {description}"[:64]


def texts_category_keyboard(category, page=0, page_size=8):
    keys = sorted(key for key in TRANSLATIONS if text_category_for_key(key) == category)
    total_pages = max(1, (len(keys) + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    visible = keys[page * page_size:(page + 1) * page_size]
    rows = _two_column_rows([
        InlineKeyboardButton(f"✏️ {text_entry_label(key)}", callback_data=f"adm_text_key:{key}")
        for key in visible
    ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_text_cat:{category}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="adm_text_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_text_cat:{category}:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("🗂 Catégories", callback_data="adm_texts")])
    return InlineKeyboardMarkup(rows)


def admin_panel_keyboard():
    maintenance_enabled = db.shop_settings()["maintenance_enabled"]
    active_warranties = db.get_conn().warranty_requests.count_documents({
        "status": {"$in": ["pending_admin_check", "accepted", "replacement_pending"]},
    })
    confirmed_payments = db.get_conn().orders.count_documents({
        "status": {"$in": ["paid", "payment_confirmed", "delivered"]},
    })
    _pending_api_rows, pending_api_count = db.list_pending_api_deliveries(page_size=1)
    maintenance_label = (
        "🔴 Full maintenance lock: ON"
        if maintenance_enabled
        else "🟢 Full maintenance lock: OFF"
    )
    buttons = [
        InlineKeyboardButton("💸 Retraits en attente", callback_data="adm_withdrawals", style="danger"),
        InlineKeyboardButton(f"🛡 Warranty ({active_warranties})", callback_data="adm_warranties:0", style="danger" if active_warranties else "success"),
        InlineKeyboardButton(f"✅ Payment Confirmed ({confirmed_payments})", callback_data="adm_payments:0", style="success"),
        InlineKeyboardButton(f"⏳ Livraison API en attente ({pending_api_count})", callback_data="adm_api_pending:0", style="danger" if pending_api_count else "success"),
        InlineKeyboardButton("🎫 Tickets support", callback_data="adm_tickets", style="primary"),
        InlineKeyboardButton("📦 Catalogue", callback_data="adm_catalog", style="primary"),
        InlineKeyboardButton("📋 Produits en stock", callback_data="adm_stock_products:0", style="success"),
        InlineKeyboardButton("👥 Activité utilisateurs", callback_data="adm_user_activity", style="primary"),
        InlineKeyboardButton("📢 Créer une annonce", callback_data="adm_broadcast_message", style="primary"),
        InlineKeyboardButton("🧹 Historique annonces", callback_data="adm_broadcast_history", style="primary"),
        InlineKeyboardButton(maintenance_label, callback_data="adm_maintenance_toggle", style="danger" if maintenance_enabled else "success"),
        InlineKeyboardButton("🎛 Personnaliser", callback_data="adm_customize", style="primary"),
    ]
    return InlineKeyboardMarkup(_two_column_rows(buttons))


def _admin_page_navigation(prefix, page, total, page_size):
    total_pages = max(1, (int(total) + int(page_size) - 1) // int(page_size))
    page = max(0, min(int(page), total_pages - 1))
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="adm_text_noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"{prefix}:{page + 1}"))
    return row


def available_products_screen(page=0, page_size=15):
    """Render active, in-stock offers using their catalog Premium emoji."""
    offers = [
        offer for offer in db.list_catalog_offers()
        if bool(offer.get("unlimited_stock")) or int(offer.get("stock") or 0) > 0
    ]
    total = len(offers)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    visible = offers[page * page_size:(page + 1) * page_size]
    lines = [
        "📋 <b>Available products (in stock)</b>",
        f"Total: <b>{total}</b> · Page <b>{page + 1}/{total_pages}</b>",
        "",
    ]
    for offer in visible:
        fallback = str(offer.get("service_emoji") or "📦").strip() or "📦"
        icon_id = _safe_custom_emoji_id(offer.get("service_custom_emoji_id"))
        icon = (
            f'<tg-emoji emoji-id="{html.escape(icon_id)}">{html.escape(fallback)}</tg-emoji>'
            if icon_id else html.escape(fallback)
        )
        catalog_name = html.escape(str(offer.get("service_name") or "Catalog").strip())
        offer_name = html.escape(str(offer.get("name") or f"Offer #{offer.get('id')}").strip())
        duration = html.escape(warranty_service.offer_period_label(offer, "en"))
        try:
            amount = f"{float(offer.get('price')):.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            amount = str(offer.get("price") or "—")
        currency = str(offer.get("currency") or CURRENCY).upper()
        price = f"${amount}" if currency in {"USD", "USDT"} else f"{amount} {html.escape(currency)}"
        lines.append(
            f"{icon} <b>{catalog_name} - {offer_name}</b> | {duration} | <b>{price}</b>"
        )
    if not visible:
        lines.append("No active products are currently in stock.")
    rows = [_admin_page_navigation("adm_stock_products", page, total, page_size)]
    rows.append([InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def _admin_timestamp(value):
    if isinstance(value, datetime):
        stamp = value.astimezone(UTC)
    else:
        try:
            stamp = datetime.fromtimestamp(float(value), UTC)
        except (TypeError, ValueError, OverflowError):
            return "—"
    return stamp.strftime("%d/%m %H:%M UTC")


def _full_order_context(order_id):
    """Collect every persisted order, customer, supplier, inventory and delivery field."""
    conn = db.get_conn()
    order = db.get_order(int(order_id)) or {}
    user = conn.users.find_one({"telegram_id": int(order.get("user_id") or 0)}) or {}
    offer = conn.offers.find_one({"id": order.get("offer_id")}) or {}
    service = conn.services.find_one({"id": offer.get("service_id")}) or {}
    fulfillment = conn.reseller_fulfillments.find_one({"order_id": int(order_id)}) or {}
    inventory = list(conn.inventory.find({
        "$or": [
            {"delivered_order_id": int(order_id)},
            {"reserved_order_id": int(order_id)},
            {"order_id": int(order_id)},
            {"source_external_order_id": f"BM-{int(order_id)}"},
        ],
    }).sort("id", 1))
    delivery_items = []
    cipher = db._fernet()
    for item in inventory:
        payload = item.get("payload")
        if not payload:
            continue
        try:
            delivery_items.append(cipher.decrypt(str(payload).encode()).decode())
        except Exception:
            delivery_items.append("[encrypted content could not be decrypted]")
    if not delivery_items:
        for payload in fulfillment.get("encrypted_items") or []:
            try:
                delivery_items.append(cipher.decrypt(str(payload).encode()).decode())
            except Exception:
                delivery_items.append("[encrypted content could not be decrypted]")
    stored_delivery = str(order.get("delivery_text") or "").strip()
    if not delivery_items and stored_delivery and not stored_delivery.startswith("[encrypted "):
        delivery_items.append(stored_delivery)
    return {
        "order": order,
        "user": user,
        "offer": offer,
        "service": service,
        "fulfillment": fulfillment,
        "inventory": inventory,
        "delivery_items": delivery_items,
    }


def _context_table(context, *, heading="DETAIL", fulfillment_override=None):
    order = context["order"]
    user = context["user"]
    offer = context["offer"]
    service = context["service"]
    fulfillment = fulfillment_override or context["fulfillment"]
    inventory = context["inventory"]
    username = f"@{user['username']}" if user.get("username") else "—"
    inventory_ids = ", ".join(str(item.get("id") or "—") for item in inventory) or "—"
    inventory_states = ", ".join(
        f"#{item.get('id', '—')}:{item.get('status', '—')}" for item in inventory
    ) or "—"
    rows = [
        (heading, "FULL INFORMATION"),
        ("Order", f"#{order.get('id', '—')}"),
        ("Order status", order.get("status") or "—"),
        ("Customer ID", order.get("user_id") or "—"),
        ("Customer name", user.get("first_name") or "—"),
        ("Username", username),
        ("Language", user.get("lang") or "—"),
        ("Service", order.get("service_name") or service.get("name") or "—"),
        ("Offer", order.get("offer_name") or offer.get("name") or "—"),
        ("Offer ID", order.get("offer_id") or "—"),
        ("Quantity", order.get("qty") or 1),
        ("Unit price", f"{float(order.get('unit_price') or 0):.2f} {order.get('currency') or CURRENCY}"),
        ("Wallet paid", f"{float(order.get('wallet_amount') or 0):.2f} {order.get('currency') or CURRENCY}"),
        ("External paid", f"{float(order.get('total_price') or 0):.2f} {order.get('currency') or CURRENCY}"),
        ("Total charged", f"{db.order_charge_total(order):.2f} {order.get('currency') or CURRENCY}"),
        ("Payment method", order.get("verify_method") or order.get("payment_method") or "—"),
        ("TXID", order.get("txid") or "—"),
        ("Created", _admin_timestamp(order.get("created_at"))),
        ("Paid", _admin_timestamp(order.get("paid_at"))),
        ("Delivered", _admin_timestamp(order.get("delivered_at"))),
        ("Updated", _admin_timestamp(order.get("updated_at"))),
        ("Warranty", order.get("warranty") or warranty_service.order_warranty_label(order) or "—"),
        ("Warranty days", order.get("warranty_days") if order.get("warranty_days") is not None else offer.get("warranty_days", "—")),
        ("Product period", order.get("period_days") if order.get("period_days") is not None else offer.get("period_days", "—")),
        ("Supplier", fulfillment.get("provider") or offer.get("supplier_provider") or "—"),
        ("Supplier status", fulfillment.get("status") or "fulfillment missing"),
        ("Local reference", fulfillment.get("external_order_id") or order.get("supplier_external_order_id") or f"BM-{order.get('id', '—')}"),
        ("Supplier order", fulfillment.get("supplier_order_id") or "—"),
        ("Supplier product", fulfillment.get("supplier_product_id") or offer.get("supplier_product_id") or "—"),
        ("Supplier created", _admin_timestamp(fulfillment.get("created_at"))),
        ("Supplier updated", _admin_timestamp(fulfillment.get("updated_at"))),
        ("Inventory IDs", inventory_ids),
        ("Inventory status", inventory_states),
        ("Admin note", order.get("admin_note") or "—"),
    ]
    return build_order_table(rows, max_val_len=48)


def _html_report_preview(title, report, *, max_escaped=3500):
    body = str(report or "")
    truncated = False
    while len(html.escape(body)) > max_escaped and len(body) > 200:
        body = body[:int(len(body) * 0.85)]
        truncated = True
    note = "\n\n<i>Preview truncated. Tap Full report for every field and complete content.</i>" if truncated else ""
    return f"{title}\n\n<pre>{html.escape(body)}</pre>{note}"


def warranty_requests_keyboard(page=0, page_size=10):
    requests, total = db.list_warranty_requests(page=page, page_size=page_size)
    icons = {
        "pending_admin_check": "🟠",
        "accepted": "🔵",
        "replacement_pending": "🟣",
        "replacement_delivered": "✅",
        "refunded": "💰",
        "refused": "❌",
    }
    buttons = []
    for request in requests:
        status = str(request.get("status") or "unknown")
        buttons.append(InlineKeyboardButton(
            f"{icons.get(status, '•')} #{request['id']} · Order #{request.get('order_id')} · {status}"[:64],
            callback_data=f"adm_warranty_view:{request['id']}",
        ))
    if not buttons:
        buttons.append(InlineKeyboardButton("Aucune demande de garantie", callback_data="adm_text_noop"))
    rows = [[button] for button in buttons]
    rows.append(_admin_page_navigation("adm_warranties", page, total, page_size))
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data=f"adm_warranties:{int(page)}"),
        InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows), requests, total


def warranty_request_report(request):
    if not request:
        return "Warranty request not found."
    context = _full_order_context(int(request.get("order_id") or 0))
    request_rows = [
        ("WARRANTY REQUEST", "FULL INFORMATION"),
        ("Request ID", f"#{int(request['id'])}"),
        ("Request status", request.get("status") or "—"),
        ("Resolution", request.get("resolution") or "—"),
        ("Days used", int(request.get("days_used") or 0)),
        ("Calculated refund", f"{float(request.get('refund_amount') or 0):.2f} {CURRENCY}"),
        ("Request created", _admin_timestamp(request.get("created_at"))),
        ("Request updated", _admin_timestamp(request.get("updated_at"))),
        ("Replacement sent", _admin_timestamp(request.get("replacement_delivered_at"))),
        ("Admin note", request.get("admin_note") or "—"),
    ]
    report = [
        build_order_table(request_rows, max_val_len=48),
        _context_table(context, heading="ORDER / SUPPLIER"),
        "CUSTOMER WARRANTY MESSAGE\n" + (str(request.get("reason") or "[not stored for this legacy request]")),
        "REAL DELIVERED CONTENT\n" + (
            "\n\n".join(context["delivery_items"])
            if context["delivery_items"] else "[no delivered content persisted]"
        ),
    ]
    return "\n\n".join(report)


def warranty_request_text(request):
    if not request:
        return "Warranty request not found."
    return _html_report_preview(
        f"🛡 <b>Warranty request #{int(request['id'])}</b>",
        warranty_request_report(request),
    )


def warranty_request_keyboard(request):
    rows = []
    status = str((request or {}).get("status") or "")
    request_id = int((request or {}).get("id") or 0)
    if status == "pending_admin_check":
        rows.append([
            InlineKeyboardButton("✅ Accept", callback_data=f"adm_warranty_accept:{request_id}", style="success"),
            InlineKeyboardButton("❌ Refuse", callback_data=f"adm_warranty_refuse:{request_id}", style="danger"),
        ])
    elif status == "accepted":
        rows.append([
            InlineKeyboardButton("🔁 Replacement", callback_data=f"adm_warranty_resolve:replacement:{request_id}", style="primary"),
            InlineKeyboardButton("💰 Refund", callback_data=f"adm_warranty_resolve:refund:{request_id}", style="success"),
        ])
    elif status == "replacement_pending":
        rows.append([InlineKeyboardButton(
            "📨 Send replacement",
            callback_data=f"adm_warranty_send:{request_id}",
            style="success",
        )])
    rows.append([InlineKeyboardButton(
        "📄 Full report + real content",
        callback_data=f"adm_warranty_report:{request_id}",
        style="primary",
    )])
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data=f"adm_warranty_view:{request_id}"),
        InlineKeyboardButton("⬅️ Warranty", callback_data="adm_warranties:0"),
    ])
    return InlineKeyboardMarkup(rows)


def confirmed_payments_keyboard(page=0, page_size=10):
    orders, total = db.list_confirmed_orders(page=page, page_size=page_size)
    buttons = []
    for order in orders:
        amount = db.order_charge_total(order)
        delivered = "📦" if order.get("status") == "delivered" else "⏳"
        buttons.append(InlineKeyboardButton(
            f"{delivered} #{order['id']} · {amount:.2f} {CURRENCY} · {order.get('offer_name') or order.get('service_name') or 'Product'}"[:64],
            callback_data=f"adm_order:{order['id']}",
        ))
    if not buttons:
        buttons.append(InlineKeyboardButton("Aucun paiement confirmé", callback_data="adm_text_noop"))
    rows = [[button] for button in buttons]
    rows.append(_admin_page_navigation("adm_payments", page, total, page_size))
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data=f"adm_payments:{int(page)}"),
        InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows), orders, total


def pending_api_deliveries_keyboard(page=0, page_size=10):
    fulfillments, total = db.list_pending_api_deliveries(page=page, page_size=page_size)
    buttons = [InlineKeyboardButton(
        f"⏳ #{row.get('order_id')} · {row.get('provider') or 'API'} · {row.get('status') or 'pending'}"[:64],
        callback_data=f"adm_api_pending_view:{int(row.get('order_id') or 0)}",
    ) for row in fulfillments]
    if not buttons:
        buttons.append(InlineKeyboardButton("✅ Aucune livraison API en attente", callback_data="adm_text_noop"))
    rows = [[button] for button in buttons]
    rows.append(_admin_page_navigation("adm_api_pending", page, total, page_size))
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data=f"adm_api_pending:{int(page)}"),
        InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows), fulfillments, total


def pending_api_delivery_report(fulfillment):
    if not fulfillment:
        return "Pending API delivery not found."
    order_id = int(fulfillment.get("order_id") or 0)
    context = _full_order_context(order_id)
    report = [_context_table(
        context,
        heading="DELIVERY REQUEST",
        fulfillment_override=fulfillment,
    )]
    report.append("REAL DELIVERY CONTENT\n" + (
        "\n\n".join(context["delivery_items"])
        if context["delivery_items"] else "[supplier has not delivered content yet]"
    ))
    return "\n\n".join(report)


def pending_api_delivery_text(fulfillment):
    if not fulfillment:
        return "Pending API delivery not found."
    order_id = int(fulfillment.get("order_id") or 0)
    return _html_report_preview(
        f"⏳ <b>Livraison API en attente — Order #{order_id}</b>",
        pending_api_delivery_report(fulfillment),
    )


def pending_api_delivery_keyboard(order_id):
    order_id = int(order_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Open order", callback_data=f"adm_order:{order_id}", style="primary")],
        [InlineKeyboardButton(
            "📄 Full delivery report",
            callback_data=f"adm_api_pending_report:{order_id}",
            style="primary",
        )],
        [InlineKeyboardButton("🔄 Actualiser", callback_data=f"adm_api_pending_view:{order_id}"),
         InlineKeyboardButton("⬅️ Pending API", callback_data="adm_api_pending:0")],
    ])


def withdrawals_keyboard(withdrawals):
    buttons = []
    for withdrawal in withdrawals:
        amount = int(withdrawal.get("amount_cents") or 0) / 100
        destination = str(withdrawal.get("destination") or "")[:24]
        buttons.append(InlineKeyboardButton(
            f"#{withdrawal['id']} · {amount:.2f} USDT · {withdrawal.get('method')} · {destination}",
            callback_data=f"adm_withdraw_done:{withdrawal['id']}",
            style="success",
        ))
    if not buttons:
        buttons.append(InlineKeyboardButton("✅ Aucun retrait en attente", callback_data="adm_text_noop"))
    rows = _two_column_rows(buttons)
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data="adm_withdrawals"),
        InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows)


def broadcast_kind_label(kind):
    return {
        "stock": "✨ Nouveau stock",
        "restock_digest": "✨ Stocks individuels (ancien)",
        "flash_sale": "🔥 Vente flash",
        "api_flash_sale": "🔥 Vente flash",
        "admin_message": "📢 Annonce libre",
        "maintenance": "🛠 Maintenance",
        "affiliate_update": "🎁 Mise à jour affiliation",
    }.get(str(kind), "📣 Annonce")


def broadcast_history_keyboard(history):
    buttons = []
    for job in history:
        active = int(job.get("active_message_count") or 0)
        status = "🗑" if active == 0 else "🟢"
        buttons.append(InlineKeyboardButton(
            f"{status} {broadcast_kind_label(job.get('kind'))} · {active}/{int(job.get('tracked_count') or 0)}",
            callback_data=f"adm_broadcast_view:{job['id']}",
        ))
    if not buttons:
        buttons.append(InlineKeyboardButton("Aucune annonce suivie", callback_data="adm_text_noop"))
    rows = _two_column_rows(buttons)
    rows.append([
        InlineKeyboardButton("🔄 Actualiser", callback_data="adm_broadcast_history"),
        InlineKeyboardButton("⬅️ Administration", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows)


def broadcast_delete_keyboard(job):
    job_id = int(job["id"])
    buttons = []
    if int(job.get("active_message_count") or 0) > 0:
        buttons.append(InlineKeyboardButton(
            "🗑 Supprimer chez tous les clients",
            callback_data=f"adm_broadcast_confirm:{job_id}",
            style="danger",
        ))
    buttons.append(InlineKeyboardButton("⬅️ Historique", callback_data="adm_broadcast_history"))
    return InlineKeyboardMarkup(_two_column_rows(buttons))


def broadcast_delete_confirmation_keyboard(job_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Confirmer la suppression partout",
            callback_data=f"adm_broadcast_delete:{int(job_id)}",
            style="danger",
        ), InlineKeyboardButton("❌ Annuler", callback_data=f"adm_broadcast_view:{int(job_id)}")],
    ])


def user_activity_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualiser", callback_data="adm_user_activity"),
         InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel")],
    ])


def customize_keyboard():
    rows = _two_column_rows([
        InlineKeyboardButton("🧾 Fiche produit", callback_data="adm_text_key:offer_card_template"),
        InlineKeyboardButton("✨ Alertes stocks & flash", callback_data="adm_alert_design"),
        InlineKeyboardButton("✏️ Textes du bot", callback_data="adm_texts"),
        InlineKeyboardButton("🔘 Boutons du bot", callback_data="adm_buttons"),
        InlineKeyboardButton("🎨 Design des tickets", callback_data="adm_ticket_style"),
    ])
    rows.append(
        [InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel")],
    )
    return InlineKeyboardMarkup(rows)


def alert_design_keyboard():
    rows = _two_column_rows([
        InlineKeyboardButton("✨ Nouveau stock (un produit)", callback_data="adm_text_key:channel_stock_announcement"),
        InlineKeyboardButton("✨ Offre remise en avant", callback_data="adm_text_key:offer_stock_announcement"),
        InlineKeyboardButton("🔥 Vente flash", callback_data="adm_text_key:flash_sale_announcement"),
    ])
    rows.append(
        [InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize")],
    )
    return InlineKeyboardMarkup(rows)


def ticket_style_keyboard():
    rows = _two_column_rows([
        InlineKeyboardButton("✏️ Modifier le titre", callback_data="adm_ticket_style_edit:title"),
        InlineKeyboardButton("↩️ Modifier l’instruction de réponse", callback_data="adm_ticket_style_edit:reply_hint"),
        InlineKeyboardButton("🏷️ Modifier la signature", callback_data="adm_ticket_style_edit:footer"),
        InlineKeyboardButton("👁 Aperçu", callback_data="adm_ticket_style_preview"),
        InlineKeyboardButton("♻️ Restaurer le design", callback_data="adm_ticket_style_reset"),
    ])
    rows.append(
        [InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize")],
    )
    return InlineKeyboardMarkup(rows)


def texts_editor_keyboard(page=0, page_size=8):
    keys = sorted(TRANSLATIONS)
    total_pages = max(1, (len(keys) + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    visible = keys[page * page_size:(page + 1) * page_size]
    rows = _two_column_rows([
        InlineKeyboardButton(f"✏️ {text_entry_label(key)}", callback_data=f"adm_text_key:{key}")
        for key in visible
    ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_text_page:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="adm_text_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_text_page:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize")])
    return InlineKeyboardMarkup(rows)


def text_languages_keyboard(key):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data=f"adm_text_lang:{key}:en"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data=f"adm_text_lang:{key}:ar"),
        ],
        [InlineKeyboardButton("⬅️ Catégories", callback_data="adm_texts")],
    ])


def text_navigator_keyboard(index):
    keys = sorted(TRANSLATIONS)
    index = max(0, min(int(index), len(keys) - 1))
    key = keys[index]
    rows = [
        [InlineKeyboardButton("🇬🇧 English", callback_data=f"adm_text_lang:{key}:en")],
    ]
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_text_view:{index - 1}"))
    nav.append(InlineKeyboardButton(f"{index + 1}/{len(keys)}", callback_data="adm_text_noop"))
    if index < len(keys) - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_text_view:{index + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize")])
    return InlineKeyboardMarkup(rows)


def buttons_editor_keyboard():
    hidden = set(filter(None, (db.get_setting("hidden_home_actions", "") or "").split(",")))
    standard = [
        ("catalog", "Shop"),
        ("topup", "Deposit"), ("profile_withdraw", "Withdraw"),
        ("account", "My account"), ("profile_notifications", "Notifications"),
        ("warranty", "Warranty"), ("support", "Support"),
        ("language", "Language"),
    ]
    rows = _two_column_rows([InlineKeyboardButton(
        f"{'❌ Masqué' if action in hidden else '✅ Visible'} — {label}",
        callback_data=f"adm_btn_toggle:{action}",
    ) for action, label in standard])
    custom_buttons = [InlineKeyboardButton(
            f"🗑 {button.get('label_en') or button.get('label_ar') or 'Button'}",
            callback_data=f"adm_btn_del:{button['id']}",
        ) for button in db.list_custom_buttons(active_only=False)]
    rows.extend(_two_column_rows(custom_buttons))
    rows.append([
        InlineKeyboardButton("➕ Ajouter un bouton URL", callback_data="adm_btn_add"),
        InlineKeyboardButton("⬅️ Personnalisation", callback_data="adm_customize"),
    ])
    return InlineKeyboardMarkup(rows)


def tickets_keyboard():
    tickets = db.list_tickets(limit=50)
    buttons = [InlineKeyboardButton("🎨 Design des tickets", callback_data="adm_ticket_style")]
    buttons.extend(InlineKeyboardButton(
        f"#{x['id']} • utilisateur {x['user_id']}", callback_data=f"adm_ticket:{x['id']}"
    ) for x in tickets)
    rows = _two_column_rows(buttons)
    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel")])
    return InlineKeyboardMarkup(rows), tickets


def orders_list_keyboard(status):
    orders = db.list_orders(status=status, limit=50)
    rows = _two_column_rows([InlineKeyboardButton(
        f"#{o['id']} • {o['offer_name']} • {o['total_price']:.2f} {CURRENCY}",
        callback_data=f"adm_order:{o['id']}",
    ) for o in orders])
    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel")])
    return InlineKeyboardMarkup(rows), orders


def build_order_table(rows, max_val_len=24):
    """Build a clean box-drawing table for monospace rendering in Telegram."""
    processed = []
    for k, v in rows:
        v_str = str(v)
        if len(v_str) > max_val_len:
            v_str = v_str[:max_val_len - 1] + "…"
        processed.append((k, v_str))
    col1_w = max(len(r[0]) for r in processed)
    col2_w = max(len(r[1]) for r in processed)
    top = "┌" + "─" * (col1_w + 2) + "┬" + "─" * (col2_w + 2) + "┐"
    sep = "├" + "─" * (col1_w + 2) + "┼" + "─" * (col2_w + 2) + "┤"
    bot = "└" + "─" * (col1_w + 2) + "┴" + "─" * (col2_w + 2) + "┘"
    lines = [top]
    for i, (k, v) in enumerate(processed):
        lines.append(f"│ {k.ljust(col1_w)} │ {v.ljust(col2_w)} │")
        if i == 0:
            lines.append(sep)
    lines.append(bot)
    return "\n".join(lines)


def order_report(o):
    """Return the complete copyable order report, including decrypted delivery."""
    if not o:
        return "Commande introuvable."
    context = _full_order_context(int(o.get("id") or 0))
    if not context["order"]:
        context["order"] = dict(o)
    content = context["delivery_items"]
    report = _context_table(context, heading="ORDER FULL INFORMATION")
    report += "\n\nREAL DELIVERED CONTENT\n"
    report += "\n\n".join(content) if content else "[no decrypted delivery content persisted]"
    return report


def order_detail_text(o):
    if not o:
        return "Commande introuvable."
    status = str(o.get("status") or "").strip().lower()
    is_delivered = status in {"delivered", "completed"} or bool(o.get("delivered_at"))
    if is_delivered:
        statut_val, livraison_val, delivery_badge = "LIVRÉE", "OUI (Délivrée)", "✅ DÉLIVRÉE"
    elif status in {"paid", "payment_confirmed", "confirmed_no_delivery"}:
        statut_val, livraison_val, delivery_badge = "PAYÉE", "NON (Manuelle)", "⏳ NON DÉLIVRÉE"
    elif status == "pending_payment":
        statut_val, livraison_val, delivery_badge = "IMPAYÉE", "NON (En attente)", "⏳ NON DÉLIVRÉE"
    elif status == "cancelled":
        statut_val, livraison_val, delivery_badge = "ANNULÉE", "NON (Annulée)", "❌ ANNULÉE"
    else:
        statut_val, livraison_val, delivery_badge = status.upper() or "INCONNU", "NON", "❓ EN COURS"

    user_id = str(o.get("user_id") or "—")
    user_doc = db.get_conn().users.find_one({"telegram_id": int(user_id)}) if user_id.isdigit() else None
    user_display = f"{user_id} (@{user_doc['username']})" if user_doc and user_doc.get("username") else user_id
    legacy = build_order_table([
        ("Champ", "Détail"),
        ("Commande", f"#{o.get('id', '—')}"),
        ("Statut", statut_val),
        ("Livraison", livraison_val),
        ("Client", user_display),
        ("Service", str(o.get("service_name") or "—")),
        ("Offre", str(o.get("offer_name") or "—")),
        ("Quantité", str(o.get("qty") or 1)),
        ("Total", f"{db.order_charge_total(o):.2f} {o.get('currency') or CURRENCY}"),
        ("Garantie", str(warranty_service.order_warranty_label(o) or "—")),
        ("Paiement", str(o.get("verify_method") or o.get("payment_method") or "—")),
        ("TXID", str(o.get("txid") or "—")),
    ])
    report = f"{delivery_badge}\n\n{legacy}\n\n{order_report(o)}"
    # Telegram Markdown code blocks are copyable; neutralize embedded backticks.
    safe_report = report.replace("```", "'''")
    return f"🧾 COMMANDE #{o.get('id')}\n\n```\n{safe_report}\n```"


def order_detail_keyboard(o):
    rows = []
    if o and o["status"] in {"paid", "payment_confirmed"}:
        if db.is_otp_service_name(o.get("service_name")):
            workflow = str(o.get("otp_workflow_status") or "")
            if workflow == "customer_agreed":
                rows.extend(codex_otp_request_keyboard(o["id"]).inline_keyboard)
            elif workflow != "number_sent":
                rows.extend(codex_number_request_keyboard(o["id"]).inline_keyboard)
        else:
            rows.extend(manual_delivery_request_keyboard(o["id"]).inline_keyboard)
    if o:
        rows.append([InlineKeyboardButton(
            "📄 Full copyable report",
            callback_data=f"adm_order_report:{int(o['id'])}",
            style="primary",
        )])
    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel")])
    return InlineKeyboardMarkup(rows)


def manual_delivery_request_keyboard(order_id):
    """Let the administrator message the customer or complete the delivery."""
    order_id = int(order_id)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💬 Envoyer un message",
            callback_data=f"adm_client_message:{order_id}",
        ),
        InlineKeyboardButton(
            "🎁 Envoyer la commande",
            callback_data=f"adm_deliver:{order_id}",
            style="success",
        ),
    ]])


def codex_number_request_keyboard(order_id):
    """Start the first stage of a paid Codex-number order."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📱 Send number",
            callback_data=f"adm_codex_number:{int(order_id)}",
            style="success",
        ),
    ]])


def codex_otp_request_keyboard(order_id):
    """Allow OTP entry only after the customer accepted the number."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔐 Send OTP code",
            callback_data=f"adm_codex_otp:{int(order_id)}",
            style="success",
        ),
    ]])


def onchain_payment_review_keyboard(order_id):
    """Accept or reject one pending BSC/Polygon payment."""
    order_id = int(order_id)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Accepter",
            callback_data=f"adm_onchain_approve:{order_id}",
            style="success",
        ),
        InlineKeyboardButton(
            "❌ Refuser",
            callback_data=f"adm_onchain_reject:{order_id}",
            style="danger",
        ),
    ]])


def catalog_admin_keyboard():
    service_buttons = [InlineKeyboardButton(
        _service_button_text(s),
        callback_data=f"adm_svc:{s['id']}",
        icon_custom_emoji_id=_safe_custom_emoji_id(s.get("custom_emoji_id")),
        style=None if db.is_official_subscriptions_service(s) else (
            "success" if s["active"] else "danger"
        ),
    ) for s in db.list_services(active_only=False)]
    rows = _two_column_rows(service_buttons)
    rows.append([
        InlineKeyboardButton("➕ Ajouter un service", callback_data="adm_addsvc"),
        InlineKeyboardButton("⬅️ Retour", callback_data="adm_panel"),
    ])
    return InlineKeyboardMarkup(rows)


def service_admin_keyboard(service_id):
    svc = db.get_service(service_id)
    offer_buttons = []
    for offer in db.list_offers(service_id, active_only=False):
        icon_id = _safe_custom_emoji_id(offer.get("custom_emoji_id"))
        emoji = "" if icon_id else str(offer.get("emoji") or svc.get("emoji") or "📦").strip()
        name = _button_bold(offer.get("name") or f"Offre #{offer['id']}")
        offer_buttons.append(InlineKeyboardButton(
            " ".join(part for part in (emoji, name) if part)[:64],
            callback_data=f"adm_off:{offer['id']}",
            icon_custom_emoji_id=icon_id,
            style="success" if offer["active"] else "danger",
        ))
    rows = _two_column_rows(offer_buttons)
    rows.extend([
        [InlineKeyboardButton("➕ Ajouter une offre", callback_data=f"adm_addoff:{service_id}"),
         InlineKeyboardButton("✏️ Nom", callback_data=f"adm_svcname:{service_id}")],
        [InlineKeyboardButton("⬅️ Emoji gauche", callback_data=f"adm_svcemoji:{service_id}"),
         InlineKeyboardButton("Emoji droit ➡️", callback_data=f"adm_svcsuffix:{service_id}")],
        [InlineKeyboardButton("⏸ Désactiver" if svc["active"] else "▶️ Activer",
                              callback_data=f"adm_svctoggle:{service_id}"),
         InlineKeyboardButton("🗑 Archiver", callback_data=f"adm_svcdel:{service_id}")],
    ])
    rows.append([InlineKeyboardButton("⬅️ Catalogue", callback_data="adm_catalog")])
    return InlineKeyboardMarkup(rows)


def offer_admin_keyboard(offer_id):
    off = db.get_offer(offer_id)
    service = db.get_service(off.get("service_id")) or {}
    is_method = str(service.get("name") or "").strip().lower() == "methods"
    is_bot_package = off.get("feature_key") == "bot_like_mine"
    method_media = off.get("method_media") or []
    option_buttons = []
    if is_bot_package:
        option_buttons.extend([
            InlineKeyboardButton(
                "📄 Document client" + (" ✅" if off.get("benefits_document_file_id") else ""),
                callback_data=f"adm_bot_package_doc:{offer_id}",
                style="primary",
            ),
            InlineKeyboardButton(
                "🔗 Lien GitHub de livraison" + (" ✅" if off.get("delivery_url") else ""),
                callback_data=f"adm_bot_package_link:{offer_id}",
                style="primary",
            ),
        ])
    if is_method:
        option_buttons.append(InlineKeyboardButton(
            f"🎬 Method content ({len(method_media)})",
            callback_data=f"adm_method_media:{offer_id}",
            style="primary",
        ))
    else:
        option_buttons.append(InlineKeyboardButton(
            "🔐 Ajouter plusieurs comptes", callback_data=f"adm_inventory:{offer_id}"
        ))
    option_buttons.extend([
        InlineKeyboardButton("🖼 Modifier l’image", callback_data=f"adm_offimage:{offer_id}"),
        InlineKeyboardButton("💵 Modifier le prix", callback_data=f"adm_setprice:{offer_id}"),
        InlineKeyboardButton(
            "⏹ Arrêter la vente flash" if off.get("flash_sale_active")
            else "⚡ Lancer une vente flash",
            callback_data=(
                f"adm_flash_stop:{offer_id}"
                if off.get("flash_sale_active")
                else f"adm_flash_start:{offer_id}"
            ),
        ),
        InlineKeyboardButton(
            "📣 Envoyer une annonce (prix + stock)",
            callback_data=f"adm_broadcast_offer:{offer_id}",
        ),
        InlineKeyboardButton(
            "♾ Désactiver le stock illimité" if off.get("unlimited_stock")
            else "♾ Activer le stock illimité",
            callback_data=f"adm_unlimited:{offer_id}",
        ),
        InlineKeyboardButton("✏️ Modifier le nom", callback_data=f"adm_offname:{offer_id}"),
        InlineKeyboardButton("📂 Déplacer vers un autre service", callback_data=f"adm_offmove:{offer_id}"),
        InlineKeyboardButton("🎨 Emoji animé", callback_data=f"adm_offemoji:{offer_id}"),
        InlineKeyboardButton("📄 Description", callback_data=f"adm_offdesc:{offer_id}"),
    ])
    if not is_method:
        option_buttons.extend([
            InlineKeyboardButton("🛡 Garantie", callback_data=f"adm_offnote:{offer_id}"),
            InlineKeyboardButton("📅 Période", callback_data=f"adm_offperiod:{offer_id}"),
        ])
    rows = _two_column_rows(option_buttons)
    rows.extend([
        [InlineKeyboardButton("⏸ Désactiver" if off["active"] else "▶️ Activer",
                              callback_data=f"adm_offtoggle:{offer_id}"),
         InlineKeyboardButton("🗑 Archiver", callback_data=f"adm_offdel:{offer_id}")],
        [InlineKeyboardButton("⬅️ Retour", callback_data=f"adm_svc:{off['service_id']}")],
    ])
    return InlineKeyboardMarkup(rows)


def move_offer_keyboard(offer_id):
    offer = db.get_offer(int(offer_id))
    current_service_id = int((offer or {}).get("service_id") or 0)
    buttons = []
    for service in db.list_services():
        if int(service["id"]) == current_service_id or db.is_otp_service_name(service.get("name")):
            continue
        service_name = service.get("name") or f"Service #{service['id']}"
        buttons.append(InlineKeyboardButton(
            f"{service.get('emoji') or '📦'} {service_name}",
            callback_data=f"adm_offmove_to:{offer_id}:{service['id']}",
        ))
    rows = _two_column_rows(buttons)
    rows.append([InlineKeyboardButton("⬅️ Annuler", callback_data=f"adm_off:{offer_id}")])
    return InlineKeyboardMarkup(rows)


async def post_purchase_to_channel(context, order):
    """Compatibility no-op: purchases must remain private to the customer/admin."""
    return False


async def notify_new_order(context, order):
    await context.bot.send_message(
        ADMIN_ID, order_detail_text(order), parse_mode="Markdown",
        reply_markup=order_detail_keyboard(order),
    )


async def notify_manual_delivery_request(context, order):
    """Request the manual delivery in the private administrator bot chat."""
    await context.bot.send_message(
        ADMIN_ID,
        "📦 *Livraison manuelle demandée*\n\n"
        f"{order_detail_text(order)}\n\n"
        "Choisissez *Envoyer un message* pour informer le client sans terminer "
        "la commande, ou *Envoyer la commande* pour transmettre le compte/code "
        "et confirmer la livraison.",
        parse_mode="Markdown",
        reply_markup=manual_delivery_request_keyboard(order["id"]),
    )
