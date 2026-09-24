"""Read-only Binance wallet data for the authenticated admin dashboard."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import BINANCE_API_BASES, BINANCE_API_KEY, BINANCE_API_SECRET


class BinanceDashboardError(RuntimeError):
    """Safe error raised when Binance wallet data cannot be loaded."""


_DEPOSIT_STATUS = {
    0: "pending",
    1: "completed",
    6: "credited_locked",
    7: "wrong_deposit",
    8: "awaiting_confirmation",
}
_WITHDRAWAL_STATUS = {
    0: "email_sent",
    2: "awaiting_approval",
    3: "rejected",
    4: "processing",
    6: "completed",
}


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _number(value) -> float:
    return float(_decimal(value))


def _masked(value: object) -> str:
    text = str(value or "").strip()
    if len(text) <= 12:
        return text
    return f"{text[:6]}…{text[-6:]}"


def _binance_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = str(payload.get("msg") or "").strip()
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        message = ""
    return message[:300] or f"Binance HTTP {exc.code}"


def _signed_request(path: str, params: dict | None = None, *, method: str = "GET"):
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise BinanceDashboardError("Clés Binance non configurées.")

    values = dict(params or {})
    values["recvWindow"] = 5000
    values["timestamp"] = int(time.time() * 1000)
    query = urlencode(values)
    signature = hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed = f"{query}&signature={signature}"
    failures: list[str] = []

    for base_url in BINANCE_API_BASES:
        url = f"{base_url}{path}"
        data = None
        if method == "POST":
            data = signed.encode("utf-8")
        else:
            url = f"{url}?{signed}"
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "X-MBX-APIKEY": BINANCE_API_KEY,
                "Accept": "application/json",
                **({"Content-Type": "application/x-www-form-urlencoded"} if data else {}),
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8")), base_url
        except HTTPError as exc:
            message = _binance_message(exc)
            failures.append(message)
            if exc.code not in {418, 429, 451, 500, 502, 503, 504}:
                raise BinanceDashboardError(message) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(type(exc).__name__)

    detail = failures[-1] if failures else "aucun endpoint disponible"
    raise BinanceDashboardError(f"Binance est temporairement indisponible ({detail}).")


def _balances() -> tuple[list[dict], str]:
    payload, base_url = _signed_request(
        "/sapi/v3/asset/getUserAsset", {"needBtcValuation": "true"}, method="POST"
    )
    if not isinstance(payload, list):
        raise BinanceDashboardError("Réponse de solde Binance invalide.")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        free = _decimal(item.get("free"))
        locked = _decimal(item.get("locked"))
        total = free + locked
        if total <= 0:
            continue
        rows.append({
            "asset": str(item.get("asset") or "").upper(),
            "free": float(free),
            "locked": float(locked),
            "total": float(total),
            "btc_value": _number(item.get("btcValuation")),
        })
    rows.sort(key=lambda item: (item["btc_value"], item["total"]), reverse=True)
    return rows, base_url


def _deposit_rows(start_ms: int, end_ms: int) -> list[dict]:
    payload, _ = _signed_request(
        "/sapi/v1/capital/deposit/hisrec",
        {"startTime": start_ms, "endTime": end_ms, "limit": 1000},
    )
    return payload if isinstance(payload, list) else []


def _withdrawal_rows(start_ms: int, end_ms: int) -> list[dict]:
    payload, _ = _signed_request(
        "/sapi/v1/capital/withdraw/history",
        {"startTime": start_ms, "endTime": end_ms, "limit": 1000},
    )
    return payload if isinstance(payload, list) else []


def _transaction(item: dict, kind: str) -> dict:
    is_deposit = kind == "deposit"
    status_value = int(item.get("status") or 0)
    timestamp = item.get("insertTime") if is_deposit else item.get("applyTime")
    return {
        "id": str(item.get("id") or item.get("txId") or ""),
        "type": kind,
        "asset": str(item.get("coin") or "").upper(),
        "amount": _number(item.get("amount")),
        "fee": 0.0 if is_deposit else _number(item.get("transactionFee")),
        "network": str(item.get("network") or ""),
        "status": (_DEPOSIT_STATUS if is_deposit else _WITHDRAWAL_STATUS).get(
            status_value, "unknown"
        ),
        "status_code": status_value,
        "address": _masked(item.get("address")),
        "txid": str(item.get("txId") or "").strip(),
        "timestamp": timestamp,
    }


def snapshot(*, days: int = 90) -> dict:
    """Return balances, recent transfers, and API permission safety state."""
    days = max(1, min(int(days), 90))
    balances, endpoint = _balances()
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    warnings: list[str] = []

    try:
        status_payload, _ = _signed_request("/sapi/v1/account/status")
        account_status = str(status_payload.get("data") or "Unknown")
    except BinanceDashboardError as exc:
        account_status = "Unknown"
        warnings.append(str(exc))

    try:
        restrictions, _ = _signed_request("/sapi/v1/account/apiRestrictions")
        permissions = {
            "read": bool(restrictions.get("enableReading")),
            "withdrawals": bool(restrictions.get("enableWithdrawals")),
            "trading": bool(restrictions.get("enableSpotAndMarginTrading")),
            "internal_transfer": bool(restrictions.get("enableInternalTransfer")),
            "ip_restricted": bool(restrictions.get("ipRestrict")),
        }
    except BinanceDashboardError as exc:
        permissions = None
        warnings.append(str(exc))

    transactions: list[dict] = []
    for kind, loader in (("deposit", _deposit_rows), ("withdrawal", _withdrawal_rows)):
        try:
            transactions.extend(_transaction(item, kind) for item in loader(start_ms, now_ms))
        except BinanceDashboardError as exc:
            warnings.append(f"Historique {kind} indisponible: {exc}")

    transactions.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return {
        "ok": True,
        "read_only": True,
        "account_status": account_status,
        "endpoint": endpoint,
        "fetched_at": int(time.time()),
        "period_days": days,
        "permissions": permissions,
        "balances": balances,
        "transactions": transactions,
        "summary": {
            "assets": len(balances),
            "deposits": sum(item["type"] == "deposit" for item in transactions),
            "withdrawals": sum(item["type"] == "withdrawal" for item in transactions),
            "btc_value": sum(item["btc_value"] for item in balances),
        },
        "warnings": list(dict.fromkeys(warnings)),
    }
