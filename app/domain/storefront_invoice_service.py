"""Invoices for paid storefront carts.

An invoice is issued once per cart, the moment its payment is confirmed (from
the wallet or after the admin checks the transfer receipt). It snapshots the
customer, the paid lines and the payment, so later edits to an offer or an
account never change a document the customer already received. The PDF is
rebuilt from that snapshot whenever it is downloaded.

Seller details printed on the invoice come from ``INVOICE_SELLER_NAME``,
``INVOICE_SELLER_ADDRESS`` and ``INVOICE_SELLER_TAX_ID``.
"""

from __future__ import annotations

import io
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from pymongo.errors import DuplicateKeyError

import database as db
from app.constants import OrderStatus
from app.domain import email_service

log = logging.getLogger(__name__)

TUNIS_TZ = timezone(timedelta(hours=1))
LOGO_PATH = Path(__file__).resolve().parents[2] / "storefront" / "public" / "logo.png"
_PAID_STATUSES = {
    str(OrderStatus.PAID),
    str(OrderStatus.PAYMENT_CONFIRMED),
    str(OrderStatus.PREPARING_DELIVERY),
    str(OrderStatus.DELIVERED),
}


def _seller() -> dict[str, str]:
    return {
        "name": os.getenv("INVOICE_SELLER_NAME", "").strip() or email_service.BRAND,
        "address": os.getenv("INVOICE_SELLER_ADDRESS", "").strip(),
        "tax_id": os.getenv("INVOICE_SELLER_TAX_ID", "").strip(),
        "site": email_service.site_url().removeprefix("https://").removeprefix("http://"),
    }


def _money(millimes: int) -> str:
    return f"{int(millimes) / 1000:,.3f}".replace(",", " ").replace(".", ",") + " DT"


def _date(timestamp: Any) -> str:
    if not timestamp:
        return "—"
    return datetime.fromtimestamp(int(timestamp), tz=TUNIS_TZ).strftime("%d/%m/%Y")


def _method_label(method: str) -> str:
    from app.domain import site_orders_service

    return site_orders_service.method_label(method)


# ---------------------------------------------------------------------------
# Issuing
# ---------------------------------------------------------------------------


def issue(reference: str) -> dict[str, Any] | None:
    """Create and email the invoice of a paid cart; ``None`` if it already has one."""
    conn = db.get_conn()
    if conn.storefront_invoices.find_one({"cart_reference": reference}, {"_id": 1}):
        return None
    lines = sorted(
        conn.orders.find({"sales_channel": "tn_site", "cart_reference": reference}),
        key=lambda line: int(line.get("cart_position") or 0),
    )
    paid = [line for line in lines if str(line.get("status")) in _PAID_STATUSES]
    if not paid:
        return None

    first = paid[0]
    now = int(time.time())
    invoice_id = db._next_id("storefront_invoices")
    year = datetime.fromtimestamp(now, tz=TUNIS_TZ).year
    method = str(first.get("payment_method") or "")
    invoice = {
        "id": invoice_id,
        "number": f"FAC-{year}-{invoice_id:05d}",
        "cart_reference": reference,
        "customer_id": first.get("customer_id"),
        "customer_name": first.get("customer_name", ""),
        "customer_email": first.get("customer_email", ""),
        "customer_phone": str(first.get("customer_phone") or ""),
        "items": [
            {
                "service_name": line.get("service_name", ""),
                "offer_name": line.get("offer_name", ""),
                "period_days": int(line.get("period_days") or 0),
                "quantity": int(line.get("qty") or 1),
                "unit_millimes": int(line.get("unit_price_millimes") or 0),
                "total_millimes": int(line.get("total_millimes") or 0),
            }
            for line in paid
        ],
        "total_millimes": sum(int(line.get("total_millimes") or 0) for line in paid),
        "refunded_millimes": 0,
        "payment_method": method,
        "payment_label": _method_label(method),
        "transaction_reference": first.get("payment_reference", ""),
        "paid_at": max(int(line.get("paid_at") or 0) for line in paid) or now,
        "issued_at": now,
        "seller": _seller(),
    }
    try:
        conn.storefront_invoices.insert_one(dict(invoice))
    except DuplicateKeyError:
        return None
    db.audit_event("storefront.invoice_issued", details={"number": invoice["number"], "cart_reference": reference})

    if not invoice["customer_email"]:
        return invoice
    email_service.send_invoice(
        invoice["customer_email"],
        invoice["customer_name"],
        invoice["number"],
        reference,
        invoice["items"],
        invoice["total_millimes"],
        invoice["payment_label"],
        render_pdf(invoice),
    )
    return invoice


