"""Verify native SOL deposits and obtain a live SOL/USDT conversion quote."""
from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

from config import (
    SOLANA_MIN_CONFIRMATIONS,
    SOLANA_MIN_DEPOSIT,
    SOLANA_PRICE_API_URL,
    SOLANA_RPC_URL,
)

LAMPORTS_PER_SOL = Decimal("1000000000")
_SIGNATURE_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,100}")


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    request = Request(url, data=data, headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "BlackMarketBot/1.0 solana-verifier"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _rpc(method: str, params: list):
    payload = _request_json(SOLANA_RPC_URL, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if payload.get("error"):
        raise RuntimeError(payload["error"].get("message") or "Solana RPC error")
    return payload.get("result")


def _result(status: str, code: str, reason: str, **values):
    return {"status": status, "code": code, "reason": reason, **values}


def verify_solana_deposit(signature: str, destination: str) -> dict:
    signature = str(signature or "").strip()
    destination = str(destination or "").strip()
    if not _SIGNATURE_RE.fullmatch(signature):
        return _result("failed", "invalid_format", "Invalid Solana transaction signature.")
    if not _SIGNATURE_RE.fullmatch(destination):
        return _result("failed", "not_configured", "Solana receiving address is not configured.")
    try:
        status = (_rpc("getSignatureStatuses", [[signature]]) or {}).get("value", [None])[0]
        if not status:
            return _result("pending", "not_found", "Solana transaction was not found yet.")
        if status.get("err"):
            return _result("failed", "transaction_failed", "The Solana transaction failed on-chain.")
        confirmations = status.get("confirmations")
        if status.get("confirmationStatus") not in {"confirmed", "finalized"}:
            return _result("pending", "confirming", "Waiting for Solana confirmations.", confirmations=confirmations or 0)
        if confirmations is not None and confirmations < SOLANA_MIN_CONFIRMATIONS:
            return _result("pending", "confirming", "Waiting for Solana confirmations.", confirmations=confirmations)

        transaction = _rpc("getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
        if not transaction:
            return _result("pending", "not_indexed", "Solana transaction details are not indexed yet.")
        lamports = 0
        message = ((transaction.get("transaction") or {}).get("message") or {})
        for instruction in message.get("instructions") or []:
            parsed = instruction.get("parsed") or {}
            info = parsed.get("info") or {}
            if instruction.get("program") == "system" and parsed.get("type") == "transfer" and info.get("destination") == destination:
                lamports += int(info.get("lamports") or 0)
        amount = Decimal(lamports) / LAMPORTS_PER_SOL
        minimum = Decimal(str(SOLANA_MIN_DEPOSIT))
        if amount <= 0:
            return _result("failed", "wrong_recipient", "SOL was not sent to the configured address.")
        if amount < minimum:
            return _result("failed", "minimum", f"Minimum Solana deposit is {minimum} SOL.", sol_amount=float(amount))
        return _result("confirmed", "confirmed", "Solana deposit confirmed.", signature=signature, network="solana", sol_amount=float(amount), confirmations=confirmations or SOLANA_MIN_CONFIRMATIONS)
    except Exception as exc:
        return _result("pending", "api_unavailable", f"Solana RPC unavailable: {exc}")


def find_solana_deposit_since(destination: str, since: int) -> dict:
    """Find the newest finalized native SOL transfer after a customer started checking."""
    try:
        entries = _rpc("getSignaturesForAddress", [destination, {"limit": 50, "commitment": "finalized"}]) or []
        for entry in entries:
            signature = entry.get("signature")
            if entry.get("err") or int(entry.get("blockTime") or 0) < int(since):
                continue
            result = verify_solana_deposit(signature, destination)
            if result.get("status") == "confirmed":
                return result
        return _result("pending", "not_found", "No new Solana deposit was found yet.")
    except Exception as exc:
        return _result("pending", "api_unavailable", f"Solana RPC unavailable: {exc}")


def get_recent_balance_increase(
    destination: str, baseline_lamports: int, window_seconds: int,
) -> dict:
    """Return the wallet balance increase when a confirmed inbound transfer is recent."""
    try:
        current_lamports = int((_rpc("getBalance", [destination, {"commitment": "finalized"}]) or {}).get("value") or 0)
        delta_lamports = current_lamports - int(baseline_lamports)
        if delta_lamports <= 0:
            return _result("pending", "no_increase", "No new SOL balance increase was found.", current_lamports=current_lamports)
        cutoff = int(time.time()) - int(window_seconds)
        entries = _rpc("getSignaturesForAddress", [destination, {"limit": 50, "commitment": "finalized"}]) or []
        for entry in entries:
            signature = entry.get("signature")
            if entry.get("err") or int(entry.get("blockTime") or 0) < cutoff:
                continue
            inbound = verify_solana_deposit(signature, destination)
            if inbound.get("status") == "confirmed":
                return _result(
                    "confirmed", "confirmed", "Recent SOL balance increase confirmed.",
                    signature=signature,
                    sol_amount=float(Decimal(delta_lamports) / LAMPORTS_PER_SOL),
                    delta_lamports=delta_lamports,
                    current_lamports=current_lamports,
                    received_at=int(entry.get("blockTime") or 0),
                )
        return _result("failed", "expired", "The SOL balance increased, but no incoming payment was found within the last hour.")
    except Exception as exc:
        return _result("pending", "api_unavailable", f"Solana RPC unavailable: {exc}")


def fetch_sol_usdt_quote() -> dict:
    try:
        payload = _request_json(SOLANA_PRICE_API_URL)
        price = Decimal(str(payload.get("price") or "0"))
        if not price.is_finite() or price <= 0:
            raise InvalidOperation("invalid SOL price")
        return _result("confirmed", "confirmed", "SOL/USDT quote received.", price=float(price), source="Binance SOL/USDT live price")
    except Exception as exc:
        return _result("pending", "quote_unavailable", f"SOL/USDT quote unavailable: {exc}")
