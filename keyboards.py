"""Constructeurs de claviers inline et reply."""
import html
import re

from telegram import CopyTextButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram import InlineKeyboardButton as _InlineKeyboardButton


def InlineKeyboardButton(*args, style=None, **kwargs):
    # Telegram expects ``icon_custom_emoji_id`` to be an ASCII identifier,
    # not a regular Unicode emoji such as "📦".  A malformed icon makes
    # Telegram reject the entire keyboard, so discard it defensively.
    icon_custom_emoji_id = kwargs.get("icon_custom_emoji_id")
    if icon_custom_emoji_id is not None:
        normalized_icon_id = str(icon_custom_emoji_id).strip()
        kwargs["icon_custom_emoji_id"] = (
            normalized_icon_id
            if normalized_icon_id and normalized_icon_id.isascii()
            else None
        )
    if style in {"primary", "success", "danger"}:
        api_kwargs = kwargs.pop("api_kwargs", None) or {}
        api_kwargs["style"] = style
        kwargs["api_kwargs"] = api_kwargs
    btn = _InlineKeyboardButton(*args, **kwargs)
    if style:
        object.__setattr__(btn, "style", style)
    return btn

import database as db
from config import ADMIN_ID, REQUIRED_CHANNEL
from i18n import t

BUTTON_TEXT_KEYS = {
    "menu_catalog", "menu_methods", "menu_bot_like_mine", "menu_lovable", "menu_orders", "menu_topup", "menu_account", "menu_affiliate",
    "menu_support", "menu_lang", "menu_admin", "menu_reseller_api", "btn_main_menu", "support_no_order",
    "catalog_request_button", "catalog_preorder_button",
    "catalog_notifications_on", "catalog_notifications_off",
    "profile_deposit", "profile_withdraw", "profile_orders", "profile_referral",
    "profile_shop", "profile_notifications", "profile_reseller_api", "profile_main_menu",
    "topup_verify_txid", "topup_verify_bybit", "topup_onchain", "topup_bsc", "topup_polygon",
    "topup_home_button",
    "btn_main_menu_short", "btn_refresh_short", "btn_back_services", "btn_buy", "btn_back", "btn_paid",
    "btn_cancel_short", "btn_verify_txid", "btn_cancel_order", "btn_pay_wallet",
    "btn_pay_binance", "btn_pay_bybit", "btn_pay_bsc", "btn_pay_polygon", "btn_submit_chain_txid",
    "btn_cancel", "btn_continue_payment", "btn_new_order", "btn_reply_manual_order",
    "btn_codex_number_agree",
    "reseller_api_create", "reseller_api_regenerate", "reseller_api_confirm_regenerate",
    "reseller_api_docs", "reseller_api_refresh", "reseller_api_cancel",
    "affiliate_copy", "affiliate_share", "orders_all", "btn_join_channel", "btn_join_group",
    "btn_verify_join", "btn_channel_buy_now",
}


def is_button_text_key(key):
    return key in BUTTON_TEXT_KEYS or str(key).startswith("support_category_")


