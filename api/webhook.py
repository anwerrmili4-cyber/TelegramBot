"""HTTP endpoint for Telegram updates, the dashboard, assets, and scheduled jobs."""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import hmac
import html
import io
import json
import logging
import mimetypes
import os
import re
import threading
import time
import traceback
from datetime import UTC, datetime
from email.parser import BytesParser
from email.policy import default as email_policy
from enum import Enum
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from api.buyer_api_docs import openapi_document, swagger_html
from api.dashboard import render_dashboard
from api.public_site import render_public_site
from app import __version__, support_bridge
from app.domain import (
    admin_ai_service,
    binance_dashboard_service,
    buyer_api_service,
    external_api_service,
    inventory_service,
    lovable_service,
    order_service,
    reseller_comparison_service,
    reseller_service,
    support_service,
    wallet_service,
    warranty_service,
)
from app.web import dashboard_api, notification_service
from bot import (
    build_app,
    monitor_codex_number_deadlines,
    queue_broadcast,
)
from config import (
    ADMIN_ID,
    BOT_TOKEN,
    CURRENCY,
    DASHBOARD_PASSWORD,
    env_value,
    public_base_url_from_environment,
)
from i18n import t
from payment_verifier import binance_healthcheck, bybit_healthcheck

_loop = asyncio.new_event_loop()
_app = None
_runtime_lock = threading.RLock()
log = logging.getLogger(__name__)
MAX_WEBHOOK_BODY_BYTES = 1_000_000
ADMIN_UI_DIST = Path(__file__).resolve().parent.parent / "admin-ui" / "dist"
ADMIN_SESSION_COOKIE = "blackmarket_admin_session"
ADMIN_SESSION_TTL_SECONDS = 12 * 60 * 60


def _duration_form_values(form, prefix: str, default_days: int, *, allow_zero: bool):
    """Read a value/unit pair while remaining compatible with old day-only forms."""
    unit = warranty_service.normalize_duration_unit(form.get(f"{prefix}_unit", "days"))
    raw_value = form.get(f"{prefix}_value")
    if raw_value is None or str(raw_value).strip() == "":
        raw_value = form.get(f"{prefix}_days", str(default_days))
        unit = "days"
    value = int(str(raw_value).strip())
    if value < 0 or (not allow_zero and value < 1):
        raise ValueError(f"{prefix} invalide")
    return value, unit, warranty_service.duration_to_days(value, unit)


