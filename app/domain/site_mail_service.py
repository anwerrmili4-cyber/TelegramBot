"""Messages an administrator sends to existing Tunisian site customers.

The From address is the one already configured for the shop. Recipients are
storefront accounts only, so the panel cannot be used to write to an arbitrary
address.
"""

from __future__ import annotations

import time
from typing import Any

import database as db
from app.domain import email_service

_MAX_RECIPIENTS = 100


class SiteMailError(ValueError):
    """French message safe to show in the admin panel."""


_KIND_LABELS = {
    "send_verification_code": "Code de vérification",
    "send_welcome": "Bienvenue",
    "send_password_reset": "Mot de passe",
    "send_order_received": "Commande reçue",
    "send_payment_confirmed": "Paiement confirmé",
    "send_order_delivered": "Commande livrée",
    "send_order_cancelled": "Commande annulée",
    "send_invoice": "Facture",
    "send_deposit_received": "Recharge reçue",
    "send_deposit_approved": "Recharge créditée",
    "send_deposit_rejected": "Recharge refusée",
    "send_back_in_stock": "Retour en stock",
    "send_review_request": "Demande d'avis",
    "send_ticket_reply": "Réponse du support",
    "send_client_message": "Message du shop",
    "send_favorite": "Favori",
}


def _customer_emails() -> set[str]:
    found = set()
    for account in db.get_conn().storefront_customers.find({}, {"email": 1}):
        email = str(account.get("email") or "").strip().lower()
        if email:
            found.add(email)
    return found


def _preview(text: str) -> str:
    """One line for the inbox. Access details stay in the opened message."""
    body = str(text or "").split("Tes accès", 1)[0]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if lines and lines[0].startswith("Bonjour"):
        lines = lines[1:]
    return " ".join(lines)[:140]


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    return {
        "id": row["id"],
        "created_at": int(row.get("created_at") or 0),
        "kind": kind,
        "kind_label": str(row.get("kind_label") or _KIND_LABELS.get(kind, kind)),
        "to": str(row.get("to") or ""),
        "name": str(row.get("name") or ""),
        "subject": str(row.get("subject") or ""),
        "status": str(row.get("status") or "queued"),
        "preview": _preview(str(row.get("text") or row.get("preview") or "")),
        "tone": email_service.tone_for(kind),
    }


def _list_row(row: dict[str, Any]) -> dict[str, Any]:
    return _summary({**row, "id": int(row["id"])})


def _hist(
    message_id: str,
    created_at: int,
    kind: str,
    to: str,
    name: str,
    subject: str,
    text: str,
    html: str,
) -> dict[str, Any]:
    return {
        "id": message_id,
        "created_at": int(created_at or 0),
        "kind": kind,
        "kind_label": _KIND_LABELS.get(kind, kind),
        "to": to,
        "name": name,
        "subject": subject,
        "text": text,
        "html": html,
        "status": "sent",
    }


def _order_items(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "offer_name": line.get("offer_name") or "Offre",
            "quantity": int(line.get("qty") or line.get("quantity") or 1),
            "total_millimes": int(line.get("total_millimes") or 0),
        }
        for line in lines
    ]


def _draft_row(
    message_id: str,
    created_at: int,
    kind: str,
    to: str,
    name: str,
    draft: tuple[str, str, str],
) -> dict[str, Any]:
    subject, html, text = draft
    return _hist(message_id, created_at, kind, to, name, subject, text, html)


def _delivery_text(group: list[dict[str, Any]]) -> str:
    """The access block that was emailed for one delivery, automatic or typed by an admin."""
    from app.domain import site_orders_service

    contents = site_orders_service.deliveries_for(group)
    notes: list[str] = []
    blocks: list[str] = []
    for line in group:
        raw = str(line.get("delivery_text") or "")
        if raw and raw != site_orders_service.AUTOMATIC_DELIVERY:
            notes.append(raw)
            continue
        blocks.append(
            f"{int(line.get('qty') or 1)} × {line.get('offer_name') or 'Offre'}\n"
            f"{contents.get(int(line['id']), '')}".strip()
        )
    if notes and not blocks and len(set(notes)) == 1:
        return notes[0]
    return "\n\n".join([*blocks, *dict.fromkeys(notes)]).strip()


