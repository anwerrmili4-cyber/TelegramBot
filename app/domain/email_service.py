"""Transactional emails for the Tunisian storefront, sent through Resend.

Every message is posted from a daemon thread: a slow or failing Resend call
must never delay or break the checkout, sign-up or admin action behind it.
Without ``RESEND_API_KEY`` the message is only logged, so a local run keeps
working and a verification code can still be read from the console.

The HTML uses nested tables and inline styles only, which is what Gmail,
Outlook and Apple Mail all render the same way.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from html import escape
from typing import Any

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_SENDER = "BLACKMARKET <noreply@ourblackmarket.com>"
DEFAULT_SITE_URL = "https://www.ourblackmarket.com"
BRAND = "BLACKMARKET Tunisie"

_BG = "#0b0b0d"
_CARD = "#131316"
_LINE = "#25252b"
_TEXT = "#f4f4f5"
_SOFT = "#c4c4cc"
_MUTED = "#8b8b95"
_BRAND = "#e03a30"
_FONT = "'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_MONO = "Menlo,Consolas,'Courier New',monospace"

_TONES = {
    "brand": ("#ff6b61", "rgba(224,58,48,.14)"),
    "success": ("#4ade80", "rgba(34,197,94,.14)"),
    "pending": ("#fbbf24", "rgba(245,158,11,.14)"),
    "danger": ("#f87171", "rgba(239,68,68,.14)"),
}


def _api_key() -> str:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    return "" if key == "re_xxxxxxxxx" else key


def _sender() -> str:
    return os.environ.get("RESEND_FROM", "").strip() or DEFAULT_SENDER


def _post(message: dict[str, Any]) -> None:
    api_key = _api_key()
    if not api_key:
        log.warning("RESEND_API_KEY is not set; email not sent: %s\n%s", message["subject"], message["text"])
        return
    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps({"from": _sender(), **message}).encode(),
        method="POST",
        # Cloudflare in front of the Resend API rejects urllib's default
        # User-Agent with "error code: 1010".
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "blackmarket-storefront/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        log.error("Resend rejected an email (%s): %s", exc.code, exc.read()[:500])
    except (urllib.error.URLError, TimeoutError):
        log.exception("An email could not be sent through Resend")


def _dispatch(message: dict[str, Any]) -> None:
    threading.Thread(target=_post, args=(message,), daemon=True).start()


def send(
    to: str,
    subject: str,
    html: str,
    text: str,
    attachments: Sequence[tuple[str, bytes]] = (),
) -> None:
    if not to:
        return
    message: dict[str, Any] = {"to": [to], "subject": subject, "html": html, "text": text}
    if attachments:
        message["attachments"] = [
            {"filename": filename, "content": base64.b64encode(content).decode()}
            for filename, content in attachments
        ]
    _dispatch(message)


def _money(millimes: int) -> str:
    return f"{int(millimes) / 1000:.3f}".replace(".", ",") + " DT"


def site_url() -> str:
    return os.environ.get("STOREFRONT_PUBLIC_URL", "").strip().rstrip("/") or DEFAULT_SITE_URL


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def _layout(title: str, body: str, *, badge: str = "", tone: str = "brand", preheader: str = "") -> str:
    site = site_url()
    color, wash = _TONES.get(tone, _TONES["brand"])
    badge_html = (
        f'<span style="display:inline-block;padding:5px 12px;border-radius:999px;background:{wash};'
        f'color:{color};font-size:12px;font-weight:700;letter-spacing:.04em">{escape(badge)}</span>'
        if badge
        else ""
    )
    hidden = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{_BG}">'
        f"{escape(preheader)}{'&nbsp;&zwnj;' * 40}</div>"
        if preheader
        else ""
    )
    year = time.strftime("%Y")
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="dark light"><meta name="supported-color-schemes" content="dark light">'
        f"<title>{escape(title)}</title></head>"
        f'<body style="margin:0;padding:0;background:{_BG};font-family:{_FONT};color:{_TEXT}">'
        f"{hidden}"
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{_BG}" style="background:{_BG}">'
        '<tr><td align="center" style="padding:32px 12px 40px">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px">'
        # Brand header
        '<tr><td style="padding:0 6px 20px">'
        '<table role="presentation" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="vertical-align:middle"><a href="{escape(site)}" style="text-decoration:none">'
        f'<img src="{escape(site)}/logo.png" width="52" height="52" alt="BLACKMARKET" '
        'style="display:block;border:0;outline:none;width:52px;height:52px"></a></td>'
        '<td style="vertical-align:middle;padding-left:12px">'
        f'<div style="font-size:16px;font-weight:800;letter-spacing:.14em;color:{_TEXT}">BLACKMARKET</div>'
        f'<div style="font-size:11px;font-weight:600;letter-spacing:.34em;color:{_BRAND}">TUNISIE</div>'
        "</td></tr></table></td></tr>"
        # Card
        f'<tr><td bgcolor="{_CARD}" style="background:{_CARD};border:1px solid {_LINE};border-radius:20px;overflow:hidden">'
        f'<div style="height:4px;line-height:4px;font-size:0;background:{_BRAND};'
        f'background-image:linear-gradient(90deg,{_BRAND},#ff7a59)">&nbsp;</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
        '<td style="padding:30px 30px 12px">'
        f"{badge_html}"
        f'<h1 style="margin:{14 if badge else 0}px 0 18px;font-size:25px;line-height:1.25;font-weight:800;color:{_TEXT}">'
        f"{escape(title)}</h1>"
        f'<div style="font-size:15px;line-height:1.65;color:{_SOFT}">{body}</div>'
        "</td></tr></table></td></tr>"
        # Footer
        f'<tr><td align="center" style="padding:24px 16px 0;font-size:12px;line-height:1.7;color:{_MUTED}">'
        f'<a href="{escape(site)}" style="color:{_SOFT};text-decoration:none;font-weight:600">Boutique</a>'
        f'<span style="color:{_LINE}">&nbsp;&nbsp;•&nbsp;&nbsp;</span>'
        f'<a href="{escape(site)}{ACCOUNT_PATH}" style="color:{_SOFT};text-decoration:none;font-weight:600">Mon compte</a>'
        f'<span style="color:{_LINE}">&nbsp;&nbsp;•&nbsp;&nbsp;</span>'
        f'<a href="{escape(site)}{ACCOUNT_PATH}?onglet=portefeuille" style="color:{_SOFT};text-decoration:none;font-weight:600">'
        "Portefeuille</a>"
        f'<div style="margin-top:12px">© {year} {BRAND} · ourblackmarket.com</div>'
        "<div>Email envoyé automatiquement, merci de ne pas y répondre.</div>"
        "</td></tr></table></td></tr></table></body></html>"
    )


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 14px">{text}</p>'


def _strong(text: str) -> str:
    return f'<strong style="color:{_TEXT}">{text}</strong>'


def _button(label: str, url: str) -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0 18px"><tr>'
        f'<td bgcolor="{_BRAND}" style="border-radius:12px;background:{_BRAND}">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:14px 26px;font-size:15px;font-weight:700;'
        f'color:#ffffff;text-decoration:none;border-radius:12px">{escape(label)}&nbsp;&nbsp;→</a>'
        "</td></tr></table>"
    )


def _panel(inner: str, *, margin: str = "6px 0 20px") -> str:
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:{margin}">'
        f'<tr><td style="background:{_BG};border:1px solid {_LINE};border-radius:14px;padding:6px 18px">'
        f"{inner}</td></tr></table>"
    )


def _details(rows: Sequence[tuple[str, str]]) -> str:
    """Label / value lines in a panel; values are HTML."""
    lines = "".join(
        '<tr>'
        f'<td style="padding:10px 0;{"border-top:1px solid " + _LINE + ";" if index else ""}font-size:13px;color:{_MUTED}">'
        f"{escape(label)}</td>"
        f'<td align="right" style="padding:10px 0;{"border-top:1px solid " + _LINE + ";" if index else ""}'
        f'font-size:14px;font-weight:600;color:{_TEXT}">{value}</td></tr>'
        for index, (label, value) in enumerate(rows)
    )
    return _panel(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{lines}</table>')


def _items_table(items: Sequence[dict[str, Any]], total_millimes: int, *, total_label: str = "Total") -> str:
    rows = "".join(
        "<tr>"
        f'<td style="padding:13px 0;border-bottom:1px solid {_LINE}">'
        f'<div style="font-size:14px;font-weight:600;color:{_TEXT}">{escape(str(item["offer_name"]))}</div>'
        f'<div style="font-size:12px;color:{_MUTED}">Quantité : {int(item["quantity"])}</div></td>'
        f'<td align="right" style="padding:13px 0;border-bottom:1px solid {_LINE};white-space:nowrap;'
        f'font-size:14px;color:{_TEXT}">{_money(item["total_millimes"])}</td></tr>'
        for item in items
    )
    return _panel(
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0">'
        f"{rows}"
        f'<tr><td style="padding:14px 0 10px;font-size:14px;font-weight:700;color:{_TEXT}">{escape(total_label)}</td>'
        f'<td align="right" style="padding:14px 0 10px;font-size:18px;font-weight:800;color:#ff6b61;white-space:nowrap">'
        f"{_money(total_millimes)}</td></tr></table>"
    )


def _items_text(items: Sequence[dict[str, Any]], total_millimes: int) -> str:
    lines = [f'- {int(item["quantity"])} x {item["offer_name"]} : {_money(item["total_millimes"])}' for item in items]
    return "\n".join([*lines, f"Total : {_money(total_millimes)}"])


def _note(text: str, tone: str = "brand") -> str:
    color, wash = _TONES.get(tone, _TONES["brand"])
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:4px 0 16px"><tr>'
        f'<td style="background:{wash};border-left:3px solid {color};border-radius:10px;padding:12px 16px;'
        f'font-size:14px;line-height:1.55;color:{_TEXT}">{text}</td></tr></table>'
    )


def _greeting(name: str) -> str:
    return f"Bonjour {name}," if name else "Bonjour,"


ACCOUNT_PATH = "/mon-compte"


def _account_url(section: str = "") -> str:
    site = os.environ.get("STOREFRONT_PUBLIC_URL", "").strip().rstrip("/")
    if not site:
        return ""
    return f"{site}{ACCOUNT_PATH}" + (f"?onglet={section}" if section else "")


def _account_button(label: str, section: str = "") -> tuple[str, str]:
    """The HTML button and plain-text line pointing to the customer's space."""
    url = _account_url(section)
    if not url:
        return "", ""
    return _button(label, url), f"\n\n{label} : {url}"


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def _duration(minutes: int) -> str:
    return "1 minute" if int(minutes) == 1 else f"{int(minutes)} minutes"