def issue_quietly(reference: str) -> None:
    """Issue the invoice without ever failing the payment that triggered it."""
    try:
        issue(reference)
    except Exception:
        log.exception("Invoice for cart %s could not be issued", reference)


def record_refund(reference: str, refunded_millimes: int) -> None:
    if refunded_millimes > 0:
        db.get_conn().storefront_invoices.update_one(
            {"cart_reference": reference},
            {"$inc": {"refunded_millimes": int(refunded_millimes)}, "$set": {"refunded_at": int(time.time())}},
        )


def find(reference: str, customer_id: int | None = None) -> dict[str, Any] | None:
    query: dict[str, Any] = {"cart_reference": str(reference or "").strip().upper()}
    if customer_id is not None:
        query["customer_id"] = int(customer_id)
    return db.get_conn().storefront_invoices.find_one(query, {"_id": 0})


def numbers_for(references: list[str]) -> dict[str, str]:
    rows = db.get_conn().storefront_invoices.find(
        {"cart_reference": {"$in": references}}, {"cart_reference": 1, "number": 1, "_id": 0}
    )
    return {row["cart_reference"]: row["number"] for row in rows}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _latin(value: Any) -> str:
    """Helvetica only covers Windows-1252; drop emoji and other symbols."""
    return str(value or "").encode("cp1252", "ignore").decode("cp1252").strip()


def _period(days: int) -> str:
    if not days:
        return ""
    if days % 365 == 0:
        years = days // 365
        return f"{years} an{'s' if years > 1 else ''}"
    if days % 30 == 0:
        return f"{days // 30} mois"
    return f"{days} jour{'s' if days > 1 else ''}"


