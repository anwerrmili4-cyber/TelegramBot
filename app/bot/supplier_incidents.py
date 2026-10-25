"""Credential-safe admin presentation for supplier delivery incidents."""

from __future__ import annotations

import html

import database as db
from app.domain import reseller_service
from config import CURRENCY


def supplier_delivery_problem_text(order_id, result):
    """Build a complete supplier delivery incident report."""
    order = db.get_order(int(order_id)) or {}
    offer = db.get_offer(order.get("offer_id")) if order.get("offer_id") else {}
    provider = str((offer or {}).get("supplier_provider") or "").strip().lower()
    provider_name = reseller_service.provider_display_name(provider)
    provider_bot = reseller_service.provider_bot_username(provider)
    buyer = db.get_conn().users.find_one(
        {"telegram_id": int(order.get("user_id") or 0)},
        {"_id": 0, "username": 1, "first_name": 1, "full_name": 1, "lang": 1},
    ) or {}
    fulfillment = db.get_conn().reseller_fulfillments.find_one(
        {"provider": provider, "external_order_id": f"BM-{int(order_id)}"},
        {"_id": 0, "encrypted_items": 0},
    ) or {}

    def safe(value, fallback="—"):
        normalized = str(value if value not in (None, "") else fallback).strip()
        return html.escape(normalized or fallback)

    username = str(buyer.get("username") or "").strip().lstrip("@")
    buyer_username = f"@{safe(username)}" if username else "Non renseigné"
    buyer_name = (
        buyer.get("full_name") or buyer.get("first_name") or "Non renseigné"
    )
    supplier_bot = (
        f'<a href="https://t.me/{safe(provider_bot)}">@{safe(provider_bot)}</a>'
        if provider_bot
        else "Non renseigné par le fournisseur"
    )
    supplier_order_id = fulfillment.get("supplier_order_id") or "Non retourné"
    payment_reference = order.get("txid") or "Wallet / aucune référence TXID"
    error_code = result.get("error_code") or "supplier_delivery_error"
    error_message = (
        result.get("error_message") or "Contenu de livraison non retourné"
    )
    incident_warning = (
        "La commande fournisseur peut déjà avoir été débitée. Vérifiez son statut "
        "avant toute nouvelle tentative afin d’éviter une double livraison."
        if error_code == "supplier_delivery_pending"
        else "Le fournisseur indique que la commande n’a pas été créée. Vérifiez "
        "tout de même son bot avant une livraison ou une nouvelle tentative."
    )
    return (
        "🚨 <b>ÉCHEC DE LIVRAISON API</b>\n\n"
        "🏪 <b>Fournisseur</b>\n"
        f"• Nom : <b>{safe(provider_name)}</b>\n"
        f"• Bot Telegram : {supplier_bot}\n"
        f"• Code fournisseur : <code>{safe(provider)}</code>\n"
        f"• Statut API : <code>{safe(fulfillment.get('status'))}</code>\n\n"
        "📦 <b>Commande</b>\n"
        f"• ID local : <b>#{int(order_id)}</b>\n"
        f"• Référence envoyée : <code>BM-{int(order_id)}</code>\n"
        f"• ID fournisseur : <code>{safe(supplier_order_id)}</code>\n"
        "• ID produit fournisseur : "
        f"<code>{safe((offer or {}).get('supplier_product_id'))}</code>\n"
        "• Produit : "
        f"<b>{safe(order.get('service_name'))} — {safe(order.get('offer_name'))}</b>\n"
        f"• Quantité : <b>{safe(order.get('qty'), '1')}</b>\n"
        "• Prix unitaire : "
        f"<b>{safe(order.get('unit_price'), '0')} {html.escape(CURRENCY)}</b>\n"
        "• Total : "
        f"<b>{safe(order.get('total_price'), '0')} {html.escape(CURRENCY)}</b>\n"
        f"• Statut local : <code>{safe(order.get('status'))}</code>\n\n"
        "👤 <b>Acheteur</b>\n"
        f"• Telegram ID : <code>{safe(order.get('user_id'))}</code>\n"
        f"• Nom : <b>{safe(buyer_name)}</b>\n"
        f"• Username : <b>{buyer_username}</b>\n"
        f"• Langue : <code>{safe(buyer.get('lang'))}</code>\n\n"
        "💳 <b>Paiement</b>\n"
        "• Méthode : "
        f"<code>{safe(order.get('verify_method') or order.get('payment_method'))}</code>\n"
        f"• TXID / référence : <code>{safe(payment_reference)}</code>\n\n"
        "❌ <b>Erreur</b>\n"
        f"• Code : <code>{safe(error_code)}</code>\n"
        f"• Détail : {safe(error_message)}\n\n"
        f"⚠️ {html.escape(incident_warning)}\n\n"
        "Utilisez les boutons ci-dessous pour informer l’acheteur ou effectuer "
        "une livraison manuelle."
    )


__all__ = ["supplier_delivery_problem_text"]
