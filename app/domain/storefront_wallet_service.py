"""Dinar wallet for storefront accounts, topped up by admin-verified receipts.

The Telegram bot keeps its own USDT wallet keyed by Telegram id; this one is
keyed by storefront customer id and counts millimes. Every balance change is a
single conditional ``$inc`` followed by a ledger entry, so the balance can
never go negative and every dinar can be traced to a deposit, a purchase, a
refund or an admin adjustment.

Deposits never credit anything on their own: the customer declares the
amount, the transaction reference and a receipt screenshot, and an
administrator approves (possibly correcting the amount) or rejects it.
"""

from __future__ import annotations

import re
import time
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import database as db
from app.domain import email_service, site_settings_service, storefront_receipt_service

MIN_DEPOSIT_MILLIMES = 1_000
MAX_DEPOSIT_MILLIMES = 5_000_000
MAX_PENDING_DEPOSITS = 3
HISTORY_LIMIT = 50

DEPOSIT_PENDING = "pending"
DEPOSIT_APPROVED = "approved"
DEPOSIT_REJECTED = "rejected"

LEDGER_LABELS = {
    "deposit": "Recharge",
    "purchase": "Achat",
    "refund": "Remboursement",
    "adjustment": "Ajustement",
}


class WalletError(ValueError):
    """Validation error safe to show to the customer or the admin."""


def parse_amount(value: Any) -> int:
    """Read a dinar amount such as ``25``, ``25,5`` or ``25.500`` as millimes."""
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"\d{1,7}(\.\d{1,3})?", text):
        raise WalletError("Saisis un montant valide en dinars, par exemple 25,500.")
    whole, _, fraction = text.partition(".")
    return int(whole) * 1000 + int((fraction + "000")[:3])


def balance(customer_id: int) -> int:
    wallet = db.get_conn().storefront_wallets.find_one({"customer_id": int(customer_id)})
    return int(wallet.get("balance_millimes") or 0) if wallet else 0


def _ledger(customer_id: int, kind: str, amount: int, balance_after: int, reference: str, note: str) -> None:
    db.get_conn().storefront_wallet_ledger.insert_one({
        "id": db._next_id("storefront_wallet_ledger"),
        "customer_id": int(customer_id),
        "kind": kind,
        "amount_millimes": int(amount),
        "balance_after_millimes": int(balance_after),
        "reference": reference,
        "note": note[:300],
        "created_at": int(time.time()),
    })


