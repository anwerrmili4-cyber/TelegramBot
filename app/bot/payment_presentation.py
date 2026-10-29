"""Telegram payment and wallet top-up instructions."""

from __future__ import annotations

import html

from config import BINANCE_PAY_ID, BYBIT_UID, USDT_EVM_ADDRESS


def topup_provider_screen(lang, provider):
    is_bybit = provider == "bybit"
    provider_name = "Bybit Transfer (UID)" if is_bybit else "Binance Pay (ID)"
    pay_label = "Pay UID" if is_bybit else "Pay ID"
    pay_id = BYBIT_UID if is_bybit else BINANCE_PAY_ID
    if lang == "ar":
        provider_name = "تحويل Bybit (UID)" if is_bybit else "Binance Pay (المعرّف)"
        pay_label = "معرّف الدفع UID" if is_bybit else "معرّف الدفع"
        txid_note = (
            "⚠️ <b>Bybit:</b> رقم المعاملة هو الرمز الذي يحتوي على شرطات — وليس "
            "رقم الطلب أو الإيصال الطويل."
            if is_bybit
            else "⚠️ <b>Binance:</b> أرسل رقم المعاملة أو رقم الطلب من إيصال "
            "Binance Pay. لا يوجد حد أدنى للإيداع. المبالغ الأقل من 0.01 USDT "
            "تتراكم حتى تصل إلى سنت قابل للاستخدام."
        )
        return (
            f"<b>{provider_name}</b>\n\n"
            f"<b>{pay_label}</b>\n<code>{html.escape(str(pay_id))}</code>\n"
            "👇 <i>اضغط الزر أدناه للنسخ</i>\n\n"
            "<b>طريقة الإيداع</b>\n"
            "<blockquote>1️⃣ انسخ المعرّف أعلاه\n"
            "2️⃣ أرسل أي مبلغ USDT من محفظتك أو منصتك\n"
            "3️⃣ انسخ رقم المعاملة (TXID)\n"
            "4️⃣ الصق رقم المعاملة هنا في هذه المحادثة\n"
            "5️⃣ التحقق التلقائي وإضافة الرصيد فوراً ⚡</blockquote>\n\n"
            f"<blockquote>{txid_note}</blockquote>\n\n"
            "<blockquote>⏰ أكمل الدفع خلال 30 دقيقة من فتح هذه "
            "الشاشة لإضافة الرصيد تلقائياً.</blockquote>"
        )
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
    if lang == "ar":
        return (
            f"<b>شحن USDT — {network_label}</b>\n\n"
            f"<b>عنوان المحفظة</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
            "👇 <i>اضغط الزر أدناه للنسخ</i>\n\n"
            "<b>طريقة الإيداع</b>\n"
            "<blockquote>1️⃣ انسخ عنوان المحفظة أعلاه\n"
            f"2️⃣ أرسل بالضبط <b>{float(amount):.2f} USDT</b>\n"
            f"3️⃣ اختر شبكة <b>{network_label}</b> فقط\n"
            "4️⃣ انسخ رقم المعاملة (TXID/الهاش)\n"
            "5️⃣ الصق رقم المعاملة هنا في هذه المحادثة\n"
            "6️⃣ التحقق التلقائي وإضافة الرصيد فوراً ⚡</blockquote>\n\n"
            f"<blockquote>⚠️ <b>{network_label} فقط:</b> تأكد أن عنوان عقد USDT "
            f"ينتهي بـ <b>{contract_suffix}</b>.</blockquote>\n\n"
            "<blockquote>⏰ أكمل الدفع خلال 30 دقيقة من فتح هذه الشاشة "
            "لإضافة الرصيد تلقائياً.</blockquote>"
        )
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
    if lang == "ar":
        return (
            f"<b>دفع USDT — {network}</b>\n\n"
            f"<b>المنتج</b>\n{html.escape(str(order.get('offer_name') or '—'))}\n"
            f"<b>الطلب</b>\n#{int(order['id'])}\n\n"
            f"<b>عنوان المحفظة</b>\n<code>{html.escape(str(USDT_EVM_ADDRESS))}</code>\n"
            "👇 <i>اضغط الزر أدناه للنسخ</i>\n\n"
            "<b>طريقة الدفع</b>\n"
            "<blockquote>1️⃣ انسخ عنوان المحفظة أعلاه\n"
            f"2️⃣ أرسل بالضبط <b>{float(order['total_price']):.2f} USDT</b>\n"
            f"3️⃣ اختر شبكة <b>{network}</b> فقط\n"
            "4️⃣ انسخ رقم المعاملة (TXID/الهاش)\n"
            "5️⃣ اضغط إرسال رقم المعاملة والصقه في هذه المحادثة\n"
            "6️⃣ التحقق التلقائي وبدء التسليم ⚡</blockquote>\n\n"
            f"<blockquote>⚠️ <b>{network} فقط:</b> تأكد أن عنوان عقد USDT "
            f"ينتهي بـ <b>{contract_suffix}</b>.</blockquote>\n\n"
            "<blockquote>⏰ أكمل الدفع خلال 30 دقيقة من فتح هذه الشاشة "
            "للتحقق التلقائي.</blockquote>"
        )
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