def clean_translated_button_text(value):
    """Remove stored rich-text markup; Premium emoji is rendered by the icon field."""
    value = str(value or "").removeprefix("[[HTML]]")
    value = re.sub(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"\[\[TGEMOJI:[^\]]+\]\]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(html.unescape(value).split())[:64]


def translated_button(lang, key, *, callback_data=None, url=None, style=None, switch_inline_query=None):
    """Build an inline button with the admin-selected Premium emoji icon."""
    return InlineKeyboardButton(
        clean_translated_button_text(t(lang, key)),
        callback_data=callback_data, url=url, style=style,
        switch_inline_query=switch_inline_query,
        icon_custom_emoji_id=db.get_text_override_icon(key, lang) or None,
    )


def compact_offer_name(name, max_len=34):
    clean_name = " ".join(str(name or "").split())
    if len(clean_name) <= max_len:
        return clean_name
    return clean_name[: max_len - 3].rstrip() + "..."


KNOWN_SERVICE_EMOJIS = {}


def get_service_emoji(name, current_emoji=""):
    emoji = str(current_emoji or "").strip()
    if emoji in {"🟢", "🔴", "🔵", "📦"}:
        return ""
    return emoji


def service_button_label(service, max_len=40):
    """Render configurable Unicode emojis around a service name."""
    service = service or {}
    icon_id = str(service.get("custom_emoji_id") or "").strip()
    has_premium_left_icon = bool(icon_id and icon_id.isascii())
    left = "" if has_premium_left_icon else str(service.get("emoji") or "").strip()
    right = str(service.get("suffix_emoji") or service.get("service_suffix_emoji") or "").strip()
    reserved = len(left) + len(right) + int(bool(left)) + int(bool(right))
    name = compact_offer_name(clean_button_name(service.get("name")) or f"Service #{service.get('id', '')}", max(8, max_len - reserved))
    return " ".join(part for part in (left, name, right) if part).strip()[:64]


def stock_badge(stock, unlimited=False):
    if unlimited:
        return "🟩"
    stock = int(stock or 0)
    if stock > 3:
        return "🟩"
    if stock > 0:
        return "🟦"
    return "🟥"


def stock_button_style(stock):
    """Render available products green and unavailable products red."""
    return "success" if int(stock or 0) > 0 else "danger"


def clean_button_name(value):
    """Remove decorative emoji characters from button text; icons use Telegram's icon field."""
    text = " ".join(str(value or "").split())
    pattern = re.compile(
        r"^[\s\W\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b00-\u2bff\u2000-\u206f]+|"
        r"[\s\W\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b00-\u2bff\u2000-\u206f]+$"
    )
    return pattern.sub("", text).strip()


def offer_period_label(lang, offer):
    """Return the compact period label shown between name and price."""
    try:
        raw = offer.get("period_days")
        if raw is None or raw == "" or int(raw) <= 0:
            raw = offer.get("warranty_days")
        period_days = int(raw or 0)
    except (TypeError, ValueError):
        period_days = 0
    if period_days <= 0:
        note = str(offer.get("note") or "")
        match = re.search(r"(\d{1,3})\s*(?:d|day|days|j|jour|jours)", note, re.I)
        period_days = int(match.group(1)) if match else 30
    if lang == "fr":
        return f"{period_days} j"
    if lang == "ar":
        return f"{period_days} يوم"
    return f"{period_days} day{'s' if period_days != 1 else ''}"


def offer_button_label(lang, offer, *, stock_label=None, price_tbd=None):
    price = offer.get("price")
    if price is None:
        price_text = price_tbd if price_tbd is not None else t(lang, "price_tbd")
    else:
        amount = f"{float(price):.2f}".rstrip("0").rstrip(".")
        currency = str(offer.get("currency") or "USDT").upper()
        price_text = f"${amount}" if currency in {"USD", "USDT"} else f"{amount} {currency}"

    label = stock_label if stock_label is not None else t(lang, "stock_label")
    lbl = str(label or "Stock").title()
    period = offer_period_label(lang, offer)

    icon_id = str(
        offer.get("custom_emoji_id") or offer.get("service_custom_emoji_id") or ""
    ).strip()
    emoji = ""
    if not (icon_id and icon_id.isascii()):
        emoji = str(
            (icon_id if icon_id else offer.get("emoji") or offer.get("service_emoji"))
            or ""
        ).strip()
        if not emoji:
            sid = offer.get("service_id")
            if sid:
                svc = db.get_service(sid)
                if svc:
                    emoji = str(svc.get("emoji") or "").strip()
    clean_name = clean_button_name(offer["name"])

    if offer.get("unlimited_stock"):
        suffix_parts = [p for p in (period, price_text, f"{lbl}: ∞") if p]
        suffix = " | ".join(suffix_parts)
        max_name_length = max(8, 64 - len(suffix) - 3)
        name = compact_offer_name(clean_name, max_name_length - len(emoji) - int(bool(emoji)))
        display_name = " ".join(part for part in (emoji, name) if part)
        return f"{display_name} | {suffix}"

    stock = int(offer.get("stock") or 0)
    suffix_parts = [p for p in (period, price_text, f"{lbl}: {stock}") if p]
    suffix = " | ".join(suffix_parts)
    max_name_length = max(8, 64 - len(suffix) - 3)
    name = compact_offer_name(clean_name, max_name_length - len(emoji) - int(bool(emoji)))
    display_name = " ".join(part for part in (emoji, name) if part)
    return f"{display_name} | {suffix}"


def lang_keyboard():
    active = str(db.shop_settings().get("active_languages") or "en,ar").split(",")
    active = [code.strip() for code in active if code.strip() in {"en", "ar"}]
    if not active:
        active = ["en"]
    labels = {
        "en": ("🇬🇧 English", "lang:en"),
        "ar": ("🇸🇦 العربية", "lang:ar"),
    }
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(labels[code][0], callback_data=labels[code][1])
        for code in active
    ]])


def channel_offer_keyboard(lang, bot_username, offer_id):
    """Open a restocked offer privately from a public channel post."""
    deep_link = f"https://t.me/{str(bot_username).lstrip('@')}?start=offer_{int(offer_id)}"
    return InlineKeyboardMarkup([[
        translated_button(lang, "btn_channel_buy_now", url=deep_link, style="success"),
    ]])

def channel_join_keyboard(lang):
    """Offer the required channel link before unlocking the customer menu."""
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
    return InlineKeyboardMarkup([
        [translated_button(lang, "btn_join_channel", url=channel_url, style="primary")],
        [translated_button(lang, "btn_verify_join", callback_data="verify_channel_join", style="success")],
    ])