def send_verification_code(to: str, name: str, code: str, minutes: int) -> None:
    delay = _duration(minutes)
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph("Entre ce code pour confirmer ton adresse.")
        + '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:8px 0 22px"><tr>'
        f'<td align="center" style="background:{_BG};border:1px dashed #3a3a42;border-radius:16px;padding:22px 10px">'
        f'<div style="font-family:{_MONO};font-size:36px;font-weight:800;letter-spacing:.28em;color:{_TEXT};'
        f'padding-left:.28em">{escape(code)}</div>'
        f'<div style="margin-top:8px;font-size:12px;color:{_MUTED}">Valable {delay}</div>'
        "</td></tr></table>"
        + _paragraph("Ne le partage avec personne. Si tu n'as rien demandé, ignore cet e-mail.")
    )
    text = (
        f"{_greeting(name)}\n\n"
        "Entre ce code pour confirmer ton adresse :\n\n"
        f"{code}\n\n"
        f"Valable {delay}. Ne le partage avec personne.\n"
        "Si tu n'as rien demandé, ignore cet e-mail."
    )
    send(
        to,
        f"{code} — code BlackMarket",
        _layout("Confirme ton adresse", body, badge="Code", preheader=f"Ton code : {code}. Valable {delay}."),
        text,
    )


