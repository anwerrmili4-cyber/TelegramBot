"""Server-side client and catalog mapping for external reseller suppliers."""

from __future__ import annotations

import json
import logging
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pymongo.errors import DuplicateKeyError

import database as db
from app.domain import warranty_service
from config import (
    CANBOSO_API_BASE,
    CANBOSO_API_KEY,
    CGPT_ACTIVE_API_BASE,
    CGPT_ACTIVE_API_KEY,
    GPT_CHEAP_API_KEY,
    KAKAO_API_BASE,
    KAKAO_API_KEY,
    MAILREADER_API_BASE,
    MAILREADER_API_KEY,
    NASTELE_API_BASE,
    NASTELE_API_KEY,
    NASTELE_VND_PER_USDT,
    SHAMEKH_API_BASE,
    SHAMEKH_API_KEY,
    SHOP_CRON_API_KEY,
    UPIBOT_API_BASE,
    UPIBOT_API_KEY,
    VEX_API_BASE,
    VEX_API_KEY,
)

PROVIDER = "mailreader"
SHAMEKH_PROVIDER = "shamekh"
KAKAO_PROVIDER = "kakao"
VEX_PROVIDER = "vex"
NASTELE_PROVIDER = "nastele"
CANBOSO_PROVIDER = "canboso"
GPT_CHEAP_PROVIDER = "gpt_cheap"
SHOP_CRON_PROVIDER = "shop_cron"
UPIBOT_PROVIDER = "upibot"
CGPT_ACTIVE_PROVIDER = "cgpt_active"
CGPT_ACTIVE_DISPLAY_NAME = "Rich AI Store"
PROVIDER_DISPLAY_NAMES = {
    PROVIDER: "MailReader",
    SHAMEKH_PROVIDER: "Shamekh's bot",
    KAKAO_PROVIDER: "Kakao Shop",
    VEX_PROVIDER: "VEX Reseller",
    NASTELE_PROVIDER: "NasTele",
    CANBOSO_PROVIDER: "Piggy AI",
    GPT_CHEAP_PROVIDER: "GPT Cheap",
    SHOP_CRON_PROVIDER: "Shop Cron",
    UPIBOT_PROVIDER: "UPIBot Shop",
    CGPT_ACTIVE_PROVIDER: CGPT_ACTIVE_DISPLAY_NAME,
}
PROVIDER_BOT_USERNAMES = {
    PROVIDER: "dodistore_bot",
    SHAMEKH_PROVIDER: "Shamekhstock_bot",
    KAKAO_PROVIDER: "Shop_KOKORO_BOT",
    VEX_PROVIDER: "VexoranShoppieBot",
    NASTELE_PROVIDER: "BolemT",
    CANBOSO_PROVIDER: "PiggyAi799_Bot",
    GPT_CHEAP_PROVIDER: "GPTCheapChat_bot",
    SHOP_CRON_PROVIDER: "shop_cron191_en_bot",
    UPIBOT_PROVIDER: "scanupigptbot",
    CGPT_ACTIVE_PROVIDER: "RichAIStoreBot",
}
SUPPORTED_PROVIDERS = {
    PROVIDER,
    SHAMEKH_PROVIDER,
    KAKAO_PROVIDER,
    VEX_PROVIDER,
    NASTELE_PROVIDER,
    CANBOSO_PROVIDER,
    GPT_CHEAP_PROVIDER,
    SHOP_CRON_PROVIDER,
    UPIBOT_PROVIDER,
    CGPT_ACTIVE_PROVIDER,
}
CANBOSO_PROVIDERS = {
    CANBOSO_PROVIDER,
    GPT_CHEAP_PROVIDER,
    SHOP_CRON_PROVIDER,
}
log = logging.getLogger(__name__)


class ResellerApiError(RuntimeError):
    """A safe, administrator-facing supplier error."""


class ResellerOrderNotCreatedError(ResellerApiError):
    """The supplier rejected the purchase before creating an order."""


def provider_display_name(provider: str) -> str:
    """Return the public supplier name used in admin messages."""
    normalized = str(provider or "").strip().lower()
    return PROVIDER_DISPLAY_NAMES.get(normalized, normalized or "Fournisseur inconnu")


def provider_bot_username(provider: str) -> str:
    """Return the supplier's public Telegram bot username, without @."""
    return PROVIDER_BOT_USERNAMES.get(str(provider or "").strip().lower(), "")


def get_nastele_vnd_rate() -> float:
    """Return VND per USDT exchange rate from DB settings or config."""
    setting = db.get_setting("nastele_vnd_per_usdt")
    if setting is not None:
        try:
            val = float(setting)
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    return float(NASTELE_VND_PER_USDT or 25500.0)