def support_category_keyboard(lang):
    categories = ("payment", "delivery", "invalid_content", "order", "affiliation", "other")
    rows = [
        [translated_button(lang, f"support_category_{category}", callback_data=f"support_cat:{category}")]
        for category in categories
    ]
    rows.append([translated_button(lang, "btn_main_menu", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def support_order_keyboard(lang, orders):
    rows = [
        [InlineKeyboardButton(f"#{order['id']} — {order['offer_name']}", callback_data=f"support_order:{order['id']}")]
        for order in orders[:8]
    ]
    rows.append([translated_button(lang, "support_no_order", callback_data="support_order:0")])
    return InlineKeyboardMarkup(rows)


def support_keyboard(lang):
    return InlineKeyboardMarkup([
        [translated_button(lang, "menu_support", callback_data="support_cat:payment")],
        [translated_button(lang, "btn_main_menu", callback_data="home")],
    ])




def ticket_conversation_keyboard(lang, ticket_id):
    close_label = {
        "fr": "Close Ticket",
        "en": "Close Ticket",
        "ar": "Close Ticket",
    }.get(lang, "Close Ticket")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            close_label,
            callback_data=f"ticket_close:{int(ticket_id)}",
            style="danger",
        )],
        [translated_button(lang, "btn_main_menu", callback_data="home")],
    ])
def main_menu_keyboard(lang, user_id):
    hidden = set(filter(None, (db.get_setting("hidden_home_actions", "") or "").split(",")))
    candidates = [
        [("catalog", t(lang, "menu_catalog")), ("orders", t(lang, "menu_orders"))],
        [("bot_like_mine", t(lang, "menu_bot_like_mine"))],
        [("topup", t(lang, "menu_topup"))],
        [("account", t(lang, "menu_account")), ("affiliate", t(lang, "menu_affiliate"))],
        [("support", t(lang, "menu_support")), ("language", t(lang, "menu_lang"))],
    ]
    rows = [[label for action, label in row if action not in hidden] for row in candidates]
    rows = [row for row in rows if row]
    if user_id == ADMIN_ID:
        rows.append([t(lang, "menu_admin")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def home_keyboard(lang, user_id):
    hidden = set(filter(None, (db.get_setting("hidden_home_actions", "") or "").split(",")))
    candidate_rows = [
        [translated_button(lang, "menu_catalog", callback_data="catalog", style="success")],
        [
            translated_button(lang, "menu_methods", callback_data="methods", style="primary"),
            translated_button(
                lang, "menu_bot_like_mine", callback_data="bot_like_mine", style="success",
            ),
        ],
        [
            translated_button(lang, "profile_deposit", callback_data="topup", style="primary"),
            translated_button(lang, "menu_account", callback_data="account", style="primary"),
        ],
        [
            translated_button(lang, "menu_lang", callback_data="language", style="primary"),
            translated_button(lang, "menu_support", callback_data="support", style="danger"),
        ],
    ]
    rows = []
    for row in candidate_rows:
        visible = [button for button in row if button.callback_data not in hidden]
        if visible:
            rows.append(visible)
    for button in db.list_custom_buttons():
        label = button.get(f"label_{lang}") or button.get("label_en") or button.get("label_ar") or "Link"
        rows.append([InlineKeyboardButton(label[:64], url=button["url"], style="success")])
    if user_id == ADMIN_ID:
        rows.append([translated_button(
            lang, "menu_admin", callback_data="adm_panel", style="success",
        )])
    return InlineKeyboardMarkup(rows)


def topup_keyboard(lang):
    return InlineKeyboardMarkup([
        [translated_button(lang, "topup_verify_bybit", callback_data="topup_bybit", style="success")],
        [translated_button(lang, "topup_verify_txid", callback_data="topup_txid", style="success")],
        [translated_button(lang, "topup_onchain", callback_data="topup_onchain", style="success")],
        [translated_button(lang, "topup_home_button", callback_data="home", style="danger")],
    ])


def topup_provider_keyboard(lang, provider, pay_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📋 Copy UID" if provider == "bybit" else "📋 Copy ID",
            copy_text=CopyTextButton(str(pay_id)),
            style="primary",
        )],
        [InlineKeyboardButton("🔄 Change Method", callback_data="topup", style="primary")],
        [translated_button(lang, "topup_home_button", callback_data="home", style="danger")],
    ])


def topup_onchain_keyboard(lang):
    return InlineKeyboardMarkup([
        [translated_button(lang, "topup_bsc", callback_data="topup_bsc", style="primary")],
        [translated_button(lang, "topup_polygon", callback_data="topup_polygon", style="primary")],
        [InlineKeyboardButton("🔄 Change Method", callback_data="topup", style="primary")],
        [translated_button(lang, "topup_home_button", callback_data="home", style="danger")],
    ])


def topup_review_keyboard(topup_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve & credit",
                callback_data=f"adm_topup_approve:{int(topup_id)}",
                style="success",
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"adm_topup_reject:{int(topup_id)}",
                style="danger",
            ),
        ],
    ])