def render_pdf(invoice: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink = colors.HexColor("#111114")
    muted = colors.HexColor("#6b6b75")
    line = colors.HexColor("#e6e6ea")
    brand = colors.HexColor("#e03a30")
    wash = colors.HexColor("#fdf1f0")
    dark = colors.HexColor("#0b0b0d")
    green = colors.HexColor("#16a34a")

    seller = invoice.get("seller") or _seller()
    width, height = A4
    margin = 18 * mm
    band = 44 * mm

    def text(size: float = 9.5, color: Any = ink, bold: bool = False, align: int = 0, leading: float | None = None):
        return ParagraphStyle(
            "s",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,
            leading=leading or size * 1.4,
            textColor=color,
            alignment=align,
        )

    def para(value: Any, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(_latin(value)).replace("\n", "<br/>"), style)

    def decorate(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(dark)
        canvas.rect(0, height - band, width, band, stroke=0, fill=1)
        canvas.setFillColor(brand)
        canvas.rect(0, height - band - 1.4 * mm, width, 1.4 * mm, stroke=0, fill=1)
        logo_size = 22 * mm
        logo_y = height - band + (band - logo_size) / 2
        if LOGO_PATH.exists():
            canvas.drawImage(
                str(LOGO_PATH), margin - 3 * mm, logo_y, logo_size, logo_size, mask="auto", preserveAspectRatio=True
            )
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(margin + 21 * mm, height - band / 2 + 1 * mm, "BLACKMARKET")
        canvas.setFillColor(brand)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(margin + 21 * mm, height - band / 2 - 4.5 * mm, "T U N I S I E")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawRightString(width - margin, height - band / 2 + 1 * mm, "FACTURE")
        canvas.setFillColor(colors.HexColor("#b4b4bd"))
        canvas.setFont("Helvetica", 10)
        canvas.drawRightString(width - margin, height - band / 2 - 5 * mm, _latin(invoice["number"]))

        canvas.setStrokeColor(line)
        canvas.line(margin, 20 * mm, width - margin, 20 * mm)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7.5)
        legal = " · ".join(
            part
            for part in (
                _latin(seller.get("name")),
                _latin(seller.get("address")),
                f"MF : {_latin(seller['tax_id'])}" if seller.get("tax_id") else "",
                _latin(seller.get("site")),
            )
            if part
        )
        canvas.drawString(margin, 15 * mm, legal[:150])
        canvas.drawString(margin, 11 * mm, "Montants en dinars tunisiens (TND), toutes taxes comprises.")
        canvas.drawRightString(width - margin, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=band + 12 * mm,
        bottomMargin=26 * mm,
        title=f"Facture {invoice['number']}",
        author=_latin(seller.get("name")),
    )
    content_width = width - 2 * margin

    label = text(7.5, muted, bold=True)
    seller_lines = [
        seller.get("name"),
        seller.get("address"),
        f"Matricule fiscal : {seller['tax_id']}" if seller.get("tax_id") else "",
        seller.get("site"),
    ]
    customer_lines = [invoice.get("customer_name") or "Client", invoice.get("customer_email"), invoice.get("customer_phone")]
    meta = [
        ("Date d'émission", _date(invoice.get("issued_at"))),
        ("Commande", invoice.get("cart_reference")),
        ("Paiement", invoice.get("payment_label")),
        ("Réf. transaction", invoice.get("transaction_reference") or "—"),
        ("Payée le", _date(invoice.get("paid_at"))),
    ]

    def block(title: str, rows: list[Any]) -> list[Any]:
        filled = [row for row in rows if row]
        return [para(title, label), Spacer(1, 2 * mm)] + [
            para(row, text(10 if index == 0 else 9, ink if index == 0 else muted, bold=index == 0))
            for index, row in enumerate(filled)
        ]

    meta_table = Table(
        [[para(key, text(8.5, muted)), para(value, text(8.5, ink, bold=True, align=TA_RIGHT))] for key, value in meta],
        colWidths=[30 * mm, 34 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f6f8")),
        ("BOX", (0, 0), (-1, -1), 0.6, line),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    parties = Table(
        [[block("ÉMISE PAR", seller_lines), block("FACTURÉE À", customer_lines), meta_table]],
        colWidths=[content_width * 0.3, content_width * 0.3, content_width * 0.4],
    )
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (1, 0), 10),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))

    header = ["Désignation", "Qté", "Prix unitaire", "Total"]
    rows: list[list[Any]] = [[para(cell, text(8, colors.white, bold=True, align=TA_RIGHT if i else 0)) for i, cell in enumerate(header)]]
    for item in invoice["items"]:
        details = " · ".join(part for part in (_latin(item.get("service_name")), _period(item.get("period_days", 0))) if part)
        description = f"<b>{escape(_latin(item.get('offer_name')))}</b>" + (
            f"<br/><font color='#6b6b75' size='8'>{escape(details)}</font>" if details else ""
        )
        rows.append([
            Paragraph(description, text(9.5)),
            para(item["quantity"], text(9.5, align=TA_RIGHT)),
            para(_money(item["unit_millimes"]), text(9.5, align=TA_RIGHT)),
            para(_money(item["total_millimes"]), text(9.5, bold=True, align=TA_RIGHT)),
        ])
    items_table = Table(rows, colWidths=[content_width * 0.52, content_width * 0.1, content_width * 0.19, content_width * 0.19], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), dark),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, line),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafb")]),
    ]))

    total = int(invoice["total_millimes"])
    refunded = int(invoice.get("refunded_millimes") or 0)
    totals_rows = [[para("Sous-total", text(9.5, muted)), para(_money(total), text(9.5, align=TA_RIGHT))]]
    if refunded:
        totals_rows.append([para("Remboursé sur le portefeuille", text(9.5, muted)), para(f"- {_money(refunded)}", text(9.5, brand, align=TA_RIGHT))])
    totals_rows.append([
        para("Total payé TTC" if not refunded else "Net payé TTC", text(11, ink, bold=True)),
        para(_money(total - refunded), text(13, brand, bold=True, align=TA_RIGHT)),
    ])
    totals = Table(totals_rows, colWidths=[48 * mm, 34 * mm])
    totals.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
        ("BACKGROUND", (0, -1), (-1, -1), wash),
    ]))

    status_text = "PAYÉE" if not refunded else ("REMBOURSÉE" if refunded >= total else "PAYÉE · REMBOURSEMENT PARTIEL")
    stamp = Table(
        [[para(status_text, text(10, colors.white if not refunded else brand, bold=True))]],
        colWidths=[34 * mm if not refunded else 70 * mm],
        hAlign="LEFT",
    )
    stamp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), green if not refunded else wash),
        ("BOX", (0, 0), (-1, -1), 0.8, green if not refunded else brand),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    summary = Table([[stamp, totals]], colWidths=[content_width - 84 * mm, 84 * mm])
    summary.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))

    story = [
        parties,
        Spacer(1, 10 * mm),
        items_table,
        Spacer(1, 6 * mm),
        summary,
        Spacer(1, 12 * mm),
        para("Merci pour ta confiance !", text(11, ink, bold=True)),
        Spacer(1, 1.5 * mm),
        para(
            "Tes accès restent disponibles à tout moment dans ton espace client, rubrique « Mes commandes ».",
            text(9, muted),
        ),
    ]
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
