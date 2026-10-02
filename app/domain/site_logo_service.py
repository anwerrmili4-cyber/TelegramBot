"""Service logos uploaded from the admin site space and shown on the storefront.

A logo arrives as a ``data:`` URL in the admin form and is stored in MongoDB as
raw bytes, one document per service. The service keeps a ``site_logo_version``
timestamp so the public URL changes on every upload and can be cached forever.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from typing import Any

from bson.binary import Binary

import database as db
from app.domain.storefront_receipt_service import _DATA_URL, _SIGNATURES

MAX_LOGO_BYTES = 500_000
PUBLIC_PATH = "/api/storefront/service-logo"


class LogoError(ValueError):
    """Validation error shown as-is in the admin UI."""


def decode(data_url: Any) -> tuple[bytes, str]:
    match = _DATA_URL.fullmatch(str(data_url or "").strip())
    if not match:
        raise LogoError("Le logo doit être une image PNG, JPEG ou WebP.")
    content_type, encoded = match.groups()
    try:
        data = base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise LogoError("Le fichier du logo est illisible.") from exc
    if not data or len(data) > MAX_LOGO_BYTES:
        raise LogoError("Le logo doit peser moins de 500 Ko.")
    if not _SIGNATURES[content_type](data):
        raise LogoError("Le fichier du logo est illisible.")
    return data, content_type


def save(service_id: int, data: bytes, content_type: str) -> int:
    version = time.time_ns() // 1_000_000
    conn = db.get_conn()
    conn.service_logos.update_one(
        {"service_id": int(service_id)},
        {"$set": {
            "service_id": int(service_id),
            "content_type": content_type,
            "size": len(data),
            "data": Binary(data),
            "updated_at": int(time.time()),
        }},
        upsert=True,
    )
    conn.services.update_one({"id": int(service_id)}, {"$set": {"site_logo_version": version}})
    return version


def remove(service_id: int) -> None:
    conn = db.get_conn()
    conn.service_logos.delete_one({"service_id": int(service_id)})
    conn.services.update_one({"id": int(service_id)}, {"$unset": {"site_logo_version": ""}})


def logo_url(service: dict[str, Any]) -> str:
    version = service.get("site_logo_version")
    if not version:
        return ""
    return f"{PUBLIC_PATH}?id={int(service['id'])}&v={int(version)}"


CATEGORY_LOGO_PATH = "/api/storefront/category-logo"


def save_category_logo(logo_id: int, data: bytes, content_type: str) -> int:
    """Store one logo for a product category, shared by every offer in it."""
    version = time.time_ns() // 1_000_000
    conn = db.get_conn()
    conn.category_logos.update_one(
        {"logo_id": int(logo_id)},
        {"$set": {
            "logo_id": int(logo_id),
            "content_type": content_type,
            "size": len(data),
            "data": Binary(data),
            "updated_at": int(time.time()),
        }},
        upsert=True,
    )
    return version


def remove_category_logo(logo_id: int) -> None:
    db.get_conn().category_logos.delete_one({"logo_id": int(logo_id)})


def category_logo_url(logo_id: Any, version: Any) -> str:
    try:
        logo_id = int(logo_id)
        version = int(version)
    except (TypeError, ValueError):
        return ""
    if logo_id <= 0 or version <= 0:
        return ""
    return f"{CATEGORY_LOGO_PATH}?id={logo_id}&v={version}"


def load_category_logo(logo_id: Any) -> tuple[bytes, str] | None:
    try:
        logo_id = int(logo_id)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().category_logos.find_one({"logo_id": logo_id})
    if not row:
        return None
    return bytes(row["data"]), str(row.get("content_type") or "application/octet-stream")


def load(service_id: Any) -> tuple[bytes, str] | None:
    try:
        service_id = int(service_id)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().service_logos.find_one({"service_id": service_id})
    if not row:
        return None
    return bytes(row["data"]), str(row.get("content_type") or "application/octet-stream")


MAX_OFFER_IMAGE_BYTES = 1_000_000
OFFER_IMAGE_PATH = "/api/storefront/offer-image"


def decode_offer_image(data_url: Any) -> tuple[bytes, str]:
    match = _DATA_URL.fullmatch(str(data_url or "").strip())
    if not match:
        raise LogoError("L’image doit être un fichier PNG, JPEG ou WebP.")
    content_type, encoded = match.groups()
    try:
        data = base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise LogoError("Le fichier de l’image est illisible.") from exc
    if not data or len(data) > MAX_OFFER_IMAGE_BYTES:
        raise LogoError("L’image doit peser moins de 1 Mo.")
    if not _SIGNATURES[content_type](data):
        raise LogoError("Le fichier de l’image est illisible.")
    return data, content_type


def save_offer_image(offer_id: int, data: bytes, content_type: str) -> str:
    """Store an uploaded product image and point the offer's site image at it."""
    version = time.time_ns() // 1_000_000
    conn = db.get_conn()
    conn.offer_images.update_one(
        {"offer_id": int(offer_id)},
        {"$set": {
            "offer_id": int(offer_id),
            "content_type": content_type,
            "size": len(data),
            "data": Binary(data),
            "updated_at": int(time.time()),
        }},
        upsert=True,
    )
    url = f"{OFFER_IMAGE_PATH}?id={int(offer_id)}&v={version}"
    conn.offers.update_one({"id": int(offer_id)}, {"$set": {"site_image_url": url}})
    return url