def health_payload() -> dict:
    """Return a public, non-sensitive health response."""
    return {
        "ok": True,
        "service": "TelegramBot webhook",
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _telegram_api(method: str, payload: dict | None = None) -> dict:
    """Call Telegram without ever including the bot token in returned errors."""
    if not BOT_TOKEN:
        return {"ok": False, "message": "HP_BOT_TOKEN n’est pas configuré."}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    result = None
    for attempt in range(3):
        request = Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method="POST" if body else "GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if exc.code >= 500 and attempt < 2:
                time.sleep(attempt + 1)
                continue
            return {
                "ok": False,
                "http_status": exc.code,
                "message": f"Telegram répond HTTP {exc.code}.",
            }
        except (URLError, TimeoutError, json.JSONDecodeError):
            if attempt < 2:
                time.sleep(attempt + 1)
                continue
            return {"ok": False, "message": "Telegram est temporairement indisponible."}
    return result if isinstance(result, dict) else {
        "ok": False,
        "message": "Réponse Telegram invalide.",
    }


def telegram_webhook_health() -> dict:
    """Return a safe, admin-facing view of Telegram webhook state."""
    response = _telegram_api("getWebhookInfo")
    if not response.get("ok"):
        return {
            "ok": False,
            "message": response.get("message") or response.get("description") or "Telegram indisponible.",
            "http_status": response.get("http_status"),
        }
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    expected_url = public_base_url_from_environment() + "/api/webhook"
    return {
        "ok": True,
        "healthy": result.get("url") == expected_url and not result.get("last_error_message"),
        "url": result.get("url") or "",
        "expected_url": expected_url,
        "pending_update_count": int(result.get("pending_update_count") or 0),
        "last_error_message": str(result.get("last_error_message") or "")[:500],
    }


def repair_telegram_webhook() -> dict:
    """Register the stable production webhook with Telegram's secret header."""
    secret = env_value("HP_WEBHOOK_SECRET")
    if not secret:
        return {"ok": False, "message": "HP_WEBHOOK_SECRET n’est pas configuré."}
    expected_url = public_base_url_from_environment() + "/api/webhook"
    response = _telegram_api(
        "setWebhook",
        {
            "url": expected_url,
            "secret_token": secret,
            "drop_pending_updates": False,
        },
    )
    if not response.get("ok"):
        return {
            "ok": False,
            "message": response.get("message") or response.get("description") or "Réparation refusée par Telegram.",
            "http_status": response.get("http_status"),
        }
    return {"ok": True, "url": expected_url, "message": "Webhook Telegram réparé."}


def dashboard_write_token() -> str:
    """Create a scoped write token without exposing the dashboard password."""
    if not DASHBOARD_PASSWORD:
        return ""
    return hmac.new(
        DASHBOARD_PASSWORD.encode("utf-8"),
        b"telegram-bot-dashboard-write-v1",
        hashlib.sha256,
    ).hexdigest()


def reseller_dashboard_summary() -> dict:
    """Return provider-aware dashboard state without exposing API keys."""
    providers = reseller_service.provider_summaries()
    configured = [item for item in providers if item["configured"]]
    default_provider = (
        reseller_service.PROVIDER
        if any(item["id"] == reseller_service.PROVIDER for item in configured)
        else configured[0]["id"] if configured else reseller_service.PROVIDER
    )
    return {
        "configured": bool(configured),
        "default_provider": default_provider,
        "selected_count": db.get_conn().reseller_products.count_documents(
            {"enabled": True}
        ),
    }


def admin_session_token(expires_at: int) -> str:
    """Create a short-lived signed session tied to the current admin password."""
    if not DASHBOARD_PASSWORD:
        return ""
    signature = hmac.new(
        DASHBOARD_PASSWORD.encode("utf-8"),
        f"telegram-bot-admin-session-v1:{int(expires_at)}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{int(expires_at)}.{signature}"


def undo_audit_event(event_id: int) -> dict:
    """Restore a recent reversible admin event only when its target is unchanged."""
    conn = db.get_conn()
    event = conn.audit_events.find_one({"id": int(event_id)})
    if not event:
        raise ValueError("Événement introuvable")
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    if not details.get("reversible") or details.get("undone"):
        raise ValueError("Cet événement ne peut pas être restauré")
    created_at = event.get("created_at")
    if isinstance(created_at, datetime):
        normalized_created_at = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at.astimezone(UTC)
    else:
        normalized_created_at = None
    if normalized_created_at and (datetime.now(UTC) - normalized_created_at).total_seconds() > 86_400:
        raise ValueError("Le délai de restauration de 24 heures est dépassé")

    action = str(event.get("action") or "")
    collection = conn.services if action == "service.toggled" else conn.offers
    if action not in {"service.toggled", "offer.toggled", "offer.bulk_toggled", "offer.bulk_updated"}:
        raise ValueError("Type d’événement non restaurable")
    if isinstance(details.get("changes"), list):
        changes = details["changes"]
    else:
        entity_id = details.get("service_id") if action == "service.toggled" else details.get("offer_id")
        changes = [{"id": entity_id, "before": details.get("before") or {}, "after": details.get("after") or {}}]

    restored = 0
    skipped = 0
    for change in changes[:100]:
        entity_id = change.get("id")
        before = change.get("before") if isinstance(change.get("before"), dict) else {}
        after = change.get("after") if isinstance(change.get("after"), dict) else {}
        current = collection.find_one({"id": entity_id})
        if not current or any(current.get(key) != value for key, value in after.items()):
            skipped += 1
            continue
        set_values = {key: value for key, value in before.items() if value is not None}
        unset_values = {key: "" for key, value in before.items() if value is None}
        update = {}
        if set_values:
            update["$set"] = set_values
        if unset_values:
            update["$unset"] = unset_values
        if update:
            collection.update_one({"id": entity_id}, update)
            if action != "service.toggled" and "service_id" in before:
                conn.reseller_products.update_many(
                    {"local_offer_id": int(entity_id)},
                    {"$set": {"service_id": before["service_id"], "updated_at": int(time.time())}},
                )
        restored += 1

    conn.audit_events.update_one({"id": int(event_id)}, {"$set": {
        "details.undone": True,
        "details.undone_at": datetime.now(UTC),
        "details.undo_restored": restored,
        "details.undo_skipped": skipped,
    }})
    db.audit_event("audit.undo", actor_id=ADMIN_ID, details={
        "event_id": int(event_id), "source_action": action, "restored": restored, "skipped": skipped,
    })
    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "message": f"{restored} élément(s) restauré(s), {skipped} ignoré(s).",
    }


def public_site_html() -> str:
    bot_username = os.environ.get("HP_BOT_USERNAME", "blackmarketa_bot").strip().lstrip("@")
    shop_name = os.environ.get("HP_SHOP_NAME", "BlackMarket").strip() or "BlackMarket"
    public_base_url = public_base_url_from_environment()
    return render_public_site(bot_username, shop_name, public_base_url)


def _legacy_public_site_html() -> str:
    """Kept temporarily as a reference while older deployments roll over."""
    bot_username = os.environ.get("HP_BOT_USERNAME", "blackmarketa_bot").strip().lstrip("@")
    shop_name = os.environ.get("HP_SHOP_NAME", "BlackMarket").strip() or "BlackMarket"
    public_base_url = public_base_url_from_environment()
    bot_url = f"https://t.me/{html.escape(bot_username)}"
    social_image_url = f"{html.escape(public_base_url)}/assets/blackmarket-midnight-og.png"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(shop_name)} - Bot Telegram</title>
  <meta property="og:title" content="{html.escape(shop_name)} · Midnight Merchant">
  <meta property="og:description" content="Catalogue, commandes et support depuis le bot Telegram officiel.">
  <meta property="og:image" content="{social_image_url}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{social_image_url}">
  <style>
    :root {{ color-scheme: dark; --bg:#07101d; --panel:#101d2f; --line:#26364d; --text:#e8eef8; --muted:#9fb0c9; --brand:#0891b2; --brand2:#22d3ee; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; font-family:Inter,Arial,sans-serif; background:var(--bg); color:var(--text); display:flex; align-items:center; justify-content:center; padding:24px; }}
    main {{ width:min(920px,100%); }}
    .hero {{ border:1px solid var(--line); background:var(--panel); border-radius:18px; padding:34px; box-shadow:0 24px 80px rgba(0,0,0,.35); }}
    h1 {{ margin:0 0 10px; font-size:clamp(32px,6vw,58px); line-height:1; }}
    p {{ color:var(--muted); font-size:18px; line-height:1.6; margin:0 0 26px; max-width:720px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-top:22px; }}
    a {{ text-decoration:none; color:var(--text); }}
    .btn {{ display:flex; align-items:center; justify-content:center; min-height:54px; border:1px solid var(--line); border-radius:12px; background:#0b1728; font-weight:700; }}
    .btn.primary {{ background:linear-gradient(135deg,var(--brand),var(--brand2)); color:white; border-color:transparent; }}
    .btn:hover {{ transform:translateY(-1px); border-color:var(--brand2); }}
    .status {{ display:inline-flex; gap:8px; align-items:center; padding:8px 12px; border-radius:999px; background:#0b1728; color:var(--muted); border:1px solid var(--line); margin-bottom:18px; }}
    .dot {{ width:10px; height:10px; border-radius:50%; background:#22c55e; box-shadow:0 0 18px #22c55e; }}
    footer {{ color:var(--muted); margin-top:16px; font-size:13px; text-align:center; }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="status"><span class="dot"></span> Site connecte directement au bot Telegram</div>
      <h1>{html.escape(shop_name)}</h1>
      <p>Choisis une action. Chaque bouton ouvre le bot Telegram officiel pour commander, consulter le catalogue, suivre les commandes ou contacter le support.</p>
      <div class="grid">
        <a class="btn primary" href="{bot_url}" target="_blank" rel="noopener">Ouvrir le bot</a>
        <a class="btn" href="{bot_url}?start=catalog" target="_blank" rel="noopener">Catalogue</a>
        <a class="btn" href="{bot_url}?start=orders" target="_blank" rel="noopener">Mes commandes</a>
        <a class="btn" href="{bot_url}?start=support" target="_blank" rel="noopener">Support</a>
      </div>
    </section>
    <footer>Bot: @{html.escape(bot_username)} - Webhook actif</footer>
  </main>
</body>
</html>"""


def _run_async(awaitable):
    """Serialize access to the shared Telegram asyncio event loop."""
    with _runtime_lock:
        return _loop.run_until_complete(awaitable)


def _application():
    global _app
    with _runtime_lock:
        if _app is None:
            candidate = build_app()
            _run_async(candidate.initialize())
            _app = candidate
    return _app


def _deliver_ticket_reply(user_id: int, ticket_id: int, message: str) -> None:
    """Send the Telegram copy outside the dashboard request latency path."""
    def deliver() -> None:
        try:
            _run_async(
                _application().bot.send_message(
                    user_id,
                    f"🎫 <b>Réponse du Support (Ticket #{ticket_id})</b>\n\n{html.escape(message)}",
                    parse_mode=ParseMode.HTML,
                )
            )
        except Exception:
            log.exception("Failed to notify user about ticket reply")

    threading.Thread(target=deliver, name=f"ticket-reply-{ticket_id}", daemon=True).start()


def _notify_wallet_adjustment(result: dict, reason: str = "") -> bool:
    """Notify a customer after an admin wallet adjustment without undoing it on failure."""
    amount = float(result.get("amount") or 0)
    if amount <= 0:
        return False
    user_id = int(result["user_id"])
    balance = float(result.get("balance") or 0)
    safe_reason = html.escape(str(reason or "Crédit ajouté par l’administrateur").strip()[:500])
    message = (
        "💰 <b>Votre solde a été crédité</b>\n\n"
        f"Montant ajouté : <b>+{amount:.2f} {html.escape(CURRENCY)}</b>\n"
        f"Nouveau solde : <b>{balance:.2f} {html.escape(CURRENCY)}</b>\n"
        f"Motif : {safe_reason}\n\n"
        "Le crédit est disponible immédiatement dans votre portefeuille."
    )
    try:
        _run_async(
            _application().bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
            )
        )
        return True
    except Exception:
        log.exception("Unable to notify user %s about wallet credit", user_id)
        return False


def _notify_onchain_topup(topup: dict, approved: bool) -> bool:
    """Tell the customer about the administrator's on-chain top-up decision."""
    user_id = int(topup["user_id"])
    lang = db.get_user_lang(user_id) or "en"
    if approved:
        amount = int(topup.get("amount_cents") or 0) / 100
        text = t(
            lang,
            "topup_onchain_approved",
            amount=f"{amount:.2f}",
            balance=f"{float(topup.get('balance') or 0):.2f}",
        )
    else:
        text = t(lang, "topup_onchain_rejected")
    try:
        _run_async(
            _application().bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        )
        return True
    except Exception:
        log.exception("Unable to notify user %s about on-chain top-up", user_id)
        return False


class handler(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict, headers: dict[str, str] | None = None):
        body = json.dumps(payload, default=self._json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _reply_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        filename: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_multipart(self, max_bytes: int) -> tuple[dict[str, str], dict]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            raise ValueError("Le formulaire de pièce jointe est invalide.")
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > max_bytes:
            raise ValueError("La pièce jointe dépasse la taille autorisée.")
        envelope = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
            + self.rfile.read(size)
        )
        parsed = BytesParser(policy=email_policy).parsebytes(envelope)
        fields: dict[str, str] = {}
        upload: dict = {}
        for part in parsed.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename and name == "file":
                upload = {
                    "body": payload,
                    "filename": Path(filename).name[:180] or "attachment",
                    "content_type": part.get_content_type(),
                }
            elif not filename:
                fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not upload:
            raise ValueError("Choisissez une image ou une vidéo.")
        return fields, upload

    @staticmethod
    def _json_default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        return str(value)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path.rstrip("/")

        if path == "/api/openapi.json":
            self._reply(200, openapi_document())
            return

        if path == "/api/swagger":
            body = swagger_html().encode("utf-8")
            self._reply_bytes(200, body, "text/html; charset=utf-8")
            return

        if path in {
            "/api/v2/telegram-buyer/products",
            "/api/v2/telegram-buyer/balance",
        }:
            endpoint = "products" if path.endswith("/products") else "balance"
            try:
                if "key" in parse_qs(url.query):
                    raise buyer_api_service.BuyerApiError(
                        400,
                        "API_KEY_LOCATION_NOT_ALLOWED",
                        "Send the API key only as Authorization: Bearer <API_KEY>.",
                    )
                key = buyer_api_service.authenticate_bearer(
                    self.headers.get("Authorization", ""), self._client_ip(), endpoint
                )
                payload = (
                    buyer_api_service.products(key)
                    if endpoint == "products"
                    else buyer_api_service.balance(key)
                )
                self._reply(200, payload)
            except buyer_api_service.BuyerApiError as exc:
                self._reply_buyer_error(exc)
            except Exception:
                log.exception("Buyer API %s request failed", endpoint)
                self._reply(500, {
                    "success": False,
                    "code": "INTERNAL_ERROR",
                    "message": "The buyer API is temporarily unavailable.",
                })
            return

        if path == "/api/cron/restock":
            expected = env_value("CRON_SECRET")
            supplied = self.headers.get("Authorization", "")
            if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                result = reseller_service.detect_restock_events()
                queued_jobs = []
                for event in result["events"]:
                    event_source = {"window": int(time.time() // 300), "event": event}
                    event_key = "restock:" + hashlib.sha256(
                        json.dumps(event_source, sort_keys=True).encode()
                    ).hexdigest()[:32]
                    queued_jobs.append(queue_broadcast(
                        "stock",
                        offer_id=int(event["offer_id"]),
                        added=max(0, int(event.get("added") or 0)),
                        stock=max(0, int(event.get("stock") or 0)),
                        supplier_event=event,
                        dedupe_key=event_key,
                    ))
                result["queued_broadcasts"] = sum(1 for job in queued_jobs if job["queued"])
                result["queued_recipients"] = sum(
                    job.get("recipient_count", 0) for job in queued_jobs if job["queued"]
                )
                result["announced_messages"] = 0
                db.set_setting("stock_cron_last_run_at", int(time.time()))
                db.set_setting("stock_cron_last_status", "ok" if result["ok"] else "partial")
                db.set_setting("stock_cron_last_checked", int(result["checked"]))
                db.set_setting("stock_cron_last_events", len(result["events"]))
                db.set_setting("stock_cron_last_announced", 0)
                db.set_setting("stock_cron_last_queued", result["queued_broadcasts"])
                self._reply(200 if result["ok"] else 207, result)
            except Exception as exc:
                log.exception("Automatic reseller stock check failed")
                db.set_setting("stock_cron_last_run_at", int(time.time()))
                db.set_setting("stock_cron_last_status", "failed")
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        if path == "/api/cron/prices":
            expected = env_value("CRON_SECRET")
            supplied = self.headers.get("Authorization", "")
            if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                result = reseller_service.detect_supplier_price_changes()
                db.set_setting("price_cron_last_run_at", int(time.time()))
                db.set_setting("price_cron_last_status", "queueing")
                db.set_setting("price_cron_last_checked", int(result["checked"]))
                db.set_setting("price_cron_last_changes", len(result["changes"]))
                db.set_setting("price_cron_last_flash_sales", len(result["flash_sales"]))
                queued = 0
                queued_recipients = 0
                for event in result["changes"]:
                    dedupe_source = {"window": int(time.time() // 300), "event": event}
                    dedupe_key = "api-price:" + hashlib.sha256(json.dumps(dedupe_source, sort_keys=True).encode()).hexdigest()[:32]
                    job = queue_broadcast(
                        "api_flash_sale" if event.get("decreased") else "supplier_price_update",
                        event=event,
                        dedupe_key=dedupe_key,
                    )
                    queued += int(job["queued"])
                    queued_recipients = max(queued_recipients, job["recipient_count"])
                result["queued_broadcasts"] = queued
                result["queued_recipients"] = queued_recipients
                result["announced_messages"] = 0
                db.set_setting("price_cron_last_status", "ok" if result["ok"] else "partial")
                db.set_setting("price_cron_last_announced", 0)
                db.set_setting("price_cron_last_queued", queued)
                self._reply(200 if result["ok"] else 207, result)
            except Exception as exc:
                log.exception("Automatic reseller price check failed")
                db.set_setting("price_cron_last_run_at", int(time.time()))
                db.set_setting("price_cron_last_status", "failed")
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        if path == "/api/cron/pending-payments":
            expected = env_value("CRON_SECRET")
            supplied = self.headers.get("Authorization", "")
            if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                cancelled_ids = order_service.cancel_stale_pending_orders()
                self._reply(200, {
                    "ok": True,
                    "cancelled": len(cancelled_ids),
                    "order_ids": cancelled_ids,
                })
            except Exception as exc:
                log.exception("Pending-payment cancellation monitor failed")
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        if path == "/fr" or path.startswith("/fr/"):
            self._reply(404, {"ok": False, "error": "language_removed"})
            return

        order_match = re.fullmatch(
            r"/api/v2/telegram-buyer/orders/([^/]+)", path
        )
        if order_match:
            try:
                if "key" in parse_qs(url.query):
                    raise buyer_api_service.BuyerApiError(
                        400,
                        "API_KEY_LOCATION_NOT_ALLOWED",
                        "Send the API key only as Authorization: Bearer <API_KEY>.",
                    )
                key = buyer_api_service.authenticate_bearer(
                    self.headers.get("Authorization", ""), self._client_ip(), "status"
                )
                payload = buyer_api_service.order_status(key, order_match.group(1))
                headers = {"Cache-Control": "no-store"}
                if payload.get("status") == "processing":
                    headers["Retry-After"] = "5"
                self._reply(200, payload, headers=headers)
            except buyer_api_service.BuyerApiError as exc:
                self._reply_buyer_error(exc)
            except Exception:
                log.exception("Buyer API order-status request failed")
                self._reply(500, {
                    "success": False,
                    "code": "INTERNAL_ERROR",
                    "message": "The buyer API is temporarily unavailable.",
                })
            return

        if path in {"", "/", "/ar"} or path.startswith("/ar/"):
            body = public_site_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        public_assets = {
            "/assets/chatgpt-plus-benefits.png": "chatgpt-plus-benefits.png",
            "/assets/blackmarket-welcome-v2.png": "blackmarket-welcome-v2.png",
            "/assets/blackmarket-midnight-og.png": "blackmarket-midnight-og.png",
        }
        if path in public_assets:
            asset_path = Path(__file__).resolve().parent.parent / "assets" / public_assets[path]
            if asset_path.exists():
                body = asset_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=604800, immutable")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._reply(404, {"ok": False, "error": "asset_not_found"})
            return

        if path == "/admin/notification-sw.js":
            body = (ADMIN_UI_DIST / "notification-sw.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Service-Worker-Allowed", "/admin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        admin_tabs = {"overview", "control-center", "phone", "data-explorer", "ai-manager", "api-clients", "orders", "catalog", "api-products", "inventory", "customers", "deposits", "withdrawals", "finance", "warranties", "support", "interactions", "activity", "settings", "binance-wallet"}
        react_admin_route = (
            path in {"/admin", "/admin-v2", "/admin/login"}
            or path.startswith("/admin-v2/")
            or path.startswith("/admin/")
            and path.removeprefix("/admin/").split("/", 1)[0] in admin_tabs
        )
        if react_admin_route:
            relative_path = path.removeprefix("/admin-v2/") if path.startswith("/admin-v2/") else ""
            requested_file = ADMIN_UI_DIST / relative_path
            if not relative_path or not requested_file.is_file():
                requested_file = ADMIN_UI_DIST / "index.html"
            try:
                resolved_file = requested_file.resolve()
                resolved_file.relative_to(ADMIN_UI_DIST.resolve())
            except (OSError, ValueError):
                self._reply(404, {"ok": False, "error": "asset_not_found"})
                return
            if not resolved_file.is_file():
                self._reply(503, {
                    "ok": False,
                    "error": "admin_ui_not_built",
                    "message": "Run `npm install && npm run build` in admin-ui.",
                })
                return
            body = resolved_file.read_bytes()
            content_type = mimetypes.guess_type(resolved_file.name)[0] or "application/octet-stream"
            if resolved_file.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            elif resolved_file.suffix in {".js", ".css"}:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Cache-Control",
                "no-store, max-age=0" if resolved_file.suffix == ".html"
                else "no-cache" if resolved_file.suffix == ".webmanifest"
                else "public, max-age=31536000, immutable",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/cron/codex-deadlines":
            expected = env_value("CRON_SECRET")
            supplied = self.headers.get("Authorization", "")
            if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                expired = _run_async(
                    monitor_codex_number_deadlines(_application().bot)
                )
                self._reply(200, {
                    "ok": True,
                    "expired": len(expired),
                    "order_ids": [int(order["id"]) for order in expired],
                })
            except Exception as exc:
                log.exception("Codex acceptance deadline monitor failed")
                self._reply(500, {"ok": False, "error": str(exc)})
            return


        if path == "/admin-legacy" or path.startswith("/admin-legacy/") and path.removeprefix("/admin-legacy/") in admin_tabs:
            if not self._dashboard_authorized():
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="TelegramBot Admin"')
                self.end_headers()
                return

            # Servir le dashboard HTML
            try:
                active_tab = path.removeprefix("/admin-legacy/") if path.startswith("/admin-legacy/") else "overview"
                data = db.dashboard_data()
                data["shop_name"] = os.environ.get("HP_SHOP_NAME", "BlackMarket").strip()
                data["currency"] = CURRENCY
                data["bot_username"] = os.environ.get(
                    "HP_BOT_USERNAME", "blackmarketa_bot"
                ).strip().lstrip("@")
                data["reseller"] = reseller_dashboard_summary()
                body = render_dashboard(
                    data,
                    active_tab=active_tab,
                    dashboard_write_token=dashboard_write_token(),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                traceback.print_exc()
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        elif path == "/admin/api/data":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                data = db.dashboard_data()
                data["shop_name"] = os.environ.get("HP_SHOP_NAME", "BlackMarket").strip()
                data["currency"] = CURRENCY
                data["bot_username"] = os.environ.get(
                    "HP_BOT_USERNAME", "blackmarketa_bot"
                ).strip().lstrip("@")
                data["dashboard_write_token"] = dashboard_write_token()
                data["reseller"] = reseller_dashboard_summary()
                self._reply(200, data)
            except Exception as exc:
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        elif path == "/admin/api/binance-health":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, binance_healthcheck())
            return

        elif path == "/admin/api/binance-wallet":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                raw_days = parse_qs(url.query).get("days", ["90"])[0]
                payload = binance_dashboard_service.snapshot(days=int(raw_days))
                self._reply(200, payload, headers={"Cache-Control": "no-store"})
            except (TypeError, ValueError):
                self._reply(400, {"ok": False, "error": "Période invalide."})
            except binance_dashboard_service.BinanceDashboardError as exc:
                self._reply(503, {"ok": False, "error": str(exc)}, headers={"Cache-Control": "no-store"})
            except Exception:
                log.exception("Binance admin wallet request failed")
                self._reply(503, {"ok": False, "error": "Portefeuille Binance temporairement indisponible."}, headers={"Cache-Control": "no-store"})
            return

        elif path == "/admin/api/bybit-health":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, bybit_healthcheck())
            return

        elif path == "/admin/api/telegram-health":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            result = telegram_webhook_health()
            self._reply(200 if result.get("ok") else 503, result)
            return

        elif path == "/admin/api/reseller-providers":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, {
                "ok": True,
                "providers": reseller_service.provider_summaries(),
            })
            return

        elif path == "/admin/api/reseller-products":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                provider = parse_qs(url.query).get(
                    "provider", [reseller_service.PROVIDER]
                )[0]
                self._reply(200, reseller_service.catalog(provider))
            except reseller_service.ResellerApiError as exc:
                summary = next(
                    (
                        item for item in reseller_service.provider_summaries()
                        if item["id"] == provider
                    ),
                    {"id": provider, "configured": False},
                )
                self._reply(503, {
                    "ok": False,
                    "configured": bool(summary["configured"]),
                    "provider": summary["id"],
                    "error": str(exc),
                })
            return

        elif path == "/admin/api/reseller-comparison":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                refresh = parse_qs(url.query).get("refresh", ["0"])[0] == "1"
                self._reply(
                    200,
                    reseller_comparison_service.compare_catalogs(force=refresh),
                )
            except Exception as exc:
                log.exception("Supplier comparison failed")
                self._reply(503, {
                    "ok": False,
                    "error": str(exc)[:300] or "Comparaison indisponible",
                })
            return

        elif path == "/admin/api/ai-manager/config":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, admin_ai_service.public_config())
            return

        elif path == "/admin/api/buyer-keys":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, {"ok": True, "keys": buyer_api_service.list_keys()})
            return

        elif path == "/admin/api/external-connectors":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, {"ok": True, "connectors": external_api_service.list_connectors()})
            return

        elif path == "/admin/api/wallet-topups":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.list_wallet_topups(parse_qs(url.query)))
            return

        elif path == "/admin/api/finance":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.finance_summary(parse_qs(url.query)))
            return

        elif path == "/admin/api/notifications/config":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, notification_service.push_config(), headers={"Cache-Control": "no-store"})
            return

        elif path == "/admin/api/notifications":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            query = parse_qs(url.query)
            try:
                limit = int(query.get("limit", [100])[0])
            except (TypeError, ValueError):
                limit = 100
            payload = dashboard_api.list_admin_notifications(limit=limit)
            dismissed = set(notification_service.dismissed_ids())
            payload["items"] = [item for item in payload.get("items", []) if item.get("id") not in dismissed]
            payload["total"] = len(payload["items"])
            payload["read_ids"] = notification_service.read_ids()
            payload["poll_after_seconds"] = 5
            self._reply(200, payload, headers={"Cache-Control": "no-store"})
            return

        elif path == "/admin/api/withdrawals":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.list_withdrawals(parse_qs(url.query)))
            return

        elif path == "/admin/api/warranties":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.list_warranties(parse_qs(url.query)))
            return

        elif path == "/admin/api/telegram-media":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                file_id = parse_qs(url.query).get("file_id", [""])[0].strip()
                if not file_id or len(file_id) > 512:
                    raise ValueError("Fichier Telegram invalide.")
                telegram_file = _run_async(_application().bot.get_file(file_id))
                body = bytes(_run_async(telegram_file.download_as_bytearray()))
                file_path = str(getattr(telegram_file, "file_path", "") or "")
                content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                self._reply_bytes(200, body, content_type, headers={
                    "Cache-Control": "private, max-age=3600",
                    "X-Content-Type-Options": "nosniff",
                })
            except ValueError as exc:
                self._reply(400, {"ok": False, "error": str(exc)})
            except Exception:
                log.exception("Unable to proxy Telegram support media")
                self._reply(502, {"ok": False, "error": "Média Telegram indisponible."})
            return

        elif path == "/admin/api/telegram-custom-emoji":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                emoji_id = parse_qs(url.query).get("id", [""])[0].strip()
                if not emoji_id or len(emoji_id) > 128:
                    raise ValueError("Emoji Telegram invalide.")
                stickers = _run_async(_application().bot.get_custom_emoji_stickers([emoji_id]))
                if not stickers:
                    raise ValueError("Emoji Telegram introuvable.")
                sticker = stickers[0]
                source = getattr(sticker, "thumbnail", None) or sticker
                telegram_file = _run_async(_application().bot.get_file(source.file_id))
                body = bytes(_run_async(telegram_file.download_as_bytearray()))
                file_path = str(getattr(telegram_file, "file_path", "") or "")
                content_type = mimetypes.guess_type(file_path)[0] or "image/webp"
                self._reply_bytes(200, body, content_type, headers={
                    "Cache-Control": "private, max-age=86400",
                    "X-Content-Type-Options": "nosniff",
                })
            except ValueError as exc:
                self._reply(404, {"ok": False, "error": str(exc)})
            except Exception:
                log.exception("Unable to render Telegram custom emoji")
                self._reply(502, {"ok": False, "error": "Emoji Telegram indisponible."})
            return

        elif path == "/admin/api/ticket-messages":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                query = parse_qs(url.query)
                ticket_id = int(query.get("ticket_id", [0])[0])
                messages = support_service.get_messages(ticket_id)
                self._reply(200, messages)
            except Exception as exc:
                self._reply(500, {"ok": False, "error": str(exc)})
            return

        elif path == "/admin/api/orders":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            params = parse_qs(url.query)
            order_id = params.get("order_id", [""])[0]
            if order_id.isdigit() and params.get("detail", [""])[0] == "1":
                order = dashboard_api.order_detail(int(order_id))
                self._reply(200 if order else 404, order or {"ok": False, "error": "Not found"})
            else:
                self._reply(200, dashboard_api.list_orders(params))
            return

        elif path == "/admin/api/tickets":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.list_tickets(parse_qs(url.query)))
            return

        elif path == "/admin/api/inventory":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            params = parse_qs(url.query)
            if params:
                self._reply(200, dashboard_api.list_inventory(params))
            else:
                self._reply(200, {"items": dashboard_api.inventory_summary()})
            return

        elif path == "/admin/api/customers":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            params = parse_qs(url.query)
            user_id = params.get("user_id", [""])[0]
            if user_id.isdigit():
                customer = dashboard_api.customer_detail(int(user_id))
                self._reply(200 if customer else 404, customer or {"ok": False, "error": "Not found"})
            else:
                self._reply(200, dashboard_api.list_customers(params))
            return

        elif path == "/admin/api/reseller-clients":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            self._reply(200, dashboard_api.list_reseller_clients(parse_qs(url.query)))
            return

        elif path == "/admin/api/inventory-export":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            params = parse_qs(url.query)
            result = dashboard_api.list_inventory({**params, "page": ["1"], "per_page": ["100"]})
            items = list(result["items"])
            for page in range(2, result["pages"] + 1):
                page_result = dashboard_api.list_inventory({**params, "page": [str(page)], "per_page": ["100"]})
                items.extend(page_result["items"])
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(("reference_id", "offer_id", "masked_preview", "status", "order_id", "created_at"))
            for item in items:
                writer.writerow((
                    item.get("reference_id"),
                    item.get("offer_id"),
                    item.get("masked_preview"),
                    item.get("status"),
                    item.get("reserved_order_id") or item.get("delivered_order_id") or "",
                    item.get("created_at", ""),
                ))
            self._reply_bytes(
                200,
                output.getvalue().encode("utf-8-sig"),
                "text/csv; charset=utf-8",
                "inventory-masked.csv",
            )
            return

        # Health check par défaut
        self._reply(200, health_payload())

    def _dashboard_authorized(self) -> bool:
        if not DASHBOARD_PASSWORD:
            return False
        write_token = self.headers.get("X-Dashboard-Write-Token", "")
        if write_token and hmac.compare_digest(write_token, dashboard_write_token()):
            return True
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            session = cookies.get(ADMIN_SESSION_COOKIE)
            if session:
                expires_raw, _ = session.value.split(".", 1)
                expires_at = int(expires_raw)
                if expires_at >= int(time.time()) and hmac.compare_digest(
                    session.value, admin_session_token(expires_at)
                ):
                    return True
        except (KeyError, TypeError, ValueError):
            pass
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            _, password = base64.b64decode(header[6:]).decode().split(":", 1)
            return hmac.compare_digest(password, DASHBOARD_PASSWORD)
        except Exception:
            return False

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        return forwarded or str(self.client_address[0])

    def _reply_buyer_error(self, exc: buyer_api_service.BuyerApiError) -> None:
        headers = (
            {"Retry-After": str(exc.retry_after)}
            if exc.retry_after is not None
            else None
        )
        self._reply(exc.status, exc.payload(), headers=headers)

    def _read_json_body(self, *, max_bytes: int = 64_000) -> dict:
        content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            raise buyer_api_service.BuyerApiError(
                415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json."
            )
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise buyer_api_service.BuyerApiError(400, "INVALID_BODY", "Invalid request body.") from exc
        if length <= 0 or length > max_bytes:
            raise buyer_api_service.BuyerApiError(413, "INVALID_BODY_SIZE", "Invalid request body size.")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise buyer_api_service.BuyerApiError(400, "INVALID_JSON", "Invalid JSON body.") from exc
        if not isinstance(payload, dict):
            raise buyer_api_service.BuyerApiError(400, "INVALID_BODY", "JSON body must be an object.")
        return payload

    def do_OPTIONS(self):
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/api/lovable/license/validate":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()
            return
        self._reply(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/admin/api/login":
            try:
                payload = self._read_json_body(max_bytes=4_000)
                username = str(payload.get("username") or "").strip().lower()
                password = str(payload.get("password") or "")
                valid = (
                    bool(DASHBOARD_PASSWORD)
                    and username == "admin"
                    and hmac.compare_digest(password, DASHBOARD_PASSWORD)
                )
                if not valid:
                    self._reply(401, {
                        "ok": False,
                        "error": "Identifiant ou mot de passe incorrect.",
                    })
                    return
                expires_at = int(time.time()) + ADMIN_SESSION_TTL_SECONDS
                cookie = (
                    f"{ADMIN_SESSION_COOKIE}={admin_session_token(expires_at)}; "
                    f"Path=/; Max-Age={ADMIN_SESSION_TTL_SECONDS}; HttpOnly; SameSite=Strict"
                )
                if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
                    cookie += "; Secure"
                self._reply(200, {"ok": True}, headers={
                    "Set-Cookie": cookie,
                    "Cache-Control": "no-store",
                })
            except buyer_api_service.BuyerApiError as exc:
                self._reply(exc.status, {"ok": False, "error": exc.message})
            return
        if path == "/admin/api/notifications":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            token = self.headers.get("X-Dashboard-Write-Token", "")
            if not token or not hmac.compare_digest(token, dashboard_write_token()):
                self._reply(403, {"ok": False, "error": "Session expirée. Rechargez le tableau de bord."})
                return
            try:
                payload = self._read_json_body(max_bytes=64_000)
                self._reply(200, notification_service.device_action(payload), headers={"Cache-Control": "no-store"})
            except buyer_api_service.BuyerApiError as exc:
                self._reply(exc.status, {"ok": False, "error": exc.message})
            except ValueError as exc:
                self._reply(400, {"ok": False, "error": str(exc)})
            except Exception:
                log.warning("Admin notification request failed")
                self._reply(503, {"ok": False, "error": "Notifications temporairement indisponibles. Réessayez."})
            return
        if path == "/admin/api/logout":
            self._reply(200, {"ok": True}, headers={
                "Set-Cookie": f"{ADMIN_SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict",
                "Cache-Control": "no-store",
            })
            return
        if path == "/api/lovable/license/validate":
            try:
                payload = self._read_json_body(max_bytes=4_000)
                result = lovable_service.validate_license(payload.get("license", ""))
                self._reply(200, result, headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-store",
                })
            except buyer_api_service.BuyerApiError as exc:
                self._reply(exc.status, {"ok": False, "valid": False, "error": exc.message}, headers={
                    "Access-Control-Allow-Origin": "*",
                })
            return
        if path == "/admin/api/ai-manager/chat":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                payload = self._read_json_body(max_bytes=80_000)
                result = admin_ai_service.chat(
                    payload.get("messages"),
                    payload.get("model"),
                    db.dashboard_data(),
                )
                self._reply(200, result)
            except admin_ai_service.AdminAIError as exc:
                self._reply(503, {"ok": False, "error": str(exc)})
            except buyer_api_service.BuyerApiError as exc:
                self._reply(exc.status, {"ok": False, "error": exc.message})
            except Exception:
                log.exception("AI Bot Manager request failed")
                self._reply(500, {"ok": False, "error": "AI Bot Manager est indisponible."})
            return

        if path == "/api/v2/telegram-buyer/purchase":
            try:
                payload = self._read_json_body()
                if "key" in payload:
                    raise buyer_api_service.BuyerApiError(
                        400,
                        "API_KEY_LOCATION_NOT_ALLOWED",
                        "Send the API key only as Authorization: Bearer <API_KEY>.",
                    )
                key = buyer_api_service.authenticate_bearer(
                    self.headers.get("Authorization", ""), self._client_ip(), "purchase"
                )
                try:
                    quantity = int(payload.get("quantity", 1))
                except (TypeError, ValueError) as exc:
                    raise buyer_api_service.BuyerApiError(
                        400, "INVALID_QUANTITY", "quantity must be an integer."
                    ) from exc
                status, result, replayed = buyer_api_service.purchase(
                    key,
                    product_id=payload.get("product_id", ""),
                    quantity=quantity,
                    idempotency_key=self.headers.get("Idempotency-Key", ""),
                )
                self._reply(status, result, headers={"Idempotent-Replayed": str(replayed).lower()})
            except buyer_api_service.BuyerApiError as exc:
                self._reply_buyer_error(exc)
            except Exception:
                log.exception("Buyer API purchase failed")
                self._reply(500, {
                    "success": False,
                    "code": "INTERNAL_ERROR",
                    "message": "The buyer API is temporarily unavailable.",
                })
            return

        if path == "/admin/api/buyer-keys":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            try:
                payload = self._read_json_body()
                action = str(payload.get("action") or "create").lower()
                if action == "create":
                    issued = buyer_api_service.create_key(
                        int(payload.get("user_id")), label=str(payload.get("label") or "Buyer API")
                    )
                    self._reply(201, {"ok": True, "key": issued})
                elif action == "revoke":
                    revoked = buyer_api_service.revoke_key(int(payload.get("key_id")))
                    self._reply(200 if revoked else 404, {"ok": revoked})
                else:
                    self._reply(400, {"ok": False, "error": "invalid_action"})
            except (TypeError, ValueError) as exc:
                self._reply(400, {"ok": False, "error": str(exc)})
            except buyer_api_service.BuyerApiError as exc:
                self._reply_buyer_error(exc)
            return
        if path == "/admin/api/ticket-media":
            if not self._dashboard_authorized():
                self._reply(401, {"ok": False, "error": "Unauthorized"})
                return
            token = self.headers.get("X-Dashboard-Write-Token", "")
            if not token or not hmac.compare_digest(token, dashboard_write_token()):
                self._reply(403, {"ok": False, "error": "Session expirée. Rechargez le tableau de bord."})
                return
            try:
                fields, upload = self._read_multipart(52_000_000)
                ticket_id = int(fields.get("ticket_id", "0"))
                ticket = support_service.get_ticket(ticket_id)
                if not ticket or ticket.get("status") in {"closed", "resolved"}:
                    raise ValueError("Cette conversation n’est plus disponible.")
                content_type = str(upload["content_type"] or "").lower()
                guessed = mimetypes.guess_type(upload["filename"])[0] or ""
                media_kind = "image" if content_type.startswith("image/") else "video" if content_type.startswith("video/") else ""
                if not media_kind and guessed:
                    media_kind = "image" if guessed.startswith("image/") else "video" if guessed.startswith("video/") else ""
                    content_type = guessed
                if media_kind not in {"image", "video"}:
                    raise ValueError("Seules les images et les vidéos sont acceptées.")
                max_size = 10_000_000 if media_kind == "image" else 50_000_000
                if len(upload["body"]) > max_size:
                    limit = "10 Mo" if media_kind == "image" else "50 Mo"
                    raise ValueError(f"Ce fichier dépasse la limite de {limit}.")
                signature = upload["body"][:16]
                is_image = (
                    signature.startswith(b"\xff\xd8\xff")
                    or signature.startswith(b"\x89PNG\r\n\x1a\n")
                    or signature.startswith((b"GIF87a", b"GIF89a"))
                    or signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
                )
                is_video = (
                    signature[4:8] == b"ftyp"
                    or signature.startswith(b"\x1aE\xdf\xa3")
                    or signature.startswith(b"RIFF") and signature[8:12] == b"AVI "
                )
                if (media_kind == "image" and not is_image) or (media_kind == "video" and not is_video):
                    raise ValueError("Le contenu du fichier ne correspond pas à une image ou vidéo prise en charge.")
                caption = str(fields.get("message") or "").strip()[:850]
                telegram_caption = (
                    f"🎫 <b>Réponse du Support (Ticket #{ticket_id})</b>"
                    + (f"\n\n{html.escape(caption)}" if caption else "")
                )
                bot = _application().bot

                def input_file():
                    return InputFile(io.BytesIO(upload["body"]), filename=upload["filename"])

                with _runtime_lock:
                    try:
                        if media_kind == "image":
                            sent = _run_async(bot.send_photo(
                                ticket["user_id"], photo=input_file(), caption=telegram_caption,
                                parse_mode=ParseMode.HTML,
                            ))
                        else:
                            sent = _run_async(bot.send_video(
                                ticket["user_id"], video=input_file(), caption=telegram_caption,
                                parse_mode=ParseMode.HTML, supports_streaming=True,
                            ))
                    except BadRequest:
                        sent = _run_async(bot.send_document(
                            ticket["user_id"], document=input_file(), caption=telegram_caption,
                            parse_mode=ParseMode.HTML,
                        ))
                media = support_bridge.message_media(sent) or {
                    "type": media_kind,
                    "file_id": "",
                    "file_name": upload["filename"],
                    "mime_type": content_type,
                }
                if not media.get("file_id"):
                    raise ValueError("Telegram n’a pas retourné la pièce jointe envoyée.")
                message = support_service.add_message(
                    ticket_id,
                    ADMIN_ID,
                    caption or f"[{media_kind.title()}]",
                    sender_type="admin",
                    media=media,
                )
                self._reply(201, {
                    "ok": True,
                    "message": "Pièce jointe envoyée au client.",
                    "ticket_message": message,
                })
            except ValueError as exc:
                self._reply(400, {"ok": False, "error": str(exc)})
            except Exception:
                log.exception("Unable to send support media")
                self._reply(502, {"ok": False, "error": "Telegram n’a pas pu envoyer cette pièce jointe."})
            return
        if path == "/admin":
            self._dashboard_action()
            return

        # Webhook Telegram
        secret = env_value("HP_WEBHOOK_SECRET")
        supplied = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secret:
            log.error("HP_WEBHOOK_SECRET is not configured; refusing webhook request")
            self._reply(503, {"ok": False, "error": "webhook_not_configured"})
            return
        if not hmac.compare_digest(supplied, secret):
            self._reply(403, {"ok": False, "error": "invalid webhook secret"})
            return

        try:
            content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
            if content_type != "application/json":
                self._reply(415, {"ok": False, "error": "content_type_must_be_json"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_WEBHOOK_BODY_BYTES:
                self._reply(413, {"ok": False, "error": "invalid_body_size"})
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                self._reply(400, {"ok": False, "error": "invalid_update"})
                return
            update_id = payload.get("update_id")
            if update_id is None or not db.claim_update(update_id):
                self._reply(200, {"ok": True, "duplicate": True})
                return
            with _runtime_lock:
                app = _application()
                update = Update.de_json(payload, app.bot)
                _run_async(app.process_update(update))
            self._reply(200, {"ok": True})
        except Exception as exc:
            if "update_id" in locals() and update_id is not None:
                db.release_update(update_id)
            traceback.print_exc()
            log.exception(
                "webhook_processing_failed update_id=%s",
                update_id if "update_id" in locals() else None,
            )
            self.log_error("Webhook processing failed: %s", exc)
            self._reply(500, {"ok": False})

    def _dashboard_action(self):
        if not self._dashboard_authorized():
            self._reply(401, {"ok": False, "error": "Unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 2_000_000:
                raise ValueError("Request too large")
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode(), keep_blank_values=True).items()}
            action = form.get("action")

            if action == "add_service":
                name = form["name"].strip()[:80]
                emoji = form.get("emoji", "📦")[:12]
                sid = db.add_service(
                    name,
                    emoji,
                    suffix_emoji=form.get("suffix_emoji", "").strip()[:12],
                    sales_channels=["bot"],
                    name_ar=form.get("name_ar", "").strip(),
                )
                db.audit_event("service.created", details={"service_id": sid, "name": name})
                self._reply(200, {"ok": True, "service_id": sid, "message": f"Catégorie « {name} » créée."})
                return

            elif action == "update_service":
                sid = int(form["service_id"])
                name = form["name"].strip()[:80]
                emoji = form.get("emoji", "")[:12]
                db.update_service(
                    sid,
                    name=name,
                    emoji=emoji,
                    suffix_emoji=form.get("suffix_emoji", "").strip()[:12],
                    sales_channels=["bot"],
                    name_ar=form.get("name_ar", "").strip(),
                )
                db.audit_event("service.updated", details={"service_id": sid, "name": name})

            elif action == "toggle_service":
                sid = int(form["service_id"])
                service = db.get_service(sid)
                next_active = 0 if service["active"] else 1
                db.update_service(sid, active=next_active)
                db.audit_event("service.toggled", details={
                    "service_id": sid,
                    "active": bool(next_active),
                    "reversible": True,
                    "before": {"active": int(service["active"])},
                    "after": {"active": next_active},
                })

            elif action == "archive_service":
                sid = int(form["service_id"])
                service = db.get_service(sid)
                if not service:
                    raise ValueError("Service introuvable")
                db.archive_service(sid)
                db.audit_event("service.archived", details={"service_id": sid, "name": service.get("name", "")})

            elif action == "add_offer":
                service_id_raw = form.get("service_id", "").strip()
                if service_id_raw:
                    sid = int(service_id_raw)
                else:
                    default_service = db.get_conn().services.find_one({"name": "Catalogue"})
                    if default_service:
                        sid = int(default_service["id"])
                    else:
                        sid = db.add_service("Catalogue", "🛒")
                        db.audit_event("service.created", details={"service_id": sid, "name": "Catalogue"})
                name = form["name"].strip()[:120]
                price = float(form["price"])
                note = form.get("note", "")[:250]
                description = form.get("description", "").strip()[:1000]
                auto_delivery = form.get("auto_delivery", "") == "on"
                if service_id_raw:
                    sid = int(service_id_raw)
                else:
                    default_service = db.get_conn().services.find_one({"name": "Catalogue"})
                    if default_service:
                        sid = int(default_service["id"])
                    else:
                        sid = db.add_service("Catalogue", "🛒")
                        db.audit_event("service.created", details={"service_id": sid, "name": "Catalogue"})
                name = form["name"].strip()[:120]
                price = float(form["price"])
                note = form.get("note", "")[:250]
                description = form.get("description", "").strip()[:1000]
                auto_delivery = form.get("auto_delivery", "") == "on"
                low_stock_threshold = max(0, int(form.get("low_stock_threshold", 5)))
                bulk_quantity = max(0, int(form.get("bulk_quantity", "0") or 0))
                bulk_price_raw = form.get("bulk_unit_price", "").strip()
                bulk_unit_price = float(bulk_price_raw) if bulk_price_raw else None
                if bulk_unit_price is not None and bulk_unit_price < 0:
                    raise ValueError("Le prix en gros ne peut pas être négatif")
                if bulk_quantity and (bulk_unit_price is None or bulk_unit_price >= price):
                    raise ValueError("Le prix en gros doit être inférieur au prix normal")
                delivery_delay = form.get("delivery_delay", "").strip()[:120]
                emoji_val = form.get("custom_emoji_id", form.get("emoji", "")).strip()
                period_value, period_unit, period_days = _duration_form_values(
                    form, "period", 30, allow_zero=False,
                )
                warranty_value, warranty_unit, warranty_days = _duration_form_values(
                    form, "warranty", 0, allow_zero=True,
                )
                note = form.get("note", "").strip()[:250]
                if not note or note.isdigit() or note == "0":
                    note = "NW" if warranty_days == 0 else warranty_service.format_duration(warranty_value, warranty_unit)
                oid = db.add_offer(
                    sid,
                    name,
                    price,
                    0,
                    note,
                    description=description,
                    auto_delivery=auto_delivery,
                    low_stock_threshold=low_stock_threshold,
                    delivery_delay=delivery_delay,
                    custom_emoji_id=emoji_val,
                    sales_channels=["bot"],
                    name_ar=form.get("name_ar", "").strip(),
                    description_ar=form.get("description_ar", "").strip(),
                    period_days=period_days,
                    warranty_days=warranty_days,
                    period_value=period_value,
                    period_unit=period_unit,
                    warranty_value=warranty_value,
                    warranty_unit=warranty_unit,
                    bulk_quantity=bulk_quantity,
                    bulk_unit_price=bulk_unit_price,
                )
                if emoji_val and sid:
                    db.update_service(sid, emoji=emoji_val)
                initial_inventory_text = form.get("initial_inventory", "").strip()
                if initial_inventory_text:
                    inventory_service.add_items(
                        oid, inventory_service.parse_bulk_inventory(initial_inventory_text),
                    )
                db.audit_event("offer.created", details={"offer_id": oid, "name": name})

            elif action == "update_offer":
                oid = int(form["offer_id"])
                previous_offer = db.get_offer(oid)
                if not previous_offer:
                    raise ValueError("Produit introuvable")
                target_service_id = int(form.get("service_id") or previous_offer["service_id"])
                name = form["name"].strip()[:120]
                price = None if form.get("price", "") == "" else float(form["price"])
                bulk_quantity = max(0, int(form.get("bulk_quantity", "0") or 0))
                bulk_price_raw = form.get("bulk_unit_price", "").strip()
                bulk_unit_price = float(bulk_price_raw) if bulk_price_raw else None
                effective_price = price if price is not None else float(previous_offer.get("price") or 0)
                if bulk_unit_price is not None and bulk_unit_price < 0:
                    raise ValueError("Le prix en gros ne peut pas être négatif")
                if bulk_quantity and (bulk_unit_price is None or bulk_unit_price >= effective_price):
                    raise ValueError("Le prix en gros doit être inférieur au prix normal")
                period_value, period_unit, period_days = _duration_form_values(
                    form, "period", int(previous_offer.get("period_days") or 30), allow_zero=False,
                )
                warranty_value, warranty_unit, warranty_days = _duration_form_values(
                    form, "warranty", int(previous_offer.get("warranty_days") or 0), allow_zero=True,
                )
                note = form.get("note", "").strip()[:250]
                if not note or note.isdigit() or note == "0":
                    note = "NW" if warranty_days == 0 else warranty_service.format_duration(warranty_value, warranty_unit)
                emoji_val = form.get("custom_emoji_id", form.get("emoji", "")).strip()
                db.update_offer(
                    oid,
                    service_id=target_service_id,
                    price=price,
                    name=name,
                    note=note if note else None,
                    description=form.get("description", "").strip()[:1000],
                    sort_order=max(0, int(form.get("sort_order", 0))),
                    auto_delivery=form.get("auto_delivery", "") == "on",
                    low_stock_threshold=max(0, int(form.get("low_stock_threshold", 5))),
                    delivery_delay=form.get("delivery_delay", "").strip()[:120],
                    custom_emoji_id=emoji_val,
                    sales_channels=["bot"],
                    name_ar=form.get("name_ar", "").strip(),
                    description_ar=form.get("description_ar", "").strip(),
                    period_days=period_days,
                    warranty_days=warranty_days,
                    period_value=period_value,
                    period_unit=period_unit,
                    warranty_value=warranty_value,
                    warranty_unit=warranty_unit,
                    bulk_quantity=bulk_quantity,
                    bulk_unit_price=bulk_unit_price if bulk_unit_price is not None else 0,
                )
                existing_offer = db.get_offer(oid)
                if emoji_val and existing_offer and existing_offer.get("service_id"):
                    db.update_service(int(existing_offer["service_id"]), emoji=emoji_val)
                db.audit_event("offer.updated", details={
                    "offer_id": oid,
                    "name": name,
                    "previous_service_id": previous_offer.get("service_id"),
                    "service_id": target_service_id,
                })

            elif action == "toggle_offer":
                oid = int(form["offer_id"])
                offer = db.get_offer(oid)
                next_active = 0 if offer["active"] else 1
                db.update_offer(oid, active=next_active)
                db.audit_event("offer.toggled", details={
                    "offer_id": oid,
                    "active": bool(next_active),
                    "reversible": True,
                    "before": {"active": int(offer["active"])},
                    "after": {"active": next_active},
                })

            elif action == "bulk_toggle_offers":
                offer_ids = list(dict.fromkeys(
                    int(value) for value in form.get("offer_ids", "").split(",")
                    if value.strip().isdigit()
                ))
                if not offer_ids or len(offer_ids) > 100:
                    raise ValueError("Sélection de produits invalide")
                active = 1 if form.get("active") == "1" else 0
                before_rows = list(db.get_conn().offers.find(
                    {"id": {"$in": offer_ids}, "archived": {"$ne": 1}},
                    {"id": 1, "active": 1},
                ))
                result = db.get_conn().offers.update_many(
                    {"id": {"$in": offer_ids}, "archived": {"$ne": 1}},
                    {"$set": {"active": active}},
                )
                db.audit_event(
                    "offer.bulk_toggled",
                    details={
                        "offer_ids": offer_ids,
                        "active": bool(active),
                        "modified": result.modified_count,
                        "reversible": True,
                        "changes": [{
                            "id": row["id"],
                            "before": {"active": int(row.get("active", 1))},
                            "after": {"active": active},
                        } for row in before_rows],
                    },
                )
                self._reply(200, {
                    "ok": True,
                    "modified": result.modified_count,
                    "message": f"{result.modified_count} produit(s) mis à jour.",
                })
                return

            elif action == "bulk_update_offers":
                offer_ids = list(dict.fromkeys(
                    int(value) for value in form.get("offer_ids", "").split(",")
                    if value.strip().isdigit()
                ))
                if not offer_ids or len(offer_ids) > 100:
                    raise ValueError("Sélection de produits invalide")
                operation = form.get("operation", "")
                rows = list(db.get_conn().offers.find({
                    "id": {"$in": offer_ids}, "archived": {"$ne": 1},
                }))
                changes = []
                if operation == "price_percent":
                    percent = float(form.get("value", "0").replace(",", "."))
                    if percent < -90 or percent > 500 or percent == 0:
                        raise ValueError("Pourcentage invalide (-90 à 500, hors zéro)")
                    factor = 1 + percent / 100
                    for row in rows:
                        before = {
                            "price": row.get("price"),
                            "tn_price_millimes": row.get("tn_price_millimes"),
                        }
                        after = {
                            "price": round(float(row.get("price") or 0) * factor, 4),
                            "tn_price_millimes": (
                                max(0, round(int(row["tn_price_millimes"]) * factor))
                                if row.get("tn_price_millimes") is not None else None
                            ),
                        }
                        update = {"price": after["price"]}
                        if after["tn_price_millimes"] is not None:
                            update["tn_price_millimes"] = after["tn_price_millimes"]
                        db.get_conn().offers.update_one({"id": row["id"]}, {"$set": update})
                        changes.append({"id": row["id"], "before": before, "after": after})
                elif operation == "move_service":
                    service_id = int(form.get("value", "0"))
                    service = db.get_conn().services.find_one({"id": service_id, "archived": {"$ne": 1}})
                    if not service:
                        raise ValueError("Service de destination introuvable")
                    for row in rows:
                        before = {"service_id": row.get("service_id")}
                        after = {"service_id": service_id}
                        db.move_offer(row["id"], service_id)
                        changes.append({"id": row["id"], "before": before, "after": after})
                elif operation == "archive":
                    archived_at = int(time.time())
                    for row in rows:
                        before = {
                            "active": row.get("active", 1),
                            "archived": row.get("archived"),
                            "archived_at": row.get("archived_at"),
                        }
                        after = {"active": 0, "archived": 1, "archived_at": archived_at}
                        db.get_conn().offers.update_one({"id": row["id"]}, {"$set": after})
                        changes.append({"id": row["id"], "before": before, "after": after})
                else:
                    raise ValueError("Action groupée inconnue")
                db.audit_event("offer.bulk_updated", details={
                    "operation": operation,
                    "offer_ids": offer_ids,
                    "modified": len(changes),
                    "reversible": True,
                    "changes": changes,
                })
                self._reply(200, {
                    "ok": True,
                    "modified": len(changes),
                    "message": f"{len(changes)} produit(s) mis à jour.",
                })
                return

            elif action == "archive_offer":
                oid = int(form["offer_id"])
                offer = db.get_offer(oid)
                if not offer or not db.archive_offer(oid):
                    raise ValueError("Produit introuvable")
                db.audit_event("offer.archived", details={"offer_id": oid, "name": offer.get("name", "")})

            elif action == "duplicate_offer":
                oid = int(form["offer_id"])
                new_id = db.duplicate_offer(oid)
                if new_id is None:
                    raise ValueError("Offre introuvable")
                db.audit_event("offer.duplicated", details={"offer_id": oid, "new_offer_id": new_id})

            elif action == "add_inventory":
                oid = int(form["offer_id"])
                items = inventory_service.parse_bulk_inventory(form.get("items", ""))
                count = inventory_service.add_items(oid, items)
                db.audit_event("inventory.added", details={"offer_id": oid, "count": count})

            elif action == "toggle_inventory":
                item_id = int(form["inventory_id"])
                disabled = form.get("disabled", "1") == "1"
                if not inventory_service.set_disabled(item_id, disabled):
                    raise ValueError("L'article ne peut pas changer d'état")

            elif action == "reveal_inventory":
                item_id = int(form["inventory_id"])
                value = inventory_service.reveal_item(item_id)
                if value is None:
                    raise ValueError("Article introuvable")
                self._reply(200, {"ok": True, "value": value})
                return

            elif action == "toggle_ban":
                uid = int(form["user_id"])
                banned = bool(int(form["banned"]))
                db.set_user_banned(uid, banned)

            elif action == "bulk_credit_wallets":
                if form.get("confirmation", "").strip() != "CREDIT ALL":
                    raise ValueError("Saisissez CREDIT ALL pour confirmer.")
                amount = float(form.get("amount", "0").strip().replace(",", "."))
                result = wallet_service.credit_all_users(
                    amount, form.get("operation_id", ""), ADMIN_ID,
                )
                self._reply(200, {"ok": True, **result})
                return

            elif action == "adjust_user_wallet":
                uid = int(form["user_id"])
                amount = float(form.get("amount", "0").strip().replace(",", "."))
                reason = form.get("reason", "")
                result = wallet_service.adjust_balance(
                    uid, amount, ADMIN_ID, reason,
                )
                notification_sent = _notify_wallet_adjustment(result, reason)
                if amount > 0:
                    message = (
                        "Solde crédité et notification Telegram envoyée au client."
                        if notification_sent
                        else "Solde crédité, mais la notification Telegram n’a pas pu être envoyée."
                    )
                else:
                    message = "Solde débité avec succès."
                self._reply(200, {
                    "ok": True,
                    **result,
                    "notification_sent": notification_sent,
                    "message": message,
                })
                return

            elif action in {"approve_wallet_topup", "reject_wallet_topup"}:
                topup_id = int(form["topup_id"])
                approved = action == "approve_wallet_topup"
                topup = (
                    wallet_service.approve_onchain_topup(topup_id, ADMIN_ID)
                    if approved
                    else wallet_service.reject_onchain_topup(topup_id, ADMIN_ID)
                )
                if not topup:
                    raise ValueError("Ce rechargement a déjà été traité ou n’existe plus.")
                notification_sent = _notify_onchain_topup(topup, approved)
                decision = "accepté et crédité" if approved else "refusé"
                suffix = (
                    "Le client a été notifié sur Telegram."
                    if notification_sent
                    else "La décision est enregistrée, mais Telegram n’a pas pu notifier le client."
                )
                self._reply(200, {
                    "ok": True,
                    "topup_id": topup_id,
                    "status": "confirmed" if approved else "rejected",
                    "notification_sent": notification_sent,
                    "message": f"Rechargement {decision}. {suffix}",
                })
                return

            elif action == "close_ticket":
                tid = int(form["ticket_id"])
                if not support_service.close_ticket(tid):
                    raise ValueError("Ce ticket est déjà fermé ou introuvable.")

            elif action == "close_all_tickets":
                count = support_service.close_all_tickets()
                self._reply(200, {
                    "ok": True,
                    "modified": count,
                    "message": f"{count} ticket(s) ouvert(s) fermé(s).",
                })
                return

            elif action == "ticket_archive":
                tid = int(form["ticket_id"])
                if not support_service.archive_ticket(tid):
                    raise ValueError("Fermez ce ticket avant de l’archiver.")
                self._reply(200, {"ok": True, "message": f"Ticket #{tid} archivé."})
                return

            elif action == "tickets_archive_closed":
                count = support_service.archive_closed_tickets()
                self._reply(200, {
                    "ok": True,
                    "modified": count,
                    "message": f"{count} ticket(s) fermé(s) archivé(s).",
                })
                return

            elif action == "ticket_unarchive":
                tid = int(form["ticket_id"])
                if not support_service.unarchive_ticket(tid):
                    raise ValueError("Ce ticket n’est pas archivé ou n’existe plus.")
                self._reply(200, {"ok": True, "message": f"Ticket #{tid} restauré."})
                return

            elif action == "reply_ticket":
                tid = int(form["ticket_id"])
                message = form.get("message", "").strip()
                if message:
                    message_record = support_service.add_message(tid, 0, message, sender_type="admin")
                    # Notifier le client sur Telegram
                    ticket = support_service.get_ticket(tid)
                    if ticket:
                        _deliver_ticket_reply(int(ticket["user_id"]), tid, message)
                    self._reply(200, {"ok": True, "message_record": message_record})
                    return
                raise ValueError("Le message ne peut pas être vide.")

            elif action == "complete_withdrawal":
                withdrawal_id = int(form["withdrawal_id"])
                withdrawal = db.update_withdrawal(
                    withdrawal_id, "completed", form.get("admin_note", "").strip()[:500],
                )
                if not withdrawal:
                    raise ValueError("Ce retrait a déjà été traité ou n’existe plus.")
                amount = float(withdrawal.get("amount_cents") or 0) / 100
                db.audit_event("withdrawal.completed", details={"withdrawal_id": withdrawal_id})
                notification_sent = True
                try:
                    _run_async(_application().bot.send_message(
                        withdrawal["user_id"],
                        f"✅ <b>Retrait terminé</b>\n\nVotre retrait <b>#{withdrawal_id}</b> de <b>{amount:.2f} {CURRENCY}</b> a été envoyé.",
                        parse_mode=ParseMode.HTML,
                    ))
                except Exception:
                    notification_sent = False
                self._reply(200, {"ok": True, "notification_sent": notification_sent,
                                  "message": f"Retrait #{withdrawal_id} marqué comme payé."})
                return

            elif action == "withdrawal_reject":
                withdrawal_id = int(form["withdrawal_id"])
                reason = form.get("admin_note", "").strip()[:500]
                if not reason:
                    raise ValueError("Indiquez la raison du refus.")
                withdrawal = db.reject_withdrawal(withdrawal_id, reason)
                if not withdrawal:
                    raise ValueError("Ce retrait a déjà été traité ou n’existe plus.")
                amount = float(withdrawal.get("amount_cents") or 0) / 100
                notification_sent = True
                try:
                    _run_async(_application().bot.send_message(
                        withdrawal["user_id"],
                        f"❌ <b>Retrait refusé</b>\n\nLa demande <b>#{withdrawal_id}</b> a été refusée et <b>{amount:.2f} {CURRENCY}</b> a été recrédité.\nRaison : {html.escape(reason)}",
                        parse_mode=ParseMode.HTML,
                    ))
                except Exception:
                    notification_sent = False
                self._reply(200, {"ok": True, "notification_sent": notification_sent,
                                  "message": f"Retrait #{withdrawal_id} refusé et remboursé."})
                return

            elif action == "warranty_accept":
                request_id = int(form["warranty_id"])
                request = db.accept_warranty_request(request_id)
                if not request:
                    raise ValueError("Cette garantie a déjà été traitée ou n’existe plus.")
                self._reply(200, {"ok": True, "message": f"Garantie #{request_id} acceptée."})
                return

            elif action == "warranty_refuse":
                request_id = int(form["warranty_id"])
                reason = form.get("admin_note", "").strip()[:1000]
                if not reason:
                    raise ValueError("Indiquez la raison du refus.")
                request = db.refuse_warranty_request(request_id, reason)
                if not request:
                    raise ValueError("Cette garantie a déjà été traitée ou n’existe plus.")
                notification_sent = True
                try:
                    _run_async(_application().bot.send_message(
                        request["user_id"],
                        f"❌ <b>Demande de garantie refusée</b>\n\nDemande <b>#{request_id}</b>\nRaison : {html.escape(reason)}",
                        parse_mode=ParseMode.HTML,
                    ))
                except Exception:
                    notification_sent = False
                self._reply(200, {"ok": True, "notification_sent": notification_sent,
                                  "message": f"Garantie #{request_id} refusée."})
                return

            elif action == "warranty_refund":
                request_id = int(form["warranty_id"])
                request = db.resolve_warranty_request(request_id, "refund", form.get("admin_note", ""))
                if not request:
                    raise ValueError("Cette garantie n’est plus en attente d’une résolution.")
                refund = float(request.get("refund_amount") or 0)
                notification_sent = True
                try:
                    _run_async(_application().bot.send_message(
                        request["user_id"],
                        f"💰 <b>Remboursement de garantie approuvé</b>\n\n<b>{refund:.2f} {CURRENCY}</b> a été ajouté à votre portefeuille pour la demande <b>#{request_id}</b>.",
                        parse_mode=ParseMode.HTML,
                    ))
                except Exception:
                    notification_sent = False
                self._reply(200, {"ok": True, "notification_sent": notification_sent,
                                  "message": f"Garantie #{request_id} remboursée."})
                return

            elif action == "warranty_replacement":
                request_id = int(form["warranty_id"])
                replacement = form.get("replacement", "").strip()[:3600]
                if not replacement:
                    raise ValueError("Saisissez le contenu de remplacement.")
                request = db.resolve_warranty_request(request_id, "replacement")
                if not request:
                    request = db.get_conn().warranty_requests.find_one({
                        "id": request_id, "status": "replacement_pending",
                    })
                if not request:
                    raise ValueError("Cette garantie n’attend plus de remplacement.")
                _run_async(_application().bot.send_message(
                    request["user_id"],
                    "🔁 Votre remplacement sous garantie est prêt\n\n"
                    f"Commande : #{int(request['order_id'])}\n"
                    f"Garantie : #{request_id}\n\n{replacement}",
                ))
                if not db.complete_warranty_replacement(request_id):
                    raise ValueError("Le remplacement a été envoyé mais son statut n’a pas pu être finalisé.")
                self._reply(200, {"ok": True, "message": f"Remplacement de garantie #{request_id} envoyé."})
                return

            elif action == "confirm_payment":
                raise ValueError(
                    "La confirmation manuelle est désactivée. "
                    "Le paiement doit être confirmé automatiquement par Binance."
                )

            elif action == "cancel_order":
                oid = int(form["order_id"])
                reason = form.get("reason", "").strip()
                if order_service.cancel_order(oid, reason):
                    order = db.get_order(oid)
                    app = _application()
                    try:
                        _run_async(
                            app.bot.send_message(
                                order["user_id"],
                                f"❌ <b>Commande #{oid} annulée</b>\n\nRaison : {html.escape(reason or 'Annulée par l admin')}",
                                parse_mode=ParseMode.HTML,
                            )
                        )
                    except Exception as e:
                        print(f"Failed to notify cancellation to user: {e}")

            elif action == "reset_order":
                oid = int(form["order_id"])
                if not order_service.reset_for_payment(oid):
                    raise ValueError("La commande ne peut pas être remise en attente")

            elif action == "refund_order":
                oid = int(form["order_id"])
                reason = form.get("reason", "").strip()[:500]
                if not order_service.mark_refunded(oid, reason):
                    raise ValueError("La commande ne peut pas être remboursée")
                order = db.get_order(oid)
                _run_async(
                    _application().bot.send_message(
                        order["user_id"],
                        f"💸 <b>Commande #{oid} remboursée</b>\n\n{html.escape(reason)}",
                        parse_mode=ParseMode.HTML,
                    )
                )

            elif action == "resend_delivery":
                oid = int(form["order_id"])
                order = db.get_order(oid)
                content = inventory_service.delivered_content(oid)
                if not order or not content:
                    raise ValueError("Aucune livraison automatique à renvoyer")
                _run_async(
                    _application().bot.send_message(
                        order["user_id"],
                        f"🎁 <b>Livraison de la commande #{oid}</b>\n\n<code>{html.escape(chr(10).join(content))}</code>",
                        parse_mode=ParseMode.HTML,
                    )
                )

            elif action == "message_customer":
                oid = int(form["order_id"])
                message = form.get("message", "").strip()[:2000]
                order = db.get_order(oid)
                if not order or not message:
                    raise ValueError("Commande ou message invalide")
                _run_async(
                    _application().bot.send_message(order["user_id"], html.escape(message), parse_mode=ParseMode.HTML)
                )
                db.audit_event("customer.message_sent", details={"order_id": oid, "user_id": order["user_id"]})

            elif action == "save_order_note":
                oid = int(form["order_id"])
                note = form.get("note", "").strip()
                db.get_conn().orders.update_one({"id": oid}, {"$set": {"admin_note": note}})
                db.audit_event("order.note_updated", details={"order_id": oid})

            elif action == "update_order_admin":
                oid = int(form["order_id"])
                updated = order_service.admin_update_order(
                    oid,
                    status=form.get("status", "").strip() or None,
                    txid=form.get("txid", "").strip(),
                    qty=int(form["qty"]) if form.get("qty", "").strip() else None,
                    unit_price=float(form["unit_price"]) if form.get("unit_price", "").strip() else None,
                    total_price=float(form["total_price"]) if form.get("total_price", "").strip() else None,
                    admin_note=form.get("admin_note", ""),
                )
                if not updated:
                    raise ValueError("Commande introuvable")

            elif action == "manual_deliver_order":
                oid = int(form["order_id"])
                content = form.get("delivery_text", "").strip()
                order = order_service.manual_deliver_order(oid, content)
                if not order:
                    raise ValueError("Commande introuvable")
                _run_async(
                    _application().bot.send_message(
                        order["user_id"],
                        f"🎁 <b>Votre commande #{oid} est livrée !</b>\n\n"
                        f"<code>{html.escape(content)}</code>",
                        parse_mode=ParseMode.HTML,
                    )
                )

            elif action == "save_settings":
                shop_name = form.get("shop_name", "BlackMarket").strip()
                currency = form.get("currency", "USDT").strip()
                low_stock = int(form.get("low_stock_threshold", 5))
                expiry = int(form.get("order_expiry_seconds", 1800))
                payment_recipient = form.get("payment_recipient", "").strip()
                maintenance_enabled = form.get("maintenance_enabled", "") == "on"
                maintenance_message = form.get("maintenance_message", "").strip()[:500]
                affiliate_enabled = form.get("affiliate_enabled", "") == "on"
                affiliate_target = max(1, int(form.get("affiliate_target", 10)))
                affiliate_reward_cents = max(0, int(form.get("affiliate_reward_cents", 100)))
                active_languages = ",".join(
                    code for code in ("en", "ar") if code in form.get("active_languages", "en,ar").split(",")
                ) or "en"

                db.set_setting("shop_name", shop_name)
                db.set_setting("currency", currency)
                db.set_setting("low_stock_threshold", low_stock)
                db.set_setting("order_expiry_seconds", expiry)
                db.set_setting("payment_recipient", payment_recipient)
                db.set_setting("maintenance_enabled", maintenance_enabled)
                db.set_setting("maintenance_message", maintenance_message)
                db.set_setting("affiliate_enabled", affiliate_enabled)
                db.set_setting("affiliate_target", affiliate_target)
                db.set_setting("affiliate_reward_cents", affiliate_reward_cents)
                db.set_setting("welcome_message", form.get("welcome_message", "").strip()[:2000])
                db.set_setting("help_message", form.get("help_message", "").strip()[:4000])
                db.set_setting("terms_message", form.get("terms_message", "").strip()[:4000])
                db.set_setting("privacy_message", form.get("privacy_message", "").strip()[:4000])
                db.set_setting("active_languages", active_languages)
                ann_new = form.get("announcement_new_stock", "").strip()
                ann_flash = form.get("announcement_flash_sale", "").strip()
                ann_restock = form.get("announcement_restock", "").strip()
                if ann_new:
                    db.set_setting("announcement_new_stock", ann_new)
                    db.set_text_override("channel_stock_announcement", "en", ann_new)
                if ann_flash:
                    db.set_setting("announcement_flash_sale", ann_flash)
                    db.set_text_override("flash_sale_announcement", "en", ann_flash)
                if ann_restock:
                    db.set_setting("announcement_restock", ann_restock)
                    db.set_text_override("offer_stock_announcement", "en", ann_restock)
                db.audit_event("settings.updated")

            elif action == "save_reseller_product":
                provider = form.get("provider", reseller_service.PROVIDER).strip().lower()
                product_id = form.get("product_id", "").strip()
                retail_price = float(form.get("retail_price", "0"))
                enabled = form.get("enabled", "") == "1"
                period_value, period_unit, period_days = _duration_form_values(
                    form, "period", 30, allow_zero=False,
                )
                warranty_value, warranty_unit, warranty_days = _duration_form_values(
                    form, "warranty", 0, allow_zero=True,
                )
                raw_service_id = form.get("service_id", "").strip()
                saved = reseller_service.save_catalog_product(
                    product_id,
                    provider=provider,
                    retail_price=retail_price,
                    enabled=enabled,
                    service_id=int(raw_service_id) if raw_service_id else None,
                    new_service_name=form.get("new_service_name", "").strip(),
                    service_emoji=form.get("service_emoji", "📦").strip(),
                    display_name=form.get("display_name", "").strip(),
                    description=form.get("description", "").strip(),
                    warranty=form.get("warranty", "").strip(),
                    period_days=period_days,
                    warranty_days=warranty_days,
                    period_value=period_value,
                    period_unit=period_unit,
                    warranty_value=warranty_value,
                    warranty_unit=warranty_unit,
                    delivery_delay=form.get(
                        "delivery_delay", "Instantané après confirmation"
                    ).strip(),
                    sort_order=int(form.get("sort_order", "0") or 0),
                    low_stock_threshold=int(
                        form.get("low_stock_threshold", "5") or 5
                    ),
                )
                db.audit_event(
                    "reseller_product.updated",
                    details={
                        "provider": provider,
                        "product_id": product_id,
                        "enabled": enabled,
                        "retail_price": retail_price,
                        "service_id": saved.get("service_id"),
                        "local_offer_id": saved.get("local_offer_id"),
                    },
                )
                self._reply(200, {"ok": True, "product": saved})
                return

            elif action == "save_external_connector":
                connector = external_api_service.save_connector(form)
                db.audit_event("external_api.saved", details={"connector_id": connector["id"], "name": connector["name"]})
                self._reply(200, {"ok": True, "connector": connector, "message": "Connexion API enregistrée."})
                return

            elif action == "delete_external_connector":
                connector_id = int(form["connector_id"])
                if not external_api_service.delete_connector(connector_id):
                    raise ValueError("Connexion API introuvable")
                db.audit_event("external_api.deleted", details={"connector_id": connector_id})
                self._reply(200, {"ok": True, "message": "Connexion API supprimée."})
                return

            elif action == "run_external_connector":
                connector_id = int(form["connector_id"])
                result = external_api_service.execute(connector_id, form.get("body"))
                db.audit_event(
                    "external_api.executed",
                    details={"connector_id": connector_id, "status": result["status"], "duration_ms": result["duration_ms"]},
                )
                self._reply(200 if result["ok"] else 502, result)
                return

            elif action == "undo_audit_event":
                self._reply(200, undo_audit_event(int(form["event_id"])))
                return

            elif action == "repair_telegram_webhook":
                result = repair_telegram_webhook()
                db.audit_event(
                    "webhook.repair_requested",
                    details={"ok": bool(result.get("ok"))},
                )
                self._reply(200 if result.get("ok") else 503, result)
                return

            else:
                raise ValueError(f"Unknown action: {action}")

            self._reply(200, {"ok": True})
        except Exception as exc:
            traceback.print_exc()
            self._reply(400, {"ok": False, "error": str(exc)})