def send_welcome(to: str, name: str, site_url: str) -> None:
    steps = "".join(
        '<tr>'
        f'<td style="padding:10px 12px 10px 0;vertical-align:top;width:30px">'
        f'<div style="width:28px;height:28px;line-height:28px;border-radius:999px;background:rgba(224,58,48,.16);'
        f'color:#ff6b61;font-size:13px;font-weight:800;text-align:center">{number}</div></td>'
        f'<td style="padding:10px 0;font-size:14px;color:{_SOFT}">{_strong(title)}<br>{text}</td></tr>'
        for number, title, text in (
            (1, "Recharge ton portefeuille", "Par D17, Flouci, IZI ou Wafa Cash, avec la capture de ton reçu."),
            (2, "Achète en un clic", "Paie tes commandes directement avec ton solde."),
            (3, "Reçois tes accès", "Par email et dans ton espace client, disponibles à tout moment."),
        )
    )
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ton compte {BRAND} est prêt. Voici comment ça marche :")
        + _panel(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{steps}</table>')
        + (_button("Découvrir le catalogue", site_url) if site_url else "")
    )
    text = (
        f"{_greeting(name)}\n\nTon compte {BRAND} est prêt.\n"
        "Recharge ton portefeuille par D17, Flouci, IZI ou Wafa Cash, puis achète en un clic : "
        "tes accès arrivent par email et restent disponibles dans ton espace client."
        + (f"\n\n{site_url}" if site_url else "")
    )
    send(
        to,
        f"Bienvenue sur {BRAND}",
        _layout("Bienvenue !", body, badge="Compte créé", tone="success", preheader="Ton compte est prêt."),
        text,
    )


