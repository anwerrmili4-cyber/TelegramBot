"""Customer wallet top-ups and atomic balance usage."""
from __future__ import annotations

import re
import time
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import database as db
from config import USDT_EVM_ADDRESS
from onchain_verifier import verify_onchain_usdt
from payment_verifier import verify_bybit_incoming_transfer, verify_incoming_transfer
from config import (
    SOLANA_CHECK_WINDOW_SECONDS,
    SOLANA_DEPOSIT_ADDRESS,
    SOLANA_INITIAL_BALANCE_LAMPORTS,
)
from solana_verifier import fetch_sol_usdt_quote, get_recent_balance_increase, verify_solana_deposit


def balance_cents(user_id: int) -> int:
    wallet = db.get_conn().wallets.find_one({"user_id": user_id}) or {}
    return max(0, int(wallet.get("balance_cents", 0)))


def claim_transfer(user_id: int, txid: str, provider: str = "binance") -> dict[str, Any]:
    txid = (txid or "").strip()
    provider = str(provider or "binance").strip().lower()
    if provider not in {"binance", "bybit"}:
        return {"status": "failed", "code": "invalid_provider", "message": "Fournisseur invalide."}
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", txid):
        return {"status": "failed", "code": "invalid_format", "message": "TXID invalide."}
    conn = db.get_conn()
    if conn.wallet_topups.find_one({"txid": txid}):
        return {"status": "failed", "code": "already_used", "message": "Ce TXID a déjà été crédité."}
    verifier = (
        verify_bybit_incoming_transfer
        if provider == "bybit"
        else verify_incoming_transfer
    )
    verification = verifier(txid, minimum_amount=1)
    if verification["status"] != "confirmed":
        return {
            "status": verification["status"],
            "code": verification.get("code"),
            "message": verification.get("reason"),
        }
    amount_cents = round(float(verification["amount"]) * 100)
    try:
        conn.wallet_topups.insert_one({
            "txid": txid,
            "user_id": user_id,
            "amount_cents": amount_cents,
            "currency": verification["currency"],
            "provider": provider,
            "created_at": int(time.time()),
        })
    except DuplicateKeyError:
        return {"status": "failed", "code": "already_used", "message": "Ce TXID a déjà été crédité."}
    conn.wallets.update_one(
        {"user_id": user_id},
        {"$inc": {"balance_cents": amount_cents}},
        upsert=True,
    )
    db.audit_event("wallet.topup_confirmed", actor_id=user_id, details={"txid": txid, "amount_cents": amount_cents, "provider": provider})
    return {"status": "confirmed", "amount": amount_cents / 100, "balance": balance_cents(user_id) / 100}


def submit_onchain_topup(
    user_id: int, txid: str, amount: float, network: str,
    created_at: int | None = None,
) -> dict[str, Any]:
    """Automatically verify and credit a BSC/Polygon wallet top-up."""
    txid = (txid or "").strip()
    network = str(network or "").lower()
    if network not in {"bsc", "polygon"}:
        return {"status": "failed", "code": "invalid_network", "message": "Réseau invalide."}
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", txid):
        return {"status": "failed", "code": "invalid_format", "message": "TXID invalide."}
    amount_cents = round(float(amount) * 100)
    if amount_cents < 100:
        return {"status": "failed", "code": "minimum", "message": "Minimum: 1 USDT."}

    conn = db.get_conn()
    if conn.wallet_topups.find_one({"txid": txid}) or conn.orders.find_one({"txid": txid}):
        return {"status": "failed", "code": "already_used", "message": "TXID déjà utilisé."}

    verification = verify_onchain_usdt(
        txid, network, amount_cents / 100, USDT_EVM_ADDRESS,
        created_at,
    )
    if verification["status"] != "confirmed":
        return {
            "status": verification["status"],
            "code": verification.get("code"),
            "message": verification.get("reason"),
        }

    topup_id = db._next_id("wallet_topups")
    if not db.claim_onchain_transaction(
        txid, network, user_id, "wallet_topup", topup_id, amount_cents / 100,
    ):
        return {"status": "failed", "code": "already_used", "message": "TXID déjà utilisé."}
    try:
        conn.wallet_topups.insert_one({
            "id": topup_id,
            "txid": txid,
            "user_id": int(user_id),
            "amount_cents": amount_cents,
            "currency": "USDT",
            "network": network,
            "verification_method": "automatic_onchain",
            "status": "confirmed",
            "created_at": int(time.time()),
        })
    except DuplicateKeyError:
        return {
            "status": "failed",
            "code": "already_used",
            "message": "Ce TXID a déjà été soumis.",
        }
    conn.wallets.update_one(
        {"user_id": int(user_id)},
        {"$inc": {"balance_cents": amount_cents}},
        upsert=True,
    )
    balance = balance_cents(user_id) / 100
    db.audit_event(
        "wallet.topup_confirmed_onchain",
        actor_id=user_id,
        details={"topup_id": topup_id, "network": network, "amount_cents": amount_cents},
    )
    return {
        "status": "confirmed",
        "id": topup_id,
        "txid": txid,
        "amount": amount_cents / 100,
        "balance": balance,
        "network": network,
        "user_id": int(user_id),
    }