def services_keyboard(lang):
    buttons = []
    services = db.list_services_with_stock()

    # Grouper par catégorie
    categories = {}
    for svc in services:
        cat = svc.get("category") or t(lang, "cat_other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(svc)

    for _cat, svcs in categories.items():
        row = []
        for _i, svc in enumerate(svcs):
            label = service_button_label(svc, 34)
            is_official = db.is_official_subscriptions_service(svc)
            service_button = InlineKeyboardButton(
                label,
                callback_data=f"svc:{svc['id']}",
                style="primary",
                icon_custom_emoji_id=svc.get("custom_emoji_id") or None,
            )
            if is_official:
                if row:
                    buttons.append(row)
                    row = []
                buttons.append([service_button])
                continue
            row.append(service_button)
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    buttons.append([
        translated_button(
            lang, "catalog_request_button",
            callback_data="catalog_request", style="primary",
        ),
    ])
    buttons.append([
        translated_button(
            lang, "btn_refresh_short", callback_data="catalog", style="success",
        ),
        translated_button(
            lang, "btn_main_menu_short", callback_data="home", style="danger",
        ),
    ])
    return InlineKeyboardMarkup(buttons)


def format_split_button_texts(name, price_str, right_text):
    """Format left and right button texts cleanly without duplicate emojis or artificial truncation."""
    clean_r = str(right_text or "").replace("📦", "").strip()
    right_label = f"📦 {clean_r}" if clean_r else "📦 Info"
    p_part = f" | {price_str}" if price_str else ""
    left_label = f"{clean_button_name(name)}{p_part}"
    return left_label, right_label


def catalog_offers_keyboard(lang, catalog_notifications_enabled=True):
    """Group multi-offer services and show single offers directly."""
    buttons = []
    db.preload_text_overrides(
        (
            "stock_label", "price_tbd", "catalog_request_button",
            "catalog_preorder_button", "catalog_notifications_on",
            "catalog_notifications_off", "btn_refresh_short", "btn_main_menu_short",
        ),
        lang,
    )
    stock_label = t(lang, "stock_label")
    price_tbd = t(lang, "price_tbd")
    stock_icon = db.get_text_override_icon("stock_label", lang) or None

    all_offers = db.list_catalog_offers()

    # Group offers by service_id
    service_offers = {}
    for offer in all_offers:
        sid = offer.get("service_id")
        if sid not in service_offers:
            service_offers[sid] = []
        service_offers[sid].append(offer)

    grouped_category_buttons = []
    regular_offer_buttons = []
    added_services = set()

    for offer in all_offers:
        sid = offer.get("service_id")
        offers_in_service = service_offers.get(sid, [])
        # A service only needs its own catalogue screen when there is actually
        # a choice to make.  Single offers are actionable from the main catalog.
        should_group = len(offers_in_service) > 1

        if should_group:
            if sid not in added_services:
                added_services.add(sid)
                service_emoji = get_service_emoji(
                    offer.get("service_name"),
                    offer.get("service_emoji"),
                )
                service_name = (offer.get("service_name") or f"Service #{sid}").strip()
                clean_name = clean_button_name(service_name) or service_name
                service_icon = (
                    offer.get("service_custom_emoji_id")
                    or offer.get("custom_emoji_id")
                    or None
                )
                # Telegram renders the custom icon before the text.  Do not also
                # put the service's Unicode emoji in the label or two icons appear.
                label = service_button_label({
                    "id": sid,
                    "name": clean_name,
                    "emoji": service_emoji,
                    "suffix_emoji": offer.get("service_suffix_emoji"),
                    "custom_emoji_id": service_icon,
                }, 46)
                grouped_category_buttons.append((
                    InlineKeyboardButton(
                        label,
                        callback_data=f"svc:{sid}",
                        style="primary",
                        icon_custom_emoji_id=service_icon,
                    ),
                    db.is_official_subscriptions_service(service_name),
                ))
        else:
            safe_offer = dict(offer)
            safe_offer["name"] = clean_button_name(offer.get("name")) or f"Offer #{offer['id']}"
            stock = int(offer.get("stock") or 0)
            is_out = not offer.get("unlimited_stock") and stock <= 0
            cb_data = f"off:{offer['id']}"
            btn_style = "danger" if is_out else ("success" if offer.get("unlimited_stock") else stock_button_style(stock))
            regular_offer_buttons.append([InlineKeyboardButton(
                offer_button_label(
                    lang, safe_offer,
                    stock_label=stock_label,
                    price_tbd=price_tbd,
                ),
                callback_data=cb_data,
                style=btn_style,
                icon_custom_emoji_id=(
                    stock_icon
                    or offer.get("custom_emoji_id")
                    or offer.get("service_custom_emoji_id")
                    or None
                ),
            )])

    # 1. Place grouped category buttons (Adobe, ChatGPT, Telegram, VPNs, Netflix) AT THE TOP in rows of 2
    row = []
    for btn, is_official in grouped_category_buttons:
        if is_official:
            if row:
                buttons.append(row)
                row = []
            buttons.append([btn])
            continue
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # 2. Add individual offer buttons below
    buttons.extend(regular_offer_buttons)

    buttons.append([
        translated_button(
            lang,
            "catalog_preorder_button",
            callback_data="preorder_catalog",
            style="primary",
        ),
    ])
    buttons.append([
        translated_button(
            lang, "catalog_request_button",
            callback_data="catalog_request", style="primary",
        ),
    ])
    notification_key = (
        "catalog_notifications_on"
        if catalog_notifications_enabled
        else "catalog_notifications_off"
    )
    buttons.append([
        translated_button(
            lang,
            notification_key,
            callback_data="catalog_notifications_toggle",
            style="success" if catalog_notifications_enabled else "danger",
        ),
    ])
    buttons.append([
        translated_button(
            lang, "btn_refresh_short", callback_data="catalog", style="success",
        ),
        translated_button(
            lang, "btn_main_menu_short", callback_data="home", style="danger",
        ),
    ])
    return InlineKeyboardMarkup(buttons)


def offers_keyboard(lang, service_id):
    buttons = []
    service = db.get_service(service_id)
    svc_emoji = (service.get("emoji") or "").strip() if service else ""
    for off in db.list_offers(service_id):
        safe_offer = dict(off)
        off_name = (off.get("name") or f"Offre #{off['id']}").strip()
        clean_name = clean_button_name(off_name) or off_name
        emoji = (safe_offer.get("emoji") or svc_emoji).strip()
        safe_offer["service_emoji"] = emoji
        safe_offer["service_custom_emoji_id"] = (
            service.get("custom_emoji_id") if service else None
        )
        button_icon = (
            db.get_text_override_icon("stock_label", lang)
            or off.get("custom_emoji_id")
            or (service.get("custom_emoji_id") if service else None)
            or None
        )
        if emoji and not button_icon and not off_name.startswith(emoji):
            safe_offer["name"] = f"{emoji} {clean_name}"
        else:
            safe_offer["name"] = clean_name

        stock = int(off.get("stock") or 0)
        is_out = not off.get("unlimited_stock") and stock <= 0
        cb_data = f"off:{off['id']}"
        btn_style = "danger" if is_out else ("success" if off.get("unlimited_stock") else stock_button_style(stock))

        buttons.append([InlineKeyboardButton(
            offer_button_label(lang, safe_offer),
            callback_data=cb_data,
            style=btn_style,
            icon_custom_emoji_id=button_icon,
        )])
    buttons.append([translated_button(lang, "btn_back_services", callback_data="catalog")])
    return InlineKeyboardMarkup(buttons)


def offer_detail_keyboard(lang, offer):
    buttons = []
    if offer.get("feature_key") == "bot_like_mine":
        buttons.append([translated_button(
            lang,
            "btn_bot_package_preview",
            callback_data=f"bot_package_preview:{offer['id']}",
            style="primary",
        )])
    if offer.get("price") is not None and db.offer_has_stock(offer):
        buttons.append([translated_button(lang, "btn_buy", callback_data=f"buy:{offer['id']}")])
    buttons.append([translated_button(lang, "btn_back", callback_data="catalog")])
    return InlineKeyboardMarkup(buttons)


def _preorder_catalog_offers(service_id=None):
    """Return active, priced physical offers that currently have no stock."""
    return [
        offer
        for offer in db.list_catalog_offers()
        if (
            (service_id is None or int(offer.get("service_id") or 0) == int(service_id))
            and offer.get("price") is not None
            and not offer.get("unlimited_stock")
            and int(offer.get("stock") or 0) <= 0
        )
    ]


def preorder_services_keyboard(lang):
    """List services containing pre-orderable offers as red Telegram buttons."""
    services = {}
    for offer in _preorder_catalog_offers():
        service_id = int(offer["service_id"])
        services.setdefault(service_id, offer)

    rows, row = [], []
    for service_id, offer in services.items():
        service_name = str(offer.get("service_name") or f"Service #{service_id}").strip()
        service_icon = offer.get("service_custom_emoji_id") or None
        label = service_button_label({
            "name": service_name,
            "emoji": offer.get("service_emoji"),
            "custom_emoji_id": service_icon,
            "suffix_emoji": offer.get("service_suffix_emoji"),
        }, 28)
        is_official = db.is_official_subscriptions_service(service_name)
        service_button = InlineKeyboardButton(
            label,
            callback_data=f"preorder_svc:{service_id}",
            style="primary",
            icon_custom_emoji_id=service_icon,
        )
        if is_official:
            if row:
                rows.append(row)
                row = []
            rows.append([service_button])
            continue
        row.append(service_button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([translated_button(lang, "btn_back", callback_data="catalog")])
    return InlineKeyboardMarkup(rows)


def profile_keyboard(lang):
    """Compact profile navigation matching the two-column customer layout."""
    return InlineKeyboardMarkup([
        [
            translated_button(lang, "profile_deposit", callback_data="topup", style="success"),
        ],
        [
            translated_button(lang, "profile_withdraw", callback_data="profile_withdraw", style="primary"),
            translated_button(lang, "profile_notifications", callback_data="profile_notifications", style="primary"),
        ],
        [
            translated_button(lang, "profile_orders", callback_data="orders", style="primary"),
            translated_button(lang, "menu_warranty", callback_data="warranty", style="primary"),
        ],
        [
            translated_button(lang, "profile_referral", callback_data="affiliate", style="primary"),
            translated_button(lang, "profile_shop", callback_data="catalog", style="primary"),
        ],
        [translated_button(lang, "profile_reseller_api", callback_data="reseller_api", style="success")],
        [translated_button(lang, "profile_main_menu", callback_data="home", style="danger")],
    ])


def withdrawal_methods_keyboard(lang):
    labels = {
        "fr": [("Binance ID", "binance"), ("Bybit ID", "bybit"), ("Adresse USDT BEP20", "bep20")],
        "en": [("Binance ID", "binance"), ("Bybit ID", "bybit"), ("USDT BEP20 address", "bep20")],
        "ar": [("Binance ID", "binance"), ("Bybit ID", "bybit"), ("عنوان USDT BEP20", "bep20")],
    }
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"withdraw_method:{method}")]
        for label, method in labels.get(lang, labels["en"])
    ] + [[translated_button(lang, "menu_account", callback_data="account")]])