def send_password_reset(to: str, name: str, link: str) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph("Choisis un nouveau mot de passe avec le bouton ci-dessous.")
        + _button("Choisir un mot de passe", link)
        + _paragraph("Le lien est valable une heure. Si tu n'as rien demandé, ignore cet e-mail : ton mot de passe actuel ne change pas.")
    )
    text = (
        f"{_greeting(name)}\n\n"
        "Choisis un nouveau mot de passe ici :\n"
        f"{link}\n\n"
        "Le lien est valable une heure. Si tu n'as rien demandé, ignore cet e-mail."
    )
    send(
        to,
        "Nouveau mot de passe",
        _layout("Nouveau mot de passe", body, badge="Sécurité", preheader="Le lien est valable une heure."),
        text,
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def send_order_received(
    to: str,
    name: str,
    reference: str,
    items: Sequence[dict[str, Any]],
    total_millimes: int,
    method_label: str,
) -> None:
    """A transfer-paid cart: the receipt is waiting for an administrator."""
    button, link = _account_button("Suivre ma commande", "commandes")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Nous avons bien reçu ta commande {_strong(escape(reference))}.")
        + _items_table(items, total_millimes)
        + _details([("Paiement", escape(method_label)), ("Statut", "Reçu en vérification")])
        + _note(
            f"Ton reçu {escape(method_label)} est en cours de vérification par un administrateur. "
            "Dès qu'il est validé, tes accès arrivent par email et dans ton espace client.",
            "pending",
        )
        + button
    )
    text = (
        f"{_greeting(name)}\n\nNous avons bien reçu ta commande {reference}.\n\n"
        f"{_items_text(items, total_millimes)}\n\n"
        f"Ton reçu {method_label} est en cours de vérification par un administrateur. "
        "Dès qu'il est validé, tes accès arrivent par email et dans ton espace client."
        + link
    )
    send(
        to,
        f"Commande {reference} reçue",
        _layout("Commande reçue", body, badge=reference, tone="pending", preheader=f"Total {_money(total_millimes)}"),
        text,
    )


def send_payment_confirmed(
    to: str, name: str, reference: str, items: Sequence[dict[str, Any]], total_millimes: int
) -> None:
    button, link = _account_button("Suivre ma commande", "commandes")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ton paiement pour la commande {_strong(escape(reference))} est confirmé.")
        + _items_table(items, total_millimes)
        + _note(
            "Nous préparons ta livraison. Tes accès arriveront par email et dans ton espace client dès qu'ils sont prêts.",
            "success",
        )
        + button
    )
    text = (
        f"{_greeting(name)}\n\nTon paiement pour la commande {reference} est confirmé.\n\n"
        f"{_items_text(items, total_millimes)}\n\n"
        "Nous préparons ta livraison. Tes accès arriveront par email et dans ton espace client dès qu'ils sont prêts."
        + link
    )
    send(
        to,
        f"Paiement confirmé — {reference}",
        _layout("Paiement confirmé", body, badge=reference, tone="success", preheader="Ta livraison est en préparation."),
        text,
    )


def _delivery_access(content: str) -> str:
    """Render labeled access lines as rows. Free text stays in a single block."""
    lines = [line.strip() for line in str(content or "").splitlines() if line.strip()]
    fields = []
    for line in lines:
        label, separator, value = line.partition(" : ")
        label, value = label.strip(), value.strip()
        if not separator or not label or not value or len(label) > 80:
            fields = []
            break
        fields.append((label, value))
    if not fields:
        return (
            f'<pre style="margin:0 0 18px;padding:16px 18px;background:{_BG};border:1px solid {_LINE};'
            "border-radius:14px;white-space:pre-wrap;word-break:break-word;font-size:14px;line-height:1.6;"
            f'color:{_TEXT};font-family:{_MONO}">{escape(content)}</pre>'
        )
    rows = "".join(
        f'<tr><td style="padding:10px 14px;border-bottom:1px solid {_LINE}">'
        f'<div style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:{_MUTED}">{escape(label)}</div>'
        f'<div style="margin-top:3px;font-size:15px;line-height:1.45;color:{_TEXT}">{escape(value)}</div></td></tr>'
        for label, value in fields
    )
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin:0 0 18px;background:{_BG};border:1px solid {_LINE};border-radius:14px;overflow:hidden">{rows}</table>'
    )


