"""WebAuthn passkeys for sensitive administrator operations.

Biometric data stays inside the platform authenticator.  The server stores only
the public credential required to verify a signed WebAuthn assertion.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import database as db
from config import public_base_url_from_environment
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


class PasskeyError(ValueError):
    """Safe error suitable for the administrator UI."""


CHALLENGE_TTL_SECONDS = 5 * 60
MAX_PASSKEYS = 2


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _rp() -> tuple[str, str]:
    configured = public_base_url_from_environment()
    parsed = urlsplit(configured)
    host = (parsed.hostname or "localhost").lower()
    scheme = parsed.scheme or ("http" if host in {"localhost", "127.0.0.1"} else "https")
    port = f":{parsed.port}" if parsed.port else ""
    return host, f"{scheme}://{host}{port}"


def _credential_descriptor(row: dict) -> PublicKeyCredentialDescriptor:
    return PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))


def _new_challenge(kind: str, challenge: bytes) -> str:
    challenge_id = secrets.token_urlsafe(24)
    now = datetime.now(UTC)
    db.get_conn().admin_webauthn_challenges.insert_one({
        "challenge_id": challenge_id,
        "kind": kind,
        "challenge": challenge,
        "created_at": now,
        "expires_at": now + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    })
    return challenge_id


def _consume_challenge(challenge_id: object, kind: str) -> bytes:
    row = db.get_conn().admin_webauthn_challenges.find_one_and_delete({
        "challenge_id": str(challenge_id or ""),
        "kind": kind,
        "expires_at": {"$gt": datetime.now(UTC)},
    })
    if not row:
        raise PasskeyError("La demande biométrique a expiré. Recommencez.")
    return bytes(row["challenge"])


def status() -> dict:
    rows = list(db.get_conn().admin_passkeys.find({}, {
        "_id": 0, "credential_id": 1, "label": 1, "created_at": 1, "last_used_at": 1,
    }).sort("created_at", 1))
    for row in rows:
        row["id"] = hashlib.sha256(row.pop("credential_id").encode()).hexdigest()[:16]
    rp_id, _ = _rp()
    return {
        "ok": True,
        "supported": True,
        "rp_id": rp_id,
        "max_passkeys": MAX_PASSKEYS,
        "passkeys": rows,
    }


def registration_options() -> dict:
    rows = list(db.get_conn().admin_passkeys.find({}, {"credential_id": 1}))
    if len(rows) >= MAX_PASSKEYS:
        raise PasskeyError("Deux appareils sont déjà enregistrés. Révoquez-en un avant d’en ajouter un autre.")
    rp_id, _ = _rp()
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="BlackMarket Control Center",
        user_name="admin",
        user_display_name="Administrateur",
        user_id=hashlib.sha256(b"blackmarket-admin-passkey-v1").digest(),
        challenge=challenge,
        timeout=60_000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[_credential_descriptor(row) for row in rows],
    )
    return {"ok": True, "challenge_id": _new_challenge("register", challenge), "publicKey": json.loads(options_to_json(options))}


def register(challenge_id: object, credential: object, label: object) -> dict:
    challenge = _consume_challenge(challenge_id, "register")
    rp_id, origin = _rp()
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise PasskeyError("Face ID ou Windows Hello n’a pas pu être vérifié.") from exc
    credential_id = _b64url(verified.credential_id)
    clean_label = " ".join(str(label or "Appareil biométrique").split())[:60]
    now = datetime.now(UTC)
    if db.get_conn().admin_passkeys.count_documents({}) >= MAX_PASSKEYS:
        raise PasskeyError("La limite de deux appareils enregistrés est atteinte.")
    db.get_conn().admin_passkeys.update_one(
        {"credential_id": credential_id},
        {"$setOnInsert": {
            "credential_id": credential_id,
            "public_key": verified.credential_public_key,
            "sign_count": int(verified.sign_count),
            "device_type": str(verified.credential_device_type.value),
            "backed_up": bool(verified.credential_backed_up),
            "label": clean_label,
            "created_at": now,
        }},
        upsert=True,
    )
    db.audit_event("admin.passkey_registered", details={"label": clean_label})
    return {"ok": True, "message": f"{clean_label} est maintenant autorisé."}


def authentication_options() -> dict:
    rows = list(db.get_conn().admin_passkeys.find({}, {"credential_id": 1}))
    if not rows:
        raise PasskeyError("Aucun appareil Face ID ou Windows Hello n’est enregistré.")
    rp_id, _ = _rp()
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        timeout=60_000,
        allow_credentials=[_credential_descriptor(row) for row in rows],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {"ok": True, "challenge_id": _new_challenge("authenticate", challenge), "publicKey": json.loads(options_to_json(options))}


def authenticate(challenge_id: object, credential: object) -> dict:
    challenge = _consume_challenge(challenge_id, "authenticate")
    credential_id = str((credential or {}).get("id") if isinstance(credential, dict) else "")
    row = db.get_conn().admin_passkeys.find_one({"credential_id": credential_id})
    if not row:
        raise PasskeyError("Cet appareil n’est pas autorisé.")
    rp_id, origin = _rp()
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=int(row.get("sign_count") or 0),
            require_user_verification=True,
        )
    except Exception as exc:
        raise PasskeyError("Face ID ou Windows Hello n’a pas pu être vérifié.") from exc
    db.get_conn().admin_passkeys.update_one(
        {"credential_id": credential_id},
        {"$set": {"sign_count": int(verified.new_sign_count), "last_used_at": datetime.now(UTC)}},
    )
    db.audit_event("admin.passkey_verified", details={"label": row.get("label", "")})
    return {"ok": True, "verified": True, "label": row.get("label", "Appareil biométrique")}


def revoke(public_id: object) -> dict:
    target = str(public_id or "")
    for row in db.get_conn().admin_passkeys.find({}, {"credential_id": 1, "label": 1}):
        public = hashlib.sha256(row["credential_id"].encode()).hexdigest()[:16]
        if secrets.compare_digest(public, target):
            db.get_conn().admin_passkeys.delete_one({"credential_id": row["credential_id"]})
            db.audit_event("admin.passkey_revoked", details={"label": row.get("label", "")})
            return {"ok": True}
    raise PasskeyError("Appareil introuvable.")
