"""Customer accounts for the Tunisian storefront: sign-up, login and password reset.

Passwords are hashed with ``scrypt`` from the standard library. Sessions and
reset links are random tokens that only ever reach MongoDB as SHA-256 hashes,
so a database dump cannot be replayed as a login or a password reset.

A new account stays unverified, without a session, until the customer types
the six-digit code emailed to them. Accounts created before verification
existed have no ``email_verified`` field and are treated as verified.

A reset request answers the same way whether or not the address has an
account, so the endpoint cannot be used to discover who is a customer.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from pymongo.errors import DuplicateKeyError

import database as db
from app.domain import email_service

log = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 24 * 3600
RESET_TTL_SECONDS = 3600
CODE_TTL_SECONDS = 15 * 60
CODE_MAX_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
EMAIL_UNVERIFIED = "email_unverified"

RESET_PATH = "/reinitialiser-mot-de-passe"

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

# Per-process sliding windows. They reset on restart, which is acceptable for
# slowing down guessing; they are not a substitute for strong passwords.
_ATTEMPT_WINDOW_SECONDS = 15 * 60
_LOGIN_FAILURES_PER_KEY = 8
_RESET_REQUESTS_PER_KEY = 5
_CODE_SENDS_PER_KEY = 5
_CODE_CHECKS_PER_IP = 20
_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


class AuthError(ValueError):
    """Validation error safe to show to the customer."""

    def __init__(
        self, message: str, status: int = 400, retry_after: int | None = None, code: str | None = None
    ):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.code = code


def _recent(key: str, now: float) -> list[float]:
    recent = [at for at in _attempts.get(key, []) if now - at < _ATTEMPT_WINDOW_SECONDS]
    if recent:
        _attempts[key] = recent
    else:
        _attempts.pop(key, None)
    return recent


def _check_limit(keys: list[str], limit: int) -> None:
    now = time.time()
    with _attempts_lock:
        waits = [
            int(recent[-limit] + _ATTEMPT_WINDOW_SECONDS - now) + 1
            for recent in (_recent(key, now) for key in keys)
            if len(recent) >= limit
        ]
    if waits:
        wait = max(waits)
        raise AuthError(
            f"Trop de tentatives. Réessaie dans {max(1, wait // 60)} min.", status=429, retry_after=wait
        )


def _record(keys: list[str]) -> None:
    now = time.time()
    with _attempts_lock:
        for key in keys:
            _attempts.setdefault(key, []).append(now)


def _clear(keys: list[str]) -> None:
    with _attempts_lock:
        for key in keys:
            _attempts.pop(key, None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = str(stored or "").split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


# Checking a password against this keeps a login for an unknown address as
# slow as one for a real account.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_hash(token: Any) -> str:
    return hashlib.sha256(str(token or "").encode()).hexdigest()


def _email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise AuthError("Saisis une adresse email valide.")
    return email


def _name(value: Any) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())[:100]
    if len(name) < 2:
        raise AuthError("Saisis ton nom complet.")
    return name


def _password(value: Any) -> str:
    password = str(value or "")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Le mot de passe ne doit pas dépasser {MAX_PASSWORD_LENGTH} caractères.")
    return password


def _expiry_date(timestamp: int) -> datetime:
    """MongoDB TTL indexes only expire documents on a BSON date field."""
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _public_customer(customer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(customer["id"]),
        "name": customer.get("name", ""),
        "email": customer.get("email", ""),
        "created_at": customer.get("created_at"),
    }


def _open_session(customer: dict[str, Any]) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + SESSION_TTL_SECONDS
    db.get_conn().storefront_sessions.insert_one({
        "token_hash": _token_hash(token),
        "customer_id": int(customer["id"]),
        "created_at": now,
        "expires_at": expires_at,
        "expires_at_date": _expiry_date(expires_at),
    })
    return {"ok": True, "token": token, "expires_at": expires_at, "customer": _public_customer(customer)}


def _is_verified(customer: dict[str, Any]) -> bool:
    return customer.get("email_verified") is not False


def _code_hash(customer_id: int, code: str) -> str:
    return hashlib.sha256(f"{customer_id}:{code}".encode()).hexdigest()


def _send_code(customer: dict[str, Any]) -> None:
    """Replace any pending code for this customer and email a fresh one."""
    code = f"{secrets.randbelow(10**6):06d}"
    customer_id = int(customer["id"])
    now = int(time.time())
    expires_at = now + CODE_TTL_SECONDS
    db.get_conn().storefront_email_codes.replace_one(
        {"customer_id": customer_id},
        {
            "customer_id": customer_id,
            "code_hash": _code_hash(customer_id, code),
            "attempts": 0,
            "created_at": now,
            "expires_at": expires_at,
            "expires_at_date": _expiry_date(expires_at),
        },
        upsert=True,
    )
    email_service.send_verification_code(
        customer["email"], customer.get("name", ""), code, CODE_TTL_SECONDS // 60
    )


def _code_keys(email: str, client_ip: str) -> list[str]:
    return [f"code-ip:{client_ip}", f"code-email:{email}"]


def _send_code_limited(customer: dict[str, Any], client_ip: str) -> None:
    keys = _code_keys(customer["email"], client_ip)
    _check_limit(keys, _CODE_SENDS_PER_KEY)
    _record(keys)
    _send_code(customer)


def _verification_required(email: str) -> dict[str, Any]:
    return {"ok": True, "verification_required": True, "email": email}


def register(payload: dict[str, Any], client_ip: str = "") -> dict[str, Any]:
    name = _name(payload.get("name"))
    email = _email(payload.get("email"))
    password = _password(payload.get("password"))
    conn = db.get_conn()
    now = int(time.time())

    existing = conn.storefront_customers.find_one({"email": email})
    if existing and _is_verified(existing):
        raise AuthError("Un compte existe déjà avec cette adresse email.", status=409)
    code_keys = _code_keys(email, client_ip)
    _check_limit(code_keys, _CODE_SENDS_PER_KEY)
    if existing:
        # Nobody has proven they own this address yet, so a new sign-up simply
        # takes over the pending account; the code still has to be typed.
        conn.storefront_customers.update_one(
            {"id": existing["id"]},
            {"$set": {"name": name, "password_hash": hash_password(password), "updated_at": now}},
        )
        customer = {**existing, "name": name}
    else:
        customer = {
            "id": db._next_id("storefront_customers"),
            "name": name,
            "email": email,
            "password_hash": hash_password(password),
            "email_verified": False,
            "created_at": now,
            "updated_at": now,
        }
        try:
            conn.storefront_customers.insert_one(customer)
        except DuplicateKeyError as exc:
            raise AuthError("Un compte existe déjà avec cette adresse email.", status=409) from exc
        db.audit_event("storefront.customer_registered", details={"customer_id": customer["id"]})
    _record(code_keys)
    _send_code(customer)
    return _verification_required(email)


def verify_email(payload: dict[str, Any], client_ip: str = "") -> dict[str, Any]:
    email = _email(payload.get("email"))
    code = re.sub(r"\D", "", str(payload.get("code") or ""))[:6]
    ip_keys = [f"verify-ip:{client_ip}"]
    _check_limit(ip_keys, _CODE_CHECKS_PER_IP)
    _record(ip_keys)

    conn = db.get_conn()
    customer = conn.storefront_customers.find_one({"email": email})
    if customer and _is_verified(customer):
        raise AuthError("Cette adresse est déjà confirmée. Connecte-toi.", status=409)
    pending = conn.storefront_email_codes.find_one({"customer_id": int(customer["id"])}) if customer else None
    if (
        not pending
        or int(pending.get("expires_at") or 0) < time.time()
        or int(pending.get("attempts") or 0) >= CODE_MAX_ATTEMPTS
    ):
        raise AuthError("Ce code a expiré. Demande un nouveau code.", status=410)
    if len(code) != 6 or not hmac.compare_digest(_code_hash(int(customer["id"]), code), pending["code_hash"]):
        conn.storefront_email_codes.update_one({"_id": pending["_id"]}, {"$inc": {"attempts": 1}})
        left = CODE_MAX_ATTEMPTS - int(pending.get("attempts") or 0) - 1
        if left <= 0:
            raise AuthError("Code incorrect. Demande un nouveau code.", status=410)
        raise AuthError(f"Code incorrect. Encore {left} essai{'s' if left > 1 else ''}.")

    now = int(time.time())
    conn.storefront_email_codes.delete_many({"customer_id": int(customer["id"])})
    conn.storefront_customers.update_one(
        {"id": customer["id"]}, {"$set": {"email_verified": True, "email_verified_at": now, "updated_at": now}}
    )
    db.audit_event("storefront.customer_email_verified", details={"customer_id": customer["id"]})
    email_service.send_welcome(email, customer.get("name", ""), _site_url())
    return _open_session(customer)


def resend_verification(payload: dict[str, Any], client_ip: str = "") -> dict[str, Any]:
    email = _email(payload.get("email"))
    customer = db.get_conn().storefront_customers.find_one({"email": email})
    if customer and not _is_verified(customer):
        _send_code_limited(customer, client_ip)
    return {"ok": True}


def login(payload: dict[str, Any], client_ip: str) -> dict[str, Any]:
    email = _email(payload.get("email"))
    password = str(payload.get("password") or "")[:MAX_PASSWORD_LENGTH]
    keys = [f"login-ip:{client_ip}", f"login-email:{email}"]
    _check_limit(keys, _LOGIN_FAILURES_PER_KEY)

    customer = db.get_conn().storefront_customers.find_one({"email": email})
    if not verify_password(password, customer["password_hash"] if customer else _DUMMY_HASH) or not customer:
        _record(keys)
        raise AuthError("Email ou mot de passe incorrect.", status=401)
    _clear(keys)
    if not _is_verified(customer):
        try:
            _send_code_limited(customer, client_ip)
        except AuthError:
            pass  # A code sent in the last minutes is still valid.
        raise AuthError(
            "Confirme d'abord ton adresse email avec le code que nous venons de t'envoyer.",
            status=403,
            code=EMAIL_UNVERIFIED,
        )
    return _open_session(customer)


def customer_for_token(token: Any) -> dict[str, Any]:
    if not token:
        raise AuthError("Connecte-toi pour continuer.", status=401)
    conn = db.get_conn()
    session = conn.storefront_sessions.find_one({"token_hash": _token_hash(token)})
    if not session or int(session.get("expires_at") or 0) < time.time():
        raise AuthError("Ta session a expiré. Reconnecte-toi.", status=401)
    customer = conn.storefront_customers.find_one({"id": int(session["customer_id"])})
    if not customer:
        raise AuthError("Ta session a expiré. Reconnecte-toi.", status=401)
    return customer


def me(token: Any) -> dict[str, Any]:
    return {"ok": True, "customer": _public_customer(customer_for_token(token))}


def logout(token: Any) -> dict[str, Any]:
    if token:
        db.get_conn().storefront_sessions.delete_one({"token_hash": _token_hash(token)})
    return {"ok": True}


def _site_url() -> str:
    return os.environ.get("STOREFRONT_PUBLIC_URL", "").strip().rstrip("/")


def forgot_password(payload: dict[str, Any], client_ip: str) -> dict[str, Any]:
    email = _email(payload.get("email"))
    keys = [f"reset-ip:{client_ip}", f"reset-email:{email}"]
    _check_limit(keys, _RESET_REQUESTS_PER_KEY)
    _record(keys)

    customer = db.get_conn().storefront_customers.find_one({"email": email})
    site_url = _site_url()
    if customer and not site_url:
        log.error("STOREFRONT_PUBLIC_URL is not set; cannot build a password reset link")
    elif customer:
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + RESET_TTL_SECONDS
        db.get_conn().storefront_password_resets.insert_one({
            "token_hash": _token_hash(token),
            "customer_id": int(customer["id"]),
            "created_at": int(time.time()),
            "expires_at": expires_at,
            "expires_at_date": _expiry_date(expires_at),
        })
        link = f"{site_url}{RESET_PATH}?token={quote(token)}"
        email_service.send_password_reset(email, customer.get("name", ""), link)
    return {"ok": True}


def reset_password(payload: dict[str, Any]) -> dict[str, Any]:
    password = _password(payload.get("password"))
    conn = db.get_conn()
    reset = conn.storefront_password_resets.find_one_and_delete({"token_hash": _token_hash(payload.get("token"))})
    if not reset or int(reset.get("expires_at") or 0) < time.time():
        raise AuthError("Ce lien de réinitialisation est invalide ou a expiré.")
    customer_id = int(reset["customer_id"])
    # Opening the reset link proves the customer owns the address.
    conn.storefront_customers.update_one(
        {"id": customer_id},
        {"$set": {"password_hash": hash_password(password), "email_verified": True, "updated_at": int(time.time())}},
    )
    conn.storefront_sessions.delete_many({"customer_id": customer_id})
    conn.storefront_password_resets.delete_many({"customer_id": customer_id})
    conn.storefront_email_codes.delete_many({"customer_id": customer_id})
    db.audit_event("storefront.customer_password_reset", details={"customer_id": customer_id})
    return {"ok": True}
