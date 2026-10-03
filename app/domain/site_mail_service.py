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


def recent_messages() -> list[dict[str, Any]]:
    allowed = _customer_emails()
    merged = list(email_service.list_provider_messages())
    rows = db.get_conn().storefront_mail_log.find().sort("created_at", -1).limit(300)
    seen = {str(item["id"]) for item in merged}
    for row in rows:
        address = str(row.get("to") or "").strip().lower()
        if address not in allowed:
            continue
        item = _list_row(row)
        if str(item["id"]) in seen:
            continue
        merged.append(item)
        seen.add(str(item["id"]))
    merged = [item for item in merged if str(item.get("to") or "").strip().lower() in allowed]
    merged.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return merged[:100]


def message_detail(message_id: Any) -> dict[str, Any] | None:
    raw = str(message_id or "")
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