def convert_token_amount_to_usdt_cents(token_amount: float, usdt_rate: float) -> int:
    """Preserve the reusable token-to-USDT credit calculation for future networks."""
    amount_cents = round(float(token_amount) * float(usdt_rate) * 100)
    if amount_cents < 1:
        raise ValueError("Converted amount is below 0.01 USDT.")
    return amount_cents


def submit_solana_topup(user_id: int, signature: str) -> dict[str, Any]:
    """Verify native SOL, lock the live SOL/USDT quote, and credit once."""
    signature = str(signature or "").strip()
    conn = db.get_conn()
    if conn.wallet_topups.find_one({"txid": signature}) or conn.orders.find_one({"txid": signature}):
        return {"status": "failed", "code": "already_used", "message": "This transaction has already been credited."}
    verification = verify_solana_deposit(signature, SOLANA_DEPOSIT_ADDRESS)
    if verification["status"] != "confirmed":
        return {"status": verification["status"], "code": verification.get("code"), "message": verification.get("reason")}
    quote = fetch_sol_usdt_quote()
    if quote["status"] != "confirmed":
        return {"status": quote["status"], "code": quote.get("code"), "message": quote.get("reason")}
    sol_amount = float(verification["sol_amount"])
    rate = float(quote["price"])
    try:
        amount_cents = convert_token_amount_to_usdt_cents(sol_amount, rate)
    except ValueError as exc:
        return {"status": "failed", "code": "amount_too_small", "message": str(exc)}
    topup_id = db._next_id("wallet_topups")
    if not db.claim_onchain_transaction(signature, "solana", user_id, "wallet_topup", topup_id, amount_cents / 100):
        return {"status": "failed", "code": "already_used", "message": "This transaction has already been submitted."}
    try:
        conn.wallet_topups.insert_one({"id": topup_id, "txid": signature, "user_id": int(user_id), "amount_cents": amount_cents, "currency": "USDT", "source_currency": "SOL", "source_amount": sol_amount, "conversion_rate": rate, "quote_source": quote["source"], "quote_at": int(time.time()), "network": "solana", "confirmations": int(verification.get("confirmations") or 0), "verification_method": "automatic_solana_sol", "status": "confirmed", "created_at": int(time.time())})
    except DuplicateKeyError:
        return {"status": "failed", "code": "already_used", "message": "This transaction has already been submitted."}
    conn.wallets.update_one({"user_id": int(user_id)}, {"$inc": {"balance_cents": amount_cents}}, upsert=True)
    balance = balance_cents(user_id) / 100
    db.audit_event("wallet.topup_confirmed_solana", actor_id=user_id, details={"topup_id": topup_id, "txid": signature, "sol_amount": sol_amount, "sol_usdt_rate": rate, "amount_cents": amount_cents})
    return {"status": "confirmed", "id": topup_id, "txid": signature, "sol_amount": sol_amount, "rate": rate, "amount": amount_cents / 100, "balance": balance, "user_id": int(user_id)}


