"""Telegram payment and wallet top-up instructions."""

from __future__ import annotations

import html

from config import BINANCE_PAY_ID, BYBIT_UID, USDT_EVM_ADDRESS


def topup_provider_screen(lang, provider):
    is_bybit = provider == "bybit"
    provider_name = "Bybit Transfer (UID)" if is_bybit else "Binance Pay (ID)"
    pay_label = "Pay UID" if is_bybit else "Pay ID"
    pay_id = BYBIT_UID if is_bybit else BINANCE_PAY_ID
    txid_note = (
        "⚠️ <b>Bybit:</b> the Transaction ID is the code with dashes — not the "
        "long order/receipt number."
        if is_bybit
        else "⚠️ <b>Binance:</b> send the Transaction ID or Order ID from your "
        "Binance Pay receipt. No minimum deposit. Amounts below 0.01 USDT "
        "accumulate until they reach a spendable cent."
    )
    return (
        f"<b>{provider_name}</b>\n\n"
        f"<b>{pay_label}</b>\n<code>{html.escape(str(pay_id))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to deposit</b>\n"
        "<blockquote>1️⃣ Copy the ID above\n"
        "2️⃣ Send any USDT amount from your wallet/exchange\n"
        "3️⃣ Copy the Transaction ID (TXID)\n"
        "4️⃣ Paste the TXID here in this chat\n"
        "5️⃣ Auto-verify and instant credit ⚡</blockquote>\n\n"
        f"<blockquote>{txid_note}</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this "
        "screen for auto-credit.</blockquote>"
    )


def topup_onchain_screen(lang, network, amount):
    """Render BSC/Polygon top-ups in the compact payment-card style."""
    is_bsc = str(network).lower() == "bsc"
    network_label = "BSC (BEP20)" if is_bsc else "Polygon"
    contract_suffix = "97955" if is_bsc else "58e8f"
    return (
        f"<b>USDT TOP UP — {network_label}</b>\n\n"
        f"<b>Wallet Address</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to deposit</b>\n"
        "<blockquote>1️⃣ Copy the wallet address above\n"
        f"2️⃣ Send exactly <b>{float(amount):.2f} USDT</b>\n"
        f"3️⃣ Select only the <b>{network_label}</b> network\n"
        "4️⃣ Copy the Transaction ID (TXID/hash)\n"
        "5️⃣ Paste the TXID here in this chat\n"
        "6️⃣ Auto-verify and instant credit ⚡</blockquote>\n\n"
        f"<blockquote>⚠️ <b>{network_label} only:</b> verify that the USDT "
        f"contract address ends in <b>{contract_suffix}</b>.</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this screen "
        "for auto-credit.</blockquote>"
    )


def onchain_payment_screen(lang, order):
    method = order.get("payment_method")
    network = "BSC (BEP20)" if method == "usdt_bsc" else "Polygon"
    contract_suffix = "97955" if method == "usdt_bsc" else "58e8f"
    return (
        f"<b>USDT PAYMENT — {network}</b>\n\n"
        f"<b>Product</b>\n{html.escape(str(order.get('offer_name') or '—'))}\n"
        f"<b>Order</b>\n#{int(order['id'])}\n\n"
        f"<b>Wallet Address</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
        "👇 <i>Tap the button below to copy</i>\n\n"
        "<b>How to pay</b>\n"
        "<blockquote>1️⃣ Copy the wallet address above\n"
        f"2️⃣ Send exactly <b>{float(order['total_price']):.2f} USDT</b>\n"
        f"3️⃣ Select only the <b>{network}</b> network\n"
        "4️⃣ Copy the Transaction ID (TXID/hash)\n"
        "5️⃣ Tap Submit TXID and paste it in this chat\n"
        "6️⃣ Auto-verify and begin delivery ⚡</blockquote>\n\n"
        f"<blockquote>⚠️ <b>{network} only:</b> verify that the USDT contract "
        f"address ends in <b>{contract_suffix}</b>.</blockquote>\n\n"
        "<blockquote>⏰ Complete payment within 30 minutes of opening this screen "
        "for automatic verification.</blockquote>"
    )


__all__ = [
    "onchain_payment_screen",
    "topup_onchain_screen",
    "topup_provider_screen",
]