def _request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not MAILREADER_API_KEY:
        raise ResellerApiError(
            "MailReader n’est pas configuré. Ajoutez HP_MAILREADER_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{MAILREADER_API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {MAILREADER_API_KEY}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # MailReader uses the response body to explain rejected orders (for
        # example, HTTP 409 for an out-of-stock product). Preserve that reason
        # instead of reducing every non-auth/non-payment error to a generic
        # review_required state.
        error_message = ""
        try:
            raw_error = exc.read().decode("utf-8", errors="replace")
            error_payload = json.loads(raw_error)
            if isinstance(error_payload, dict):
                error_message = str(
                    error_payload.get("message")
                    or error_payload.get("error")
                    or error_payload.get("detail")
                    or ""
                ).strip()
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        normalized_error = error_message.lower()
        no_order_words = (
            "stock", "out of stock", "insufficient", "unavailable",
            "sold out", "inventory", "balance", "solde", "rupture",
            "indisponible", "épuis", "epuis",
        )
        if any(word in normalized_error for word in no_order_words):
            detail = error_message or f"HTTP {exc.code}"
            raise ResellerOrderNotCreatedError(
                f"MailReader a refusé la commande sans la créer : {detail}"
            ) from exc
        if exc.code in {401, 403}:
            raise ResellerApiError(
                "Clé API MailReader refusée. Remplacez-la par une clé active."
            ) from exc
        if exc.code == 402:
            raise ResellerOrderNotCreatedError(
                "Solde MailReader insuffisant : aucune commande fournisseur n’a été créée."
            ) from exc
        detail = f" : {error_message}" if error_message else ""
        raise ResellerApiError(
            f"MailReader a répondu avec l’erreur HTTP {exc.code}{detail}."
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("MailReader est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse MailReader invalide.")
    if payload.get("success") is False or payload.get("ok") is False:
        message = str(payload.get("message") or payload.get("error") or "Requête MailReader refusée.")[:300]
        if any(word in message.lower() for word in ("balance", "solde", "insufficient")):
            raise ResellerOrderNotCreatedError(message)
        raise ResellerApiError(message)
    return payload


def _mailreader_preflight_purchase(offer: dict[str, Any], quantity: int) -> None:
    """Refresh MailReader balance/stock immediately before an order.

    The products endpoint includes the current reseller balance and product
    stock. A fresh read prevents stale catalog data from triggering an order
    that the supplier cannot create, and gives us a deterministic no-order
    error before the purchase POST is sent.
    """
    payload = _request_json("/api/reseller/products")
    reseller = payload.get("reseller") if isinstance(payload.get("reseller"), dict) else {}
    try:
        balance = float(reseller.get("balance"))
    except (TypeError, ValueError):
        balance = None
    try:
        unit_price = float(offer.get("wholesale_price") or 0)
    except (TypeError, ValueError):
        unit_price = 0.0
    if balance is not None and unit_price > 0 and balance < unit_price * quantity:
        raise ResellerOrderNotCreatedError(
            f"Solde MailReader insuffisant ({balance:.2f} USDT disponible, "
            f"{unit_price * quantity:.2f} USDT requis)."
        )

    product_id = str(offer.get("supplier_product_id") or "")
    products = payload.get("products")
    if not isinstance(products, list):
        return
    for product in products:
        if not isinstance(product, dict):
            continue
        current_id = str(
            product.get("id") or product.get("_id") or product.get("product_id")
            or product.get("productId") or ""
        )
        if current_id != product_id or "stock" not in product:
            continue
        try:
            stock = float(product.get("stock"))
        except (TypeError, ValueError):
            return
        if stock < quantity:
            raise ResellerOrderNotCreatedError(
                f"Stock MailReader insuffisant pour {product_id} "
                f"({int(stock) if stock.is_integer() else stock} disponible, {quantity} requis)."
            )
        return


def _shamekh_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not SHAMEKH_API_KEY:
        raise ResellerApiError(
            "Shamekh’s bot n’est pas configuré. Ajoutez HP_SHAMEKH_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{SHAMEKH_API_BASE}{path}",
        headers={
            "X-API-Key": SHAMEKH_API_KEY,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise ResellerApiError(
                "Clé API Shamekh refusée. Remplacez-la par une clé active."
            ) from exc
        raise ResellerApiError(
            f"Shamekh’s bot a répondu avec l’erreur HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("Shamekh’s bot est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse Shamekh invalide.")
    if payload.get("ok") is False:
        raise ResellerApiError(str(payload.get("error") or "Requête Shamekh refusée.")[:300])
    return payload


def _kakao_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not KAKAO_API_KEY:
        raise ResellerApiError(
            "Kakao Shop n’est pas configuré. Ajoutez HP_KAKAO_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{KAKAO_API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {KAKAO_API_KEY}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            401: "Clé API Kakao refusée. Remplacez-la par une clé active.",
            402: "Solde Kakao insuffisant pour cette commande.",
            404: "Produit Kakao introuvable.",
            409: "Produit Kakao en rupture de stock.",
        }
        raise ResellerApiError(
            messages.get(exc.code, f"Kakao Shop a répondu avec l’erreur HTTP {exc.code}.")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("Kakao Shop est temporairement indisponible.") from exc
    if isinstance(payload, list):
        payload = {"success": True, "products": payload}
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse Kakao invalide.")
    if payload.get("success") is False or payload.get("ok") is False:
        raise ResellerApiError(str(payload.get("error") or "Requête Kakao refusée.")[:300])
    return payload


def _vex_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not VEX_API_KEY:
        raise ResellerApiError(
            "VEX Reseller n’est pas configuré. Ajoutez HP_VEX_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    endpoint = path if path.startswith(("?", "/")) else f"/{path}"
    request = Request(
        f"{VEX_API_BASE}{endpoint}",
        headers={
            "Authorization": f"Bearer {VEX_API_KEY}",
            "x-api-key": VEX_API_KEY,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            401: "Clé API VEX refusée. Remplacez-la par une clé active.",
            402: "Solde VEX insuffisant pour cette commande.",
            409: "Produit VEX indisponible ou commande en conflit.",
            429: "Limite VEX atteinte. Réessayez dans une minute.",
        }
        raise ResellerApiError(
            messages.get(exc.code, f"VEX Reseller a répondu avec l’erreur HTTP {exc.code}.")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("VEX Reseller est temporairement indisponible.") from exc
    if isinstance(payload, list):
        payload = {"ok": True, "products": payload}
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse VEX invalide.")
    if payload.get("success") is False or payload.get("ok") is False or (payload.get("error") and not payload.get("products") and "balance" not in payload):
        raise ResellerApiError(str(payload.get("error") or "Requête VEX refusée.")[:300])
    return payload


def _nastele_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call NasTele Partner API without exposing its key in logs or errors."""
    if not NASTELE_API_KEY:
        raise ResellerApiError(
            "NasTele n'est pas configuré. Ajoutez HP_NASTELE_API_KEY "
            "dans les variables d'environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{NASTELE_API_BASE}{path}",
        headers={
            "X-API-Key": NASTELE_API_KEY,
            "Accept": "application/json",
            **({
                "Content-Type": "application/json"
            } if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            401: "Clé API NasTele refusée. Remplacez-la par une clé active.",
            402: "Solde NasTele insuffisant pour cette commande.",
            403: "Compte NasTele suspendu.",
            404: "Produit NasTele introuvable.",
            409: "Stock NasTele insuffisant ou prix modifié.",
            422: "Requête NasTele invalide (productId / qty).",
            429: "Limite NasTele atteinte. Réessayez dans une minute.",
        }
        error_type = (
            ResellerOrderNotCreatedError
            if exc.code in {402, 404, 409}
            else ResellerApiError
        )
        raise error_type(
            messages.get(exc.code, f"NasTele a répondu avec l'erreur HTTP {exc.code}.")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("NasTele est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse NasTele invalide.")
    if payload.get("success") is False:
        raise ResellerApiError(
            str(payload.get("message") or payload.get("error") or "Requête NasTele refusée.")[:300]
        )
    return payload


def _canboso_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
    provider: str = CANBOSO_PROVIDER,
) -> dict[str, Any]:
    """Call the buyer-key API without ever placing its key in logs or errors."""
    api_key, provider_name = {
        CANBOSO_PROVIDER: (CANBOSO_API_KEY, "Piggy AI"),
        GPT_CHEAP_PROVIDER: (GPT_CHEAP_API_KEY, "GPT Cheap"),
        SHOP_CRON_PROVIDER: (SHOP_CRON_API_KEY, "Shop Cron"),
    }.get(provider, ("", "Canboso"))
    api_key = str(api_key).strip()
    if not api_key:
        raise ResellerApiError(
            f"{provider_name} n’est pas configuré. Ajoutez sa clé API "
            "dans les variables d’environnement."
        )
    request_body = None
    url = f"{CANBOSO_API_BASE}{path}"
    if method == "GET":
        url = f"{url}?{urlencode({'key': api_key})}"
    else:
        request_body = {"key": api_key, **(body or {})}
    payload_bytes = (
        json.dumps(request_body).encode("utf-8")
        if request_body is not None
        else None
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if request_body is not None else {}),
            **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            400: f"Requête {provider_name} refusée ou solde fournisseur insuffisant.",
            401: f"Clé API {provider_name} refusée. Remplacez-la par une clé active.",
            404: f"Produit {provider_name} introuvable.",
            409: f"Stock {provider_name} insuffisant ou commande déjà en cours.",
            429: f"Limite {provider_name} atteinte. Respectez le délai Retry-After avant de réessayer.",
            503: f"Protection des achats {provider_name} temporairement indisponible.",
        }
        raise ResellerApiError(
            messages.get(exc.code, f"{provider_name} a répondu avec l’erreur HTTP {exc.code}.")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError(f"{provider_name} est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError(f"Réponse {provider_name} invalide.")
    if payload.get("success") is False:
        raise ResellerApiError(str(payload.get("message") or f"Requête {provider_name} refusée.")[:300])
    return payload


def _upibot_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call UPIBot's Shop API without exposing its deposit-spending key."""
    if not UPIBOT_API_KEY:
        raise ResellerApiError(
            "UPIBot n’est pas configuré. Ajoutez HP_UPIBOT_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{UPIBOT_API_BASE}{path}",
        headers={
            "X-Shop-API-Key": UPIBOT_API_KEY,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            400: "Commande UPIBot invalide.",
            401: "Clé API UPIBot refusée. Remplacez-la par une clé active.",
            402: "Solde UPIBot insuffisant : aucune commande fournisseur n’a été créée.",
            404: "Produit ou commande UPIBot introuvable.",
            409: "Produit UPIBot en rupture de stock ou sans prix.",
            423: "La boutique UPIBot est actuellement désactivée.",
            502: "Le fournisseur UPIBot a échoué et a remboursé la commande.",
            503: "UPIBot est temporairement indisponible.",
        }
        error_type = (
            ResellerOrderNotCreatedError
            if exc.code in {400, 402, 404, 409, 423}
            else ResellerApiError
        )
        raise error_type(
            messages.get(exc.code, f"UPIBot a répondu avec l’erreur HTTP {exc.code}.")
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("UPIBot est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse UPIBot invalide.")
    if payload.get("ok") is False:
        message = str(
            payload.get("message") or payload.get("error") or "Requête UPIBot refusée."
        )[:300]
        raise ResellerApiError(message)
    return payload


def _cgpt_active_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Call Rich AI Store without exposing its bearer credential."""
    if not CGPT_ACTIVE_API_KEY:
        raise ResellerApiError(
            "Rich AI Store n’est pas configuré. Ajoutez HP_CGPT_ACTIVE_API_KEY "
            "dans les variables d’environnement."
        )
    payload_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{CGPT_ACTIVE_API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {CGPT_ACTIVE_API_KEY}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
            "User-Agent": "BlackMarket-Reseller/1.0",
        },
        data=payload_bytes,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_payload: dict[str, Any] = {}
        try:
            decoded = json.loads(exc.read().decode("utf-8"))
            if isinstance(decoded, dict):
                error_payload = decoded
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        code = str(error_payload.get("code") or "")
        request_id = str(error_payload.get("request_id") or "")
        if request_id:
            log.warning("Rich AI Store request failed: status=%s code=%s request_id=%s", exc.code, code, request_id)
        message = str(error_payload.get("message") or "")[:300]
        if exc.code in {401, 403} or code == "unauthorized":
            raise ResellerApiError(
                "Clé API Rich AI Store refusée. Remplacez-la par une clé active."
            ) from exc
        if code == "insufficient_balance":
            raise ResellerOrderNotCreatedError(
                message or "Solde Rich AI Store insuffisant : aucune commande fournisseur n’a été créée."
            ) from exc
        raise ResellerApiError(
            message or f"Rich AI Store a répondu avec l’erreur HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ResellerApiError("Rich AI Store est temporairement indisponible.") from exc
    if not isinstance(payload, dict):
        raise ResellerApiError("Réponse Rich AI Store invalide.")
    return payload


def provider_summaries() -> list[dict[str, Any]]:
    """Return safe provider metadata without exposing credentials."""
    return [
        {
            "id": PROVIDER,
            "name": "MailReader",
            "configured": bool(MAILREADER_API_KEY),
            "documentation_url": "https://api.mailreader.tech/docs",
        },
        {
            "id": SHAMEKH_PROVIDER,
            "name": "Shamekh’s bot",
            "configured": bool(SHAMEKH_API_KEY),
            "documentation_url": "",
        },
        {
            "id": KAKAO_PROVIDER,
            "name": "Kakao Shop",
            "configured": bool(KAKAO_API_KEY),
            "documentation_url": "",
        },
        {
            "id": VEX_PROVIDER,
            "name": "VEX Reseller",
            "configured": bool(VEX_API_KEY),
            "documentation_url": "",
        },
        {
            "id": NASTELE_PROVIDER,
            "name": "NasTele",
            "configured": bool(NASTELE_API_KEY),
            "documentation_url": "https://nastele.online/api/partner/docs",
        },
        {
            "id": CANBOSO_PROVIDER,
            "name": "Piggy AI",
            "configured": bool(CANBOSO_API_KEY),
            "documentation_url": "https://canboso.com/api/swagger",
        },
        {
            "id": GPT_CHEAP_PROVIDER,
            "name": "GPT Cheap",
            "configured": bool(GPT_CHEAP_API_KEY),
            "documentation_url": "https://canboso.com/api/swagger",
        },
        {
            "id": SHOP_CRON_PROVIDER,
            "name": "Shop Cron",
            "configured": bool(SHOP_CRON_API_KEY),
            "documentation_url": "https://canboso.com/api/swagger",
        },
        {
            "id": UPIBOT_PROVIDER,
            "name": "UPIBot Shop",
            "configured": bool(UPIBOT_API_KEY),
            "documentation_url": "https://upibot.00969600.xyz/shop-api/docs",
        },
        {
            "id": CGPT_ACTIVE_PROVIDER,
            "name": CGPT_ACTIVE_DISPLAY_NAME,
            "configured": bool(CGPT_ACTIVE_API_KEY),
            "documentation_url": f"{CGPT_ACTIVE_API_BASE}/docs",
        },
    ]


def catalog(provider: str = PROVIDER) -> dict[str, Any]:
    """Fetch the live supplier catalog and overlay local retail selections."""
    provider = str(provider or PROVIDER).lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Fournisseur API inconnu.")
    if provider == SHAMEKH_PROVIDER:
        payload = _shamekh_request_json("/api/products")
        account = _shamekh_request_json("/api/me")
        reseller = account.get("user") if isinstance(account.get("user"), dict) else {}
        supplier_name = "Shamekh’s bot"
    elif provider == KAKAO_PROVIDER:
        payload = _kakao_request_json("/api/products")
        balance_payload = _kakao_request_json("/api/balance")
        balance_data = (
            balance_payload.get("data")
            if isinstance(balance_payload.get("data"), dict)
            else balance_payload
        )
        reseller = {"balance": balance_data.get("balance", 0)}
        supplier_name = "Kakao Shop"
    elif provider == VEX_PROVIDER:
        payload = _vex_request_json("?action=products")
        balance_payload = _vex_request_json("?action=balance")
        balance_data = (
            balance_payload.get("data")
            if isinstance(balance_payload.get("data"), dict)
            else balance_payload
        )
        reseller = {"balance": balance_data.get("balance", 0)}
        supplier_name = "VEX Reseller"
    elif provider == NASTELE_PROVIDER:
        payload = _nastele_request_json("/api/partner/products")
        balance_payload = _nastele_request_json("/api/partner/balance")
        balance_data = (
            balance_payload.get("data")
            if isinstance(balance_payload.get("data"), dict)
            else balance_payload
        )
        rate = get_nastele_vnd_rate()
        raw_balance = float(balance_data.get("balance", 0))
        reseller = {"balance": round(raw_balance / rate, 2)}
        supplier_name = "NasTele"
    elif provider in CANBOSO_PROVIDERS:
        provider_name = {
            CANBOSO_PROVIDER: "Piggy AI",
            GPT_CHEAP_PROVIDER: "GPT Cheap",
            SHOP_CRON_PROVIDER: "Shop Cron",
        }[provider]
        payload = _canboso_request_json("/products", provider=provider)
        balance_payload = _canboso_request_json("/balance", provider=provider)
        wallet_currency = str(balance_payload.get("walletCurrency") or "VND").upper()
        balance = (
            balance_payload.get("usdtBalance", balance_payload.get("balance", 0))
            if wallet_currency == "USD"
            else balance_payload.get("balance", 0)
        )
        reseller = {"balance": balance}
        supplier_name = provider_name
    elif provider == UPIBOT_PROVIDER:
        payload = _upibot_request_json("/products")
        account = _upibot_request_json("/me")
        reseller = {"balance": account.get("deposit_balance", 0)}
        supplier_name = "UPIBot Shop"
    elif provider == CGPT_ACTIVE_PROVIDER:
        payload = _cgpt_active_request_json("/v1/products")
        account = _cgpt_active_request_json("/v1/me")
        reseller = {"balance": account.get("balance", 0)}
        supplier_name = CGPT_ACTIVE_DISPLAY_NAME
    else:
        payload = _request_json("/api/reseller/products")
        reseller = payload.get("reseller") if isinstance(payload.get("reseller"), dict) else {}
        supplier_name = str(reseller.get("name") or "MailReader")
    raw_products = payload.get("products")
    if provider in {KAKAO_PROVIDER, VEX_PROVIDER, NASTELE_PROVIDER} and not isinstance(raw_products, list):
        raw_products = payload.get("data")
    if not isinstance(raw_products, list):
        raise ResellerApiError("Le fournisseur ne contient aucune liste de produits.")

    saved = {
        row["product_id"]: row
        for row in db.list_reseller_product_configs(provider)
    }
    products = []
    for raw in raw_products:
        if not isinstance(raw, dict):
            continue
        # The current Telegram checkout has no supplier-input collection or
        # asynchronous invite polling yet. Only publish products that return
        # redeemable codes immediately after a successful purchase.
        if provider == CGPT_ACTIVE_PROVIDER and raw.get("product_type") != "cdk":
            continue
        raw_product_id = (
            raw.get("_id") or raw.get("productId") or raw.get("id")
            if provider in CANBOSO_PROVIDERS
            else raw.get("id")
        )
        if not raw_product_id:
            continue
        product_id = str(raw_product_id)
        try:
            canboso_price = raw.get("price")
            if isinstance(canboso_price, dict):
                canboso_price = canboso_price.get("amount", 0)
            if provider == NASTELE_PROVIDER:
                rate = get_nastele_vnd_rate()
                vnd_price = float(Decimal(str(raw.get("price") or 0)))
                wholesale = round(vnd_price / rate, 2)
            else:
                wholesale = float(Decimal(str(
                    raw.get("usdPricing", canboso_price or 0)
                    if provider in CANBOSO_PROVIDERS
                    else (
                        raw.get("price")
                        if provider in {SHAMEKH_PROVIDER, KAKAO_PROVIDER, VEX_PROVIDER}
                        else raw.get("sell_price")
                        if provider == UPIBOT_PROVIDER
                        else raw.get("your_unit_price")
                        if provider == CGPT_ACTIVE_PROVIDER
                        else raw.get("wholesale_price", "0")
                    )
                )))
        except (InvalidOperation, ValueError):
            wholesale = 0.0
        stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
        availability = (
            raw.get("availability")
            if isinstance(raw.get("availability"), dict)
            else {}
        )
        unlimited_stock = (
            (provider == CGPT_ACTIVE_PROVIDER and raw.get("stock") is None)
            or (provider == UPIBOT_PROVIDER and raw.get("stock_count") is None)
            or (provider == PROVIDER and raw.get("stock") is None)
            or raw.get("stock") == -1
            or bool(raw.get("unlimited_stock") or raw.get("unlimited"))
        )
        stock = max(0, int(
            (stats.get("available") or availability.get("available") or 0)
            if provider in CANBOSO_PROVIDERS
            else (
                (raw.get("stock_count") or 0)
                if provider in {SHAMEKH_PROVIDER, UPIBOT_PROVIDER}
                else raw.get("stock") or 0
            )
        ))
        config = saved.get(product_id, {})
        retail_price = config.get("retail_price")
        local_offer_id = config.get("local_offer_id")
        native_offer = db.get_offer(int(local_offer_id)) if local_offer_id else None
        native_service = (
            db.get_service(int(config["service_id"]))
            if config.get("service_id") is not None
            else None
        )
        if local_offer_id:
            db.update_offer(
                int(local_offer_id),
                stock=stock,
                unlimited_stock=unlimited_stock,
                supplier_provider=provider,
                supplier_product_id=product_id,
            )
        products.append({
            "id": product_id,
            "name": str(
                raw.get("name_en")
                or raw.get("product_name")
                or raw.get("name")
                or product_id
            )[:200],
            "description": str(
                raw.get("description")
                or (f"Source : {raw.get('source')}" if raw.get("source") else "")
            )[:2000],
            "delivery_instruction": str(
                raw.get("delivery_instruction")
                or raw.get("delivery_instructions")
                or ""
            )[:2000],
            "wholesale_price": wholesale,
            "currency": str(
                (
                    "USDT"
                    if str(
                        (raw.get("price") or {}).get("currency", "USD")
                        if isinstance(raw.get("price"), dict)
                        else "USD"
                    ).upper() in {"USD", "USDT"}
                    else (raw.get("price") or {}).get("currency", "USDT")
                )
                if provider in CANBOSO_PROVIDERS
                else raw.get("currency") or "USDT"
            )[:12],
            "stock": stock,
            "unlimited_stock": unlimited_stock,
            "manual_delivery": bool(
                raw.get("manual_delivery", False)
                or (
                    provider in CANBOSO_PROVIDERS
                    and (
                        raw.get("requiresCustomerEmail")
                        or raw.get("productType") == "slot"
                        or (
                            isinstance(raw.get("purchaseRequirements"), dict)
                            and raw["purchaseRequirements"].get("customerEmail")
                        )
                    )
                )
            ),
            "enabled": bool(config.get("enabled", False)),
            "retail_price": float(retail_price) if retail_price is not None else None,
            "profit": (
                round(float(retail_price) - wholesale, 2)
                if retail_price is not None else None
            ),
            "service_id": config.get("service_id"),
            "local_offer_id": local_offer_id,
            "display_name": config.get("display_name") or str(
                raw.get("product_name") or raw.get("name") or product_id
            )[:200],
            "service_name": (
                (native_service or {}).get("name")
                or config.get("service_name")
                or ""
            ),
            "service_emoji": (
                (native_service or {}).get("emoji")
                or config.get("service_emoji")
                or "📦"
            ),
            "custom_description": config.get("description") or str(raw.get("description") or "")[:2000],
            "warranty": (
                config.get("warranty")
                or (native_offer or {}).get("note")
                or f"Produit API {supplier_name}"
            ),
            "period_days": int(
                config.get("period_days")
                or (native_offer or {}).get("period_days")
                or 30
            ),
            "delivery_delay": config.get("delivery_delay") or "Instantané après confirmation",
            "sort_order": int(config.get("sort_order") or 0),
            "low_stock_threshold": int(config.get("low_stock_threshold") or 5),
            "published": bool(config.get("local_offer_id")),
        })
    used_count = sum(1 for product in products if product["enabled"])
    return {
        "ok": True,
        "configured": True,
        "provider": provider,
        "supplier_name": supplier_name,
        "balance": float(Decimal(str(reseller.get("balance", "0")))),
        "currency": (
            ("USDT" if wallet_currency == "USD" else wallet_currency)
            if provider in CANBOSO_PROVIDERS
            else "USDT"
        ),
        "providers": provider_summaries(),
        "products": products,
        # Keep selected_count for older dashboards while exposing explicit
        # usage buckets shared by every external provider.
        "selected_count": used_count,
        "used_count": used_count,
        "unused_count": len(products) - used_count,
    }


def detect_restock_events() -> dict[str, Any]:
    """Refresh configured API products and return newly added supplier stock."""
    configured = {
        PROVIDER: bool(MAILREADER_API_KEY),
        SHAMEKH_PROVIDER: bool(SHAMEKH_API_KEY),
        KAKAO_PROVIDER: bool(KAKAO_API_KEY),
        VEX_PROVIDER: bool(VEX_API_KEY),
        NASTELE_PROVIDER: bool(NASTELE_API_KEY),
        CANBOSO_PROVIDER: bool(CANBOSO_API_KEY),
        GPT_CHEAP_PROVIDER: bool(GPT_CHEAP_API_KEY),
        SHOP_CRON_PROVIDER: bool(SHOP_CRON_API_KEY),
        UPIBOT_PROVIDER: bool(UPIBOT_API_KEY),
        CGPT_ACTIVE_PROVIDER: bool(CGPT_ACTIVE_API_KEY),
    }
    events: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    checked = 0

    for provider in sorted(SUPPORTED_PROVIDERS):
        if not configured[provider]:
            continue
        try:
            live_catalog = catalog(provider)
        except (ResellerApiError, ValueError) as exc:
            errors.append({"provider": provider, "error": str(exc)})
            continue

        for product in live_catalog["products"]:
            if not product.get("enabled") or not product.get("local_offer_id"):
                continue
            checked += 1
            stock = max(0, int(product.get("stock") or 0))
            previous = db.observe_reseller_stock(provider, product["id"], stock)
            # The first successful poll establishes a baseline and must not spam
            # customers with stock that was already available.
            if previous is None or stock <= previous:
                continue
            events.append({
                "provider": provider,
                "product_id": product["id"],
                "offer_id": int(product["local_offer_id"]),
                "previous_stock": previous,
                "stock": stock,
                "added": stock - previous,
            })

    return {
        "ok": not errors,
        "checked": checked,
        "events": events,
        "errors": errors,
    }


def detect_supplier_price_changes() -> dict[str, Any]:
    """Refresh API prices while preserving each configured profit amount."""
    configured = {
        PROVIDER: bool(MAILREADER_API_KEY),
        SHAMEKH_PROVIDER: bool(SHAMEKH_API_KEY),
        KAKAO_PROVIDER: bool(KAKAO_API_KEY),
        VEX_PROVIDER: bool(VEX_API_KEY),
        NASTELE_PROVIDER: bool(NASTELE_API_KEY),
        CANBOSO_PROVIDER: bool(CANBOSO_API_KEY),
        GPT_CHEAP_PROVIDER: bool(GPT_CHEAP_API_KEY),
        SHOP_CRON_PROVIDER: bool(SHOP_CRON_API_KEY),
        UPIBOT_PROVIDER: bool(UPIBOT_API_KEY),
        CGPT_ACTIVE_PROVIDER: bool(CGPT_ACTIVE_API_KEY),
    }
    changes: list[dict[str, Any]] = []
    flash_sales: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    checked = 0

    for provider in sorted(SUPPORTED_PROVIDERS):
        if not configured[provider]:
            continue
        try:
            live_catalog = catalog(provider)
        except (ResellerApiError, ValueError) as exc:
            errors.append({"provider": provider, "error": str(exc)})
            continue
        for product in live_catalog["products"]:
            if not product.get("enabled") or not product.get("local_offer_id"):
                continue
            checked += 1
            change = db.sync_reseller_supplier_price(
                provider, product["id"], product["wholesale_price"],
            )
            if not change:
                continue
            change.update({"provider": provider, "product_id": product["id"]})
            changes.append(change)
            if change["decreased"]:
                flash_sales.append(change)

    return {
        "ok": not errors,
        "checked": checked,
        "changes": changes,
        "flash_sales": flash_sales,
        "errors": errors,
    }


def save_product(
    product_id: str,
    *,
    name: str,
    wholesale_price: float,
    currency: str,
    retail_price: float,
    enabled: bool,
) -> dict[str, Any]:
    """Validate and save one product's resale settings."""
    if not str(product_id).strip():
        raise ValueError("Produit fournisseur invalide.")
    wholesale_price = max(0.0, float(wholesale_price))
    retail_price = float(retail_price)
    if retail_price < 0:
        raise ValueError("Le prix client ne peut pas être négatif.")
    if enabled and retail_price <= wholesale_price:
        raise ValueError("Le prix client doit être supérieur au prix grossiste.")
    return db.save_reseller_product_config(
        PROVIDER,
        str(product_id),
        name=name,
        wholesale_price=wholesale_price,
        currency=currency,
        retail_price=retail_price,
        enabled=enabled,
    )


def save_catalog_product(
    product_id: str,
    *,
    provider: str = PROVIDER,
    retail_price: float,
    enabled: bool,
    service_id: int | None = None,
    new_service_name: str = "",
    service_emoji: str = "📦",
    display_name: str = "",
    description: str = "",
    warranty: str = "Produit API MailReader",
    period_days: int = 30,
    warranty_days: int = 0,
    period_value: int | None = None,
    period_unit: str = "days",
    warranty_value: int | None = None,
    warranty_unit: str = "days",
    delivery_delay: str = "Instantané après confirmation",
    sort_order: int = 0,
    low_stock_threshold: int = 5,
) -> dict[str, Any]:
    """Publish one live supplier product into the bot's native catalog."""
    provider = str(provider or PROVIDER).lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Fournisseur API inconnu.")
    product = next(
        (item for item in catalog(provider)["products"] if item["id"] == str(product_id)),
        None,
    )
    if not product:
        raise ValueError("Ce produit n’est plus disponible chez le fournisseur.")

    display_name = str(display_name or product["name"]).strip()[:120]
    description = str(description or product.get("description") or "").strip()[:1000]
    default_warranty = {
        SHAMEKH_PROVIDER: "Produit API Shamekh’s bot",
        KAKAO_PROVIDER: "Produit API Kakao Shop",
        VEX_PROVIDER: "Produit API VEX Reseller",
        NASTELE_PROVIDER: "Produit API NasTele",
        CANBOSO_PROVIDER: "Produit API Piggy AI",
        GPT_CHEAP_PROVIDER: "Produit API GPT Cheap",
        SHOP_CRON_PROVIDER: "Produit API Shop Cron",
        UPIBOT_PROVIDER: "Produit API UPIBot Shop",
        CGPT_ACTIVE_PROVIDER: "Produit API Rich AI Store",
    }.get(provider, "Produit API MailReader")
    warranty = str(warranty or default_warranty).strip()[:250]
    delivery_delay = str(delivery_delay or "Instantané après confirmation").strip()[:120]
    service_emoji = str(service_emoji or "📦").strip()[:12]
    low_stock_threshold = max(0, int(low_stock_threshold or 0))
    sort_order = max(0, int(sort_order or 0))
    retail_price = float(retail_price)
    if enabled and retail_price <= float(product["wholesale_price"]):
        raise ValueError("Le prix client doit être supérieur au prix grossiste.")

    existing = next(
        (
            row for row in db.list_reseller_product_configs(provider)
            if row["product_id"] == product["id"]
        ),
        {},
    )
    if new_service_name.strip():
        normalized_name = new_service_name.strip()[:80]
        matching_service = next(
            (
                row for row in db.list_services(active_only=True)
                if str(row.get("name") or "").casefold() == normalized_name.casefold()
            ),
            None,
        )
        service_id = (
            matching_service["id"]
            if matching_service
            else db.add_service(normalized_name, service_emoji)
        )
    elif service_id is None:
        service_id = existing.get("service_id")
    service = db.get_service(int(service_id)) if service_id is not None else None
    if not service:
        raise ValueError("Choisissez un service existant ou créez-en un nouveau.")

    if service_emoji and service_id is not None:
        db.update_service(int(service_id), emoji=service_emoji)

    local_offer_id = existing.get("local_offer_id")
    local_offer = db.get_offer(int(local_offer_id)) if local_offer_id else None
    if local_offer:
        db.update_offer(
            local_offer["id"],
            name=display_name,
            price=retail_price,
            stock=int(product["stock"]),
            active=1 if enabled else 0,
            description=description,
            note=warranty,
            currency=product["currency"],
            sort_order=sort_order,
            auto_delivery=not bool(product.get("manual_delivery")),
            low_stock_threshold=low_stock_threshold,
            delivery_delay=delivery_delay,
            # ``service_emoji`` is a regular Unicode emoji.  Telegram's
            # custom_emoji_id field only accepts a Premium emoji identifier.
            # Preserve any separately configured Premium icon on updates.
            custom_emoji_id=None,
            unlimited_stock=bool(product.get("unlimited_stock")),
            manual_stock=False,
            supplier_provider=provider,
            supplier_product_id=product["id"],
            period_days=period_days,
            warranty_days=warranty_days,
            period_value=period_value,
            period_unit=period_unit,
            warranty_value=warranty_value,
            warranty_unit=warranty_unit,
        )
        if int(local_offer.get("service_id")) != int(service_id):
            db.get_conn().offers.update_one(
                {"id": local_offer["id"]},
                {"$set": {"service_id": int(service_id)}},
            )
        local_offer_id = local_offer["id"]
    else:
        local_offer_id = db.add_offer(
            int(service_id),
            display_name,
            retail_price,
            int(product["stock"]),
            note=warranty,
            description=description,
            currency=product["currency"],
            auto_delivery=not bool(product.get("manual_delivery")),
            low_stock_threshold=low_stock_threshold,
            delivery_delay=delivery_delay,
            custom_emoji_id="",
            unlimited_stock=bool(product.get("unlimited_stock")),
            manual_stock=False,
            supplier_provider=provider,
            supplier_product_id=product["id"],
            period_days=period_days,
            warranty_days=warranty_days,
            period_value=period_value,
            period_unit=period_unit,
            warranty_value=warranty_value,
            warranty_unit=warranty_unit,
        )
        db.update_offer(local_offer_id, sort_order=sort_order)

    return db.save_reseller_product_config(
        provider,
        product["id"],
        name=product["name"],
        wholesale_price=product["wholesale_price"],
        currency=product["currency"],
        retail_price=retail_price,
        enabled=enabled,
        service_id=int(service_id),
        local_offer_id=int(local_offer_id),
        display_name=display_name,
        service_name=service.get("name") or "",
        service_emoji=service.get("emoji") or service_emoji,
        description=description,
        warranty=warranty,
        period_days=period_days,
        warranty_days=warranty_days,
        period_value=period_value,
        period_unit=period_unit,
        warranty_value=warranty_value,
        warranty_unit=warranty_unit,
        delivery_delay=delivery_delay,
        sort_order=sort_order,
        low_stock_threshold=low_stock_threshold,
    )


def _delivery_items(payload: dict[str, Any]) -> list[str]:
    """Extract delivery strings from documented and common wrapped responses."""
    candidates: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = [payload]
    seen: set[int] = set()
    while queue:
        candidate = queue.pop(0)
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        candidates.append(candidate)
        for key in ("order", "data", "result", "response", "payload", "delivery"):
            value = candidate.get(key)
            if isinstance(value, dict):
                queue.append(value)
    raw_items: Any = None
    for candidate in candidates:
        for key in (
            "delivery",
            "delivery_items",
            "delivered_keys",
            "delivered_codes",
            "deliveredAccounts",
            "delivered_accounts",
            "accounts",
            "items",
            "credentials",
            "products",
            "data",
        ):
            value = candidate.get(key)
            if isinstance(value, list):
                raw_items = value
                break
            if isinstance(value, dict) and key not in {"data", "delivery"}:
                raw_items = [value]
                break
            if isinstance(value, str) and value.strip():
                raw_items = [value]
                break
        if raw_items is not None:
            break
    if raw_items is None:
        return []
    items: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            if isinstance(item.get("accounts"), list):
                for acc in item["accounts"]:
                    if isinstance(acc, str) and acc.strip():
                        items.append(acc.strip())
                    elif isinstance(acc, dict):
                        acc_val = acc.get("content") or acc.get("value") or acc.get("account") or ""
                        if acc_val:
                            items.append(str(acc_val).strip())
                        else:
                            items.append(json.dumps(acc, ensure_ascii=False, separators=(",", ":")))
                continue
            direct = (
                item.get("content")
                or item.get("value")
                or item.get("credentials")
                or item.get("account")
                or item.get("account_data")
                or item.get("delivery")
                or ""
            )
            value = str(direct).strip() if not isinstance(direct, dict) else ""
            if not value:
                credential_values = [
                    str(item[key]).strip()
                    for key in (
                        "email", "username", "user", "login", "password", "pass",
                        "verifyEmail", "url", "link", "recovery_url",
                        "recoveryUrl", "recovery", "expiryText", "otherInfo",
                    )
                    if item.get(key) is not None and str(item[key]).strip()
                ]
                value = ":".join(credential_values)
            if not value:
                value = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        else:
            value = str(item).strip()
        if value:
            items.append(value)
    return items


def fulfill_paid_order(order_id: int) -> list[str] | None:
    """Purchase and persist a paid reseller order with idempotent supplier billing."""
    conn = db.get_conn()
    order = conn.orders.find_one({"id": int(order_id)})
    if not order:
        return None
    offer = conn.offers.find_one({"id": order.get("offer_id")})
    provider = str((offer or {}).get("supplier_provider") or "")
    if not offer or provider not in SUPPORTED_PROVIDERS:
        return None

    external_order_id = f"BM-{int(order_id)}"
    existing = conn.reseller_fulfillments.find_one({
        "provider": provider,
        "external_order_id": external_order_id,
    })
    cipher = db._fernet()
    if existing and existing.get("status") == "completed":
        return [
            cipher.decrypt(value.encode()).decode()
            for value in existing.get("encrypted_items", [])
        ]
    if existing:
        raise ResellerApiError(
            "Cette commande fournisseur existe déjà et nécessite une vérification "
            "avant toute nouvelle tentative. Aucun second achat API n’a été envoyé."
        )
    if order.get("status") not in {"paid", "payment_confirmed"}:
        return None

    supplier_idempotency_key = (
        str(uuid.uuid4()) if provider == CGPT_ACTIVE_PROVIDER else external_order_id
    )
    try:
        conn.reseller_fulfillments.insert_one({
            "provider": provider,
            "external_order_id": external_order_id,
            "order_id": int(order_id),
            "supplier_product_id": str(offer["supplier_product_id"]),
            "idempotency_key": supplier_idempotency_key,
            "status": "purchasing",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        })
    except DuplicateKeyError as exc:
        raise ResellerApiError(
            "Une commande fournisseur existe déjà. Aucun second achat API n’a été envoyé."
        ) from exc

    try:
        if provider == SHAMEKH_PROVIDER:
            response = _shamekh_request_json(
                "/api/buy",
                method="POST",
                body={
                    "product_id": (
                        int(str(offer["supplier_product_id"]))
                        if str(offer["supplier_product_id"]).isdigit()
                        else str(offer["supplier_product_id"])
                    ),
                    "quantity": int(order.get("qty") or 1),
                },
            )
        elif provider == KAKAO_PROVIDER:
            response = _kakao_request_json(
                "/api/purchase",
                method="POST",
                body={
                    "product_id": str(offer["supplier_product_id"]),
                    "quantity": int(order.get("qty") or 1),
                    "external_order_id": external_order_id,
                },
            )
        elif provider == VEX_PROVIDER:
            response = _vex_request_json(
                "?action=order",
                method="POST",
                body={
                    "product_id": str(offer["supplier_product_id"]),
                    "quantity": int(order.get("qty") or 1),
                    "external_order_id": external_order_id,
                },
            )
        elif provider == NASTELE_PROVIDER:
            response = _nastele_request_json(
                "/api/partner/orders",
                method="POST",
                body={
                    "productId": (
                        int(str(offer["supplier_product_id"]))
                        if str(offer["supplier_product_id"]).isdigit()
                        else str(offer["supplier_product_id"])
                    ),
                    "qty": int(order.get("qty") or 1),
                },
            )
        elif provider in CANBOSO_PROVIDERS:
            response = _canboso_request_json(
                "/purchase",
                method="POST",
                body={
                    "product_id": str(offer["supplier_product_id"]),
                    "quantity": int(order.get("qty") or 1),
                },
                idempotency_key=external_order_id,
                **({"provider": provider} if provider != CANBOSO_PROVIDER else {}),
            )
        elif provider == UPIBOT_PROVIDER:
            response = _upibot_request_json(
                "/orders",
                method="POST",
                body={
                    "product_id": int(str(offer["supplier_product_id"])),
                    "quantity": int(order.get("qty") or 1),
                    "customer_name": f"telegram_user_{int(order['user_id'])}",
                    "idempotency_key": external_order_id,
                },
            )
        elif provider == CGPT_ACTIVE_PROVIDER:
            response = _cgpt_active_request_json(
                "/v1/orders",
                method="POST",
                body={
                    "product_id": int(str(offer["supplier_product_id"])),
                    "quantity": int(order.get("qty") or 1),
                },
                idempotency_key=supplier_idempotency_key,
            )
        else:
            _mailreader_preflight_purchase(offer, int(order.get("qty") or 1))
            response = _request_json(
                "/api/reseller?action=order",
                method="POST",
                body={
                    "product_id": str(offer["supplier_product_id"]),
                    "quantity": int(order.get("qty") or 1),
                    "external_order_id": external_order_id,
                },
            )
    except ResellerOrderNotCreatedError:
        conn.reseller_fulfillments.update_one(
            {"provider": provider, "external_order_id": external_order_id},
            {"$set": {"status": "not_created", "updated_at": int(time.time())}},
        )
        raise
    except ResellerApiError:
        conn.reseller_fulfillments.update_one(
            {"provider": provider, "external_order_id": external_order_id},
            {"$set": {"status": "review_required", "updated_at": int(time.time())}},
        )
        raise
    order_payload = response.get("order")
    data_payload = response.get("data") if isinstance(response.get("data"), dict) else {}
    supplier_order_id = (
        response.get("transaction_id")
        or response.get("orderCode")
        or response.get("order_id")
        or response.get("orderId")
        or response.get("id")
        or (data_payload.get("orderId") if isinstance(data_payload, dict) else "")
        or (data_payload.get("id") if isinstance(data_payload, dict) else "")
        or (order_payload.get("orderCode") if isinstance(order_payload, dict) else "")
        or (order_payload.get("id") if isinstance(order_payload, dict) else "")
        or ""
    )
    items = _delivery_items(response)
    if provider == CGPT_ACTIVE_PROVIDER and items and response.get("delivery_instructions"):
        items[-1] = (
            f"{items[-1]}\n\nHow to redeem:\n"
            f"{str(response['delivery_instructions']).strip()}"
        )
    if len(items) < int(order.get("qty") or 1):
        conn.reseller_fulfillments.update_one(
            {"provider": provider, "external_order_id": external_order_id},
            {"$set": {
                "status": "delivery_pending",
                "supplier_order_id": str(supplier_order_id),
                "updated_at": int(time.time()),
            }},
        )
        raise ResellerApiError(
            "La commande fournisseur a été créée mais la livraison n’est pas encore disponible."
        )

    encrypted_items = [cipher.encrypt(item.encode()).decode() for item in items]
    now = int(time.time())
    conn.reseller_fulfillments.update_one(
        {"provider": provider, "external_order_id": external_order_id},
        {
            "$set": {
                "order_id": int(order_id),
                "supplier_product_id": str(offer["supplier_product_id"]),
                "status": "completed",
                "encrypted_items": encrypted_items,
                "supplier_order_id": str(supplier_order_id),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    for index, encrypted in enumerate(encrypted_items):
        conn.inventory.update_one(
            {
                "source_provider": provider,
                "source_external_order_id": external_order_id,
                "source_item_index": index,
            },
            {
                "$setOnInsert": {
                    "id": db._next_id("inventory"),
                    "offer_id": offer["id"],
                    "payload": encrypted,
                    "masked_preview": "Produit API livré",
                    "status": "delivered",
                    "delivered_order_id": int(order_id),
                    "delivered_at": now,
                    "created_at": now,
                }
            },
            upsert=True,
        )
    conn.orders.update_one(
        {"id": int(order_id), "status": {"$in": ["paid", "payment_confirmed"]}},
        {
            "$set": {
                "status": "delivered",
                "delivery_text": "[encrypted reseller delivery]",
                "supplier_external_order_id": external_order_id,
                "delivered_at": now,
                "updated_at": now,
            }
        },
    )
    db.audit_event(
        "order.reseller_delivered",
        details={
            "order_id": int(order_id),
            "provider": provider,
            "items_count": len(items),
        },
    )
    return items