def submit_solana_scan(user_id: int, since: int) -> dict[str, Any]:
    conn = db.get_conn()
    previous = conn.wallet_topups.find_one(
        {"network": "solana", "balance_after_lamports": {"$exists": True}},
        sort=[("created_at", -1), ("_id", -1)],
    )
    baseline_lamports = int(
        (previous or {}).get("balance_after_lamports")
        or SOLANA_INITIAL_BALANCE_LAMPORTS
    )
    verification = get_recent_balance_increase(
        SOLANA_DEPOSIT_ADDRESS,
        baseline_lamports,
        SOLANA_CHECK_WINDOW_SECONDS,
    )
    if verification["status"] != "confirmed":
        return {"status": verification["status"], "code": verification.get("code"), "message": verification.get("reason")}
    signature = verification["signature"]
    if conn.wallet_topups.find_one({"txid": signature}) or conn.orders.find_one({"txid": signature}):
        return {"status": "failed", "code": "already_used", "message": "This payment has already been credited."}
    if conn.wallet_topups.find_one({"network": "solana", "balance_after_lamports": verification["current_lamports"]}):
        return {"status": "failed", "code": "already_used", "message": "This payment amount has already been credited."}
    quote = fetch_sol_usdt_quote()
    if quote["status"] != "confirmed":
        return {"status": quote["status"], "code": quote.get("code"), "message": quote.get("reason")}
    amount_cents = convert_token_amount_to_usdt_cents(verification["sol_amount"], quote["price"])
    topup_id = db._next_id("wallet_topups")
    if not db.claim_onchain_transaction(signature, "solana", user_id, "wallet_topup", topup_id, amount_cents / 100):
        return {"status": "failed", "code": "already_used", "message": "This payment has already been submitted."}
    try:
        conn.wallet_topups.insert_one({"id": topup_id, "txid": signature, "user_id": int(user_id), "amount_cents": amount_cents, "currency": "USDT", "source_currency": "SOL", "source_amount": verification["sol_amount"], "conversion_rate": quote["price"], "quote_source": quote["source"], "quote_at": int(time.time()), "network": "solana", "baseline_lamports": baseline_lamports, "balance_after_lamports": verification["current_lamports"], "received_at": verification.get("received_at"), "verification_method": "automatic_solana_balance_increase", "status": "confirmed", "created_at": int(time.time())})
    except DuplicateKeyError:
        return {"status": "failed", "code": "already_used", "message": "This payment has already been submitted."}
    conn.wallets.update_one({"user_id": int(user_id)}, {"$inc": {"balance_cents": amount_cents}}, upsert=True)
    return {"status": "confirmed", "id": topup_id, "txid": signature, "sol_amount": verification["sol_amount"], "rate": quote["price"], "quote_source": quote["source"], "quote_at": int(time.time()), "amount": amount_cents / 100, "balance": balance_cents(user_id) / 100, "user_id": int(user_id)}


