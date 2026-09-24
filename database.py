"""MongoDB persistence for users, catalogue, orders, and affiliate data."""
import contextlib
import base64
import hashlib
import os
import re
import time
import unicodedata
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.domain import warranty_service
from config import INVENTORY_KEY, MONGODB_DB, MONGODB_URI

_client = None
_db = None
_schema_initialized = False
SCHEMA_VERSION = 26
CODEX_ACCEPTANCE_SECONDS = 5 * 60
_text_override_cache: dict[tuple[str, str], tuple[float, dict | None]] = {}
TEXT_OVERRIDE_CACHE_SECONDS = 60


def _normalized_service_name(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.encode("ascii", "ignore").decode()).split())


def is_official_subscriptions_service(value):
    """Return whether a service is the catalogue that must stay pinned first."""
    name = value.get("name") if isinstance(value, dict) else value
    tokens = _normalized_service_name(name).split()
    has_official = any(
        token.startswith("official") or token.startswith("officiel")
        for token in tokens
    )
    has_subscription = any(token.startswith("subscri") for token in tokens)
    return has_official and has_subscription


def _service_sort_key(service):
    # The owner's official-subscriptions catalogue is always pinned first,
    # independently of accents, casing, or its stored sort_order.
    pinned = 0 if is_official_subscriptions_service(service) else 1
    return pinned, int(service.get("sort_order", 0)), int(service.get("id", 0))


def is_otp_service_name(value):
    """Return whether a service uses the legacy OTP / Codex-number flow."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())
    tokens = set(normalized.split())
    return (
        "number" in tokens or "numbers" in tokens
    ) and ("otp" in tokens or "codex" in tokens)


def expire_codex_number_acceptance(order_id, now=None):
    """Atomically expire one paid Codex order whose acceptance window elapsed."""
    now = int(time.time() if now is None else now)
    row = get_conn().orders.find_one_and_update(
        {
            "id": int(order_id),
            "status": {"$in": ["paid", "payment_confirmed"]},
            "otp_workflow_status": "number_sent",
            "codex_agree_deadline": {"$lte": now, "$gt": 0},
        },
        {"$set": {
            "status": "expired",
            "otp_workflow_status": "acceptance_expired",
            "codex_expired_at": now,
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if row:
        audit_event("order.codex_acceptance_expired", details={"order_id": int(order_id)})
    return _public(row)


def due_codex_number_acceptances(now=None):
    """Return IDs that are ready for the five-minute acceptance expiry."""
    now = int(time.time() if now is None else now)
    return [
        int(row["id"])
        for row in get_conn().orders.find(
            {
                "status": {"$in": ["paid", "payment_confirmed"]},
                "otp_workflow_status": "number_sent",
                "codex_agree_deadline": {"$lte": now, "$gt": 0},
            },
            {"id": 1},
        )
    ]


def _otp_offer_values():
    return {
        "price": 0.5,
        "currency": "USDT",
        "unlimited_stock": True,
        "manual_stock": True,
        "auto_delivery": False,
        "delivery_delay": "After admin confirmation",
    }


def _ensure_otp_service_offer(conn, service_id):
    """Enforce fixed OTP pricing and create a default offer when none is active."""
    conn.offers.update_many(
        {"service_id": service_id},
        {"$set": _otp_offer_values()},
    )
    if conn.offers.count_documents(
        {"service_id": service_id, "active": 1},
        limit=1,
    ):
        return
    last = conn.offers.find_one(
        {"service_id": service_id},
        sort=[("sort_order", DESCENDING)],
    )
    insert_values = {
        "id": _next_id("offers"),
        "service_id": service_id,
        "name": "Codex number",
        "description": "A Codex number delivered by the administrator after payment.",
        "stock": 0,
        "note": "After receiving the number, tap I agree to request the OTP code.",
        "low_stock_threshold": 0,
        "custom_emoji_id": "",
        "photo_file_id": "",
        "instructions": "",
        "supplier_provider": "",
        "supplier_product_id": "",
        "sort_order": int((last or {}).get("sort_order", 0)) + 1,
    }
    try:
        conn.offers.update_one(
            {"service_id": service_id, "otp_default": True},
            {
                "$set": {**_otp_offer_values(), "active": 1},
                "$setOnInsert": {**insert_values, "otp_default": True},
            },
            upsert=True,
        )
    except DuplicateKeyError:
        conn.offers.update_one(
            {"service_id": service_id, "otp_default": True},
            {"$set": {**_otp_offer_values(), "active": 1}},
        )


def _enforce_otp_catalog_rules(conn):
    for row in conn.services.find({}, {"id": 1, "name": 1}):
        if is_otp_service_name(row.get("name")):
            conn.services.update_one(
                {"id": row["id"]},
                {"$set": {"name": "Codex number"}},
            )
            _ensure_otp_service_offer(conn, row["id"])


def ensure_lovable_unlimited_feature(conn=None):
    """The Lovable Unlimited Credit catalog has been deleted."""
    return None


def get_conn():
    """Return the configured MongoDB database, reusing the process-wide client."""
    global _client, _db
    if _db is None:
        if not MONGODB_URI:
            raise RuntimeError("HP_MONGODB_URI is required")
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
        _db = _client[MONGODB_DB]
    return _db


def _public(document):
    if document is None:
        return None
    result = dict(document)
    result.pop("_id", None)
    return result


def order_charge_total(order):
    """Return the amount charged for an order, including wallet credit."""
    if not order:
        return 0.0
    return round(
        float(order.get("total_price") or 0)
        + float(order.get("wallet_amount") or 0),
        2,
    )


def order_charge_total_expression():
    """Mongo expression matching :func:`order_charge_total`."""
    return {
        "$add": [
            {"$ifNull": ["$total_price", 0]},
            {"$ifNull": ["$wallet_amount", 0]},
        ]
    }


def _next_id(sequence):
    row = get_conn().counters.find_one_and_update(
        {"_id": sequence}, {"$inc": {"value": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return row["value"]


def init_db():
    global _schema_initialized
    if _schema_initialized:
        return
    _text_override_cache.clear()
    db = get_conn()
    db.command("ping")
    db.offers.create_index(
        [("service_id", ASCENDING), ("otp_default", ASCENDING)],
        unique=True,
        partialFilterExpression={"otp_default": True},
    )
    _enforce_otp_catalog_rules(db)
    schema = db.schema_meta.find_one({"_id": "schema"}, {"version": 1})
    if schema and schema.get("version") == SCHEMA_VERSION:
        _schema_initialized = True
        return
    db.users.create_index("telegram_id", unique=True)
    db.services.create_index([("sort_order", ASCENDING), ("id", ASCENDING)])
    db.services.create_index("id", unique=True)
    db.offers.create_index("id", unique=True)
    db.offers.create_index([("service_id", ASCENDING), ("id", ASCENDING)])
    db.offers.create_index([("supplier_provider", ASCENDING), ("supplier_product_id", ASCENDING)])
    db.broadcast_jobs.create_index("id", unique=True)
    db.broadcast_jobs.create_index("dedupe_key", unique=True, sparse=True)
    db.broadcast_messages.create_index(
        [("job_id", ASCENDING), ("chat_id", ASCENDING), ("message_id", ASCENDING)],
        unique=True,
    )
    db.broadcast_messages.create_index([("job_id", ASCENDING), ("deleted", ASCENDING)])
    db.orders.create_index("id", unique=True)
    db.orders.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.orders.create_index("status")
    db.orders.create_index("txid", unique=True, partialFilterExpression={"txid": {"$gt": ""}})
    db.orders.create_index("expires_at")
    db.orders.create_index("tracking_token_hash", unique=True, sparse=True)
    db.orders.create_index([("sales_channel", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    db.settings.create_index("key", unique=True)
    db.text_overrides.create_index([("key", ASCENDING), ("lang", ASCENDING)], unique=True)
    db.lovable_licenses.create_index("id", unique=True)
    db.lovable_licenses.create_index("token_hash", unique=True)
    db.lovable_licenses.create_index("order_id", unique=True, sparse=True)
    db.lovable_licenses.create_index([("user_id", ASCENDING), ("plan", ASCENDING)])
    db.lovable_trial_requests.create_index("id", unique=True)
    db.lovable_trial_requests.create_index("user_id", unique=True)
    db.custom_buttons.create_index("id", unique=True)
    db.reseller_products.create_index(
        [("provider", ASCENDING), ("product_id", ASCENDING)], unique=True,
    )
    db.reseller_fulfillments.create_index(
        [("provider", ASCENDING), ("external_order_id", ASCENDING)], unique=True,
    )
    db.referrals.create_index("referred_id", unique=True)
    db.referrals.create_index("referrer_id")
    db.wallets.create_index("user_id", unique=True)
    db.wallet_topups.create_index("txid", unique=True)
    db.wallet_topups.create_index("id", unique=True, sparse=True)
    db.withdrawals.create_index("id", unique=True)
    db.withdrawals.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.warranty_requests.create_index("id", unique=True)
    db.warranty_requests.create_index([("user_id", ASCENDING), ("order_id", ASCENDING)], unique=True)
    db.onchain_transactions.create_index("txid", unique=True)
    db.bulk_wallet_credits.create_index("operation_id", unique=True)
    db.buyer_api_keys.create_index("id", unique=True)
    db.buyer_api_keys.create_index("key_hash", unique=True)
    db.buyer_api_keys.create_index([
        ("user_id", ASCENDING), ("active", ASCENDING), ("created_at", DESCENDING),
    ])
    db.external_api_connectors.create_index("id", unique=True)
    db.buyer_api_purchases.create_index(
        [("buyer_key_id", ASCENDING), ("idempotency_key", ASCENDING)], unique=True,
    )
    db.buyer_api_purchases.create_index([
        ("user_id", ASCENDING), ("response.success", ASCENDING), ("created_at", DESCENDING),
    ])
    db.buyer_api_rate_limits.create_index(
        [("bucket", ASCENDING), ("window", ASCENDING)], unique=True,
    )
    db.buyer_api_rate_limits.create_index("expire_at", expireAfterSeconds=0)
    db.affiliate_rewards.create_index([("referrer_id", ASCENDING), ("milestone", ASCENDING)], unique=True)
    db.loyalty.create_index("user_id", unique=True)
    db.pending_states.create_index("user_id", unique=True)
    db.inventory.create_index([("offer_id", ASCENDING), ("status", ASCENDING)])
    db.inventory.create_index(
        [
            ("source_provider", ASCENDING),
            ("source_external_order_id", ASCENDING),
            ("source_item_index", ASCENDING),
        ],
        unique=True,
        sparse=True,
    )
    _backfill_inventory_ids(db)
    db.inventory.create_index("id", unique=True, sparse=True)
    fingerprint_index = db.inventory.index_information().get("fingerprint_1")
    if fingerprint_index:
        db.inventory.drop_index("fingerprint_1")
    db.inventory.create_index("reserved_order_id")
    db.processed_updates.create_index("created_at", expireAfterSeconds=604800)
    db.audit_events.create_index("created_at")
    db.interaction_events.create_index([("created_at", DESCENDING)])
    db.interaction_events.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.interaction_events.create_index([("interaction_type", ASCENDING), ("created_at", DESCENDING)])
    db.support_tickets.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.support_tickets.create_index([("category", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)])
    db.support_tickets.create_index("user_id")
    db.ticket_messages.create_index([("ticket_id", ASCENDING), ("created_at", ASCENDING)])
    db.support_tickets.create_index("channel_message_ids")
    if not schema or int(schema.get("version") or 0) < 15:
        _remove_legacy_announcement_overrides(db)
    if not schema or int(schema.get("version") or 0) < 17:
        _retire_ventebot_provider(db)
    if not schema or int(schema.get("version") or 0) < 18:
        _backfill_structured_warranties(db)
    if not schema or int(schema.get("version") or 0) < 20:
        _sanitize_corrupted_emojis_and_offers(db)
    if not schema or int(schema.get("version") or 0) < 21:
        _delete_lovable_catalog(db)
    if not schema or int(schema.get("version") or 0) < 22:
        db.text_overrides.delete_many({"key": {"$regex": r"^onboarding_"}})
    if not schema or int(schema.get("version") or 0) < 23:
        _backfill_order_product_descriptions(db)
    if not schema or int(schema.get("version") or 0) < 26:
        db.drop_collection("admin_passkeys")
        db.drop_collection("admin_webauthn_challenges")
    if os.environ.get("HP_SEED_DEFAULT_CATALOG", "").strip().lower() in {"1", "true", "yes"}:
        _seed_catalog()
    db.schema_meta.update_one(
        {"_id": "schema"},
        {"$set": {"version": SCHEMA_VERSION, "updated_at": int(time.time())}},
        upsert=True,
    )
    _schema_initialized = True


def _remove_legacy_announcement_overrides(conn):
    """Let obsolete stock templates fall back to the current announcement design."""
    legacy_heading = (
        r"NEW\s+(?:API\s+)?STOCKS?\s+JUST\s+DROPPED"
        r"|API\s+PRICE\s+DROP"
        r"|BAISSE\s+DE\s+PRIX\s+API"
    )
    result = conn.text_overrides.delete_many({
        "key": {"$in": [
            "channel_stock_announcement",
            "offer_stock_announcement",
            "flash_sale_announcement",
        ]},
        "text": {"$regex": legacy_heading, "$options": "i"},
    })
    return int(result.deleted_count)


def _retire_ventebot_provider(conn):
    """Hide retired VenteBot offers while preserving orders and audit history."""
    now = int(time.time())
    offers = conn.offers.update_many(
        {"supplier_provider": "ventebot"},
        {"$set": {
            "active": 0,
            "archived": 1,
            "archived_at": now,
            "auto_delivery": False,
        }},
    )
    products = conn.reseller_products.update_many(
        {"provider": "ventebot"},
        {"$set": {"enabled": False, "retired_at": now}},
    )
    return {
        "offers_archived": int(offers.modified_count),
        "products_disabled": int(products.modified_count),
    }


def _backfill_structured_warranties(conn):
    """Backfill default period_days for offers missing it."""
    result = conn.offers.update_many(
        {"period_days": {"$exists": False}},
        {"$set": {"period_days": 30}},
    )
    return result.modified_count


def _backfill_order_product_descriptions(conn):
    """Snapshot catalog descriptions for delivered orders that predate snapshots."""
    migrated = 0
    query = {
        "status": "delivered",
        "$or": [
            {"product_description_snapshot": {"$exists": False}},
            {"product_description_snapshot": ""},
        ],
    }
    for order in conn.orders.find(query, {"_id": 1, "user_id": 1, "offer_id": 1}):
        offer_id = order.get("offer_id")
        if offer_id is None:
            continue
        offer = conn.offers.find_one(
            {"id": offer_id},
            {"description": 1, "description_ar": 1},
        )
        if not offer:
            continue
        user = conn.users.find_one(
            {"telegram_id": order.get("user_id")},
            {"lang": 1},
        ) or {}
        language = str(user.get("lang") or "en")
        description = (
            offer.get("description_ar")
            if language == "ar" and offer.get("description_ar")
            else offer.get("description")
        )
        if not str(description or "").strip():
            continue
        result = conn.orders.update_one(
            {
                "_id": order["_id"],
                "$or": [
                    {"product_description_snapshot": {"$exists": False}},
                    {"product_description_snapshot": ""},
                ],
            },
            {"$set": {
                "product_description_snapshot": str(description)[:2000],
                "product_description_language": language,
            }},
        )
        migrated += int(result.modified_count)
    return migrated


def _sanitize_corrupted_emojis_and_offers(conn):
    """Sanitize corrupted service emoji values and unarchive active offers."""
    for service in conn.services.find():
        emoji = service.get("emoji")
        custom_id = service.get("custom_emoji_id")
        if emoji:
            emoji_str = str(emoji).strip()
            if emoji_str.isdigit() or (emoji_str.isascii() and len(emoji_str) > 4):
                updates = {"emoji": "📦"}
                if not custom_id:
                    updates["custom_emoji_id"] = emoji_str
                conn.services.update_one({"id": service["id"]}, {"$set": updates})
    conn.offers.update_many(
        {"active": 1, "archived": 1},
        {"$set": {"archived": 0}, "$unset": {"archived_at": ""}},
    )


def _delete_lovable_catalog(conn):
    """Permanently delete Lovable Unlimited Credit from services and offers."""
    conn.services.delete_many({
        "$or": [
            {"feature_key": "lovable_unlimited"},
            {"name": {"$regex": r"^lovable\s+unlimited", "$options": "i"}},
        ]
    })
    conn.offers.delete_many({
        "$or": [
            {"feature_key": "lovable_unlimited"},
            {"plan_key": {"$regex": r"^lovable_", "$options": "i"}},
            {"name": {"$regex": r"^lovable", "$options": "i"}},
        ]
    })


def _backfill_inventory_ids(conn):
    """Assign stable numeric IDs to inventory created before the new schema."""
    for item in conn.inventory.find({"id": {"$exists": False}}, {"_id": 1}):
        conn.inventory.update_one(
            {"_id": item["_id"], "id": {"$exists": False}},
            {"$set": {"id": _next_id("inventory")}},
        )


def _seed_catalog():
    db = get_conn()
    if db.services.count_documents({}, limit=1):
        _repair_catalog_encoding(db)
        return
    catalog = [
        ("Canva", "🎨", [("Canva Pro 1m", .14, 113, ""), ("Canva Pro Head 1m", .86, 2, "")]),
        ("Capcut", "🎬", [("Capcut Pro 1m", 2.00, 24, "")]),
        ("Chatgpt", "🤖", [("Code Reedem Chatgpt GO 3m", .06, 14360, "")]),
        ("Discord Nitro", "🎮", [("Code Reedem Discord Nitro 1m", .29, 4, "")]),
        ("Gemini AI", "✨", [("Gemini Pro 12m [invit]", 1.43, 38, ""), ("Gemini Pro 12m [head]", 4.28, 50, "")]),
        ("Grok AI", "🧠", [("Supergrok 3M Sharing [garantie 25j]", 2.86, 5, "Garantie 25 jours"), ("Supergrok 3M Privat", 8.57, 28, "Gros volume >=25 pcs: 5.71$/pc"), ("Supergrok 6M Privat", 11.42, 100, "Gros volume: 10.85$/pc"), ("Supergrok 12M Privat", 17.14, 108, "Gros volume: 16.57$/pc")]),
        ("Manus AI", "🚀", [("Manus AI Pro 1m", 3.14, 14, "")]),
    ]
    extras = [("Adobe Creative Cloud", "🅰️", 5), ("Alight Motion", "📲", 46), ("Base44 AI", "🧩", 3), ("Duolingo", "🦉", 3), ("Emergent AI", "🌐", 1), ("Flux AI", "⚡", 1), ("Freebeat AI", "🎵", 19), ("Gamma AI", "📊", 16), ("Getcontac Premium", "📞", 3), ("Google Colab", "🐍", 36), ("Meitu", "📸", 1), ("Outlook Mail", "📧", 198), ("Perplexity AI", "🔍", 3), ("Picsart", "🖼️", 3), ("Reelshort", "📹", 1), ("Uncensored AI", "🔓", 3), ("Viu", "📺", 38), ("VPN", "🛡️", 2), ("Weshsop AI", "🛍️", 14)]
    catalog.extend((name, emoji, [("Offre standard", None, stock, "Prix à définir")]) for name, emoji, stock in extras)
    for order, (name, emoji, offers) in enumerate(catalog, 1):
        sid = _next_id("services")
        db.services.insert_one({"id": sid, "name": name, "emoji": emoji, "sort_order": order, "active": 1})
        for name_, price, stock, note in offers:
            db.offers.insert_one({"id": _next_id("offers"), "service_id": sid, "name": name_, "price": price, "stock": stock, "note": note, "active": 1})


def _repair_catalog_encoding(db):
    """Repair catalogue notes previously seeded from a misencoded deployment."""
    db.offers.update_many(
        {"note": {"$in": ["Prix Ã  définir", "Prix Ã  dÃ©finir"]}},
        {"$set": {"note": "Prix à définir"}},
    )


def upsert_user(telegram_id, username, first_name):
    now = int(time.time())
    result = get_conn().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"username": username, "first_name": first_name}, "$setOnInsert": {
            "lang": "en",
            "catalog_notifications_enabled": True,
            "created_at": now,
        }},
        upsert=True,
    )
    return result.upserted_id is not None


def get_user_lang(telegram_id):
    row = get_conn().users.find_one({"telegram_id": telegram_id}, {"lang": 1})
    return row.get("lang") if row else None


def set_user_lang(telegram_id, lang):
    get_conn().users.update_one({"telegram_id": telegram_id}, {"$set": {"lang": lang}})


def catalog_notifications_enabled(telegram_id):
    """Return the catalog-alert preference; existing users remain opted in."""
    row = get_conn().users.find_one(
        {"telegram_id": int(telegram_id)},
        {"catalog_notifications_enabled": 1},
    )
    return not row or row.get("catalog_notifications_enabled") is not False


def set_catalog_notifications_enabled(telegram_id, enabled):
    """Persist a customer's preference for stock, price, and flash-sale alerts."""
    get_conn().users.update_one(
        {"telegram_id": int(telegram_id)},
        {
            "$set": {"catalog_notifications_enabled": bool(enabled)},
            "$setOnInsert": {"created_at": int(time.time()), "lang": "en"},
        },
        upsert=True,
    )
    return bool(enabled)


