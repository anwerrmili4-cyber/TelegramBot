"""First-party statistics for the Tunisian storefront.

The shop does not use an external analytics vendor. The storefront posts a
small event (page view or interaction) and this module stores it in
``storefront_events``. The site admin reads the aggregates. Bot interactions
stay in ``interaction_events`` and are never mixed in.

Events keep a random visitor id and, when the customer is signed in, their
account id. IP addresses, emails and message bodies are not stored.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import database as db

# Tunisia stays on UTC+1 all year. Same clock as the site admin overview.
TUNIS_TZ = timezone(timedelta(hours=1))

RETENTION_SECONDS = 90 * 86400
MAX_EVENTS_PER_MINUTE = 40
VISIT_DEDUPE_SECONDS = 2
LIVE_WINDOW_SECONDS = 300
DEFAULT_DAYS = 30
MAX_DAYS = 90

# Keep this list aligned with the paths the storefront actually renders.
PAGE_LABELS = {
    "/": "Accueil",
    "/boutique": "Boutique",
    "/categories": "Catégories",
    "/offres": "Offres",
    "/prix": "Prix",
    "/annonces": "Annonces",
    "/support": "Support",
    "/aide": "Aide",
    "/conditions": "Conditions",
    "/confidentialite": "Confidentialité",
    "/contact": "Contact",
    "/communaute": "Communauté",
    "/signaler": "Signaler",
    "/messagerie": "Messagerie",
    "/connexion": "Connexion",
    "/inscription": "Inscription",
    "/verifier-email": "Vérification email",
    "/mot-de-passe-oublie": "Mot de passe oublié",
    "/reinitialiser-mot-de-passe": "Réinitialisation",
    "/mon-compte": "Mon compte",
}
PRODUCT_PAGES_PATH = "/produit"
PRODUCT_PATH = re.compile(r"^/produit/([1-9]\d{0,8})$")
VISITOR_ID = re.compile(r"^[a-f0-9]{32}$")

INTERACTION_LABELS = {
    "cart_add": "Ajout au panier",
    "checkout": "Paiement ouvert",
    "order": "Commande envoyée",
    "favorite": "Favori",
    "search": "Recherche",
    "stock_alert": "Alerte stock",
}

# Coarse buckets computed in the browser. No user agent or referrer URL is stored.
DEVICE_LABELS = {
    "mobile": "Mobile",
    "tablet": "Tablette",
    "desktop": "Ordinateur",
}
SOURCE_LABELS = {
    "direct": "Accès direct",
    "search": "Moteurs de recherche",
    "social": "Réseaux sociaux",
    "referral": "Autres sites",
}
FUNNEL_STEPS = (
    ("visitors", "Visiteurs"),
    ("product", "Fiche produit vue"),
    ("cart_add", "Ajout au panier"),
    ("checkout", "Paiement ouvert"),
    ("order", "Commande envoyée"),
)
WEEKDAY_LABELS = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")
# The previous period must still be inside the 90-day retention to be compared.
MAX_COMPARED_DAYS = 45


class SiteStatsError(ValueError):
    """Raised with a French message and an HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key) or [default]
    return str(values[0] if values else default).strip()


def _days(params: dict[str, list[str]] | None) -> int:
    raw = _first(params or {}, "days", str(DEFAULT_DAYS))
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_DAYS
    if days < 1:
        return DEFAULT_DAYS
    return min(days, MAX_DAYS)


def _label(value: Any) -> str:
    raw = " ".join(str(value or "").split())
    if "@" in raw:
        return ""
    return re.sub(r"[^\w\s.+#&'’/-]", "", raw, flags=re.UNICODE).strip()[:60]


def _offer_id(value: Any) -> int:
    if value in (None, "", 0, "0"):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SiteStatsError("Produit invalide.") from exc
    if parsed < 1 or parsed > 1_000_000_000:
        raise SiteStatsError("Produit invalide.")
    return parsed