def send_order_delivered(
    to: str,
    name: str,
    reference: str,
    items: Sequence[dict[str, Any]],
    content: str,
    *,
    remaining: int = 0,
) -> None:
    """Email the access details; ``remaining`` counts lines still being prepared."""
    lines = "".join(
        f'<tr><td style="padding:8px 0;font-size:14px;color:{_TEXT}">'
        f'<span style="color:#4ade80">✓</span>&nbsp;&nbsp;{int(item["quantity"])} × {escape(str(item["offer_name"]))}'
        "</td></tr>"
        for item in items
    )
    button, link = _account_button("Voir dans mon espace", "commandes")
    later = (
        f"{remaining} autre{'s' if remaining > 1 else ''} article{'s' if remaining > 1 else ''} de cette commande "
        f"{'sont' if remaining > 1 else 'est'} en préparation : tu recevras un autre email."
        if remaining
        else ""
    )
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ta commande {_strong(escape(reference))} est livrée :")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 14px">{lines}</table>'
        + f'<div style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.12em;color:{_MUTED}">TES ACCÈS</div>'
        + _delivery_access(content)
        + _note("Garde cet email en lieu sûr. Tes accès restent aussi disponibles dans ton espace client.")
        + (_note(escape(later), "pending") if later else "")
        + button
    )
    items_text = "\n".join(f"- {int(item['quantity'])} x {item['offer_name']}" for item in items)
    text = (
        f"{_greeting(name)}\n\nTa commande {reference} est livrée :\n{items_text}\n\n"
        f"Tes accès :\n{content}\n\n"
        "Garde cet email en lieu sûr. Tes accès restent aussi disponibles dans ton espace client."
        + (f"\n\n{later}" if later else "")
        + link
    )
    send(
        to,
        f"Ta commande {reference} est livrée",
        _layout("Commande livrée", body, badge="Livrée", tone="success", preheader="Tes accès sont arrivés."),
        text,
    )


def send_order_cancelled(to: str, name: str, reference: str, reason: str, refunded_millimes: int = 0) -> None:
    refund = (
        f"{_money(refunded_millimes)} ont été remboursés sur ton portefeuille."
        if refunded_millimes
        else ""
    )
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ta commande {_strong(escape(reference))} a été annulée.")
        + (_details([("Motif", escape(reason))]) if reason else "")
        + (_note(_strong(escape(refund)), "success") if refund else "")
        + _paragraph("Une question ? Réponds depuis ton espace client ou passe une nouvelle commande sur la boutique.")
    )
    text = (
        f"{_greeting(name)}\n\nTa commande {reference} a été annulée."
        + (f"\nMotif : {reason}" if reason else "")
        + (f"\n\n{refund}" if refund else "")
    )
    send(
        to,
        f"Commande {reference} annulée",
        _layout("Commande annulée", body, badge=reference, tone="danger", preheader=reason or "Commande annulée"),
        text,
    )


def send_invoice(
    to: str,
    name: str,
    invoice_number: str,
    reference: str,
    items: Sequence[dict[str, Any]],
    total_millimes: int,
    method_label: str,
    pdf: bytes,
) -> None:
    """The paid invoice, as a summary in the body and a PDF attachment."""
    button, link = _account_button("Mes commandes et factures", "commandes")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Merci pour ton achat ! Voici la facture de ta commande {_strong(escape(reference))}.")
        + _details([
            ("Facture", escape(invoice_number)),
            ("Commande", escape(reference)),
            ("Date", time.strftime("%d/%m/%Y")),
            ("Paiement", escape(method_label)),
        ])
        + _items_table(items, total_millimes, total_label="Total payé")
        + _note(f"La facture PDF <strong>{escape(invoice_number)}.pdf</strong> est jointe à cet email.")
        + button
    )
    text = (
        f"{_greeting(name)}\n\nMerci pour ton achat ! Voici la facture {invoice_number} "
        f"de ta commande {reference} (payée par {method_label}).\n\n"
        f"{_items_text(items, total_millimes)}\n\n"
        f"La facture PDF {invoice_number}.pdf est jointe à cet email."
        + link
    )
    send(
        to,
        f"Ta facture {invoice_number} — {reference}",
        _layout(
            f"Facture {invoice_number}",
            body,
            badge="Payée",
            tone="success",
            preheader=f"Total payé {_money(total_millimes)}",
        ),
        text,
        attachments=[(f"{invoice_number}.pdf", pdf)],
    )


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------


