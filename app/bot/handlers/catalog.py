"""Catalog command and deep-link navigation handlers."""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging

from telegram import LinkPreviewOptions
from telegram.constants import ParseMode

import database as db
import keyboards as kb
from app.bot.customer_text import premium_customer_text
from app.bot.media import send_cached_photo
from app.bot.offer_cards import compact_offer_text, offer_description_text
from app.domain import reseller_service
from config import CURRENCY, SHOP_NAME, public_base_url_from_environment
from i18n import t

log = logging.getLogger("bot")


def saved_listed_offer(offer_id):
    """Return the saved customer-visible offer without contacting a supplier."""
    offer = db.get_offer(offer_id)
    if not offer or not db.offer_is_listed_in_bot(offer):
        return None
    if db.is_bmc_vip_offer(offer):
        offer = db.get_offer(db.ensure_bmc_vip_offer())
        return offer if offer and db.offer_is_listed_in_bot(offer) else None
    return offer


async def load_offer_with_live_stock(offer_id, *, wait_for_refresh=True):
    """Load a customer-visible offer and optionally wait for supplier stock."""
    offer = saved_listed_offer(offer_id)
    if not offer or db.is_bmc_vip_offer(offer):
        return offer
    if wait_for_refresh:
        await asyncio.to_thread(reseller_service.refresh_supplier_stock, [offer])
        return saved_listed_offer(offer.get("id", offer_id))
    reseller_service.refresh_supplier_stock_in_background()
    return offer


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


async def handle_catalog_callback(
    update,
    context,
    lang,
    data,
    *,
    show_screen,
):
    """Handle catalog navigation callbacks and report whether one matched."""
    del context
    query = update.callback_query
    user_id = query.from_user.id

    if data.startswith("svc:"):
        service_id = int(data.split(":")[1])
        service = db.get_service(service_id)
        if not service or not db.is_bot_visible(service):
            await show_screen(
                query,
                t(lang, "catalog_flat_title", shop=SHOP_NAME),
                reply_markup=await catalog_reply_markup(
                    lang,
                    db.catalog_notifications_enabled(user_id),
                ),
            )
            return True
        offers = db.list_offers(service_id)
        reseller_service.refresh_supplier_stock_in_background()
        if len(offers) == 1:
            data = f"off:{offers[0]['id']}"
        else:
            await show_screen(
                query,
                t(
                    lang,
                    "service_title",
                    emoji=service.get("emoji", "📦"),
                    name=service.get("name", ""),
                ),
                reply_markup=kb.offers_keyboard(lang, service_id),
            )
            return True

    if data.startswith("offer_description:"):
        offer_id = int(data.split(":", 1)[1])
        offer = db.get_offer(offer_id)
        if db.is_bmc_vip_offer(offer):
            offer = db.get_offer(db.ensure_bmc_vip_offer())
        if not offer or not db.offer_is_listed_in_bot(offer):
            await query.message.reply_text(
                premium_customer_text(lang, "out_of_stock"),
                parse_mode=ParseMode.HTML,
                reply_markup=kb.out_of_stock_keyboard(lang),
            )
            return True
        await show_screen(
            query,
            offer_description_text(offer, lang),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=kb.offer_description_keyboard(lang, offer),
        )
        return True

    if not data.startswith("off:"):
        return False

    raw_offer_id = data.split(":")[1]
    try:
        offer_id = int(raw_offer_id)
    except (ValueError, TypeError):
        offer_id = raw_offer_id
    offer = db.get_offer(offer_id) or db.get_offer(str(raw_offer_id))
    if db.is_bmc_vip_offer(offer):
        offer = db.get_offer(db.ensure_bmc_vip_offer())
    if offer and db.offer_is_listed_in_bot(offer):
        reseller_service.refresh_supplier_stock_in_background()
    else:
        offer = None
    if (
        not offer
        or not db.offer_is_listed_in_bot(offer)
        or (
            not db.offer_has_stock(offer)
            and not db.is_bmc_vip_offer(offer)
        )
    ):
        await query.message.reply_text(
            premium_customer_text(lang, "out_of_stock"),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.out_of_stock_keyboard(lang),
        )
        return True
    try:
        detail_text = compact_offer_text(offer, lang)
    except Exception as exc:
        log.warning("compact_offer_text failed: %s", exc)
        detail_text = (
            f"🏷 <b>{html.escape(str(offer.get('name') or 'Offre'))}</b>\n\n"
            f"💎 <b>Prix :</b> {offer.get('price')} "
            f"{html.escape(str(offer.get('currency', CURRENCY)))}\n"
            f"📦 <b>Stock :</b> {offer.get('stock') or 0}"
        )

    photo_file_id = offer.get("photo_file_id")
    if photo_file_id:
        try:
            if len(detail_text) <= 900:
                await query.message.reply_photo(
                    photo=photo_file_id,
                    caption=detail_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb.offer_detail_keyboard(lang, offer),
                )
            else:
                await query.message.reply_photo(photo=photo_file_id)
                await query.message.reply_text(
                    detail_text,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                    reply_markup=kb.offer_detail_keyboard(lang, offer),
                )
            with contextlib.suppress(Exception):
                await query.message.delete()
            return True
        except Exception as exc:
            log.warning(
                "Failed to reply with offer photo %s: %s",
                photo_file_id,
                exc,
            )

    offer_name = str(offer.get("name") or "").lower()
    if "chat" in offer_name and "gpt" in offer_name:
        try:
            base_url = public_base_url_from_environment()
            await send_cached_photo(
                query.message.reply_photo,
                f"{base_url}/assets/chatgpt-plus-benefits.png",
                caption="🔥 *ChatGPT Plus Benefits*",
                parse_mode=ParseMode.MARKDOWN,
            )
            await query.message.reply_text(
                detail_text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=kb.offer_detail_keyboard(lang, offer),
            )
            with contextlib.suppress(Exception):
                await query.message.delete()
            return True
        except Exception as exc:
            log.warning("Failed to send ChatGPT photo: %s", exc)

    await show_screen(
        query,
        detail_text,
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=kb.offer_detail_keyboard(lang, offer),
    )
    return True


__all__ = [
    "catalog_reply_markup",
    "handle_catalog_callback",
    "load_offer_with_live_stock",
    "show_catalog",
    "show_deep_link_offer",
    "show_service_offers",
]