def _customer_id(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _path(value: Any) -> tuple[str, int]:
    raw = str(value or "").split("?", 1)[0].split("#", 1)[0].strip()
    if not raw or len(raw) > 80 or ".." in raw or "\\" in raw or raw.startswith("//"):
        raise SiteStatsError("Page inconnue.")
    if raw != "/":
        raw = raw.rstrip("/") or "/"
    match = PRODUCT_PATH.fullmatch(raw)
    if match:
        return raw, int(match.group(1))
    if raw in PAGE_LABELS:
        return raw, 0
    raise SiteStatsError("Page inconnue.")


def page_label(path: str) -> str:
    if path in PAGE_LABELS:
        return PAGE_LABELS[path]
    if path == PRODUCT_PAGES_PATH or PRODUCT_PATH.fullmatch(path):
        return "Fiches produit"
    return "Page"


def record(payload: dict[str, Any], customer_id: int | None = None) -> dict[str, Any]:
    """Store one storefront event. Identical page views inside two seconds collapse."""
    if not isinstance(payload, dict):
        raise SiteStatsError("Requête invalide.")
    kind = str(payload.get("kind") or "").strip()
    if kind not in {"visit", "interaction"}:
        raise SiteStatsError("Type d'événement inconnu.")
    visitor_id = str(payload.get("visitor_id") or "").strip().lower()
    if not VISITOR_ID.fullmatch(visitor_id):
        raise SiteStatsError("Visiteur invalide.")

    if kind == "visit":
        action = "page"
        if not str(payload.get("path") or "").strip():
            raise SiteStatsError("Page inconnue.")
        path, path_offer = _path(payload.get("path"))
    else:
        action = str(payload.get("action") or "").strip()
        if action not in INTERACTION_LABELS:
            raise SiteStatsError("Interaction inconnue.")
        if str(payload.get("path") or "").strip():
            path, path_offer = _path(payload.get("path"))
        else:
            path, path_offer = "/", 0

    body_offer = _offer_id(payload.get("offer_id")) if payload.get("offer_id") not in (None, "") else 0
    if path_offer and body_offer and path_offer != body_offer:
        raise SiteStatsError("Produit invalide.")
    offer_id = path_offer or body_offer
    label = _label(payload.get("label"))
    account_id = _customer_id(customer_id)

    now = int(datetime.now(UTC).timestamp())
    conn = db.get_conn()
    if kind == "visit":
        duplicate = conn.storefront_events.find_one(
            {
                "visitor_id": visitor_id,
                "kind": "visit",
                "path": path,
                "created_at": {"$gte": now - VISIT_DEDUPE_SECONDS},
            },
            {"_id": 1},
        )
        if duplicate:
            return {"ok": True, "stored": False}

    recent = conn.storefront_events.count_documents(
        {"visitor_id": visitor_id, "created_at": {"$gte": now - 60}}
    )
    if recent >= MAX_EVENTS_PER_MINUTE:
        raise SiteStatsError("Trop d'événements pour ce visiteur. Réessayez dans un instant.", status=429)

    device = str(payload.get("device") or "").strip()
    source = str(payload.get("source") or "").strip() if kind == "visit" else ""
    conn.storefront_events.insert_one({
        "kind": kind,
        "action": action,
        "path": path,
        "label": label,
        "offer_id": offer_id,
        "visitor_id": visitor_id,
        "customer_id": account_id,
        "device": device if device in DEVICE_LABELS else "",
        "source": source if source in SOURCE_LABELS else "",
        "day": datetime.now(TUNIS_TZ).strftime("%Y-%m-%d"),
        "created_at": now,
        "created_at_date": datetime.fromtimestamp(now, UTC),
    })
    return {"ok": True, "stored": True}


def _window(days: int) -> tuple[int, str, list[str]]:
    now = datetime.now(TUNIS_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    labels = [(start + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(days)]
    return int(start.timestamp()), now.strftime("%Y-%m-%d"), labels


def _grouped(match: dict[str, Any], key: str) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for row in db.get_conn().storefront_events.aggregate([
        {"$match": match},
        {"$group": {"_id": f"${key}", "count": {"$sum": 1}}},
    ]):
        counts[row.get("_id")] = int(row.get("count") or 0)
    return counts


def _visitors(match: dict[str, Any]) -> int:
    return len(db.get_conn().storefront_events.distinct("visitor_id", match))


def _period_totals(start_ts: int, end_ts: int) -> dict[str, int]:
    span = {"created_at": {"$gte": start_ts, "$lt": end_ts}}
    events = db.get_conn().storefront_events
    return {
        "visits": events.count_documents({**span, "kind": "visit"}),
        "unique": _visitors({**span, "kind": "visit"}),
        "interactions": events.count_documents({**span, "kind": "interaction"}),
        "orders": events.count_documents({**span, "kind": "interaction", "action": "order"}),
    }


def _heatmap(window: dict[str, Any]) -> list[dict[str, Any]]:
    """Visits per weekday and hour, on the Tunis clock."""
    grid = [[0] * 24 for _ in WEEKDAY_LABELS]
    cursor = db.get_conn().storefront_events.find({**window, "kind": "visit"}, {"_id": 0, "created_at": 1})
    for row in cursor:
        moment = datetime.fromtimestamp(int(row.get("created_at") or 0), TUNIS_TZ)
        grid[moment.weekday()][moment.hour] += 1
    return [{"day": label, "hours": hours} for label, hours in zip(WEEKDAY_LABELS, grid, strict=True)]


def _labelled(counts: dict[Any, int], labels: dict[str, str]) -> list[dict[str, Any]]:
    rows = [{"key": key, "label": label, "count": int(counts.get(key) or 0)} for key, label in labels.items()]
    return sorted(rows, key=lambda row: -row["count"])


def stats(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Headline figures, a daily series, and the lists shown on the site admin."""
    days = _days(params)
    start_ts, today, labels = _window(days)
    conn = db.get_conn()
    window = {"created_at": {"$gte": start_ts}}

    visits_by_day: dict[str, int] = {}
    interactions_by_day: dict[str, int] = {}
    for row in conn.storefront_events.aggregate([
        {"$match": window},
        {"$group": {
            "_id": {"day": "$day", "kind": "$kind"},
            "count": {"$sum": 1},
        }},
    ]):
        bucket = row.get("_id") or {}
        day = str(bucket.get("day") or "")
        count = int(row.get("count") or 0)
        if bucket.get("kind") == "visit":
            visits_by_day[day] = visits_by_day.get(day, 0) + count
        elif bucket.get("kind") == "interaction":
            interactions_by_day[day] = interactions_by_day.get(day, 0) + count

    visitors_by_day: dict[str, int] = {}
    days_by_visitor: dict[str, int] = {}
    for row in conn.storefront_events.aggregate([
        {"$match": {**window, "kind": "visit"}},
        {"$group": {"_id": {"day": "$day", "visitor": "$visitor_id"}}},
    ]):
        bucket = row.get("_id") or {}
        day = str(bucket.get("day") or "")
        visitors_by_day[day] = visitors_by_day.get(day, 0) + 1
        visitor = str(bucket.get("visitor") or "")
        days_by_visitor[visitor] = days_by_visitor.get(visitor, 0) + 1

    page_counts: dict[str, int] = {}
    for path, count in _grouped({**window, "kind": "visit"}, "path").items():
        key = PRODUCT_PAGES_PATH if PRODUCT_PATH.fullmatch(str(path or "")) else str(path or "")
        if not key:
            continue
        page_counts[key] = page_counts.get(key, 0) + count
    popular_pages = [
        {"path": path, "label": page_label(path), "visits": count}
        for path, count in sorted(page_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]

    view_counts = {
        int(offer_id): count
        for offer_id, count in _grouped({**window, "kind": "visit", "offer_id": {"$gt": 0}}, "offer_id").items()
        if str(offer_id).isdigit() or isinstance(offer_id, int)
    }
    cart_counts = {
        int(offer_id): count
        for offer_id, count in _grouped(
            {**window, "kind": "interaction", "action": "cart_add", "offer_id": {"$gt": 0}},
            "offer_id",
        ).items()
        if str(offer_id).isdigit() or isinstance(offer_id, int)
    }
    offer_ids = sorted(set(view_counts) | set(cart_counts))
    names = {}
    if offer_ids:
        for offer in conn.offers.find({"id": {"$in": offer_ids}}, {"id": 1, "name": 1, "site_name": 1}):
            names[int(offer["id"])] = str(offer.get("site_name") or offer.get("name") or "").strip()
    popular_products = [
        {
            "offer_id": offer_id,
            "name": names.get(offer_id) or f"Produit #{offer_id}",
            "views": view_counts.get(offer_id, 0),
            "cart_adds": cart_counts.get(offer_id, 0),
        }
        for offer_id in offer_ids
    ]
    popular_products.sort(key=lambda item: (-item["views"], -item["cart_adds"], item["name"].casefold()))
    popular_products = popular_products[:8]

    action_counts = _grouped({**window, "kind": "interaction"}, "action")
    actions = [
        {"action": action, "label": label, "count": int(action_counts.get(action) or 0)}
        for action, label in INTERACTION_LABELS.items()
    ]

    search_counts = _grouped(
        {**window, "kind": "interaction", "action": "search", "label": {"$gt": ""}},
        "label",
    )
    searches = [
        {"label": str(label), "count": count}
        for label, count in sorted(search_counts.items(), key=lambda item: (-item[1], str(item[0]).casefold()))
        if str(label or "").strip()
    ][:5]

    recent_rows = list(
        conn.storefront_events.find(window, {"_id": 0, "visitor_id": 0, "created_at_date": 0})
        .sort("created_at", -1)
        .limit(12)
    )
    customer_ids = sorted({int(row["customer_id"]) for row in recent_rows if row.get("customer_id")})
    customer_names = {}
    if customer_ids:
        for customer in conn.storefront_customers.find({"id": {"$in": customer_ids}}, {"id": 1, "name": 1}):
            customer_names[int(customer["id"])] = str(customer.get("name") or "").strip()
    recent = []
    for row in recent_rows:
        action = str(row.get("action") or "")
        account_id = _customer_id(row.get("customer_id"))
        recent.append({
            "created_at": int(row.get("created_at") or 0),
            "kind": row.get("kind") or "",
            "action": action,
            "action_label": "Visite" if action == "page" else INTERACTION_LABELS.get(action, "Interaction"),
            "path": row.get("path") or "",
            "page_label": page_label(str(row.get("path") or "")),
            "label": str(row.get("label") or ""),
            "offer_id": int(row.get("offer_id") or 0),
            "customer_name": customer_names.get(account_id or 0, ""),
        })

    daily = [
        {
            "date": day,
            "visits": visits_by_day.get(day, 0),
            "visitors": visitors_by_day.get(day, 0),
            "interactions": interactions_by_day.get(day, 0),
        }
        for day in labels
    ]

    unique = _visitors({**window, "kind": "visit"})
    funnel_counts = {
        "visitors": unique,
        "product": _visitors({**window, "kind": "visit", "offer_id": {"$gt": 0}}),
        **{
            action: _visitors({**window, "kind": "interaction", "action": action})
            for action in ("cart_add", "checkout", "order")
        },
    }
    funnel = [{"key": key, "label": label, "visitors": funnel_counts[key]} for key, label in FUNNEL_STEPS]

    source_counts = _grouped({**window, "kind": "visit", "source": {"$in": list(SOURCE_LABELS)}}, "source")
    device_counts: dict[str, int] = {}
    for row in conn.storefront_events.aggregate([
        {"$match": {**window, "kind": "visit", "device": {"$in": list(DEVICE_LABELS)}}},
        {"$group": {"_id": {"device": "$device", "visitor": "$visitor_id"}}},
    ]):
        device = str((row.get("_id") or {}).get("device") or "")
        device_counts[device] = device_counts.get(device, 0) + 1

    visits = sum(point["visits"] for point in daily)
    interactions = sum(point["interactions"] for point in daily)
    entries = sum(source_counts.values())
    previous = None
    if days <= MAX_COMPARED_DAYS:
        previous = _period_totals(start_ts - days * 86400, start_ts)

    return {
        "ok": True,
        "summary": {
            "days": days,
            "visits_today": visits_by_day.get(today, 0),
            "visits": visits,
            "unique_today": visitors_by_day.get(today, 0),
            "unique": unique,
            "interactions_today": interactions_by_day.get(today, 0),
            "interactions": interactions,
            "orders": int(action_counts.get("order") or 0),
            "live_visitors": _visitors(
                {"created_at": {"$gte": int(datetime.now(UTC).timestamp()) - LIVE_WINDOW_SECONDS}},
            ),
            "returning": sum(1 for count in days_by_visitor.values() if count > 1),
            "signed_in": _visitors({**window, "customer_id": {"$gt": 0}}),
            "engaged": _visitors({**window, "kind": "interaction"}),
            "entries": entries,
        },
        "previous": previous,
        "funnel": funnel,
        "sources": _labelled(source_counts, SOURCE_LABELS),
        "devices": _labelled(device_counts, DEVICE_LABELS),
        "heatmap": _heatmap(window),
        "daily": daily,
        "popular_pages": popular_pages,
        "popular_products": popular_products,
        "actions": actions,
        "searches": searches,
        "recent": recent,
    }
