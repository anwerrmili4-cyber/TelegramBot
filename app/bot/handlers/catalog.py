"""Catalog command and deep-link navigation handlers."""

from __future__ import annotations

import asyncio

from telegram import LinkPreviewOptions
from telegram.constants import ParseMode

import database as db
import keyboards as kb
from app.bot.customer_text import premium_customer_text
from app.bot.offer_cards import compact_offer_text
from app.domain import reseller_service
from config import SHOP_NAME
from i18n import t


async def load_offer_with_live_stock(offer_id, *, wait_for_refresh=True):
    """Load a customer-visible offer and optionally wait for supplier stock."""
    offer = db.get_offer(offer_id)
    if not offer or not db.offer_is_listed_in_bot(offer):
        return None
    if db.is_bmc_vip_offer(offer):
        offer = db.get_offer(db.ensure_bmc_vip_offer())
        return offer if db.offer_is_listed_in_bot(offer) else None
    if wait_for_refresh:
        await asyncio.to_thread(reseller_service.refresh_supplier_stock, [offer])
        offer = db.get_offer(offer.get("id", offer_id))
    else:
        reseller_service.refresh_supplier_stock_in_background()
    return offer if db.offer_is_listed_in_bot(offer) else None


async def show_deep_link_offer(update, lang, offer_id):
    """Open one channel-advertised offer in the customer's private chat."""
    offer = await load_offer_with_live_stock(
        int(offer_id),
        wait_for_refresh=False,
    )
    if (
        not offer
        or not db.offer_is_listed_in_bot(offer)
        or not db.offer_has_stock(offer)
    ):
        await update.message.reply_text(
            premium_customer_text(lang, "out_of_stock"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.out_of_stock_keyboard(lang),
        )
        return
    detail_text = compact_offer_text(offer, lang)
    markup = kb.offer_detail_keyboard(lang, offer)
    if offer.get("photo_file_id"):
        if len(detail_text) <= 900:
            await update.message.reply_photo(
                photo=offer["photo_file_id"],
                caption=detail_text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        else:
            await update.message.reply_photo(photo=offer["photo_file_id"])
            await update.message.reply_text(
                detail_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=markup,
            )
        return
    await update.message.reply_text(
        detail_text,
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=markup,
    )


async def catalog_reply_markup(lang, notifications_enabled):
    """Build from saved stock, then refresh suppliers in the background."""
    markup = await asyncio.to_thread(
        kb.catalog_offers_keyboard,
        lang,
        notifications_enabled,
    )
    reseller_service.refresh_supplier_stock_in_background()
    return markup


async def show_catalog(update, context, lang):
    """Show the flat customer catalog from a command or callback update."""
    del context
    text = t(lang, "catalog_flat_title", shop=SHOP_NAME)
    message = update.message or update.callback_query.message
    notifications_enabled = db.catalog_notifications_enabled(
        update.effective_user.id,
    )
    await message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=await catalog_reply_markup(lang, notifications_enabled),
    )


async def show_service_offers(update, context, lang, service_id):
    """Open a service, skipping its catalog screen when it has one offer."""
    service_id = int(service_id)
    service = db.get_service(service_id)
    if not service or not db.is_bot_visible(service):
        await show_catalog(update, context, lang)
        return

    offers = db.list_offers(service_id)
    reseller_service.refresh_supplier_stock_in_background()
    if len(offers) == 1:
        await show_deep_link_offer(update, lang, offers[0]["id"])
        return

    await update.message.reply_text(
        t(
            lang,
            "service_title",
            emoji=service.get("emoji", "📦"),
            name=service.get("name", ""),
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.offers_keyboard(lang, service_id),
    )


__all__ = [
    "catalog_reply_markup",
    "load_offer_with_live_stock",
    "show_catalog",
    "show_deep_link_offer",
    "show_service_offers",
]