def database_history() -> list[dict[str, Any]]:
    """Mails already sent, rebuilt with the same template the customer received."""
    from app.domain import site_orders_service, site_settings_service

    conn = db.get_conn()
    carts: dict[str, list[dict[str, Any]]] = {}
    for line in conn.orders.find({
        "sales_channel": "tn_site",
        "customer_email": {"$nin": [None, ""]},
    }):
        reference = str(line.get("cart_reference") or f"order-{line.get('id')}")
        carts.setdefault(reference, []).append(line)

    rows: list[dict[str, Any]] = []
    for reference, lines in carts.items():
        first = lines[0]
        email = str(first.get("customer_email") or "").strip()
        name = str(first.get("customer_name") or "").strip()
        if not email:
            continue
        created = min(int(line.get("created_at") or 0) for line in lines)
        total = int(first.get("cart_total_millimes") or 0) or sum(int(line.get("total_millimes") or 0) for line in lines)
        items = _order_items(lines)
        method = str(first.get("payment_method") or "")
        if method != "wallet":
            rows.append(_draft_row(
                f"db-received-{reference}",
                created,
                "send_order_received",
                email,
                name,
                email_service.order_received_content(
                    name, reference, items, total, site_orders_service.method_label(method)
                ),
            ))
        delivered = [line for line in lines if str(line.get("status") or "") == "delivered"]
        groups: dict[int, list[dict[str, Any]]] = {}
        for line in delivered:
            when = int(line.get("delivered_at") or line.get("updated_at") or created)
            groups.setdefault(when, []).append(line)
        for when, group in groups.items():
            suffix = f"-{when}" if len(groups) > 1 else ""
            rows.append(_draft_row(
                f"db-delivered-{reference}{suffix}",
                when,
                "send_order_delivered",
                email,
                name,
                email_service.order_delivered_content(name, reference, _order_items(group), _delivery_text(group)),
            ))
        if delivered or any(line.get("paid_at") for line in lines):
            invoice = conn.storefront_invoices.find_one({"cart_reference": reference}) or {}
            number = str(invoice.get("number") or "")
            if number:
                issued_at = int(invoice.get("issued_at") or invoice.get("paid_at") or created)
                issued_on = time.strftime("%d/%m/%Y", time.localtime(issued_at)) if issued_at else ""
                invoice_items = invoice.get("items") or items
                rows.append(_draft_row(
                    f"db-invoice-{reference}",
                    issued_at,
                    "send_invoice",
                    email,
                    name,
                    email_service.invoice_content(
                        name,
                        number,
                        reference,
                        invoice_items,
                        int(invoice.get("total_millimes") or total),
                        str(invoice.get("payment_label") or site_orders_service.method_label(method)),
                        issued_on,
                    ),
                ))
        cancelled = [line for line in lines if str(line.get("status") or "") == "cancelled"]
        if cancelled and len(cancelled) == len(lines):
            when = max(int(line.get("cancelled_at") or line.get("updated_at") or created) for line in cancelled)
            reason = next((str(line.get("admin_note") or "") for line in cancelled if line.get("admin_note")), "")
            refund = sum(int(line.get("refunded_millimes") or 0) for line in cancelled)
            rows.append(_draft_row(
                f"db-cancelled-{reference}",
                when,
                "send_order_cancelled",
                email,
                name,
                email_service.order_cancelled_content(name, reference, reason, refund),
            ))

    for deposit in conn.storefront_deposits.find({"customer_email": {"$nin": [None, ""]}}):
        email = str(deposit.get("customer_email") or "").strip()
        name = str(deposit.get("customer_name") or "").strip()
        if not email:
            continue
        amount = int(deposit.get("amount_millimes") or 0)
        created = int(deposit.get("created_at") or 0)
        deposit_id = int(deposit.get("id") or 0)
        method = str(deposit.get("method") or "")
        label = site_settings_service.PAYMENT_METHOD_LABELS.get(method, method or "Paiement")
        reference = str(deposit.get("transaction_reference") or deposit_id)
        rows.append(_draft_row(
            f"db-deposit-received-{deposit_id}",
            created,
            "send_deposit_received",
            email,
            name,
            email_service.deposit_received_content(name, amount, label, reference),
        ))
        status = str(deposit.get("status") or "")
        reviewed = int(deposit.get("reviewed_at") or deposit.get("updated_at") or created)
        if status == "approved":
            credited = int(deposit.get("credited_millimes") or amount)
            ledger = conn.storefront_wallet_ledger.find_one({"reference": f"R-{deposit_id}", "kind": "deposit"}) or {}
            balance = ledger.get("balance_after_millimes")
            rows.append(_draft_row(
                f"db-deposit-approved-{deposit_id}",
                reviewed,
                "send_deposit_approved",
                email,
                name,
                email_service.deposit_approved_content(
                    name, credited, int(balance) if balance is not None else None
                ),
            ))
        elif status == "rejected":
            rows.append(_draft_row(
                f"db-deposit-rejected-{deposit_id}",
                reviewed,
                "send_deposit_rejected",
                email,
                name,
                email_service.deposit_rejected_content(name, amount, str(deposit.get("reason") or "")),
            ))
    return rows


