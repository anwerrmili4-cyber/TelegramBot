"""Transactional emails for the Tunisian storefront, sent through Resend.

Every message is posted from a daemon thread: a slow or failing Resend call
must never delay or break the checkout, sign-up or admin action behind it.
Without ``RESEND_API_KEY`` the message is only logged, so a local run keeps
working and a verification code can still be read from the console.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from html import escape
from typing import Any

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_SENDER = "BLACKMARKET <noreply@ourblackmarket.com>"
BRAND = "BLACKMARKET Tunisie"


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
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        log.error("Resend rejected %r (%s): %s", message["subject"], exc.code, exc.read()[:500])
    except (urllib.error.URLError, TimeoutError):
        log.exception("Email %r could not be sent through Resend", message["subject"])


def _dispatch(message: dict[str, Any]) -> None:
    threading.Thread(target=_post, args=(message,), daemon=True).start()


def send(to: str, subject: str, html: str, text: str) -> None:
    if not to:
        return
    _dispatch({"to": [to], "subject": subject, "html": html, "text": text})


def _money(millimes: int) -> str:
    return f"{int(millimes) / 1000:.3f}".replace(".", ",") + " DT"


def _layout(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#0b0b0c;padding:24px 12px;'
        'font-family:Helvetica,Arial,sans-serif;color:#e8e8ea">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="max-width:520px;background:#141416;border:1px solid #26262a;border-radius:14px">'
        '<tr><td style="padding:22px 28px;border-bottom:1px solid #26262a;font-weight:700;'
        f'letter-spacing:.14em;font-size:13px;color:#ffffff">{BRAND.upper()}</td></tr>'
        f'<tr><td style="padding:28px">'
        f'<h1 style="margin:0 0 16px;font-size:21px;color:#ffffff">{escape(title)}</h1>'
        f'<div style="font-size:15px;line-height:1.6;color:#c9c9cf">{body}</div>'
        "</td></tr>"
        '<tr><td style="padding:18px 28px;border-top:1px solid #26262a;font-size:12px;color:#7c7c85">'
        f"Cet email a été envoyé automatiquement par {BRAND}. Merci de ne pas y répondre."
        "</td></tr></table></td></tr></table></body></html>"
    )


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 14px">{text}</p>'


def _button(label: str, url: str) -> str:
    return (
        f'<p style="margin:22px 0"><a href="{escape(url)}" style="display:inline-block;background:#ffffff;'
        'color:#0b0b0c;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:10px">'
        f"{escape(label)}</a></p>"
    )


def _items_table(items: Sequence[dict[str, Any]], total_millimes: int) -> str:
    rows = "".join(
        '<tr><td style="padding:8px 0;border-bottom:1px solid #26262a">'
        f'{int(item["quantity"])} × {escape(str(item["offer_name"]))}</td>'
        '<td align="right" style="padding:8px 0;border-bottom:1px solid #26262a;white-space:nowrap">'
        f'{_money(item["total_millimes"])}</td></tr>'
        for item in items
    )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin:6px 0 18px;font-size:14px;color:#e8e8ea">{rows}'
        '<tr><td style="padding:10px 0;font-weight:700">Total</td>'
        f'<td align="right" style="padding:10px 0;font-weight:700">{_money(total_millimes)}</td></tr></table>'
    )


def _items_text(items: Sequence[dict[str, Any]], total_millimes: int) -> str:
    lines = [f'- {int(item["quantity"])} x {item["offer_name"]} : {_money(item["total_millimes"])}' for item in items]
    return "\n".join([*lines, f"Total : {_money(total_millimes)}"])


def _greeting(name: str) -> str:
    return f"Bonjour {name}," if name else "Bonjour,"


def send_verification_code(to: str, name: str, code: str, minutes: int) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph("Voici ton code pour confirmer ton adresse email :")
        + '<p style="margin:18px 0;font-size:32px;font-weight:700;letter-spacing:.32em;color:#ffffff">'
        f"{escape(code)}</p>"
        + _paragraph(f"Il expire dans {minutes} minutes. Ne le partage avec personne.")
        + _paragraph("Si tu n'as pas créé de compte, ignore simplement cet email.")
    )
    text = (
        f"{_greeting(name)}\n\nTon code de vérification {BRAND} : {code}\n\n"
        f"Il expire dans {minutes} minutes. Ne le partage avec personne.\n"
        "Si tu n'as pas créé de compte, ignore simplement cet email."
    )
    send(to, f"{code} est ton code de vérification", _layout("Confirme ton adresse email", body), text)


def send_welcome(to: str, name: str, site_url: str) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ton compte {BRAND} est prêt. Tu peux maintenant commander plus vite.")
        + _paragraph(
            "Chaque commande est vérifiée par un administrateur sur WhatsApp, puis livrée "
            "par email dès que ton paiement est confirmé."
        )
        + (_button("Découvrir le catalogue", site_url) if site_url else "")
    )
    text = (
        f"{_greeting(name)}\n\nTon compte {BRAND} est prêt. Tu peux maintenant commander plus vite.\n"
        "Chaque commande est vérifiée par un administrateur sur WhatsApp, puis livrée par email "
        "dès que ton paiement est confirmé."
        + (f"\n\n{site_url}" if site_url else "")
    )
    send(to, f"Bienvenue sur {BRAND}", _layout("Bienvenue !", body), text)


def send_password_reset(to: str, name: str, link: str) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Tu as demandé à réinitialiser le mot de passe de ton compte {BRAND}.")
        + _button("Choisir un nouveau mot de passe", link)
        + _paragraph("Ce lien expire dans une heure. Si tu n'es pas à l'origine de cette demande, ignore cet email.")
    )
    text = (
        f"{_greeting(name)}\n\nTu as demandé à réinitialiser le mot de passe de ton compte {BRAND}.\n"
        f"Choisis un nouveau mot de passe ici : {link}\n\n"
        "Ce lien expire dans une heure. Si tu n'es pas à l'origine de cette demande, ignore cet email."
    )
    send(to, "Réinitialise ton mot de passe", _layout("Réinitialise ton mot de passe", body), text)


def send_order_received(
    to: str,
    name: str,
    reference: str,
    items: Sequence[dict[str, Any]],
    total_millimes: int,
    method_label: str,
    whatsapp_url: str,
) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Nous avons bien reçu ta commande <strong>{escape(reference)}</strong>.")
        + _items_table(items, total_millimes)
        + _paragraph(
            f"Dernière étape : paie <strong>{_money(total_millimes)}</strong> par {escape(method_label)}, "
            "puis envoie ton reçu sur WhatsApp avec ta référence. Un administrateur le vérifie avant la livraison."
        )
        + _button("Envoyer mon reçu sur WhatsApp", whatsapp_url)
    )
    text = (
        f"{_greeting(name)}\n\nNous avons bien reçu ta commande {reference}.\n\n"
        f"{_items_text(items, total_millimes)}\n\n"
        f"Dernière étape : paie {_money(total_millimes)} par {method_label}, puis envoie ton reçu "
        f"sur WhatsApp avec ta référence : {whatsapp_url}"
    )
    send(to, f"Commande {reference} reçue", _layout("Commande reçue", body), text)


def send_payment_confirmed(
    to: str, name: str, reference: str, items: Sequence[dict[str, Any]], total_millimes: int
) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ton paiement pour la commande <strong>{escape(reference)}</strong> est confirmé.")
        + _items_table(items, total_millimes)
        + _paragraph("Nous préparons ta livraison. Tu recevras tes accès par email dès qu'elle est prête.")
    )
    text = (
        f"{_greeting(name)}\n\nTon paiement pour la commande {reference} est confirmé.\n\n"
        f"{_items_text(items, total_millimes)}\n\n"
        "Nous préparons ta livraison. Tu recevras tes accès par email dès qu'elle est prête."
    )
    send(to, f"Paiement confirmé — {reference}", _layout("Paiement confirmé", body), text)


def send_order_delivered(to: str, name: str, reference: str, items: Sequence[dict[str, Any]], content: str) -> None:
    """Email the delivery; without ``content`` the access details were sent on WhatsApp only."""
    lines = "".join(f"<li>{int(item['quantity'])} × {escape(str(item['offer_name']))}</li>" for item in items)
    if content:
        access_html = (
            _paragraph("<strong>Tes accès</strong>")
            + '<pre style="margin:0 0 18px;padding:14px;background:#0b0b0c;border:1px solid #26262a;'
            "border-radius:10px;white-space:pre-wrap;word-break:break-word;font-size:14px;color:#ffffff;"
            f'font-family:Menlo,Consolas,monospace">{escape(content)}</pre>'
            + _paragraph("Garde cet email en lieu sûr.")
        )
        access_text = f"Tes accès :\n{content}\n\nGarde cet email en lieu sûr."
    else:
        access_html = _paragraph("Tes accès t'ont été envoyés sur WhatsApp.")
        access_text = "Tes accès t'ont été envoyés sur WhatsApp."
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ta commande <strong>{escape(reference)}</strong> est livrée :")
        + f'<ul style="margin:0 0 16px;padding-left:20px">{lines}</ul>'
        + access_html
        + _paragraph("En cas de problème, contacte-nous sur WhatsApp avec ta référence.")
    )
    items_text = "\n".join(f"- {int(item['quantity'])} x {item['offer_name']}" for item in items)
    text = (
        f"{_greeting(name)}\n\nTa commande {reference} est livrée :\n{items_text}\n\n"
        f"{access_text}\n\n"
        "En cas de problème, contacte-nous sur WhatsApp avec ta référence."
    )
    send(to, f"Ta commande {reference} est livrée", _layout("Commande livrée", body), text)


def send_order_cancelled(to: str, name: str, reference: str, reason: str) -> None:
    body = (
        _paragraph(escape(_greeting(name)))
        + _paragraph(f"Ta commande <strong>{escape(reference)}</strong> a été annulée.")
        + (_paragraph(f"Motif : {escape(reason)}") if reason else "")
        + _paragraph("Si tu penses qu'il s'agit d'une erreur, contacte-nous sur WhatsApp avec ta référence.")
    )
    text = (
        f"{_greeting(name)}\n\nTa commande {reference} a été annulée."
        + (f"\nMotif : {reason}" if reason else "")
        + "\n\nSi tu penses qu'il s'agit d'une erreur, contacte-nous sur WhatsApp avec ta référence."
    )
    send(to, f"Commande {reference} annulée", _layout("Commande annulée", body), text)
