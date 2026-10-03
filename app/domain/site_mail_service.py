"""Messages an administrator sends to existing Tunisian site customers.

The From address is the one already configured for the shop. Recipients are
storefront accounts only, so the panel cannot be used to write to an arbitrary
address.
"""

from __future__ import annotations

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
}


def _customer_emails() -> set[str]:
    found = set()
    for account in db.get_conn().storefront_customers.find({}, {"email": 1}):
        email = str(account.get("email") or "").strip().lower()
        if email:
            found.add(email)
    return found


def _list_row(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    return {
        "id": int(row["id"]),
        "created_at": int(row.get("created_at") or 0),
        "kind": kind,
        "kind_label": _KIND_LABELS.get(kind, kind),
        "to": str(row.get("to") or ""),
        "subject": str(row.get("subject") or ""),
        "status": str(row.get("status") or "queued"),
    }


def _hist(
    message_id: str,
    created_at: int,
    kind: str,
    to: str,
    name: str,
    subject: str,
    text: str,
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
        "html": "",
        "status": "sent",
    }


def _cart_items_text(lines: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {int(line.get('qty') or line.get('quantity') or 1)} x {line.get('offer_name') or 'Offre'}"
        for line in lines
    )


def database_history() -> list[dict[str, Any]]:
    """Mails already sent, rebuilt from site orders, invoices and deposits."""
    from app.domain import site_orders_service

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
        items = _cart_items_text(lines)
        greeting = f"Bonjour {name}," if name else "Bonjour,"
        method = str(first.get("payment_method") or "")
        if method != "wallet":
            label = site_orders_service.method_label(method)
            rows.append(_hist(
                f"db-received-{reference}",
                created,
                "send_order_received",
                email,
                name,
                f"Commande {reference} reçue",
                f"{greeting}\n\nNous avons bien reçu ta commande {reference}.\n\n{items}\n\n"
                f"Total : {email_service._money(total)}\n\n"
                f"Ton reçu {label} est en cours de vérification par un administrateur.",
            ))
        delivered = [line for line in lines if str(line.get("status") or "") == "delivered"]
        if delivered:
            when = max(int(line.get("delivered_at") or line.get("updated_at") or created) for line in delivered)
            contents = site_orders_service.deliveries_for(delivered)
            access = "\n\n".join(
                f"{int(line.get('qty') or 1)} × {line.get('offer_name') or 'Offre'}\n{contents.get(int(line['id']), '')}".strip()
                for line in delivered
            )
            rows.append(_hist(
                f"db-delivered-{reference}",
                when,
                "send_order_delivered",
                email,
                name,
                f"Ta commande {reference} est livrée",
                f"{greeting}\n\nTa commande {reference} est livrée :\n{items}\n\nTes accès :\n{access}\n",
            ))
        if delivered or any(line.get("paid_at") for line in lines):
            invoice = conn.storefront_invoices.find_one({"cart_reference": reference}) or {}
            number = str(invoice.get("number") or "")
            if number:
                rows.append(_hist(
                    f"db-invoice-{reference}",
                    int(invoice.get("issued_at") or invoice.get("paid_at") or created),
                    "send_invoice",
                    email,
                    name,
                    f"Ta facture {number} — {reference}",
                    f"{greeting}\n\nMerci pour ton achat. La facture {number} de la commande {reference} "
                    f"a été envoyée avec le PDF joint.\n\nTotal : {email_service._money(total)}\n",
                ))
        cancelled = [line for line in lines if str(line.get("status") or "") == "cancelled"]
        if cancelled and len(cancelled) == len(lines):
            when = max(int(line.get("cancelled_at") or line.get("updated_at") or created) for line in cancelled)
            reason = next((str(line.get("admin_note") or "") for line in cancelled if line.get("admin_note")), "")
            refund = sum(int(line.get("refunded_millimes") or 0) for line in cancelled)
            extra = f"\nMotif : {reason}" if reason else ""
            if refund:
                extra += f"\n\n{email_service._money(refund)} ont été remboursés sur ton portefeuille."
            rows.append(_hist(
                f"db-cancelled-{reference}",
                when,
                "send_order_cancelled",
                email,
                name,
                f"Commande {reference} annulée",
                f"{greeting}\n\nTa commande {reference} a été annulée.{extra}\n",
            ))

    for deposit in conn.storefront_deposits.find({"customer_email": {"$nin": [None, ""]}}):
        email = str(deposit.get("customer_email") or "").strip()
        name = str(deposit.get("customer_name") or "").strip()
        if not email:
            continue
        greeting = f"Bonjour {name}," if name else "Bonjour,"
        amount = int(deposit.get("amount_millimes") or 0)
        created = int(deposit.get("created_at") or 0)
        deposit_id = int(deposit.get("id") or 0)
        rows.append(_hist(
            f"db-deposit-received-{deposit_id}",
            created,
            "send_deposit_received",
            email,
            name,
            f"Recharge reçue #{deposit_id}",
            f"{greeting}\n\nNous avons bien reçu ta demande de recharge de {email_service._money(amount)}.\n",
        ))
        if str(deposit.get("status") or "") == "approved":
            credited = int(deposit.get("credited_millimes") or amount)
            rows.append(_hist(
                f"db-deposit-approved-{deposit_id}",
                int(deposit.get("reviewed_at") or deposit.get("updated_at") or created),
                "send_deposit_approved",
                email,
                name,
                f"Recharge créditée #{deposit_id}",
                f"{greeting}\n\nTa recharge est validée : {email_service._money(credited)} ont été crédités.\n",
            ))
    return rows


def recent_messages() -> list[dict[str, Any]]:
    allowed = _customer_emails()
    merged = list(email_service.list_provider_messages())
    merged.extend(database_history())
    seen_subjects = {(str(item.get("to") or "").lower(), str(item.get("subject") or "")) for item in merged}
    rows = db.get_conn().storefront_mail_log.find().sort("created_at", -1).limit(300)
    seen = {str(item["id"]) for item in merged}
    for row in rows:
        address = str(row.get("to") or "").strip().lower()
        if address not in allowed:
            continue
        item = _list_row(row)
        key = (str(item.get("to") or "").lower(), str(item.get("subject") or ""))
        if str(item["id"]) in seen or key in seen_subjects:
            continue
        merged.append(item)
        seen.add(str(item["id"]))
        seen_subjects.add(key)
    merged = [item for item in merged if str(item.get("to") or "").strip().lower() in allowed]
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