def disabled_catalog_notification_offer_ids(telegram_id, offer_ids=None):
    """Return the products muted by one customer, optionally limited to a page."""
    row = get_conn().users.find_one(
        {"telegram_id": int(telegram_id)},
        {"catalog_notification_disabled_offer_ids": 1},
    ) or {}
    disabled = {
        int(offer_id)
        for offer_id in row.get("catalog_notification_disabled_offer_ids", [])
    }
    if offer_ids is None:
        return disabled
    return disabled.intersection(int(offer_id) for offer_id in offer_ids)


def product_notifications_enabled(telegram_id, offer_id):
    return int(offer_id) not in disabled_catalog_notification_offer_ids(telegram_id)


def set_product_notifications_enabled(telegram_id, offer_id, enabled):
    """Enable or mute catalog-update alerts for one product."""
    operator = "$pull" if enabled else "$addToSet"
    get_conn().users.update_one(
        {"telegram_id": int(telegram_id)},
        {
            operator: {"catalog_notification_disabled_offer_ids": int(offer_id)},
            "$setOnInsert": {"created_at": int(time.time()), "lang": "en"},
        },
        upsert=True,
    )
    return bool(enabled)


def register_referral(referred_id, referrer_id, target=10, reward_cents=100):
    if referred_id == referrer_id or target < 1 or reward_cents < 0:
        return {"accepted": False, "rewarded": False, **affiliate_stats(referrer_id, target)}
    db = get_conn()
    if not db.users.find_one({"telegram_id": referrer_id}, {"_id": 1}):
        return {"accepted": False, "rewarded": False, **affiliate_stats(referrer_id, target)}
    try:
        db.referrals.insert_one({"referred_id": referred_id, "referrer_id": referrer_id, "created_at": int(time.time())})
    except DuplicateKeyError:
        return {"accepted": False, "rewarded": False, **affiliate_stats(referrer_id, target)}
    count = db.referrals.count_documents({"referrer_id": referrer_id})
    rewarded = False
    if count % target == 0:
        milestone = count // target
        try:
            db.affiliate_rewards.insert_one({"referrer_id": referrer_id, "milestone": milestone, "amount_cents": reward_cents, "created_at": int(time.time())})
            db.wallets.update_one({"user_id": referrer_id}, {"$inc": {"balance_cents": reward_cents}}, upsert=True)
            rewarded = True
        except DuplicateKeyError:
            pass
    return {"accepted": True, "rewarded": rewarded, **affiliate_stats(referrer_id, target)}


def affiliate_stats(user_id, target=10):
    db = get_conn()
    count = db.referrals.count_documents({"referrer_id": user_id})
    wallet = db.wallets.find_one({"user_id": user_id})
    return {"referrals": count, "balance_cents": wallet.get("balance_cents", 0) if wallet else 0, "progress": count % target, "remaining": target - (count % target) if count % target else target}


def create_withdrawal(user_id, amount, method, destination):
    amount_cents = int(round(float(amount) * 100))
    if amount_cents < 1000:
        raise ValueError("Minimum withdrawal is 10 USDT.")
    conn = get_conn()
    wallet = conn.wallets.find_one_and_update(
        {"user_id": int(user_id), "balance_cents": {"$gte": amount_cents}},
        {"$inc": {"balance_cents": -amount_cents}},
        return_document=ReturnDocument.AFTER,
    )
    if not wallet:
        raise ValueError("Insufficient wallet balance.")
    row = {
        "id": _next_id("withdrawals"), "user_id": int(user_id),
        "amount_cents": amount_cents, "method": str(method),
        "destination": str(destination).strip(), "status": "pending",
        "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC),
    }
    conn.withdrawals.insert_one(row)
    _capture_admin_notifications()
    return _public(row)


def list_withdrawals(status="pending", limit=100):
    query = {} if status in {"all", ""} else {"status": status}
    return [_public(row) for row in get_conn().withdrawals.find(query).sort("created_at", DESCENDING).limit(limit)]