def send_deposit_received(to: str, name: str, amount_millimes: int, method_label: str, reference: str) -> None:
    button, link = _account_button("Voir mon portefeuille", "portefeuille")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph("Nous avons bien reçu ta demande de recharge.")
        + _details([
            ("Montant", _money(amount_millimes)),
            ("Moyen", escape(method_label)),
            ("Référence", escape(reference)),
        ])
        + _note("Un administrateur vérifie ton reçu. Ton solde sera crédité dès la validation.", "pending")
        + button
    )
    text = (
        f"{_greeting(name)}\n\nNous avons bien reçu ta demande de recharge de {_money(amount_millimes)} "
        f"par {method_label} (référence {reference}).\n"
        "Un administrateur vérifie ton reçu. Ton solde sera crédité dès la validation."
        + link
    )
    send(
        to,
        "Recharge en cours de vérification",
        _layout("Recharge reçue", body, badge="En vérification", tone="pending", preheader=_money(amount_millimes)),
        text,
    )


def send_deposit_approved(to: str, name: str, credited_millimes: int, balance_millimes: int) -> None:
    button, link = _account_button("Voir mon portefeuille", "portefeuille")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph("Ta recharge est validée, ton portefeuille est crédité.")
        + '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:6px 0 20px"><tr>'
        f'<td align="center" style="background:{_BG};border:1px solid {_LINE};border-radius:16px;padding:22px 10px">'
        f'<div style="font-size:30px;font-weight:800;color:#4ade80">+ {_money(credited_millimes)}</div>'
        f'<div style="margin-top:6px;font-size:13px;color:{_MUTED}">Nouveau solde : '
        f'<strong style="color:{_TEXT}">{_money(balance_millimes)}</strong></div>'
        "</td></tr></table>"
        + button
    )
    text = (
        f"{_greeting(name)}\n\nTa recharge est validée : {_money(credited_millimes)} ont été crédités.\n"
        f"Nouveau solde : {_money(balance_millimes)}."
        + link
    )
    send(
        to,
        f"Portefeuille crédité de {_money(credited_millimes)}",
        _layout("Recharge validée", body, badge="Créditée", tone="success", preheader=f"Nouveau solde {_money(balance_millimes)}"),
        text,
    )


def send_deposit_rejected(to: str, name: str, amount_millimes: int, reason: str) -> None:
    button, link = _account_button("Refaire une demande", "portefeuille")
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ta demande de recharge de {_strong(_money(amount_millimes))} n'a pas pu être validée.")
        + _details([("Motif", escape(reason))])
        + _paragraph("Tu peux envoyer une nouvelle demande depuis ton espace client avec un reçu lisible.")
        + button
    )
    text = (
        f"{_greeting(name)}\n\nTa demande de recharge de {_money(amount_millimes)} n'a pas pu être validée.\n"
        f"Motif : {reason}\n\n"
        "Tu peux envoyer une nouvelle demande depuis ton espace client avec un reçu lisible."
        + link
    )
    send(
        to,
        "Recharge refusée",
        _layout("Recharge refusée", body, badge="Refusée", tone="danger", preheader=reason),
        text,
    )


def send_back_in_stock(to: str, name: str, product: str, link: str) -> None:
    """Tell someone who asked to be warned that a sold-out product is back."""
    button = _button("Voir le produit", link)
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"{_strong(escape(product))} est de nouveau disponible.")
        + _note("Le stock part vite. Ouvre la fiche pour le commander tant qu'il est là.", "success")
        + button
    )
    text = (
        f"{_greeting(name)}\n\n{product} est de nouveau disponible.\n\n"
        "Le stock part vite. Ouvre la fiche pour le commander tant qu'il est là.\n\n"
        f"{link}\n"
    )
    send(
        to,
        f"{product} est de nouveau disponible",
        _layout("De nouveau disponible", body, badge="En stock", tone="success", preheader=product),
        text,
    )
