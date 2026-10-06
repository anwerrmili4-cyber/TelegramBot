"""Payment receipt screenshots uploaded by storefront customers.

A receipt arrives as a ``data:`` URL inside the JSON body and is stored in
private object storage when configured, with legacy MongoDB support.
Only PNG, JPEG and WebP are kept, and the declared type
must match the file's own signature so nothing else can be served back to the
admin as an image.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from typing import Any

from bson.binary import Binary

import database as db
from app.domain import receipt_object_storage

MAX_RECEIPT_BYTES = 2_500_000
# Base64 grows the file by a third; the JSON envelope adds little on top.
MAX_UPLOAD_BODY_BYTES = MAX_RECEIPT_BYTES * 4 // 3 + 20_000

_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$")
_SIGNATURES = {
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda data: data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}


class ReceiptError(ValueError):
    """Validation error safe to show to the customer."""


def store(data_url: Any, *, customer_id: int, purpose: str) -> int:
    match = _DATA_URL.fullmatch(str(data_url or "").strip())
    if not match:
        raise ReceiptError("Joins une capture de ton reçu (PNG, JPEG ou WebP).")
    content_type, encoded = match.groups()
    try:
        data = base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ReceiptError("La capture du reçu est illisible.") from exc
    if not data or len(data) > MAX_RECEIPT_BYTES:
        raise ReceiptError("La capture du reçu doit peser moins de 2,5 Mo.")
    if not _SIGNATURES[content_type](data):
        raise ReceiptError("La capture du reçu est illisible.")

    receipt_id = db._next_id("storefront_receipts")
    row = {
        "id": receipt_id,
        "customer_id": int(customer_id),
        "purpose": purpose,
        "content_type": content_type,
        "size": len(data),
        "created_at": int(time.time()),
    }
    if receipt_object_storage.configured():
        row.update(receipt_object_storage.upload(data, content_type))
    else:
        row["data"] = Binary(data)
    db.get_conn().storefront_receipts.insert_one(row)
    return receipt_id


def load(receipt_id: Any) -> tuple[bytes, str] | None:
    try:
        receipt_id = int(receipt_id)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().storefront_receipts.find_one({"id": receipt_id})
    if not row:
        return None
    return load_row(row)


def load_row(row: dict) -> tuple[bytes, str]:
    """Load a row after its caller has checked ownership/authorization."""
    data = (receipt_object_storage.read(row) if row.get("object_key")
            else bytes(row["data"]))
    return data, str(row.get("content_type") or "application/octet-stream")