def update_withdrawal(withdrawal_id, status, admin_note=""):
    row = get_conn().withdrawals.find_one_and_update(
        {"id": int(withdrawal_id), "status": "pending"},
        {"$set": {"status": str(status), "admin_note": str(admin_note), "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )
    return _public(row) if row else None


def reject_withdrawal(withdrawal_id, admin_note=""):
    """Reject a pending withdrawal and return the reserved amount to the wallet."""
    conn = get_conn()
    row = conn.withdrawals.find_one_and_update(
        {"id": int(withdrawal_id), "status": "pending"},
        {"$set": {
            "status": "rejected",
            "admin_note": str(admin_note or "").strip()[:500],
            "updated_at": datetime.now(UTC),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not row:
        return None
    conn.wallets.update_one(
        {"user_id": int(row["user_id"])},
        {"$inc": {"balance_cents": int(row.get("amount_cents") or 0)}},
        upsert=True,
    )
    audit_event(
        "withdrawal.rejected",
        details={"withdrawal_id": int(withdrawal_id), "user_id": int(row["user_id"])},
    )
    return _public(row)


def create_warranty_request(user_id, order_id, days_used, refund_amount, reason=""):
    row = {
        "id": _next_id("warranty_requests"), "user_id": int(user_id), "order_id": int(order_id),
        "days_used": int(days_used), "refund_amount": round(float(refund_amount), 2),
        "reason": str(reason or "").strip(),
        "status": "pending_admin_check", "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC),
    }
    get_conn().warranty_requests.insert_one(row)
    _capture_admin_notifications()
    return _public(row)


def accept_warranty_request(request_id):
    row = get_conn().warranty_requests.find_one_and_update(
        {"id": int(request_id), "status": "pending_admin_check"},
        {"$set": {"status": "accepted", "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )
    if row:
        audit_event("warranty.accepted", details={"request_id": int(request_id)})
    return _public(row) if row else None


def list_warranty_requests(*, page=0, page_size=10):
    """Return warranty activity newest first, including completed requests."""
    page = max(0, int(page))
    page_size = max(1, min(50, int(page_size)))
    cursor = (
        get_conn().warranty_requests.find({})
        .sort([("updated_at", DESCENDING), ("created_at", DESCENDING), ("id", DESCENDING)])
        .skip(page * page_size)
        .limit(page_size)
    )
    return [_public(row) for row in cursor], get_conn().warranty_requests.count_documents({})


def list_confirmed_orders(*, page=0, page_size=10):
    """Return every successfully confirmed order, including delivered orders."""
    page = max(0, int(page))
    page_size = max(1, min(50, int(page_size)))
    query = {"status": {"$in": ["paid", "payment_confirmed", "delivered"]}}
    cursor = (
        get_conn().orders.find(query)
        .sort([("paid_at", DESCENDING), ("updated_at", DESCENDING), ("id", DESCENDING)])
        .skip(page * page_size)
        .limit(page_size)
    )
    return [_public(row) for row in cursor], get_conn().orders.count_documents(query)


def list_pending_api_deliveries(*, page=0, page_size=10):
    """Return supplier orders that still require delivery or administrator review."""
    page = max(0, int(page))
    page_size = max(1, min(50, int(page_size)))
    conn = get_conn()
    unresolved = {"purchasing", "delivery_pending", "review_required", "not_created"}
    rows = [_public(row) for row in conn.reseller_fulfillments.find({
        "status": {"$in": sorted(unresolved)},
    })]
    seen_order_ids = {int(row["order_id"]) for row in rows if row.get("order_id") is not None}

    # Also surface paid supplier orders whose fulfillment record was never created,
    # plus completed supplier records whose local order was not marked delivered.
    paid_orders = list(conn.orders.find({
        "status": {"$in": ["paid", "payment_confirmed", "preparing_delivery"]},
    }))
    for order in paid_orders:
        order_id = int(order["id"])
        offer = conn.offers.find_one({"id": order.get("offer_id")}) or {}
        provider = str(offer.get("supplier_provider") or "").strip()
        if not provider or order_id in seen_order_ids:
            continue
        fulfillment = conn.reseller_fulfillments.find_one({"order_id": order_id})
        if fulfillment:
            row = _public(fulfillment)
            if row.get("status") == "completed":
                row["status"] = "completed_not_delivered"
        else:
            row = {
                "order_id": order_id,
                "external_order_id": f"BM-{order_id}",
                "provider": provider,
                "supplier_product_id": str(offer.get("supplier_product_id") or ""),
                "status": "fulfillment_missing",
                "created_at": order.get("paid_at") or order.get("created_at"),
                "updated_at": order.get("updated_at") or order.get("paid_at"),
            }
        rows.append(row)
        seen_order_ids.add(order_id)

    rows.sort(
        key=lambda row: (
            row.get("updated_at") or row.get("created_at") or 0,
            row.get("order_id") or 0,
        ),
        reverse=True,
    )
    total = len(rows)
    start = page * page_size
    return rows[start:start + page_size], total


def get_pending_api_delivery(order_id):
    """Resolve one unresolved supplier fulfillment for the admin detail view."""
    conn = get_conn()
    order_id = int(order_id)
    order = conn.orders.find_one({"id": order_id}) or {}
    fulfillment = conn.reseller_fulfillments.find_one({"order_id": order_id})
    unresolved = {"purchasing", "delivery_pending", "review_required", "not_created"}
    if fulfillment:
        row = _public(fulfillment)
        if row.get("status") in unresolved:
            return row
        if row.get("status") == "completed" and order.get("status") != "delivered":
            row["status"] = "completed_not_delivered"
            return row
        return None
    if order.get("status") not in {"paid", "payment_confirmed", "preparing_delivery"}:
        return None
    offer = conn.offers.find_one({"id": order.get("offer_id")}) or {}
    provider = str(offer.get("supplier_provider") or "").strip()
    if not provider:
        return None
    return {
        "order_id": order_id,
        "external_order_id": f"BM-{order_id}",
        "provider": provider,
        "supplier_product_id": str(offer.get("supplier_product_id") or ""),
        "status": "fulfillment_missing",
        "created_at": order.get("paid_at") or order.get("created_at"),
        "updated_at": order.get("updated_at") or order.get("paid_at"),
    }


def resolve_warranty_request(request_id, resolution, admin_note=""):
    """Resolve an accepted warranty request and optionally credit a refund."""
    conn = get_conn()
    request = conn.warranty_requests.find_one(
        {"id": int(request_id), "status": "accepted"}
    )
    if not request or resolution not in {"replacement", "refund"}:
        return None
    status = "refunded" if resolution == "refund" else "replacement_pending"
    row = conn.warranty_requests.find_one_and_update(
        {"id": int(request_id), "status": "accepted"},
        {"$set": {
            "status": status,
            "resolution": resolution,
            "admin_note": str(admin_note),
            "updated_at": datetime.now(UTC),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if row and resolution == "refund":
        conn.wallets.update_one(
            {"user_id": int(request["user_id"])},
            {"$inc": {"balance_cents": int(round(float(request.get("refund_amount") or 0) * 100))}},
            upsert=True,
        )
    return _public(row) if row else None


def complete_warranty_replacement(request_id):
    """Mark replacement content as delivered after Telegram accepted the message."""
    now = datetime.now(UTC)
    row = get_conn().warranty_requests.find_one_and_update(
        {"id": int(request_id), "status": "replacement_pending"},
        {"$set": {
            "status": "replacement_delivered",
            "replacement_delivered_at": now,
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if row:
        audit_event(
            "warranty.replacement_delivered",
            details={
                "request_id": int(request_id),
                "order_id": int(row["order_id"]),
                "user_id": int(row["user_id"]),
            },
        )
    return _public(row) if row else None


def refuse_warranty_request(request_id, admin_note):
    row = get_conn().warranty_requests.find_one_and_update(
        {"id": int(request_id), "status": "pending_admin_check"},
        {"$set": {
            "status": "refused",
            "admin_note": str(admin_note),
            "updated_at": datetime.now(UTC),
        }},
        return_document=ReturnDocument.AFTER,
    )
    return _public(row) if row else None


def _sanitize_service_emoji(service):
    """Ensure service emojis are valid unicode emoji characters rather than numeric IDs."""
    if not service or not isinstance(service, dict):
        return service
    emoji = service.get("emoji")
    if emoji:
        emoji_str = str(emoji).strip()
        if emoji_str.isdigit() or (emoji_str.isascii() and len(emoji_str) > 4):
            if not service.get("custom_emoji_id"):
                service["custom_emoji_id"] = emoji_str
            service["emoji"] = "📦"
    return service


def list_services(active_only=True):
    query = {"active": 1} if active_only else {}
    services = [_sanitize_service_emoji(_public(x)) for x in get_conn().services.find(query)]
    return sorted(services, key=_service_sort_key)


def list_services_with_stock(active_only=True):
    """Return services and stock totals with two queries instead of one per service."""
    conn = get_conn()
    services = sorted(
        [_sanitize_service_emoji(_public(item)) for item in conn.services.find({"active": 1} if active_only else {})],
        key=_service_sort_key,
    )
    totals = {
        row["_id"]: row["total"]
        for row in conn.offers.aggregate([
            {"$match": {"active": 1}},
            {"$group": {"_id": "$service_id", "total": {"$sum": "$stock"}}},
        ])
    }
    for service in services:
        has_unlimited = conn.offers.count_documents({
            "service_id": service["id"], "active": 1, "unlimited_stock": True,
        }) > 0
        service["unlimited_stock"] = has_unlimited
        service["total_stock"] = -1 if has_unlimited else totals.get(service["id"], 0)
    return services


def get_service(service_id):
    return _sanitize_service_emoji(_public(get_conn().services.find_one({"id": service_id})))


def list_offers(service_id, active_only=True):
    service = get_service(service_id)
    if service and is_otp_service_name(service.get("name")):
        if service.get("name") != "Codex number":
            get_conn().services.update_one(
                {"id": service_id}, {"$set": {"name": "Codex number"}},
            )
            service["name"] = "Codex number"
        _ensure_otp_service_offer(get_conn(), service_id)
    query = {"service_id": service_id}
    if active_only:
        query["active"] = 1
    offers = [_resolve_flash_sale(_public(x)) for x in get_conn().offers.find(query).sort("id", ASCENDING)]
    if service and is_otp_service_name(service.get("name")):
        values = _otp_offer_values()
        for offer in offers:
            offer.update(values)
    return offers


def list_catalog_offers():
    """Return all active offers across active services for the flat customer catalog."""
    services = list_services()
    service_by_id = {service["id"]: service for service in services}
    for service in services:
        if is_otp_service_name(service.get("name")):
            _ensure_otp_service_offer(get_conn(), service["id"])
    service_ids = list(service_by_id)
    if not service_ids:
        return []
    offers = []
    for row in get_conn().offers.find({
        "service_id": {"$in": service_ids},
        "active": 1,
    }):
        offer = _resolve_flash_sale(_public(row))
        service = service_by_id[offer["service_id"]]
        # Methods have their own dedicated menu and must not appear in the
        # general product catalogue.
        if str(service.get("name") or "").strip().casefold() == "methods":
            continue
        if service.get("dedicated_home"):
            continue
        if is_otp_service_name(service.get("name")):
            offer.update(_otp_offer_values())
        offer["service_name"] = service.get("name", "")
        offer["service_emoji"] = service.get("emoji", "")
        offer["service_suffix_emoji"] = service.get("suffix_emoji", "")
        offer["service_custom_emoji_id"] = service.get("custom_emoji_id", "")
        offers.append(offer)
    offers.sort(key=lambda offer: (
        *_service_sort_key(service_by_id[offer["service_id"]]),
        int(offer.get("sort_order", 0)),
        int(offer["id"]),
    ))
    return offers
def get_offer(offer_id):
    try:
        numeric_id = int(offer_id)
    except (TypeError, ValueError):
        numeric_id = offer_id
    query = {"$or": [{"id": numeric_id}, {"id": str(offer_id)}]}
    offer = _resolve_flash_sale(_public(get_conn().offers.find_one(query)))
    if not offer:
        return None
    service = get_service(offer.get("service_id"))
    if service and is_otp_service_name(service.get("name")):
        offer.update(_otp_offer_values())
    return offer


def _resolve_flash_sale(offer):
    """Restore the regular price when a flash sale has expired."""
    if not offer or not offer.get("flash_sale_active"):
        return offer
    if int(offer.get("flash_sale_ends_at") or 0) > int(time.time()):
        return offer
    original_price = offer.get("flash_sale_original_price")
    get_conn().offers.update_one(
        {"id": offer["id"], "flash_sale_active": True},
        {
            "$set": {"price": original_price, "flash_sale_active": False},
            "$unset": {
                "flash_sale_price": "",
                "flash_sale_original_price": "",
                "flash_sale_ends_at": "",
            },
        },
    )
    offer["price"] = original_price
    offer["flash_sale_active"] = False
    offer.pop("flash_sale_price", None)
    offer.pop("flash_sale_original_price", None)
    offer.pop("flash_sale_ends_at", None)
    return offer


def start_flash_sale(offer_id, sale_price, duration_minutes):
    offer = get_offer(int(offer_id))
    sale_price = round(float(sale_price), 2)
    duration_minutes = int(duration_minutes)
    if not offer or offer.get("price") is None:
        raise ValueError("Offre introuvable ou sans prix.")
    if sale_price < 0 or sale_price >= float(offer["price"]):
        raise ValueError("Le prix flash doit être inférieur au prix actuel.")
    if duration_minutes < 1 or duration_minutes > 10080:
        raise ValueError("La durée doit être comprise entre 1 minute et 7 jours.")
    ends_at = int(time.time()) + duration_minutes * 60
    get_conn().offers.update_one(
        {"id": int(offer_id)},
        {"$set": {
            "active": 1,
            "archived": 0,
            "flash_sale_active": True,
            "flash_sale_original_price": float(offer["price"]),
            "flash_sale_price": sale_price,
            "flash_sale_ends_at": ends_at,
            "price": sale_price,
        }},
    )
    return get_offer(int(offer_id))


def stop_flash_sale(offer_id):
    offer = get_offer(int(offer_id))
    if not offer or not offer.get("flash_sale_active"):
        return offer
    original_price = offer.get("flash_sale_original_price")
    get_conn().offers.update_one(
        {"id": int(offer_id)},
        {
            "$set": {"price": original_price, "flash_sale_active": False},
            "$unset": {
                "flash_sale_price": "",
                "flash_sale_original_price": "",
                "flash_sale_ends_at": "",
            },
        },
    )
    return get_offer(int(offer_id))


def offer_has_stock(offer, qty=1):
    """Return whether an offer can fulfill a quantity, including unlimited offers."""
    if not offer or int(qty or 0) < 1:
        return False
    service = get_service(offer.get("service_id")) if offer.get("service_id") is not None else None
    if (
        str((service or {}).get("name") or "").strip().lower() == "methods"
        and not offer.get("method_media")
    ):
        return False
    return bool(offer.get("unlimited_stock")) or int(offer.get("stock") or 0) >= int(qty)


def service_total_stock(service_id):
    result = list(get_conn().offers.aggregate([{"$match": {"service_id": service_id, "active": 1}}, {"$group": {"_id": None, "total": {"$sum": "$stock"}}}]))
    return result[0]["total"] if result else 0


def update_offer(
    offer_id,
    service_id=None,
    price=None,
    stock=None,
    name=None,
    emoji=None,
    note=None,
    active=None,
    description=None,
    currency=None,
    sort_order=None,
    auto_delivery=None,
    low_stock_threshold=None,
    delivery_delay=None,
    custom_emoji_id=None,
    photo_file_id=None,
    instructions=None,
    unlimited_stock=None,
    manual_stock=None,
    supplier_provider=None,
    supplier_product_id=None,
    sales_channels=None,
    tn_price_millimes=None,
    name_ar=None,
    description_ar=None,
    site_description_fr=None,
    site_description_ar=None,
    site_image_url=None,
    site_portrait_url=None,
    site_category=None,
    site_badge=None,
    site_badge_ar=None,
    site_featured=None,
    period_days=None,
    warranty_days=None,
    method_media=None,
    benefits_document_file_id=None,
    benefits_document_name=None,
    delivery_url=None,
    bulk_quantity=None,
    bulk_unit_price=None,
    period_value=None,
    period_unit=None,
    warranty_value=None,
    warranty_unit=None,
):
    existing = get_conn().offers.find_one({"id": offer_id}, {"service_id": 1}) or {}
    if service_id is not None and int(service_id) != int(existing.get("service_id") or 0):
        source_service = get_service(existing.get("service_id"))
        target_service = get_service(int(service_id))
        if not target_service or target_service.get("archived") == 1:
            raise ValueError("Service de destination introuvable")
        if (source_service and is_otp_service_name(source_service.get("name"))) or is_otp_service_name(target_service.get("name")):
            raise ValueError("Les offres Codex number ne peuvent pas être déplacées")
    values = {
        key: value
        for key, value in {
            "service_id": int(service_id) if service_id is not None else None,
            "price": price,
            "stock": stock,
            "name": name,
            "emoji": emoji,
            "note": note,
            "active": active,
            "description": description,
            "currency": currency,
            "sort_order": sort_order,
            "auto_delivery": auto_delivery,
            "low_stock_threshold": low_stock_threshold,
            "delivery_delay": delivery_delay,
            "custom_emoji_id": custom_emoji_id,
            "photo_file_id": photo_file_id,
            "instructions": instructions,
            "unlimited_stock": unlimited_stock,
            "manual_stock": manual_stock,
            "supplier_provider": supplier_provider,
            "supplier_product_id": supplier_product_id,
            "sales_channels": sales_channels,
            "tn_price_millimes": tn_price_millimes,
            "name_ar": name_ar,
            "description_ar": description_ar,
            "site_description_fr": site_description_fr,
            "site_description_ar": site_description_ar,
            "site_image_url": site_image_url,
            "site_portrait_url": site_portrait_url,
            "site_category": site_category,
            "site_badge": site_badge,
            "site_badge_ar": site_badge_ar,
            "site_featured": site_featured,
            "period_days": int(period_days) if period_days is not None else None,
            "warranty_days": int(warranty_days) if warranty_days is not None else None,
            "method_media": list(method_media) if method_media is not None else None,
            "benefits_document_file_id": benefits_document_file_id,
            "benefits_document_name": benefits_document_name,
            "delivery_url": delivery_url,
            "bulk_quantity": int(bulk_quantity) if bulk_quantity is not None else None,
            "bulk_unit_price": float(bulk_unit_price) if bulk_unit_price is not None else None,
            "period_value": int(period_value) if period_value is not None else None,
            "period_unit": warranty_service.normalize_duration_unit(period_unit) if period_unit is not None else None,
            "warranty_value": int(warranty_value) if warranty_value is not None else None,
            "warranty_unit": warranty_service.normalize_duration_unit(warranty_unit) if warranty_unit is not None else None,
        }.items()
        if value is not None
    }
    effective_service_id = int(service_id) if service_id is not None else existing.get("service_id")
    service = get_service(effective_service_id) if existing else None
    if service and is_otp_service_name(service.get("name")):
        values.update(_otp_offer_values())
    if values.get("active") == 1:
        values["archived"] = 0
    if values:
        get_conn().offers.update_one({"id": offer_id}, {"$set": values})
        if service_id is not None:
            get_conn().reseller_products.update_many(
                {"local_offer_id": int(offer_id)},
                {"$set": {"service_id": int(service_id), "updated_at": int(time.time())}},
            )


def move_offer(offer_id, service_id):
    offer = get_offer(int(offer_id))
    if not offer:
        raise ValueError("Offre introuvable")
    previous_service_id = int(offer.get("service_id") or 0)
    update_offer(int(offer_id), service_id=int(service_id))
    return {
        "offer_id": int(offer_id),
        "previous_service_id": previous_service_id,
        "service_id": int(service_id),
        "offer": get_offer(int(offer_id)),
    }


def add_service(name, emoji="", custom_emoji_id="", sales_channels=None, name_ar="", suffix_emoji=""):
    db = get_conn()
    last = db.services.find_one(sort=[("sort_order", DESCENDING)])
    sid = _next_id("services")
    special_service = is_otp_service_name(name)
    db.services.insert_one({
        "id": sid,
        "name": "Codex number" if special_service else name,
        "emoji": emoji,
        "suffix_emoji": str(suffix_emoji or "")[:12],
        "custom_emoji_id": custom_emoji_id,
        "sort_order": (last or {}).get("sort_order", 0) + 1,
        "active": 1,
        "sales_channels": list(sales_channels or ["bot"]),
        "name_ar": str(name_ar or "")[:120],
    })
    if special_service:
        _ensure_otp_service_offer(db, sid)
    return sid


def ensure_methods_service():
    """Return the dedicated digital-methods service, creating it once if needed."""
    existing = get_conn().services.find_one({"name": {"$regex": r"^methods$", "$options": "i"}})
    if existing:
        return int(existing["id"])
    return add_service("Methods", "🧠")


BOT_LIKE_MINE_DESCRIPTION = """Launch your own professional digital-products business with a complete Telegram commerce system like BLACK MARKET.

The package includes a modern customer bot, a Telegram admin panel, a secure web admin dashboard, payment and wallet tools, automated and manual delivery, warranty management, customer support, marketing features, analytics, and a reseller API. The customer experience supports English and Arabic.

Use the “What you'll get?” button below to receive the complete functions-and-benefits document before purchasing.

Delivery format: after payment confirmation, you receive a private link to the complete source code and deployment files.

Hosting, third-party accounts, paid API keys, installation, and custom development are not included unless agreed separately with the administrator."""

BOT_LIKE_MINE_DESCRIPTION_AR = """أطلق مشروعاً احترافياً لبيع المنتجات الرقمية باستخدام نظام تجارة متكامل عبر Telegram مثل BLACK MARKET.

تتضمن الحزمة بوتاً حديثاً للعملاء، ولوحة إدارة داخل Telegram، ولوحة تحكم ويب آمنة، وأدوات الدفع والمحفظة، والتسليم التلقائي واليدوي، وإدارة الضمان، ودعم العملاء، وأدوات التسويق، والإحصائيات، وواجهة API للموزعين. تدعم واجهة العملاء اللغتين العربية والإنجليزية.

استخدم زر «ماذا ستحصل عليه؟» أدناه لاستلام مستند الوظائف والمزايا الكامل قبل الشراء.

صيغة التسليم: بعد تأكيد الدفع، ستحصل على رابط خاص للشيفرة المصدرية الكاملة وملفات النشر.

لا تشمل الحزمة الاستضافة أو حسابات الجهات الخارجية أو مفاتيح API المدفوعة أو التثبيت أو التطوير المخصص إلا باتفاق منفصل مع المسؤول."""


def ensure_bot_like_mine_feature():
    """Return the dedicated 45 USDT source-code offer, creating it once."""
    conn = get_conn()
    service = conn.services.find_one({"feature_key": "bot_like_mine"})
    if not service:
        service = conn.services.find_one({
            "name": {"$regex": r"^bot like mine$", "$options": "i"},
        })
    if not service:
        service_id = add_service("BOT LIKE MINE", "🤖", sales_channels=["bot"])
    else:
        service_id = int(service["id"])
    conn.services.update_one(
        {"id": service_id},
        {"$set": {
            "name": "BOT LIKE MINE",
            "emoji": "🤖",
            "feature_key": "bot_like_mine",
            "dedicated_home": True,
            "active": 1,
            "archived": 0,
            "sales_channels": ["bot"],
        }, "$unset": {"archived_at": ""}},
    )

    offer = conn.offers.find_one({"feature_key": "bot_like_mine"})
    if not offer:
        offer = conn.offers.find_one({
            "service_id": service_id,
            "name": {"$regex": r"^bot like mine$", "$options": "i"},
        })
    if not offer:
        offer_id = add_offer(
            service_id,
            "BOT LIKE MINE",
            45.0,
            0,
            note="Complete source-code package — delivered as a private source-code link after payment.",
            description=BOT_LIKE_MINE_DESCRIPTION,
            description_ar=BOT_LIKE_MINE_DESCRIPTION_AR,
            currency="USDT",
            auto_delivery=False,
            low_stock_threshold=0,
            delivery_delay="Private source-code link after payment confirmation",
            unlimited_stock=True,
            manual_stock=True,
            sales_channels=["bot"],
            period_days=0,
            warranty_days=0,
        )
    else:
        offer_id = int(offer["id"])
    conn.offers.update_one(
        {"id": offer_id},
        {"$set": {
            "service_id": service_id,
            "name": "BOT LIKE MINE",
            "price": 45.0,
            "currency": "USDT",
            "description": BOT_LIKE_MINE_DESCRIPTION,
            "description_ar": BOT_LIKE_MINE_DESCRIPTION_AR,
            "note": "Complete source-code package — delivered as a private source-code link after payment.",
            "feature_key": "bot_like_mine",
            "active": 1,
            "archived": 0,
            "stock": 0,
            "unlimited_stock": True,
            "manual_stock": True,
            "auto_delivery": False,
            "period_days": 0,
            "warranty_days": 0,
            "low_stock_threshold": 0,
            "delivery_delay": "Private source-code link after payment confirmation",
            "sales_channels": ["bot"],
        }, "$unset": {"archived_at": ""}},
    )
    return offer_id


def update_service(
    service_id, name=None, emoji=None, active=None, custom_emoji_id=None,
    sales_channels=None, name_ar=None, suffix_emoji=None,
):
    special_service = is_otp_service_name(name)
    values = {
        k: v
        for k, v in {
            "name": name,
            "emoji": emoji,
            "suffix_emoji": str(suffix_emoji)[:12] if suffix_emoji is not None else None,
            "active": active,
            "custom_emoji_id": custom_emoji_id,
            "sales_channels": sales_channels,
            "name_ar": name_ar,
        }.items()
        if v is not None
    }
    if special_service:
        values["name"] = "Codex number"
    updated = bool(values and get_conn().services.update_one({"id": service_id}, {"$set": values}).matched_count)
    if updated and special_service:
        _ensure_otp_service_offer(get_conn(), service_id)
    return updated


def archive_service(service_id):
    db = get_conn()
    archived_at = int(time.time())
    db.services.update_one(
        {"id": service_id},
        {"$set": {"active": 0, "archived": 1, "archived_at": archived_at}},
    )
    db.offers.update_many(
        {"service_id": service_id},
        {"$set": {"active": 0, "archived": 1, "archived_at": archived_at}},
    )


def archive_offer(offer_id):
    return bool(get_conn().offers.update_one(
        {"id": offer_id},
        {"$set": {"active": 0, "archived": 1, "archived_at": int(time.time())}},
    ).matched_count)


def unarchive_offer(offer_id):
    return bool(get_conn().offers.update_one(
        {"id": int(offer_id)},
        {"$set": {"active": 1, "archived": 0}, "$unset": {"archived_at": ""}},
    ).matched_count)


def unarchive_service(service_id):
    db = get_conn()
    db.services.update_one(
        {"id": int(service_id)},
        {"$set": {"active": 1, "archived": 0}, "$unset": {"archived_at": ""}},
    )
    db.offers.update_many(
        {"service_id": int(service_id)},
        {"$set": {"active": 1, "archived": 0}, "$unset": {"archived_at": ""}},
    )


def add_offer(
    service_id,
    name,
    price,
    stock,
    note="",
    description="",
    currency="USDT",
    auto_delivery=True,
    low_stock_threshold=5,
    delivery_delay="Instantané après confirmation",
    custom_emoji_id="",
    photo_file_id="",
    instructions="",
    unlimited_stock=False,
    manual_stock=False,
    supplier_provider="",
    supplier_product_id="",
    sales_channels=None,
    tn_price_millimes=None,
    name_ar="",
    description_ar="",
    site_description_fr="",
    site_description_ar="",
    site_image_url="",
    site_portrait_url="",
    site_category="",
    site_badge="",
    site_badge_ar="",
    site_featured=False,
    period_days=30,
    warranty_days=0,
    bulk_quantity=0,
    bulk_unit_price=None,
    period_value=None,
    period_unit="days",
    warranty_value=None,
    warranty_unit="days",
    active=True,
):
    oid = _next_id("offers")
    last = get_conn().offers.find_one({"service_id": service_id}, sort=[("sort_order", DESCENDING)])
    service = get_service(service_id) or {}
    special_values = _otp_offer_values() if is_otp_service_name(service.get("name")) else {}
    get_conn().offers.insert_one({
        "id": oid,
        "service_id": service_id,
        "name": name,
        "description": description,
        "price": price,
        "currency": currency,
        "stock": stock,
        "note": note,
        "auto_delivery": bool(auto_delivery),
        "low_stock_threshold": int(low_stock_threshold),
        "delivery_delay": delivery_delay,
        "custom_emoji_id": custom_emoji_id,
        "photo_file_id": photo_file_id,
        "instructions": instructions,
        "unlimited_stock": bool(unlimited_stock),
        "manual_stock": bool(manual_stock),
        "supplier_provider": str(supplier_provider or ""),
        "supplier_product_id": str(supplier_product_id or ""),
        "sort_order": (last or {}).get("sort_order", 0) + 1,
        "active": 1 if active else 0,
        "sales_channels": list(sales_channels or ["bot"]),
        "tn_price_millimes": tn_price_millimes,
        "name_ar": str(name_ar or "")[:200],
        "description_ar": str(description_ar or "")[:2000],
        "site_description_fr": str(site_description_fr or "")[:2000],
        "site_description_ar": str(site_description_ar or "")[:2000],
        "site_image_url": str(site_image_url or "")[:1000],
        "site_portrait_url": str(site_portrait_url or "")[:1000],
        "site_category": str(site_category or "")[:60],
        "site_badge": str(site_badge or "")[:60],
        "site_badge_ar": str(site_badge_ar or "")[:60],
        "site_featured": bool(site_featured),
        "period_days": int(30 if period_days is None else period_days),
        "warranty_days": int(warranty_days or 0),
        "period_value": int(
            period_value
            if period_value is not None
            else (30 if period_days is None else period_days)
        ),
        "period_unit": warranty_service.normalize_duration_unit(period_unit),
        "warranty_value": int(warranty_value if warranty_value is not None else (warranty_days or 0)),
        "warranty_unit": warranty_service.normalize_duration_unit(warranty_unit),
        "bulk_quantity": max(0, int(bulk_quantity or 0)),
        "bulk_unit_price": (
            round(float(bulk_unit_price), 2)
            if bulk_unit_price is not None and str(bulk_unit_price).strip() != ""
            else None
        ),
        **special_values,
    })
    return oid


def offer_sold_count(offer_id):
    """Return customer sales, excluding administrator/test purchases."""
    pipeline = [
        {"$match": customer_order_query({
            "offer_id": offer_id,
            "status": {"$in": ["paid", "payment_confirmed", "delivered"]},
        })},
        {"$group": {"_id": None, "total": {"$sum": "$qty"}}},
    ]
    result = list(get_conn().orders.aggregate(pipeline))
    return int(result[0]["total"]) if result else 0


def duplicate_offer(offer_id):
    """Duplicate an offer without copying its inventory."""
    source = get_conn().offers.find_one({"id": offer_id})
    if not source:
        return None
    return add_offer(
        source["service_id"], f"{source['name']} (copie)", source.get("price"), 0,
        source.get("note", ""), description=source.get("description", ""),
        currency=source.get("currency", "USDT"), auto_delivery=source.get("auto_delivery", True),
        low_stock_threshold=source.get("low_stock_threshold", 5),
        delivery_delay=source.get("delivery_delay", ""),
        unlimited_stock=source.get("unlimited_stock", False),
        manual_stock=source.get("manual_stock", False),
        sales_channels=source.get("sales_channels"),
        tn_price_millimes=source.get("tn_price_millimes"),
        name_ar=source.get("name_ar", ""),
        description_ar=source.get("description_ar", ""),
        site_description_fr=source.get("site_description_fr", ""),
        site_description_ar=source.get("site_description_ar", ""),
        site_image_url=source.get("site_image_url", ""),
        site_portrait_url=source.get("site_portrait_url", ""),
        site_category=source.get("site_category", ""),
        site_badge=source.get("site_badge", ""),
        site_badge_ar=source.get("site_badge_ar", ""),
        site_featured=source.get("site_featured", False),
        period_days=source.get("period_days", 30),
        warranty_days=source.get("warranty_days", 0),
        bulk_quantity=source.get("bulk_quantity", 0),
        bulk_unit_price=source.get("bulk_unit_price"),
        period_value=source.get("period_value"),
        period_unit=source.get("period_unit", "days"),
        warranty_value=source.get("warranty_value"),
        warranty_unit=source.get("warranty_unit", "days"),
    )


def decrement_stock(offer_id, qty):
    get_conn().offers.update_one({"id": offer_id}, [{"$set": {"stock": {"$max": [0, {"$subtract": ["$stock", qty]}]}}}])


def mark_order_paid(order_id, verify_method):
    db = get_conn()
    order = db.orders.find_one({"id": order_id})
    if not order or order.get("status") in ("paid", "payment_confirmed", "delivered"):
        return bool(order)
    if order.get("status") not in (
        "awaiting_verification",
        "pending_payment",
        "verification_failed",
        "manual_review",
    ):
        return False
    offer = db.offers.find_one({"id": order.get("offer_id")}) if order.get("offer_id") else None
    stock_decremented = False
    if offer and not offer.get("unlimited_stock") and not order.get("is_preorder"):
        stock = db.offers.update_one(
            {"id": order["offer_id"], "stock": {"$gte": order["qty"]}},
            {"$inc": {"stock": -order["qty"]}},
        )
        if stock.modified_count != 1:
            return False
        stock_decremented = True
    paid = db.orders.update_one(
        {"id": order_id, "status": order["status"]},
        {
            "$set": {
                "status": "payment_confirmed",
                "verify_method": verify_method,
                "paid_at": int(time.time()),
                "updated_at": int(time.time()),
            }
        },
    )
    if paid.modified_count != 1 and stock_decremented:
        db.offers.update_one({"id": order["offer_id"]}, {"$inc": {"stock": order["qty"]}})
    if paid.modified_count == 1:
        _capture_admin_notifications()
    return paid.modified_count == 1


def create_order(user_id, offer, qty):
    now = int(time.time())
    unit = float(offer.get("price") or 0)
    try:
        bulk_quantity = int(offer.get("bulk_quantity") or 0)
        bulk_unit_price = float(offer.get("bulk_unit_price"))
        if bulk_quantity > 0 and int(qty) >= bulk_quantity and 0 <= bulk_unit_price < unit:
            unit = round(bulk_unit_price, 2)
    except (TypeError, ValueError):
        pass
    service = get_service(offer["service_id"])
    language = get_user_lang(user_id) or "en"
    product_description = (
        offer.get("description_ar")
        if language == "ar" and offer.get("description_ar")
        else offer.get("description")
    )
    oid = _next_id("orders")
    get_conn().orders.insert_one({"id": oid, "user_id": user_id, "offer_id": offer["id"], "service_name": service["name"] if service else "", "offer_name": offer["name"], "product_description_snapshot": str(product_description or "")[:2000], "product_description_language": language, "warranty": warranty_service.offer_warranty_label(offer), "warranty_days": int(offer.get("warranty_days") or 0), "warranty_value": offer.get("warranty_value"), "warranty_unit": offer.get("warranty_unit", "days"), "period_days": int(offer.get("period_days") or 0), "period_value": offer.get("period_value"), "period_unit": offer.get("period_unit", "days"), "qty": qty, "unit_price": unit, "total_price": round(unit * qty, 2), "status": "pending_payment", "txid": "", "verify_method": "", "delivery_text": "", "created_at": now, "updated_at": now})
    return oid


def get_order(order_id):
    return _public(get_conn().orders.find_one({"id": order_id}))


def update_order(order_id, **kwargs):
    if not kwargs:
        return
    allowed = {"status", "txid", "verify_method", "delivery_text", "updated_at"}
    kwargs["updated_at"] = int(time.time())
    unknown = set(kwargs) - allowed
    if unknown:
        raise ValueError(f"Champs de commande interdits: {sorted(unknown)}")
    result = get_conn().orders.update_one({"id": order_id}, {"$set": kwargs})
    if result.modified_count and "status" in kwargs:
        _capture_admin_notifications()


def claim_order_channel_announcement(order_id):
    """Atomically reserve the one public purchase announcement for an order."""
    result = get_conn().orders.update_one(
        {"id": int(order_id), "channel_sale_announced": {"$ne": True}},
        {"$set": {"channel_sale_announced": True, "updated_at": int(time.time())}},
    )
    return result.modified_count == 1


def release_order_channel_announcement(order_id):
    """Allow a later retry when Telegram could not publish the announcement."""
    get_conn().orders.update_one(
        {"id": int(order_id)},
        {"$set": {"channel_sale_announced": False, "updated_at": int(time.time())}},
    )

def list_orders(status=None, limit=30):
    query = {"status": status} if status else {}
    return [_public(x) for x in get_conn().orders.find(query).sort("id", DESCENDING).limit(limit)]


def list_user_orders(user_id, limit=15):
    return [_public(x) for x in get_conn().orders.find({"user_id": user_id}).sort("id", DESCENDING).limit(limit)]


def user_account_summary(user_id):
    db = get_conn()
    user = _public(db.users.find_one({"telegram_id": user_id})) or {"telegram_id": user_id}
    orders = list_user_orders(user_id, limit=25)
    paid_statuses = {"paid", "payment_confirmed", "delivered"}
    paid = list(db.orders.find({"user_id": user_id, "status": {"$in": list(paid_statuses)}}))
    user.update({
        "orders": orders,
        "order_count": db.orders.count_documents({"user_id": user_id}),
        "paid_count": db.orders.count_documents({"user_id": user_id, "status": {"$in": list(paid_statuses)}}),
        "delivered_count": db.orders.count_documents({"user_id": user_id, "status": "delivered"}),
        "total_paid": round(sum(float(x.get("total_price") or 0) for x in paid), 2),
    })
    return user


def claim_onchain_transaction(txid, network, user_id, reference_type, reference_id, amount):
    """Atomically reserve a verified chain transaction across orders and top-ups."""
    txid = str(txid).strip().lower()
    reference_type = str(reference_type)
    reference_id = int(reference_id)
    existing = get_conn().onchain_transactions.find_one({"txid": txid})
    if existing:
        return (
            existing.get("reference_type") == reference_type
            and int(existing.get("reference_id") or 0) == reference_id
        )
    try:
        get_conn().onchain_transactions.insert_one({
            "txid": txid,
            "network": str(network),
            "user_id": int(user_id),
            "reference_type": reference_type,
            "reference_id": reference_id,
            "amount": float(amount),
            "created_at": int(time.time()),
        })
    except DuplicateKeyError:
        existing = get_conn().onchain_transactions.find_one({"txid": txid}) or {}
        return (
            existing.get("reference_type") == reference_type
            and int(existing.get("reference_id") or 0) == reference_id
        )
    return True


def get_setting(key, default=None):
    row = get_conn().settings.find_one({"key": key})
    return row.get("value", default) if row else default


def set_setting(key, value):
    get_conn().settings.update_one({"key": key}, {"$set": {"value": str(value)}}, upsert=True)


def preload_text_overrides(keys, lang):
    """Load several translations in one MongoDB query for fast keyboard rendering."""
    normalized_keys = list(dict.fromkeys(str(key) for key in keys))
    normalized_lang = str(lang)
    if not normalized_keys:
        return
    rows = {
        row["key"]: _public(row)
        for row in get_conn().text_overrides.find({
            "key": {"$in": normalized_keys},
            "lang": normalized_lang,
        })
    }
    expires_at = time.monotonic() + TEXT_OVERRIDE_CACHE_SECONDS
    for key in normalized_keys:
        _text_override_cache[(key, normalized_lang)] = (expires_at, rows.get(key))


def _cached_text_override(key, lang):
    cache_key = (str(key), str(lang))
    cached = _text_override_cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    row = _public(get_conn().text_overrides.find_one({
        "key": cache_key[0], "lang": cache_key[1],
    }))
    _text_override_cache[cache_key] = (
        time.monotonic() + TEXT_OVERRIDE_CACHE_SECONDS,
        row,
    )
    return row


def get_text_override(key, lang):
    row = _cached_text_override(key, lang)
    return row.get("text") if row else None


def get_text_override_icon(key, lang):
    row = _cached_text_override(key, lang)
    return row.get("custom_emoji_id", "") if row else ""


def set_text_override(key, lang, text, custom_emoji_id=""):
    get_conn().text_overrides.update_one(
        {"key": str(key), "lang": str(lang)},
        {"$set": {
            "text": str(text), "custom_emoji_id": str(custom_emoji_id or ""),
            "updated_at": int(time.time()),
        }},
        upsert=True,
    )
    _text_override_cache.pop((str(key), str(lang)), None)


def list_text_overrides():
    return [_public(row) for row in get_conn().text_overrides.find().sort([("key", ASCENDING), ("lang", ASCENDING)])]


def add_custom_button(*args):
    if len(args) == 4:
        _, label_en, label_ar, url = args
    elif len(args) == 3:
        label_en, label_ar, url = args
    else:
        raise TypeError("add_custom_button expects English, Arabic and URL labels")
    button_id = _next_id("custom_buttons")
    get_conn().custom_buttons.insert_one({
        "id": button_id, "label_en": label_en,
        "label_ar": label_ar, "url": url, "active": 1,
    })
    return button_id


def list_custom_buttons(active_only=True):
    query = {"active": 1} if active_only else {}
    return [_public(row) for row in get_conn().custom_buttons.find(query).sort("id", ASCENDING)]


def delete_custom_button(button_id):
    return bool(get_conn().custom_buttons.delete_one({"id": int(button_id)}).deleted_count)


def list_reseller_product_configs(provider="mailreader"):
    """Return administrator selections for one external product supplier."""
    return [
        _public(row)
        for row in get_conn().reseller_products.find(
            {"provider": str(provider)}
        ).sort("name", ASCENDING)
    ]


def observe_reseller_stock(provider, product_id, stock):
    """Atomically store supplier stock and return the previously observed value."""
    now = int(time.time())
    previous = get_conn().reseller_products.find_one_and_update(
        {"provider": str(provider), "product_id": str(product_id)},
        {
            "$set": {
                "supplier_stock_seen": max(0, int(stock or 0)),
                "supplier_stock_checked_at": now,
            },
        },
        return_document=ReturnDocument.BEFORE,
    )
    if not previous or previous.get("supplier_stock_seen") is None:
        return None
    return max(0, int(previous["supplier_stock_seen"]))


def sync_reseller_supplier_price(provider, product_id, wholesale_price):
    """Keep the configured profit amount when a supplier price changes."""
    collection = get_conn().reseller_products
    config = collection.find_one({
        "provider": str(provider),
        "product_id": str(product_id),
        "enabled": True,
        "local_offer_id": {"$ne": None},
    })
    if not config:
        return None
    offer = get_conn().offers.find_one({"id": int(config["local_offer_id"])})
    if not offer or offer.get("flash_sale_active"):
        return None

    new_wholesale = max(0.0, float(wholesale_price))
    previous_wholesale = float(
        config.get("supplier_price_seen")
        if config.get("supplier_price_seen") is not None
        else config.get("wholesale_price") or 0
    )
    configured_retail = float(config.get("retail_price") or 0)
    previous_retail = float(
        offer.get("price")
        if offer.get("price") is not None
        else configured_retail
    )
    # Supplier discounts must not discount our profit as well.  Older records
    # do not have ``profit_amount`` yet, so migrate them from the last known
    # retail and wholesale prices on their first synchronization.
    profit_amount = config.get("profit_amount")
    if profit_amount is None or abs(previous_retail - configured_retail) >= 0.005:
        profit_amount = previous_retail - previous_wholesale
    profit_amount = max(0.0, float(profit_amount))
    now = int(time.time())

    # Supplier adapters normalize missing/malformed prices to zero. Never turn
    # a paid offer into a free product because of an incomplete API response.
    if new_wholesale <= 0 < previous_wholesale:
        collection.update_one(
            {"_id": config["_id"]},
            {"$set": {"supplier_price_checked_at": now}},
        )
        return None

    if previous_wholesale == new_wholesale:
        effective_markup_percent = (
            (profit_amount / new_wholesale) * 100
            if new_wholesale > 0
            else 0.0
        )
        collection.update_one(
            {"_id": config["_id"]},
            {"$set": {
                "supplier_price_seen": new_wholesale,
                "supplier_price_checked_at": now,
                "profit_amount": profit_amount,
                "profit_markup_percent": effective_markup_percent,
                "retail_price": previous_retail,
            }},
        )
        return None

    new_retail = round(new_wholesale + profit_amount, 2)
    if new_wholesale > 0 and new_retail <= new_wholesale:
        new_retail = round(new_wholesale + 0.01, 2)
    effective_markup_percent = (
        ((new_retail / new_wholesale) - 1) * 100
        if new_wholesale > 0
        else 0.0
    )
    collection.update_one(
        {"_id": config["_id"]},
        {"$set": {
            "wholesale_price": new_wholesale,
            "supplier_price_seen": new_wholesale,
            "supplier_price_checked_at": now,
            "profit_amount": profit_amount,
            "profit_markup_percent": effective_markup_percent,
            "retail_price": new_retail,
            "updated_at": now,
        }},
    )
    get_conn().offers.update_one(
        {"id": int(config["local_offer_id"])},
        {"$set": {"price": new_retail}},
    )
    return {
        "offer_id": int(config["local_offer_id"]),
        "previous_wholesale": previous_wholesale,
        "wholesale_price": new_wholesale,
        "previous_price": previous_retail,
        "price": new_retail,
        "profit_amount": profit_amount,
        "markup_percent": effective_markup_percent,
        "decreased": new_wholesale < previous_wholesale and new_retail < previous_retail,
    }


def reorder_catalog(item_type, ordered_ids, service_id=None):
    """Persist a complete service order or one service's complete offer order."""
    item_type = str(item_type or "").strip().lower()
    ids = [int(value) for value in ordered_ids]
    if not ids or len(ids) > 2000 or len(ids) != len(set(ids)):
        raise ValueError("Ordre du catalogue invalide")
    conn = get_conn()
    if item_type == "service":
        collection = conn.services
        query = {"archived": {"$ne": 1}}
    elif item_type == "offer":
        if service_id is None:
            raise ValueError("Service requis pour ordonner les produits")
        collection = conn.offers
        query = {"service_id": int(service_id), "archived": {"$ne": 1}}
    else:
        raise ValueError("Type de catalogue invalide")
    existing_ids = [int(row["id"]) for row in collection.find(query, {"id": 1})]
    if set(existing_ids) != set(ids):
        raise ValueError("Le catalogue a changé. Actualisez la page puis réessayez.")
    for position, item_id in enumerate(ids):
        collection.update_one({"id": item_id}, {"$set": {"sort_order": position}})
    return {"item_type": item_type, "ordered_ids": ids, "service_id": int(service_id) if service_id is not None else None}


def save_reseller_product_config(
    provider,
    product_id,
    *,
    name,
    wholesale_price,
    currency,
    retail_price,
    enabled,
    service_id=None,
    local_offer_id=None,
    display_name="",
    service_name="",
    service_emoji="",
    description="",
    warranty="Produit API MailReader",
    period_days=30,
    warranty_days=0,
    period_value=None,
    period_unit="days",
    warranty_value=None,
    warranty_unit="days",
    delivery_delay="Instantané après confirmation",
    sort_order=0,
    low_stock_threshold=5,
):
    """Persist retail pricing and visibility without storing supplier secrets."""
    now = int(time.time())
    markup_percent = (
        max(0.0, ((float(retail_price) / float(wholesale_price)) - 1) * 100)
        if float(wholesale_price) > 0
        else 0.0
    )
    profit_amount = max(0.0, float(retail_price) - float(wholesale_price))
    get_conn().reseller_products.update_one(
        {"provider": str(provider), "product_id": str(product_id)},
        {
            "$set": {
                "name": str(name)[:200],
                "wholesale_price": float(wholesale_price),
                "currency": str(currency or "USDT")[:12],
                "retail_price": float(retail_price),
                "profit_amount": profit_amount,
                "profit_markup_percent": markup_percent,
                "enabled": bool(enabled),
                "service_id": int(service_id) if service_id is not None else None,
                "local_offer_id": int(local_offer_id) if local_offer_id is not None else None,
                "display_name": str(display_name or name)[:200],
                "service_name": str(service_name or "")[:100],
                "service_emoji": str(service_emoji or "")[:16],
                "description": str(description or "")[:2000],
                "warranty": str(warranty or "")[:250],
                "period_days": int(period_days or 30),
                "warranty_days": int(warranty_days or 0),
                "period_value": int(period_value if period_value is not None else (period_days or 30)),
                "period_unit": warranty_service.normalize_duration_unit(period_unit),
                "warranty_value": int(warranty_value if warranty_value is not None else (warranty_days or 0)),
                "warranty_unit": warranty_service.normalize_duration_unit(warranty_unit),
                "delivery_delay": str(delivery_delay or "")[:120],
                "sort_order": max(0, int(sort_order or 0)),
                "low_stock_threshold": max(0, int(low_stock_threshold or 0)),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return _public(
        get_conn().reseller_products.find_one(
            {"provider": str(provider), "product_id": str(product_id)}
        )
    )


def shop_settings():
    """Return typed, administrator-editable shop settings."""
    from config import (
        AFFILIATE_DAILY_CAP,
        AFFILIATE_FIVE_REWARD_CENTS,
        BINANCE_PAY_ID,
        LOW_STOCK_THRESHOLD,
        ORDER_EXPIRY_SECONDS,
        SHOP_NAME,
    )

    defaults = {
        "shop_name": SHOP_NAME,
        "currency": "USDT",
        "payment_recipient": BINANCE_PAY_ID,
        "order_expiry_seconds": ORDER_EXPIRY_SECONDS,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "affiliate_enabled": True,
        "affiliate_target": AFFILIATE_DAILY_CAP,
        "affiliate_reward_cents": AFFILIATE_FIVE_REWARD_CENTS,
        "maintenance_enabled": False,
        "maintenance_message": "The bot is temporarily under maintenance while we make improvements.",
        "welcome_message": "",
        "help_message": "",
        "terms_message": "",
        "privacy_message": "",
        "active_languages": "en,ar",
        "announcement_new_stock": "",
        "announcement_flash_sale": "",
        "announcement_restock": "",
    }
    rows = {row["key"]: row.get("value") for row in get_conn().settings.find({"key": {"$in": list(defaults)}})}
    result = defaults | rows
    try:
        from i18n import TRANSLATIONS
        if not result.get("announcement_new_stock"):
            result["announcement_new_stock"] = (
                get_text_override("channel_stock_announcement", "en")
                or TRANSLATIONS.get("channel_stock_announcement", {}).get("en", "")
            )
        if not result.get("announcement_flash_sale"):
            result["announcement_flash_sale"] = (
                get_text_override("flash_sale_announcement", "en")
                or TRANSLATIONS.get("flash_sale_announcement", {}).get("en", "")
            )
        if not result.get("announcement_restock"):
            result["announcement_restock"] = (
                get_text_override("offer_stock_announcement", "en")
                or TRANSLATIONS.get("offer_stock_announcement", {}).get("en", "")
            )
    except Exception:
        pass
    for key in ("order_expiry_seconds", "low_stock_threshold", "affiliate_target", "affiliate_reward_cents"):
        result[key] = int(result[key])
    for key in ("affiliate_enabled", "maintenance_enabled"):
        result[key] = str(result[key]).lower() in {"1", "true", "yes", "on"}
    return result


def get_pending_state(user_id):
    row = get_conn().pending_states.find_one({"user_id": user_id})
    return (row["kind"], row["ref"]) if row else None


def set_pending_state(user_id, state):
    kind, ref = state
    get_conn().pending_states.update_one(
        {"user_id": user_id},
        {"$set": {"kind": kind, "ref": ref, "updated_at": int(time.time())}},
        upsert=True,
    )


def pop_pending_state(user_id, default=None):
    row = get_conn().pending_states.find_one_and_delete({"user_id": user_id})
    return (row["kind"], row["ref"]) if row else default


def claim_update(update_id):
    """Return False when Telegram retries an update already being processed."""
    try:
        get_conn().processed_updates.insert_one({"_id": update_id, "created_at": datetime.now(UTC)})
        return True
    except DuplicateKeyError:
        return False


def release_update(update_id):
    get_conn().processed_updates.delete_one({"_id": update_id})


def _fernet():
    key = INVENTORY_KEY
    if not key:
        secret = (
            os.environ.get("HP_BOT_TOKEN", "")
            or os.environ.get("HP_WEBHOOK_SECRET", "")
            or os.environ.get("HP_DASHBOARD_PASSWORD", "")
            or os.environ.get("HP_MONGODB_URI", "")
        ).strip()
        if not secret:
            raise RuntimeError("HP_INVENTORY_KEY or another deployment secret is required for automatic inventory")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()
    return Fernet(key.encode())


def add_inventory_items(offer_id, items):
    """Legacy importer that stores every non-empty account, including duplicates."""
    db = get_conn()
    cipher = _fernet()
    added = 0
    for value in (x.strip() for x in items):
        if not value:
            continue
        db.inventory.insert_one({
            "offer_id": offer_id,
            "payload": cipher.encrypt(value.encode()).decode(),
            "status": "available",
            "created_at": int(time.time()),
        })
        added += 1
    if added:
        db.offers.update_one({"id": offer_id}, {"$inc": {"stock": added}})
    return added

def inventory_stats(offer_id):
    db = get_conn()
    return {status: db.inventory.count_documents({"offer_id": offer_id, "status": status}) for status in ("available", "sold")}


def fulfill_order(order_id):
    """Atomically claim encrypted stock and return decrypted delivery values."""
    db = get_conn()
    order = db.orders.find_one({"id": order_id, "status": "paid"})
    if not order or not order.get("offer_id"):
        return None
    claimed = []
    for _ in range(order.get("qty", 1)):
        item = db.inventory.find_one_and_update(
            {"offer_id": order["offer_id"], "status": "available"},
            {"$set": {"status": "reserved", "order_id": order_id, "reserved_at": int(time.time())}},
            return_document=ReturnDocument.AFTER,
        )
        if not item:
            db.inventory.update_many({"order_id": order_id, "status": "reserved"}, {"$set": {"status": "available"}, "$unset": {"order_id": "", "reserved_at": ""}})
            return None
        claimed.append(item)
    values = [_fernet().decrypt(x["payload"].encode()).decode() for x in claimed]
    db.inventory.update_many({"order_id": order_id, "status": "reserved"}, {"$set": {"status": "sold", "sold_at": int(time.time())}})
    db.orders.update_one({"id": order_id, "status": "paid"}, {"$set": {"status": "delivered", "delivery_text": "[encrypted automatic delivery]", "updated_at": int(time.time())}})
    return values


def audit_event(action, actor_id=None, details=None):
    event_id = _next_id("audit_events")
    get_conn().audit_events.insert_one({"id": event_id, "action": action, "actor_id": actor_id, "details": details or {}, "created_at": datetime.now(UTC)})
    if str(action).startswith(("order.", "payment.", "ticket.", "wallet.", "withdrawal.", "warranty.", "offer.", "inventory.", "system.", "webhook.", "delivery.")):
        _capture_admin_notifications()
    return event_id


def _capture_admin_notifications():
    from app.web.notification_service import _auth_version, capture_feed
    if not get_conn().admin_push_devices.count_documents({"auth_version": _auth_version()}):
        return
    capture_feed()


def log_interaction(
    user_id,
    *,
    first_name="",
    full_name="",
    username="",
    interaction_type="message",
    action="",
    content="",
    screen="",
):
    """Persist one customer interaction for live dashboard analytics."""
    now = int(time.time())
    event = {
        "user_id": int(user_id),
        "first_name": str(first_name or "")[:200],
        "full_name": str(full_name or first_name or "")[:300],
        "username": str(username or "")[:100],
        "interaction_type": str(interaction_type or "message")[:50],
        "action": str(action or "")[:500],
        "content": str(content or "")[:2000],
        "screen": str(screen or "")[:1000],
        "created_at": now,
    }
    get_conn().interaction_events.insert_one(event)
    get_conn().users.update_one(
        {"telegram_id": int(user_id)},
        {
            "$set": {"last_active_at": now},
            "$inc": {"interaction_count": 1},
        },
    )
    return _public(event)


def interaction_analytics(days=30, limit=1000):
    """Return interaction KPIs, daily chart points, and detailed recent events."""
    conn = get_conn()
    now = int(time.time())
    today_start = now - (now % 86400)
    start = today_start - (max(1, int(days)) - 1) * 86400
    live_since = now - 300
    events = [
        _public(row)
        for row in conn.interaction_events.find(
            {"created_at": {"$gte": start}}
        ).sort("created_at", DESCENDING).limit(max(1, int(limit)))
    ]
    daily_counts = {}
    type_counts = {}
    service_click_counts = {}
    service_click_totals = {}
    active_today = set()
    live_users = set()
    for event in conn.interaction_events.find(
        {"created_at": {"$gte": start}},
        {"created_at": 1, "user_id": 1, "interaction_type": 1, "action": 1, "content": 1},
    ):
        timestamp = int(event.get("created_at") or 0)
        day = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
        daily_counts[day] = daily_counts.get(day, 0) + 1
        kind = str(event.get("interaction_type") or "other")
        type_counts[kind] = type_counts.get(kind, 0) + 1
        action = str(event.get("action") or "")
        if kind == "button" and re.fullmatch(r"svc:\d+", action):
            service_id = int(action.split(":", 1)[1])
            key = (day, service_id)
            service_click_counts[key] = service_click_counts.get(key, 0) + 1
            service_click_totals[service_id] = service_click_totals.get(service_id, 0) + 1
        if timestamp >= today_start:
            active_today.add(event.get("user_id"))
        if timestamp >= live_since:
            live_users.add(event.get("user_id"))
    daily = []
    for offset in range(max(1, int(days))):
        day_timestamp = start + offset * 86400
        day = datetime.fromtimestamp(day_timestamp, UTC).strftime("%Y-%m-%d")
        daily.append({"date": day, "count": daily_counts.get(day, 0)})
    service_names = {
        int(row["id"]): str(row.get("name") or f"Service #{row['id']}")
        for row in conn.services.find(
            {"id": {"$in": list(service_click_totals)}}, {"id": 1, "name": 1}
        )
    } if service_click_totals else {}
    service_click_daily = []
    for day in sorted({key[0] for key in service_click_counts}):
        rows = [
            {
                "service_id": service_id,
                "name": service_names.get(service_id, f"Service #{service_id}"),
                "count": count,
            }
            for (event_day, service_id), count in service_click_counts.items()
            if event_day == day
        ]
        rows.sort(key=lambda row: (-row["count"], row["name"].lower()))
        service_click_daily.append({
            "date": day,
            "total": sum(row["count"] for row in rows),
            "services": rows,
        })
    service_click_services = [
        {
            "service_id": service_id,
            "name": service_names.get(service_id, f"Service #{service_id}"),
            "count": count,
        }
        for service_id, count in service_click_totals.items()
    ]
    service_click_services.sort(key=lambda row: (-row["count"], row["name"].lower()))
    return {
        "summary": {
            "total": conn.interaction_events.count_documents({}),
            "today": conn.interaction_events.count_documents(
                {"created_at": {"$gte": today_start}}
            ),
            "active_today": len(active_today),
            "live_users": len(live_users),
            "button_clicks": type_counts.get("button", 0),
            "messages": type_counts.get("message", 0) + type_counts.get("command", 0),
        },
        "daily": daily,
        "types": type_counts,
        "service_clicks": {
            "total": sum(service_click_totals.values()),
            "services": service_click_services,
            "daily": service_click_daily,
        },
        "events": events,
    }


def user_activity_summary():
    """Return bot activity counts; 'online' means active within five minutes."""
    analytics = interaction_analytics(days=30, limit=1)["summary"]
    return {
        "online_now": analytics["live_users"],
        "active_today": analytics["active_today"],
        "total_users": get_conn().users.count_documents({}),
    }


def dashboard_summary():
    """Legacy wrapper — kept for backward compatibility."""
    data = dashboard_data()
    return data.get("summary", {})


def customer_order_query(query=None):
    """Limit a statistics query to real customers, excluding the administrator."""
    from config import ADMIN_ID

    result = dict(query or {})
    if not ADMIN_ID:
        return result
    customer_only = {"user_id": {"$ne": int(ADMIN_ID)}}
    if "user_id" in result:
        return {"$and": [result, customer_only]}
    result.update(customer_only)
    return result


def dashboard_data():
    """Comprehensive dashboard data for the admin panel."""
    db = get_conn()
    now = int(time.time())
    today_start = now - (now % 86400)
    yesterday_start = today_start - 86400
    week_ago = now - 7 * 86400
    month_ago = now - 30 * 86400
    prev_week_start = week_ago - 7 * 86400

    # --- Users ---
    total_users = db.users.count_documents({})
    new_users_today = db.users.count_documents({"created_at": {"$gte": today_start}})
    new_users_7d = db.users.count_documents({"created_at": {"$gte": week_ago}})
    new_users_prev_7d = db.users.count_documents({"created_at": {"$gte": prev_week_start, "$lt": week_ago}})

    # --- Orders ---
    total_orders = db.orders.count_documents(customer_order_query())
    orders_today = db.orders.count_documents(customer_order_query({"created_at": {"$gte": today_start}}))
    orders_yesterday = db.orders.count_documents(customer_order_query({"created_at": {"$gte": yesterday_start, "$lt": today_start}}))
    pending_orders = db.orders.count_documents(customer_order_query({"status": {"$in": ["pending_payment", "awaiting_verification", "manual_review"]}}))

    paid_statuses = ["paid", "payment_confirmed", "delivered"]
    paid_orders = db.orders.count_documents(customer_order_query({"status": {"$in": paid_statuses}}))
    delivered_orders = db.orders.count_documents(customer_order_query({"status": "delivered"}))

    # --- Revenue ---
    def _revenue(match_filter):
        result = list(db.orders.aggregate([
            {"$match": customer_order_query(match_filter)},
            {"$group": {"_id": None, "total": {"$sum": order_charge_total_expression()}}},
        ]))
        return round(result[0]["total"], 2) if result else 0.0

    revenue_today = _revenue({"status": {"$in": paid_statuses}, "created_at": {"$gte": today_start}})
    revenue_yesterday = _revenue({"status": {"$in": paid_statuses}, "created_at": {"$gte": yesterday_start, "$lt": today_start}})
    revenue_7d = _revenue({"status": {"$in": paid_statuses}, "created_at": {"$gte": week_ago}})
    revenue_30d = _revenue({"status": {"$in": paid_statuses}, "created_at": {"$gte": month_ago}})
    revenue_prev_7d = _revenue({"status": {"$in": paid_statuses}, "created_at": {"$gte": prev_week_start, "$lt": week_ago}})

    # Conversion rate
    conversion_rate = round((paid_orders / total_orders * 100) if total_orders else 0, 1)

    # --- Tickets ---
    open_tickets = db.support_tickets.count_documents({
        "category": {"$ne": "catalog_request"},
        "status": {"$nin": ["closed", "resolved"]},
    })
    product_requests = db.support_tickets.count_documents({
        "category": "catalog_request",
        "status": {"$nin": ["closed", "resolved"]},
    })

    # --- Inventory & stock ---
    available_inventory = db.inventory.count_documents({"status": "available"})

    # Low stock offers
    from config import LOW_STOCK_THRESHOLD
    low_stock_offers = list(db.offers.find(
        {"active": 1, "stock": {"$lte": LOW_STOCK_THRESHOLD, "$gt": 0}},
        {"id": 1, "name": 1, "stock": 1, "service_id": 1},
    ))

    out_of_stock_offers = list(db.offers.find(
        {"active": 1, "stock": {"$lte": 0}},
        {"id": 1, "name": 1, "service_id": 1},
    ))

    # --- Alerts ---
    alerts = []
    for off in out_of_stock_offers:
        alerts.append({"type": "stock_empty", "message": f"Stock épuisé: {off['name']}", "severity": "error", "entity_id": off["id"]})
    for off in low_stock_offers:
        alerts.append({"type": "stock_low", "message": f"Stock faible ({off['stock']}): {off['name']}", "severity": "warning", "entity_id": off["id"]})

    old_pending = db.orders.count_documents(customer_order_query({
        "status": "pending_payment",
        "created_at": {"$lt": now - 3600},
    }))
    if old_pending:
        alerts.append({"type": "old_pending", "message": f"{old_pending} commande(s) en attente depuis plus d'1h", "severity": "warning"})

    unanswered_tickets = db.support_tickets.count_documents({
        "category": {"$ne": "catalog_request"},
        "status": "waiting_admin",
    })
    if unanswered_tickets:
        alerts.append({"type": "unanswered_tickets", "message": f"{unanswered_tickets} ticket(s) sans réponse", "severity": "warning"})
    unanswered_product_requests = db.support_tickets.count_documents({
        "category": "catalog_request",
        "status": "waiting_admin",
    })
    if unanswered_product_requests:
        alerts.append({
            "type": "product_requests",
            "message": f"{unanswered_product_requests} demande(s) de produit à examiner",
            "severity": "warning",
        })

    paid_not_delivered = db.orders.count_documents(customer_order_query({
        "status": {"$in": ["paid", "payment_confirmed", "preparing_delivery"]},
        "paid_at": {"$lt": now - 900},
    }))
    if paid_not_delivered:
        alerts.append({
            "type": "paid_not_delivered",
            "message": f"{paid_not_delivered} commande(s) payée(s) non livrée(s) depuis plus de 15 min",
            "severity": "error",
        })

    failed_payments = db.orders.count_documents(customer_order_query({
        "status": {"$in": ["verification_failed", "manual_review"]},
    }))
    if failed_payments:
        alerts.append({
            "type": "payment_review",
            "message": f"{failed_payments} paiement(s) nécessitent une intervention",
            "severity": "warning",
        })

    recent_errors = db.audit_events.count_documents({
        "action": {"$in": ["system.error", "webhook.error", "delivery.error"]},
        "created_at": {"$gte": datetime.fromtimestamp(now - 86400, UTC)},
    })
    if recent_errors:
        alerts.append({
            "type": "recent_errors",
            "message": f"{recent_errors} erreur(s) système durant les dernières 24 h",
            "severity": "error",
        })

    # --- Services enrichis ---
    services_enriched = []
    service_rows = sorted(
        list(db.services.find({"archived": {"$ne": 1}})),
        key=_service_sort_key,
    )
    for svc in service_rows:
        svc_data = _public(svc)
        offers = list(db.offers.find({"service_id": svc["id"], "archived": {"$ne": 1}}).sort([("sort_order", ASCENDING), ("id", ASCENDING)]))
        svc_data["offers"] = [_public(offer) for offer in offers]
        svc_data["offer_count"] = len(offers)
        svc_data["total_stock"] = sum(o.get("stock", 0) for o in offers)
        # Count sales
        svc_data["total_sales"] = db.orders.count_documents(customer_order_query({
            "offer_id": {"$in": [o["id"] for o in offers]},
            "status": {"$in": paid_statuses},
        })) if offers else 0
        offer_ids = [offer["id"] for offer in offers]
        svc_data["total_revenue"] = _revenue({
            "offer_id": {"$in": offer_ids},
            "status": {"$in": paid_statuses},
        }) if offer_ids else 0.0
        services_enriched.append(svc_data)

    summary = {
        "users": total_users,
        "new_users_today": new_users_today,
        "new_users_7d": new_users_7d,
        "new_users_prev_7d": new_users_prev_7d,
        "orders": total_orders,
        "orders_today": orders_today,
        "orders_yesterday": orders_yesterday,
        "orders_day_delta": orders_today - orders_yesterday,
        "pending_orders": pending_orders,
        "paid_orders": paid_orders,
        "delivered_orders": delivered_orders,
        "revenue_today": revenue_today,
        "revenue_yesterday": revenue_yesterday,
        "revenue_day_delta": round(revenue_today - revenue_yesterday, 2),
        "revenue_7d": revenue_7d,
        "revenue_30d": revenue_30d,
        "revenue_prev_7d": revenue_prev_7d,
        "revenue_7d_change_pct": round(
            ((revenue_7d - revenue_prev_7d) / revenue_prev_7d * 100) if revenue_prev_7d else (100.0 if revenue_7d else 0.0),
            1,
        ),
        "users_7d_change_pct": round(
            ((new_users_7d - new_users_prev_7d) / new_users_prev_7d * 100)
            if new_users_prev_7d else (100.0 if new_users_7d else 0.0),
            1,
        ),
        "conversion_rate": conversion_rate,
        "open_tickets": open_tickets,
        "product_requests": product_requests,
        "low_stock_offers": len(low_stock_offers),
        "available_inventory": available_inventory,
        "failed_payments": failed_payments,
        "paid_not_delivered": paid_not_delivered,
        "recent_errors": recent_errors,
    }

    return {
        "summary": summary,
        "alerts": alerts,
        "orders": list_orders(limit=50),
        "services": services_enriched,
        "users": list_users(limit=200),
        "tickets": list_tickets(limit=50),
        "audits": list_audit_events(limit=100),
        "interactions": interaction_analytics(days=30, limit=1000),
        **shop_settings(),
    }


def create_ticket(user_id, message):
    tid = _next_id("tickets")
    get_conn().support_tickets.insert_one({"id": tid, "user_id": user_id, "message": message[:2000], "status": "open", "created_at": datetime.now(UTC)})
    audit_event("ticket.created", user_id, {"ticket_id": tid})
    return tid


def list_tickets(status="open", limit=50):
    return [_public(x) for x in get_conn().support_tickets.find({"status": status}).sort("created_at", DESCENDING).limit(limit)]


def get_ticket(ticket_id):
    return _public(get_conn().support_tickets.find_one({"id": ticket_id}))


def close_ticket(ticket_id):
    return bool(get_conn().support_tickets.update_one({"id": ticket_id}, {"$set": {"status": "closed", "closed_at": datetime.now(UTC)}}).matched_count)


def list_users(limit=100):
    return [_public(x) for x in get_conn().users.find({}).sort("created_at", DESCENDING).limit(limit)]


CATALOG_UPDATE_BROADCAST_KINDS = {
    "stock", "restock_digest", "flash_sale", "api_flash_sale",
    "supplier_price_update",
}


def list_broadcast_users(*, catalog_updates_only=False, catalog_offer_id=None):
    """Return every active bot user eligible for private announcements."""
    query = {
        "telegram_id": {"$exists": True},
        "banned": {"$ne": True},
        "broadcast_blocked": {"$ne": True},
    }
    if catalog_updates_only:
        # Missing means enabled so customers created before this option stay opted in.
        query["catalog_notifications_enabled"] = {"$ne": False}
        if catalog_offer_id is not None:
            query["catalog_notification_disabled_offer_ids"] = {
                "$ne": int(catalog_offer_id),
            }
    return [
        _public(row)
        for row in get_conn().users.find(
            query,
            {"telegram_id": 1, "lang": 1},
        )
    ]


def create_broadcast_job(kind, payload, *, dedupe_key=""):
    """Persist a Telegram broadcast before a background worker starts it."""
    kind = str(kind or "")[:60]
    payload = dict(payload or {})
    dedupe_key = str(dedupe_key or "").strip()[:240]
    if dedupe_key:
        existing = get_conn().broadcast_jobs.find_one({"dedupe_key": dedupe_key})
        if existing:
            return _public(existing), False
    recipient_query = {
        "telegram_id": {"$exists": True},
        "banned": {"$ne": True},
        "broadcast_blocked": {"$ne": True},
    }
    if kind in CATALOG_UPDATE_BROADCAST_KINDS:
        recipient_query["catalog_notifications_enabled"] = {"$ne": False}
        offer_id = payload.get("offer_id")
        if kind in {"api_flash_sale", "supplier_price_update"}:
            offer_id = (payload.get("event") or {}).get("offer_id")
        if offer_id is not None:
            recipient_query["catalog_notification_disabled_offer_ids"] = {
                "$ne": int(offer_id),
            }
    job = {
        "id": _next_id("broadcast_jobs"),
        "kind": kind,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "recipient_count": get_conn().users.count_documents(recipient_query),
        "sent_count": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if dedupe_key:
        job["dedupe_key"] = dedupe_key
    try:
        get_conn().broadcast_jobs.insert_one(job)
    except DuplicateKeyError:
        existing = get_conn().broadcast_jobs.find_one({"dedupe_key": dedupe_key})
        return _public(existing), False
    return _public(job), True


def claim_broadcast_job(job_id):
    row = get_conn().broadcast_jobs.find_one_and_update(
        {"id": int(job_id), "status": {"$in": ["queued", "retry"]}, "attempts": {"$lt": 3}},
        {"$set": {"status": "running", "started_at": datetime.now(UTC), "updated_at": datetime.now(UTC)}, "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return _public(row)


def complete_broadcast_job(job_id, sent_count):
    get_conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": "completed", "sent_count": int(sent_count), "completed_at": datetime.now(UTC), "updated_at": datetime.now(UTC), "error": ""}},
    )


def record_broadcast_message(job_id, kind, chat_id, message_id):
    """Remember one bot-authored broadcast message so it can be deleted later."""
    if not job_id or not chat_id or not message_id:
        return False
    get_conn().broadcast_messages.update_one(
        {
            "job_id": int(job_id),
            "chat_id": int(chat_id),
            "message_id": int(message_id),
        },
        {"$setOnInsert": {
            "kind": str(kind or "broadcast")[:60],
            "deleted": False,
            "created_at": datetime.now(UTC),
        }},
        upsert=True,
    )
    return True


def list_broadcast_messages(job_id, active_only=True):
    query = {"job_id": int(job_id)}
    if active_only:
        query["deleted"] = {"$ne": True}
    return [
        _public(row) for row in get_conn().broadcast_messages.find(query)
    ]


def mark_broadcast_message_deleted(job_id, chat_id, message_id, *, error=""):
    values = {
        "delete_error": str(error or "")[:300],
        "delete_attempted_at": datetime.now(UTC),
    }
    if not error:
        values.update({"deleted": True, "deleted_at": datetime.now(UTC)})
    get_conn().broadcast_messages.update_one(
        {
            "job_id": int(job_id),
            "chat_id": int(chat_id),
            "message_id": int(message_id),
        },
        {"$set": values},
    )


def get_broadcast_job(job_id):
    return _public(get_conn().broadcast_jobs.find_one({"id": int(job_id)}))


def set_broadcast_deletion_status(job_id, status, *, deleted_count=0, failed_count=0):
    get_conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {
            "deletion_status": str(status),
            "deleted_count": int(deleted_count),
            "delete_failed_count": int(failed_count),
            "deletion_updated_at": datetime.now(UTC),
        }},
    )


def list_broadcast_history(limit=20):
    """Return recent customer announcements that still have tracked messages."""
    kinds = [
        "stock", "restock_digest", "flash_sale", "api_flash_sale",
        "supplier_price_update", "admin_message", "maintenance",
        "affiliate_update",
    ]
    jobs = get_conn().broadcast_jobs.find({
        "kind": {"$in": kinds},
        "status": "completed",
    }).sort("created_at", DESCENDING).limit(max(1, int(limit) * 3))
    history = []
    for raw in jobs:
        job = _public(raw)
        total = get_conn().broadcast_messages.count_documents({"job_id": job["id"]})
        if not total:
            continue
        active = get_conn().broadcast_messages.count_documents({
            "job_id": job["id"], "deleted": {"$ne": True},
        })
        job["tracked_count"] = total
        job["active_message_count"] = active
        history.append(job)
        if len(history) >= int(limit):
            break
    return history


def fail_broadcast_job(job_id, error):
    row = get_conn().broadcast_jobs.find_one({"id": int(job_id)}, {"attempts": 1}) or {}
    status = "retry" if int(row.get("attempts") or 0) < 3 else "failed"
    get_conn().broadcast_jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": status, "error": str(error or "")[:500], "updated_at": datetime.now(UTC)}},
    )
    return status


def pending_broadcast_jobs(limit=20):
    # A deployment can stop while a worker is sending. Make abandoned jobs
    # eligible for retry on the next bot startup.
    get_conn().broadcast_jobs.update_many(
        {"status": "running", "started_at": {"$lt": datetime.now(UTC) - timedelta(minutes=10)}},
        {"$set": {"status": "retry", "updated_at": datetime.now(UTC)}},
    )
    return [
        _public(row) for row in get_conn().broadcast_jobs.find(
            {"status": {"$in": ["queued", "retry"]}, "attempts": {"$lt": 3}},
        ).sort("created_at", ASCENDING).limit(max(1, int(limit)))
    ]


def mark_broadcast_blocked(user_id, blocked=True):
    get_conn().users.update_one(
        {"telegram_id": int(user_id)},
        {"$set": {"broadcast_blocked": bool(blocked)}},
    )


def set_user_banned(user_id, banned):
    result = get_conn().users.update_one({"telegram_id": user_id}, {"$set": {"banned": bool(banned)}})
    audit_event("user.banned" if banned else "user.unbanned", details={"user_id": user_id})
    return bool(result.matched_count)


def is_user_banned(user_id):
    row = get_conn().users.find_one({"telegram_id": user_id}, {"banned": 1})
    return bool(row and row.get("banned"))


def list_audit_events(limit=100):
    return [_public(x) for x in get_conn().audit_events.find({}).sort("created_at", DESCENDING).limit(limit)]