def approve_onchain_topup(topup_id: int, admin_id: int) -> dict[str, Any] | None:
    """Atomically approve a pending top-up and credit its wallet once."""
    conn = db.get_conn()
    topup = conn.wallet_topups.find_one_and_update(
        {"id": int(topup_id), "status": "manual_review"},
        {"$set": {
            "status": "confirmed",
            "approved_by": int(admin_id),
            "approved_at": int(time.time()),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not topup:
        return None
    conn.wallets.update_one(
        {"user_id": topup["user_id"]},
        {"$inc": {"balance_cents": int(topup["amount_cents"])}},
        upsert=True,
    )
    topup["balance"] = balance_cents(topup["user_id"]) / 100
    db.audit_event(
        "wallet.topup_confirmed_manual",
        actor_id=admin_id,
        details={"topup_id": topup_id, "user_id": topup["user_id"]},
    )
    return topup


def reject_onchain_topup(topup_id: int, admin_id: int) -> dict[str, Any] | None:
    conn = db.get_conn()
    topup = conn.wallet_topups.find_one_and_update(
        {"id": int(topup_id), "status": "manual_review"},
        {"$set": {
            "status": "rejected",
            "rejected_by": int(admin_id),
            "rejected_at": int(time.time()),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if topup:
        db.audit_event(
            "wallet.topup_rejected",
            actor_id=admin_id,
            details={"topup_id": topup_id, "user_id": topup["user_id"]},
        )
    return topup


def credit_all_users(
    amount: float, operation_id: str, admin_id: int,
) -> dict[str, Any]:
    """Idempotently add the same wallet credit to every registered user."""
    amount_cents = round(float(amount) * 100)
    operation_id = str(operation_id or "").strip()
    if amount_cents < 1 or amount_cents > 1_000_000:
        raise ValueError("Le montant doit être compris entre 0,01 et 10 000 USDT.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,128}", operation_id):
        raise ValueError("Identifiant d’opération invalide.")

    conn = db.get_conn()
    operation = conn.bulk_wallet_credits.find_one({"operation_id": operation_id})
    if operation and int(operation.get("amount_cents") or 0) != amount_cents:
        raise ValueError("Cette opération existe avec un montant différent.")
    if not operation:
        try:
            conn.bulk_wallet_credits.insert_one({
                "operation_id": operation_id,
                "amount_cents": amount_cents,
                "admin_id": int(admin_id),
                "status": "processing",
                "created_at": int(time.time()),
            })
        except DuplicateKeyError:
            operation = conn.bulk_wallet_credits.find_one({"operation_id": operation_id})
            if not operation or int(operation.get("amount_cents") or 0) != amount_cents:
                raise ValueError("Conflit d’opération de crédit.") from None

    credited = 0
    already_credited = 0
    user_ids = conn.users.distinct("telegram_id", {"telegram_id": {"$ne": None}})
    for user_id in user_ids:
        try:
            result = conn.wallets.update_one(
                {
                    "user_id": int(user_id),
                    "bulk_credit_operations": {"$ne": operation_id},
                },
                {
                    "$inc": {"balance_cents": amount_cents},
                    "$addToSet": {"bulk_credit_operations": operation_id},
                },
                upsert=True,
            )
            if result.modified_count or result.upserted_id is not None:
                credited += 1
            else:
                already_credited += 1
        except DuplicateKeyError:
            already_credited += 1

    conn.bulk_wallet_credits.update_one(
        {"operation_id": operation_id},
        {"$set": {
            "status": "completed",
            "user_count": len(user_ids),
            "credited_count": credited,
            "completed_at": int(time.time()),
        }},
    )
    db.audit_event(
        "wallet.bulk_credit",
        actor_id=admin_id,
        details={
            "operation_id": operation_id,
            "amount_cents": amount_cents,
            "credited_count": credited,
            "user_count": len(user_ids),
        },
    )
    return {
        "operation_id": operation_id,
        "amount": amount_cents / 100,
        "user_count": len(user_ids),
        "credited_count": credited,
        "already_credited_count": already_credited,
    }


def adjust_balance(user_id: int, amount: float, admin_id: int, reason: str = "") -> dict[str, Any]:
    """Credit or debit one wallet atomically without allowing a negative balance."""
    user_id = int(user_id)
    amount_cents = round(float(amount) * 100)
    reason = str(reason or "").strip()[:500]
    if amount_cents == 0 or abs(amount_cents) > 1_000_000:
        raise ValueError("Le montant doit être compris entre -10 000 et 10 000 USDT, hors zéro.")

    conn = db.get_conn()
    if not conn.users.find_one({"telegram_id": user_id}, {"_id": 1}):
        raise ValueError("Utilisateur introuvable.")

    if amount_cents > 0:
        wallet = conn.wallets.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"balance_cents": amount_cents}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    else:
        wallet = conn.wallets.find_one_and_update(
            {"user_id": user_id, "balance_cents": {"$gte": abs(amount_cents)}},
            {"$inc": {"balance_cents": amount_cents}},
            return_document=ReturnDocument.AFTER,
        )
        if not wallet:
            raise ValueError("Solde insuffisant pour effectuer ce débit.")

    new_balance_cents = max(0, int(wallet.get("balance_cents", 0)))
    db.audit_event(
        "wallet.admin_adjustment",
        actor_id=admin_id,
        details={
            "user_id": user_id,
            "amount_cents": amount_cents,
            "balance_cents": new_balance_cents,
            "reason": reason,
        },
    )
    return {"user_id": user_id, "amount": amount_cents / 100, "balance": new_balance_cents / 100}


def apply_balance(user_id: int, amount: float) -> float:
    requested = max(0, round(amount * 100))
    if not requested:
        return 0.0
    conn = db.get_conn()
    available = balance_cents(user_id)
    used = min(available, requested)
    if not used:
        return 0.0
    result = conn.wallets.update_one(
        {"user_id": user_id, "balance_cents": {"$gte": used}},
        {"$inc": {"balance_cents": -used}},
    )
    return used / 100 if result.modified_count else 0.0


def refund_balance(user_id: int, amount: float, order_id: int) -> bool:
    cents = round(max(0, amount) * 100)
    if not cents:
        return False
    conn = db.get_conn()
    result = conn.orders.update_one(
        {"id": order_id, "wallet_refunded": {"$ne": True}},
        {"$set": {"wallet_refunded": True}},
    )
    if result.modified_count != 1:
        return False
    conn.wallets.update_one({"user_id": user_id}, {"$inc": {"balance_cents": cents}}, upsert=True)
    return True
