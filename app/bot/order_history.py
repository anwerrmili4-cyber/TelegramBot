"""Group and export customer order history."""

from __future__ import annotations

from datetime import UTC, datetime

import database as db
from app.domain import order_service, warranty_service
from config import CURRENCY
from i18n import status_label


def order_service_groups(orders):
    service_emojis = {
        service["name"]: service.get("emoji", "📦")
        for service in db.list_services()
    }
    grouped = {}
    for order in orders:
        name = str(order.get("service_name") or "Other")
        grouped.setdefault(
            name,
            {
                "name": name,
                "emoji": service_emojis.get(name, "📦"),
                "orders": [],
            },
        )["orders"].append(order)
    groups = sorted(
        grouped.values(),
        key=lambda group: (-len(group["orders"]), group["name"].lower()),
    )
    for group in groups:
        group["count"] = len(group["orders"])
    return groups


def orders_text_export(lang, orders, title):
    lines = [
        f"PURCHASE HISTORY — {title}",
        "=" * max(32, len(title) + 19),
        "",
    ]
    for order in orders:
        created_at = order.get("created_at")
        delivered_at = order.get("delivered_at")
        purchase_date = (
            datetime.fromtimestamp(created_at, UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC",
            )
            if created_at
            else "—"
        )
        delivery_date = (
            datetime.fromtimestamp(delivered_at, UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC",
            )
            if delivered_at
            else "—"
        )
        qty = max(1, int(order.get("qty") or 1))
        unit_price = float(order.get("unit_price") or 0)
        wallet_amount = float(order.get("wallet_amount") or 0)
        external_amount = float(order.get("total_price") or 0)
        paid_total = round(wallet_amount + external_amount, 2)
        gross_total = float(
            order.get("gross_total")
            if order.get("gross_total") is not None
            else unit_price * qty
            if unit_price
            else paid_total
        )
        offer = (
            db.get_offer(order.get("offer_id")) if order.get("offer_id") else None
        )
        warranty = (
            "FW"
            if warranty_service.has_full_warranty(order)
            else str(order.get("warranty") or "").strip()
        )
        if not warranty and offer:
            warranty = (
                "FW"
                if warranty_service.has_full_warranty(offer)
                else str(offer.get("note") or "").strip()
                or warranty_service.offer_warranty_label(offer, lang=lang)
            )
        warranty = warranty or "No warranty information recorded"
        delivered_content = order_service.delivery_content_for_order(order)
        payment_method = str(
            order.get("verify_method") or order.get("payment_method") or "—",
        )
        txid = str(order.get("txid") or "—")
        currency = order.get("currency", CURRENCY)
        lines.extend([
            f"ORDER #{order['id']}",
            "-" * 32,
            f"Service: {order.get('service_name') or '—'}",
            f"Offer: {order.get('offer_name') or '—'}",
            f"Quantity: {qty}",
            f"Unit price: {unit_price:.2f} {currency}",
            f"Catalog total: {gross_total:.2f} {currency}",
            f"Total paid: {paid_total:.2f} {currency}",
            f"Status: {status_label(lang, order.get('status', ''))}",
            f"Purchase date: {purchase_date}",
            f"Delivery date: {delivery_date}",
            f"Payment method: {payment_method}",
            f"Transaction ID: {txid}",
            f"Warranty: {warranty}",
            "",
            "PURCHASE CONTENT",
            "-" * 32,
            delivered_content or "Content not delivered or no longer available.",
            "",
            "=" * 48,
            "",
        ])
    return "\n".join(lines)


__all__ = ["order_service_groups", "orders_text_export"]