def recent_messages() -> list[dict[str, Any]]:
    """Stored copies first, then Resend, then the same emails rebuilt from orders."""
    allowed = _customer_emails()
    merged: list[dict[str, Any]] = []
    covered: set[tuple[str, str]] = set()
    seen: set[str] = set()

    def add(item: dict[str, Any], *, exact: bool) -> None:
        address = str(item.get("to") or "").strip().lower()
        if address not in allowed:
            return
        identity = str(item.get("id"))
        key = (address, str(item.get("subject") or ""))
        if identity in seen:
            return
        if exact:
            covered.add(key)
        elif key in covered:
            return
        merged.append(_summary(item) if "preview" not in item or item.get("html") or item.get("text") else item)
        seen.add(identity)

    rows = db.get_conn().storefront_mail_log.find().sort("created_at", -1).limit(300)
    for row in rows:
        add(_list_row(row), exact=True)
    for item in email_service.list_provider_messages():
        add(item, exact=True)
    for item in database_history():
        add(item, exact=False)
    merged.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return merged[:100]


def message_detail(message_id: Any) -> dict[str, Any] | None:
    raw = str(message_id or "")
    if raw.startswith("db-"):
        for item in database_history():
            if item["id"] == raw and str(item.get("to") or "").strip().lower() in _customer_emails():
                return {"ok": True, **item}
        return None
    if raw.startswith("rs-"):
        item = email_service.provider_message(raw[3:])
        if not item:
            return None
        if str(item.get("to") or "").strip().lower() not in _customer_emails():
            return None
        if not str(item.get("html") or "").strip() and not str(item.get("text") or "").strip():
            address = str(item.get("to") or "").strip().lower()
            subject = str(item.get("subject") or "")
            match = next(
                (
                    row for row in database_history()
                    if str(row.get("to") or "").strip().lower() == address and str(row.get("subject") or "") == subject
                ),
                None,
            )
            if match:
                item["html"] = match["html"]
                item["text"] = match["text"]
                item["name"] = match.get("name") or ""
        return {"ok": True, **item}
    try:
        numeric_id = int(raw)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().storefront_mail_log.find_one({"id": numeric_id})
    if not row:
        return None
    if str(row.get("to") or "").strip().lower() not in _customer_emails():
        return None
    kind = str(row.get("kind") or "")
    return {
        "ok": True,
        "id": int(row["id"]),
        "created_at": int(row.get("created_at") or 0),
        "kind": kind,
        "kind_label": _KIND_LABELS.get(kind, kind),
        "to": str(row.get("to") or ""),
        "name": str(row.get("name") or ""),
        "subject": str(row.get("subject") or ""),
        "text": str(row.get("text") or ""),
        "html": str(row.get("html") or ""),
        "status": str(row.get("status") or "queued"),
    }


def style_catalog() -> dict[str, Any]:
    """Example of every automatic email, so Courrier can show each style."""
    return {"ok": True, "from": email_service.configured_sender(), "styles": email_service.style_catalog()}


def mailbox() -> dict[str, Any]:
    people = []
    for account in db.get_conn().storefront_customers.find({"email_verified": {"$ne": False}}):
        email = str(account.get("email") or "").strip()
        if not email:
            continue
        people.append({
            "id": int(account["id"]),
            "name": str(account.get("name") or ""),
            "email": email,
        })
    people.sort(key=lambda row: row["name"].casefold())
    return {"ok": True, "from": email_service.configured_sender(), "customers": people, "messages": recent_messages()}


def send_message(form: dict[str, Any]) -> dict[str, Any]:
    subject = str(form.get("subject") or "").strip()
    message = str(form.get("message") or "").strip()
    if not 3 <= len(subject) <= 120:
        raise SiteMailError("Le sujet doit faire entre 3 et 120 caractères.")
    if not 8 <= len(message) <= 4000:
        raise SiteMailError("Le message doit faire entre 8 et 4 000 caractères.")

    known = mailbox()["customers"]
    if str(form.get("audience") or "") == "all":
        targets = known
    else:
        try:
            customer_id = int(form.get("customer_id"))
        except (TypeError, ValueError) as exc:
            raise SiteMailError("Choisis un client du site.") from exc
        targets = [person for person in known if person["id"] == customer_id]
    if not targets:
        raise SiteMailError("Choisis un client du site.")
    if len(targets) > _MAX_RECIPIENTS:
        raise SiteMailError(f"{_MAX_RECIPIENTS} clients maximum par envoi.")

    for person in targets:
        email_service.send_client_message(person["email"], person["name"], subject, message)
    count = len(targets)
    noun = "message envoyé" if count == 1 else "messages envoyés"
    return {"ok": True, "sent": count, "message": f"{count} {noun}."}