def credit(customer_id: int, amount: int, *, kind: str, reference: str = "", note: str = "") -> int:
    if amount <= 0:
        raise WalletError("Le montant à créditer doit être positif.")
    wallet = db.get_conn().storefront_wallets.find_one_and_update(
        {"customer_id": int(customer_id)},
        {"$inc": {"balance_millimes": int(amount)}, "$set": {"updated_at": int(time.time())}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    after = int(wallet["balance_millimes"])
    _ledger(customer_id, kind, amount, after, reference, note)
    from app.domain import storefront_notification_service

    storefront_notification_service.announce_balance(int(customer_id), int(amount), after)
    return after


def purchase_recorded(customer_id: int, reference: str) -> bool:
    """True when this cart was already taken from the wallet."""
    reference = str(reference or "")
    if not reference:
        return False
    return db.get_conn().storefront_wallet_ledger.find_one({
        "customer_id": int(customer_id),
        "reference": reference,
        "kind": "purchase",
    }) is not None


def debit(customer_id: int, amount: int, *, kind: str, reference: str = "", note: str = "") -> int | None:
    """Take ``amount`` from the wallet, or return ``None`` if the balance is short.

    A purchase tied to a cart reference is taken once. Paying the same cart
    again returns the current balance and does not debit a second time.
    """
    if amount <= 0:
        raise WalletError("Le montant à débiter doit être positif.")
    reference = str(reference or "")
    if kind == "purchase" and purchase_recorded(customer_id, reference):
        return balance(customer_id)
    wallet = db.get_conn().storefront_wallets.find_one_and_update(
        {"customer_id": int(customer_id), "balance_millimes": {"$gte": int(amount)}},
        {"$inc": {"balance_millimes": -int(amount)}, "$set": {"updated_at": int(time.time())}},
        return_document=ReturnDocument.AFTER,
    )
    if not wallet:
        return None
    after = int(wallet["balance_millimes"])
    try:
        _ledger(customer_id, kind, -amount, after, reference, note)
    except DuplicateKeyError:
        if kind == "purchase" and purchase_recorded(customer_id, reference):
            db.get_conn().storefront_wallets.update_one(
                {"customer_id": int(customer_id)},
                {"$inc": {"balance_millimes": int(amount)}, "$set": {"updated_at": int(time.time())}},
            )
            return balance(customer_id)
        raise
    from app.domain import storefront_notification_service

    storefront_notification_service.announce_balance(int(customer_id), -int(amount), after)
    return after


# ---------------------------------------------------------------------------
# Customer side
# ---------------------------------------------------------------------------


def _public_deposit(row: dict[str, Any]) -> dict[str, Any]:
    method = str(row.get("method") or "")
    return {
        "id": int(row["id"]),
        "method": method,
        "method_label": site_settings_service.PAYMENT_METHOD_LABELS.get(method, method),
        "amount_millimes": int(row.get("amount_millimes") or 0),
        "credited_millimes": int(row.get("credited_millimes") or 0),
        "transaction_reference": row.get("transaction_reference", ""),
        "status": row.get("status", DEPOSIT_PENDING),
        "reason": row.get("reason", ""),
        "created_at": row.get("created_at"),
        "reviewed_at": row.get("reviewed_at"),
    }


def summary(customer: dict[str, Any]) -> dict[str, Any]:
    conn = db.get_conn()
    customer_id = int(customer["id"])
    ledger = conn.storefront_wallet_ledger.find({"customer_id": customer_id}).sort("id", -1).limit(HISTORY_LIMIT)
    deposits = conn.storefront_deposits.find({"customer_id": customer_id}).sort("id", -1).limit(HISTORY_LIMIT)
    return {
        "ok": True,
        "balance_millimes": balance(customer_id),
        "min_deposit_millimes": MIN_DEPOSIT_MILLIMES,
        "max_deposit_millimes": MAX_DEPOSIT_MILLIMES,
        "payment_methods": site_settings_service.public_payment_methods(),
        "transactions": [
            {
                "id": int(row["id"]),
                "kind": row.get("kind", ""),
                "label": LEDGER_LABELS.get(row.get("kind", ""), "Opération"),
                "amount_millimes": int(row.get("amount_millimes") or 0),
                "balance_after_millimes": int(row.get("balance_after_millimes") or 0),
                "reference": row.get("reference", ""),
                "note": row.get("note", ""),
                "created_at": row.get("created_at"),
            }
            for row in ledger
        ],
        "deposits": [_public_deposit(row) for row in deposits],
    }


def _transaction_reference(value: Any) -> str:
    reference = re.sub(r"\s+", " ", str(value or "").strip())[:64]
    if not reference:
        return ""
    if len(reference) < 3:
        raise WalletError("Saisis la référence de la transaction indiquée sur ton reçu.")
    return reference


def create_deposit(customer: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        method = site_settings_service.normalize_method(payload.get("method"))
    except ValueError as exc:
        raise WalletError(str(exc)) from exc
    amount = parse_amount(payload.get("amount"))
    if not MIN_DEPOSIT_MILLIMES <= amount <= MAX_DEPOSIT_MILLIMES:
        raise WalletError(
            f"Le montant doit être compris entre {MIN_DEPOSIT_MILLIMES // 1000} et "
            f"{MAX_DEPOSIT_MILLIMES // 1000} DT."
        )
    reference = _transaction_reference(payload.get("transaction_reference"))

    conn = db.get_conn()
    customer_id = int(customer["id"])
    if conn.storefront_deposits.count_documents({"customer_id": customer_id, "status": DEPOSIT_PENDING}) >= MAX_PENDING_DEPOSITS:
        raise WalletError("Tu as déjà des recharges en attente. Attends leur validation avant d'en ajouter.")
    reference_claim = None
    if reference:
        from app.domain.storefront_service import transfer_reference_in_use

        key = reference.lower()
        if transfer_reference_in_use(method, key):
            raise WalletError("Cette référence de transaction a déjà été déclarée.")
        reference_claim = db.claim_payment_reference(
            method, key, lambda: transfer_reference_in_use(method, key)
        )
        if reference_claim is None:
            raise WalletError("Cette référence de transaction a déjà été déclarée.")

    try:
        receipt_id = storefront_receipt_service.store(
            payload.get("receipt"), customer_id=customer_id, purpose="deposit"
        )
    except storefront_receipt_service.ReceiptError as exc:
        db.release_payment_reference(method, reference.lower(), reference_claim)
        raise WalletError(str(exc)) from exc

    now = int(time.time())
    deposit = {
        "id": db._next_id("storefront_deposits"),
        "customer_id": customer_id,
        "customer_name": customer.get("name", ""),
        "customer_email": customer.get("email", ""),
        "method": method,
        "amount_millimes": amount,
        "credited_millimes": 0,
        "transaction_reference": reference,
        **({"transaction_reference_key": reference.lower()} if reference else {}),
        "receipt_id": receipt_id,
        "status": DEPOSIT_PENDING,
        "reason": "",
        "created_at": now,
        "updated_at": now,
        "reviewed_at": None,
    }
    try:
        conn.storefront_deposits.insert_one(deposit)
    except DuplicateKeyError as exc:
        db.release_payment_reference(method, reference.lower(), reference_claim)
        raise WalletError("Cette référence de transaction a déjà été déclarée.") from exc
    db.bind_payment_reference(method, reference.lower(), reference_claim)
    db.audit_event(
        "storefront.deposit_created",
        details={"deposit_id": deposit["id"], "customer_id": customer_id, "amount_millimes": amount, "method": method},
    )
    email_service.send_deposit_received(
        deposit["customer_email"],
        deposit["customer_name"],
        amount,
        site_settings_service.PAYMENT_METHOD_LABELS[method],
        reference,
    )
    return {"ok": True, "deposit": _public_deposit(deposit)}


# ---------------------------------------------------------------------------
# Admin side
# ---------------------------------------------------------------------------

DEPOSIT_FILTERS = {
    "pending": [DEPOSIT_PENDING],
    "approved": [DEPOSIT_APPROVED],
    "rejected": [DEPOSIT_REJECTED],
}


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return str(values[0] or "").strip()


def _bounded(value: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _admin_deposit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **_public_deposit(row),
        "customer_id": int(row.get("customer_id") or 0),
        "customer_name": row.get("customer_name", ""),
        "customer_email": row.get("customer_email", ""),
        "receipt_id": row.get("receipt_id"),
        "balance_millimes": balance(int(row.get("customer_id") or 0)),
    }


def list_deposits(params: dict[str, list[str]]) -> dict[str, Any]:
    status = _first(params, "status") or "pending"
    search = _first(params, "search")[:80]
    page = _bounded(_first(params, "page"), 1, 1, 10_000)
    per_page = _bounded(_first(params, "per_page"), 20, 1, 100)

    conn = db.get_conn()
    counts = {key: conn.storefront_deposits.count_documents({"status": {"$in": value}}) for key, value in DEPOSIT_FILTERS.items()}
    query: dict[str, Any] = {}
    if status in DEPOSIT_FILTERS:
        query["status"] = {"$in": DEPOSIT_FILTERS[status]}
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"customer_name": pattern}, {"customer_email": pattern}, {"transaction_reference": pattern}]
    total = conn.storefront_deposits.count_documents(query)
    rows = conn.storefront_deposits.find(query).sort("id", -1).skip((page - 1) * per_page).limit(per_page)
    return {
        "ok": True,
        "items": [_admin_deposit(row) for row in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, -(-total // per_page)),
        "counts": counts,
        "status": status,
    }


def _pending_deposit(deposit_id: Any) -> dict[str, Any]:
    try:
        deposit_id = int(deposit_id)
    except (TypeError, ValueError) as exc:
        raise WalletError("Recharge introuvable.") from exc
    row = db.get_conn().storefront_deposits.find_one({"id": deposit_id})
    if not row:
        raise WalletError("Recharge introuvable.")
    if row.get("status") != DEPOSIT_PENDING:
        raise WalletError(f"La recharge #{deposit_id} a déjà été traitée.")
    return row


def approve_deposit(deposit_id: Any, amount: Any = "") -> dict[str, Any]:
    """Credit the wallet, with the amount the admin actually received if it differs."""
    row = _pending_deposit(deposit_id)
    credited = parse_amount(amount) if str(amount or "").strip() else int(row["amount_millimes"])
    if credited <= 0 or credited > MAX_DEPOSIT_MILLIMES:
        raise WalletError("Montant à créditer invalide.")
    now = int(time.time())
    claimed = db.get_conn().storefront_deposits.update_one(
        {"id": row["id"], "status": DEPOSIT_PENDING},
        {"$set": {"status": DEPOSIT_APPROVED, "credited_millimes": credited, "reviewed_at": now, "updated_at": now}},
    )
    if claimed.modified_count != 1:
        raise WalletError(f"La recharge #{row['id']} a déjà été traitée.")
    method_label = site_settings_service.PAYMENT_METHOD_LABELS.get(row["method"], row["method"])
    new_balance = credit(
        int(row["customer_id"]),
        credited,
        kind="deposit",
        reference=f"R-{row['id']}",
        note=" · ".join(
            part for part in (method_label, str(row.get("transaction_reference") or "").strip()) if part
        ),
    )
    db.audit_event(
        "storefront.deposit_approved",
        details={"deposit_id": row["id"], "customer_id": row["customer_id"], "credited_millimes": credited},
    )
    email_service.send_deposit_approved(
        row.get("customer_email", ""), row.get("customer_name", ""), credited, new_balance
    )
    return {"id": row["id"], "credited_millimes": credited, "balance_millimes": new_balance}


def reject_deposit(deposit_id: Any, reason: Any = "") -> dict[str, Any]:
    row = _pending_deposit(deposit_id)
    reason = str(reason or "").strip()[:500]
    if not reason:
        raise WalletError("Indique le motif du refus : le client le recevra par email.")
    now = int(time.time())
    result = db.get_conn().storefront_deposits.update_one(
        {"id": row["id"], "status": DEPOSIT_PENDING},
        {"$set": {"status": DEPOSIT_REJECTED, "reason": reason, "reviewed_at": now, "updated_at": now}},
    )
    if result.modified_count != 1:
        raise WalletError(f"La recharge #{row['id']} a déjà été traitée.")
    db.audit_event("storefront.deposit_rejected", details={"deposit_id": row["id"], "reason": reason})
    email_service.send_deposit_rejected(
        row.get("customer_email", ""), row.get("customer_name", ""), int(row["amount_millimes"]), reason
    )
    return {"id": row["id"]}


def adjust(customer_id: Any, amount: Any, note: Any) -> dict[str, Any]:
    """Manual admin credit (positive) or debit (negative) with a mandatory note."""
    try:
        customer_id = int(customer_id)
    except (TypeError, ValueError) as exc:
        raise WalletError("Client introuvable.") from exc
    customer = db.get_conn().storefront_customers.find_one({"id": customer_id})
    if not customer:
        raise WalletError("Client introuvable.")
    text = str(amount or "").strip()
    negative = text.startswith("-")
    millimes = parse_amount(text.lstrip("+-"))
    note = str(note or "").strip()[:300]
    if not millimes:
        raise WalletError("Le montant doit être différent de zéro.")
    if not note:
        raise WalletError("Indique le motif de l'ajustement.")
    if negative:
        after = debit(customer_id, millimes, kind="adjustment", note=note)
        if after is None:
            raise WalletError("Le solde du client est insuffisant pour ce retrait.")
    else:
        after = credit(customer_id, millimes, kind="adjustment", note=note)
    db.audit_event(
        "storefront.wallet_adjusted",
        details={"customer_id": customer_id, "amount_millimes": -millimes if negative else millimes, "note": note},
    )
    return {"customer_id": customer_id, "balance_millimes": after}