def withdrawal_admin_keyboard(withdrawal_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Done",
            callback_data=f"adm_withdraw_done:{int(withdrawal_id)}",
            style="success",
        ),
    ]])


def warranty_orders_keyboard(lang, orders):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛡️ #{int(order['id'])} · {str(order.get('offer_name') or order.get('service_name') or 'Product')[:40]}", callback_data=f"warranty_order:{int(order['id'])}")]
        for order in orders
    ] + [[translated_button(lang, "menu_account", callback_data="account")]])


def warranty_review_keyboard(request_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"adm_warranty_accept:{int(request_id)}", style="success"),
        InlineKeyboardButton("❌ Refuse", callback_data=f"adm_warranty_refuse:{int(request_id)}", style="danger"),
    ]])


def warranty_resolution_keyboard(request_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔁 Replacement", callback_data=f"adm_warranty_resolve:replacement:{int(request_id)}", style="primary"),
        InlineKeyboardButton("💰 Refund", callback_data=f"adm_warranty_resolve:refund:{int(request_id)}", style="success"),
    ]])


def profile_notifications_keyboard(lang, user_id, enabled, page=0, page_size=8):
    """Show a master switch plus paginated notification switches per product."""
    notification_key = "catalog_notifications_on" if enabled else "catalog_notifications_off"
    offers = db.list_catalog_offers()
    total_pages = max(1, (len(offers) + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    page_offers = offers[page * page_size:(page + 1) * page_size]
    disabled = db.disabled_catalog_notification_offer_ids(
        user_id, [offer["id"] for offer in page_offers],
    )
    rows = [
        [translated_button(
            lang,
            notification_key,
            callback_data="profile_catalog_notifications_toggle",
            style="success" if enabled else "danger",
        )],
    ]
    for offer in page_offers:
        offer_id = int(offer["id"])
        product_enabled = offer_id not in disabled
        service = clean_button_name(offer.get("service_name"))
        name = clean_button_name(offer.get("name")) or f"Product #{offer_id}"
        product_name = f"{service} — {name}" if service else name
        status = "🔔" if product_enabled else "🔕"
        rows.append([InlineKeyboardButton(
            f"{status} {compact_offer_name(product_name, 57)}",
            callback_data=f"profile_product_notification:{offer_id}:{page}",
            style="success" if product_enabled else "danger",
        )])
    if not page_offers:
        rows.append([InlineKeyboardButton("—", callback_data="profile_notifications")])
    if total_pages > 1:
        pagination = []
        if page > 0:
            pagination.append(InlineKeyboardButton(
                "⬅️", callback_data=f"profile_notifications_page:{page - 1}",
            ))
        pagination.append(InlineKeyboardButton(
            f"{page + 1}/{total_pages}", callback_data=f"profile_notifications_page:{page}",
        ))
        if page + 1 < total_pages:
            pagination.append(InlineKeyboardButton(
                "➡️", callback_data=f"profile_notifications_page:{page + 1}",
            ))
        rows.append(pagination)
    rows.append([translated_button(lang, "menu_account", callback_data="account")])
    return InlineKeyboardMarkup(rows)


def profile_back_keyboard(lang):
    return InlineKeyboardMarkup([[
        translated_button(lang, "menu_account", callback_data="account"),
    ]])


def lovable_home_keyboard(lang, *, is_admin=False):
    rows = [
        [InlineKeyboardButton("📘 How to use", callback_data="lovable_howto")],
        [InlineKeyboardButton("🛒 Buy access", callback_data="lovable_buy", style="success")],
        [InlineKeyboardButton("⬇️ Download extension", callback_data="lovable_download")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(
            "📤 Upload extension ZIP", callback_data="adm_lovable_upload",
            style="primary",
        )])
    rows.append([translated_button(lang, "btn_main_menu_short", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def lovable_plans_keyboard(lang):
    db.ensure_lovable_unlimited_feature()
    offers = list(db.get_conn().offers.find({
        "feature_key": "lovable_unlimited", "active": 1,
    }).sort("duration_days", 1))
    rows = [[InlineKeyboardButton(
        "🎁 Free trial — 1 hour", callback_data="lovable_trial", style="primary",
    )]]
    for offer in offers:
        days = int(offer.get("duration_days") or 0)
        day_label = "day" if days == 1 else "days"
        rows.append([InlineKeyboardButton(
            f"💗 {days} {day_label} — ${float(offer.get('price') or 0):g}",
            callback_data=f"buyq:{int(offer['id'])}:1",
            style="success" if days == 30 else None,
        )])
    rows.append([InlineKeyboardButton("⬅️ Lovable", callback_data="lovable")])
    return InlineKeyboardMarkup(rows)


def lovable_back_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Lovable", callback_data="lovable"),
        translated_button(lang, "btn_main_menu_short", callback_data="home"),
    ]])


def reseller_api_keyboard(lang, *, has_key, docs_url):
    rows = []
    if has_key:
        rows.append([translated_button(
            lang, "reseller_api_regenerate", callback_data="reseller_api_regen",
        )])
    else:
        rows.append([translated_button(
            lang, "reseller_api_create", callback_data="reseller_api_create", style="success",
        )])
    rows.extend([
        [translated_button(lang, "reseller_api_docs", url=docs_url)],
        [translated_button(lang, "reseller_api_refresh", callback_data="reseller_api")],
        [translated_button(lang, "btn_main_menu", callback_data="home")],
    ])
    return InlineKeyboardMarkup(rows)


def reseller_api_regenerate_keyboard(lang):
    return InlineKeyboardMarkup([
        [translated_button(
            lang, "reseller_api_confirm_regenerate",
            callback_data="reseller_api_regen_confirm", style="danger",
        )],
        [translated_button(lang, "reseller_api_cancel", callback_data="reseller_api")],
    ])


def preorder_offers_keyboard(lang, service_id):
    """List only empty offers for one service, displaying the 10%-adjusted price."""
    from app.domain.order_service import preorder_unit_price

    rows = []
    for offer in _preorder_catalog_offers(service_id):
        adjusted_offer = dict(offer)
        adjusted_offer["name"] = clean_button_name(offer.get("name")) or f"Offer #{offer['id']}"
        adjusted_offer["price"] = preorder_unit_price(offer["price"])
        rows.append([InlineKeyboardButton(
            offer_button_label(lang, adjusted_offer),
            callback_data=f"preorder_start:{offer['id']}",
            style="danger",
            icon_custom_emoji_id=(
                db.get_text_override_icon("stock_label", lang)
                or offer.get("custom_emoji_id")
                or offer.get("service_custom_emoji_id")
                or None
            ),
        )])
    rows.append([translated_button(lang, "btn_back", callback_data="preorder_catalog")])
    return InlineKeyboardMarkup(rows)


def out_of_stock_keyboard(lang):
    """Return to the catalog without exposing the retired direct pre-order action."""
    return InlineKeyboardMarkup([[
        translated_button(lang, "btn_back", callback_data="catalog"),
    ]])


def quantity_keyboard(lang, offer, page=0, page_size=20):
    stock = 100 if offer.get("unlimited_stock") else max(1, int(offer.get("stock", 1)))
    total_pages = max(1, (stock + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    start = page * page_size + 1
    end = min(stock, start + page_size - 1)
    rows = []
    row = []
    for qty in range(start, end + 1):
        row.append(InlineKeyboardButton(str(qty), callback_data=f"buyq:{offer['id']}:{qty}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"qty_page:{offer['id']}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"qty_page:{offer['id']}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([translated_button(lang, "btn_back", callback_data=f"off:{offer['id']}")])
    return InlineKeyboardMarkup(rows)


def preorder_quantity_keyboard(lang, offer_id, page=0, page_size=20, max_qty=100):
    """Quantity picker for pre-orders, which are not limited by current stock."""
    total_pages = max(1, (max_qty + page_size - 1) // page_size)
    page = max(0, min(int(page), total_pages - 1))
    start = page * page_size + 1
    end = min(max_qty, start + page_size - 1)
    rows, row = [], []
    for qty in range(start, end + 1):
        row.append(InlineKeyboardButton(str(qty), callback_data=f"preorderq:{int(offer_id)}:{qty}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"preorder_page:{int(offer_id)}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"preorder_page:{int(offer_id)}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([translated_button(lang, "btn_back", callback_data=f"off:{int(offer_id)}")])
    return InlineKeyboardMarkup(rows)


def paid_keyboard(lang, order_id, binance_id="", total="", currency="USDT"):
    return InlineKeyboardMarkup([
        [translated_button(lang, "btn_verify_txid", callback_data=f"paid:{order_id}", style="success")],
        [
            translated_button(lang, "btn_cancel_short", callback_data=f"cancel_buy:{order_id}"),
            translated_button(lang, "btn_main_menu_short", callback_data="home"),
        ],
    ])


def txid_verify_keyboard(lang, order_id):
    return InlineKeyboardMarkup([
        [translated_button(lang, "btn_verify_txid", callback_data=f"paid:{order_id}")],
        [translated_button(lang, "btn_cancel_order", callback_data=f"cancel_buy:{order_id}")],
        [translated_button(lang, "btn_main_menu_short", callback_data="home")],
    ])


def orders_services_keyboard(lang, groups, total):
    rows = [
        [InlineKeyboardButton(
            f"{group['emoji']} {compact_offer_name(group['name'], 28)} ({group['count']})",
            callback_data=f"orders_group:{index}",
            style="primary",
        )]
        for index, group in enumerate(groups)
    ]
    rows.append([InlineKeyboardButton(
        t(lang, "orders_all", count=total),
        callback_data="orders_export:all",
        style="success",
        icon_custom_emoji_id=db.get_text_override_icon("orders_all", lang) or None,
    )])
    rows.append([translated_button(lang, "btn_back", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def orders_keyboard(lang, orders=None):
    """Small generic navigation keyboard kept for help and order detail views."""
    return InlineKeyboardMarkup([[
        translated_button(lang, "menu_orders", callback_data="orders"),
        translated_button(lang, "btn_main_menu_short", callback_data="home"),
    ]])


def confirm_buy_keyboard(lang, offer_id, qty=1, preorder=False):
    """Clavier de confirmation avant achat."""
    suffix = ":preorder" if preorder else ""
    return InlineKeyboardMarkup([
        [translated_button(lang, "btn_pay_wallet", callback_data=f"pay_wallet:{offer_id}:{qty}{suffix}")],
        [translated_button(lang, "btn_pay_binance", callback_data=f"pay_binance:{offer_id}:{qty}{suffix}")],
        [translated_button(lang, "btn_pay_bybit", callback_data=f"pay_bybit:{offer_id}:{qty}{suffix}")],
        [translated_button(lang, "btn_pay_bsc", callback_data=f"pay_bsc:{offer_id}:{qty}{suffix}")],
        [translated_button(lang, "btn_pay_polygon", callback_data=f"pay_polygon:{offer_id}:{qty}{suffix}")],
        [translated_button(lang, "btn_cancel", callback_data=f"cancel_buy:{offer_id}")],
    ])


def onchain_payment_keyboard(lang, order_id):
    return InlineKeyboardMarkup([
        [translated_button(
            lang, "btn_submit_chain_txid",
            callback_data=f"paid_chain:{int(order_id)}",
            style="success",
        )],
        [translated_button(
            lang, "btn_cancel_order",
            callback_data=f"cancel_buy:{int(order_id)}",
            style="danger",
        )],
    ])


def manual_order_reply_keyboard(lang, order_id):
    """Let a customer reply while a manual order is awaiting delivery."""
    return InlineKeyboardMarkup([[
        translated_button(
            lang,
            "btn_reply_manual_order",
            callback_data=f"manual_reply:{int(order_id)}",
            style="primary",
        ),
    ]])


def codex_number_agree_keyboard(lang, order_id):
    """Require explicit customer acceptance before the OTP can be sent."""
    return InlineKeyboardMarkup([[
        translated_button(
            lang,
            "btn_codex_number_agree",
            callback_data=f"codex_number_agree:{int(order_id)}",
            style="success",
        ),
    ]])


def duplicate_order_keyboard(lang, existing_order_id, offer_id, qty=1):
    """Clavier lorsqu'une commande identique existe déjà."""
    return InlineKeyboardMarkup([
        [translated_button(lang, "btn_continue_payment", callback_data=f"continue_pay:{existing_order_id}")],
        [translated_button(lang, "btn_new_order", callback_data=f"confirm_buy:{offer_id}:{qty}")],
        [translated_button(lang, "btn_cancel", callback_data=f"cancel_buy:{offer_id}")],
    ])


def post_delivery_keyboard(lang, order_id):
    """Keep customers inside the bot after delivery."""
    return InlineKeyboardMarkup([
        [translated_button(lang, "menu_catalog", callback_data="catalog")],
    ])


def rating_keyboard(order_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{score}⭐", callback_data=f"rating:{order_id}:{score}")
        for score in range(1, 6)
    ]])


def affiliate_keyboard(lang, referral_link, share_text):
    return InlineKeyboardMarkup([
        [translated_button(lang, "affiliate_copy", callback_data="affiliate_copy")],
        [translated_button(lang, "affiliate_share", switch_inline_query=share_text)],
        [translated_button(lang, "btn_main_menu_short", callback_data="home")],
    ])