def remove_offer_image(offer_id: int) -> None:
    conn = db.get_conn()
    conn.offer_images.delete_one({"offer_id": int(offer_id)})
    conn.offers.update_one({"id": int(offer_id)}, {"$set": {"site_image_url": ""}})


def is_uploaded_offer_image(url: Any) -> bool:
    return str(url or "").startswith(f"{OFFER_IMAGE_PATH}?")


def load_offer_image(offer_id: Any) -> tuple[bytes, str] | None:
    try:
        offer_id = int(offer_id)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().offer_images.find_one({"offer_id": offer_id})
    if not row:
        return None
    return bytes(row["data"]), str(row.get("content_type") or "application/octet-stream")


MAX_OFFER_VIDEO_BYTES = 8_000_000
OFFER_VIDEO_PATH = "/api/storefront/offer-video"
_VIDEO_URL = re.compile(r"^data:(video/(?:mp4|webm));base64,([A-Za-z0-9+/=\s]+)$")
_VIDEO_SIGNATURES = {
    "video/mp4": lambda data: len(data) >= 12 and data[4:8] == b"ftyp",
    "video/webm": lambda data: data.startswith(b"\x1a\x45\xdf\xa3"),
}


def decode_offer_video(data_url: Any) -> tuple[bytes, str]:
    match = _VIDEO_URL.fullmatch(str(data_url or "").strip())
    if not match:
        raise LogoError("La vidéo doit être un fichier MP4 ou WebM.")
    content_type, encoded = match.groups()
    try:
        data = base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise LogoError("Le fichier de la vidéo est illisible.") from exc
    if not data or len(data) > MAX_OFFER_VIDEO_BYTES:
        raise LogoError("La vidéo doit peser moins de 8 Mo.")
    if not _VIDEO_SIGNATURES[content_type](data):
        raise LogoError("Le fichier de la vidéo est illisible.")
    return data, content_type


def save_offer_video(offer_id: int, data: bytes, content_type: str) -> str:
    """Store an uploaded product video and point the offer's site video at it."""
    version = time.time_ns() // 1_000_000
    conn = db.get_conn()
    conn.offer_videos.update_one(
        {"offer_id": int(offer_id)},
        {"$set": {
            "offer_id": int(offer_id),
            "content_type": content_type,
            "size": len(data),
            "data": Binary(data),
            "updated_at": int(time.time()),
        }},
        upsert=True,
    )
    url = f"{OFFER_VIDEO_PATH}?id={int(offer_id)}&v={version}"
    conn.offers.update_one({"id": int(offer_id)}, {"$set": {"site_video_url": url}})
    return url


def remove_offer_video(offer_id: int) -> None:
    conn = db.get_conn()
    conn.offer_videos.delete_one({"offer_id": int(offer_id)})
    conn.offers.update_one({"id": int(offer_id)}, {"$set": {"site_video_url": ""}})


def is_uploaded_offer_video(url: Any) -> bool:
    return str(url or "").startswith(f"{OFFER_VIDEO_PATH}?")


def load_offer_video(offer_id: Any) -> tuple[bytes, str] | None:
    try:
        offer_id = int(offer_id)
    except (TypeError, ValueError):
        return None
    row = db.get_conn().offer_videos.find_one({"offer_id": offer_id})
    if not row:
        return None
    return bytes(row["data"]), str(row.get("content_type") or "application/octet-stream")
