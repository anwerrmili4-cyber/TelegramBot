"""Tunisian storefront customer accounts: sign-up, email codes, login, sessions and password reset."""

import re

import pytest

from app.domain import storefront_auth_service as auth

CUSTOMER = {"name": "Amine Ben Salah", "email": "Amine@Example.com", "password": "motdepasse1"}


@pytest.fixture(autouse=True)
def _isolated(mock_mongodb, monkeypatch):
    mock_mongodb.storefront_customers.create_index("email", unique=True)
    monkeypatch.setattr(auth, "_attempts", {})
    monkeypatch.setenv("STOREFRONT_PUBLIC_URL", "https://shop.example.tn")


def _last_code(sent_emails):
    return re.search(r"\b(\d{6})\b", sent_emails[-1]["text"]).group(1)


def _register_verified(sent_emails, customer=CUSTOMER):
    auth.register(customer)
    return auth.verify_email({"email": customer["email"], "code": _last_code(sent_emails)})


def test_password_hash_round_trip_and_rejects_wrong_password():
    stored = auth.hash_password("secret-123")
    assert stored.startswith("scrypt$")
    assert "secret-123" not in stored
    assert auth.verify_password("secret-123", stored)
    assert not auth.verify_password("secret-124", stored)
    assert not auth.verify_password("secret-123", "garbage")


def test_register_emails_a_code_and_opens_no_session(mock_mongodb, sent_emails):
    result = auth.register(CUSTOMER)

    assert result == {"ok": True, "verification_required": True, "email": "amine@example.com"}
    assert mock_mongodb.storefront_sessions.count_documents({}) == 0
    assert mock_mongodb.storefront_customers.find_one({})["email_verified"] is False
    (message,) = sent_emails
    assert message["to"] == ["amine@example.com"]
    code = _last_code(sent_emails)
    assert code in message["subject"]
    assert code not in str(mock_mongodb.storefront_email_codes.find_one({}))


def test_verify_email_opens_a_session_and_sends_the_welcome_email(mock_mongodb, sent_emails):
    session = _register_verified(sent_emails)

    assert session["customer"]["email"] == "amine@example.com"
    assert "password_hash" not in session["customer"]
    assert auth.me(session["token"])["customer"]["name"] == "Amine Ben Salah"
    assert mock_mongodb.storefront_customers.find_one({})["email_verified"] is True
    assert mock_mongodb.storefront_email_codes.count_documents({}) == 0
    assert sent_emails[-1]["subject"] == "Bienvenue sur BLACKMARKET Tunisie"
    assert "https://shop.example.tn" in sent_emails[-1]["html"]


def test_wrong_code_counts_attempts_then_expires_the_code(sent_emails):
    auth.register(CUSTOMER)
    code = _last_code(sent_emails)
    wrong = "000000" if code != "000000" else "111111"

    with pytest.raises(auth.AuthError, match="Encore 4 essais"):
        auth.verify_email({"email": CUSTOMER["email"], "code": wrong})
    for _ in range(auth.CODE_MAX_ATTEMPTS - 2):
        with pytest.raises(auth.AuthError, match="Code incorrect"):
            auth.verify_email({"email": CUSTOMER["email"], "code": wrong})
    with pytest.raises(auth.AuthError, match="Demande un nouveau code") as exc:
        auth.verify_email({"email": CUSTOMER["email"], "code": wrong})
    assert exc.value.status == 410
    with pytest.raises(auth.AuthError, match="expiré"):
        auth.verify_email({"email": CUSTOMER["email"], "code": code})


def test_expired_code_is_rejected_and_a_new_one_works(mock_mongodb, sent_emails):
    auth.register(CUSTOMER)
    old_code = _last_code(sent_emails)
    mock_mongodb.storefront_email_codes.update_many({}, {"$set": {"expires_at": 0}})
    with pytest.raises(auth.AuthError, match="expiré"):
        auth.verify_email({"email": CUSTOMER["email"], "code": old_code})

    assert auth.resend_verification({"email": CUSTOMER["email"]}) == {"ok": True}
    assert auth.verify_email({"email": CUSTOMER["email"], "code": _last_code(sent_emails)})["token"]


def test_resend_does_not_reveal_unknown_or_verified_addresses(sent_emails):
    _register_verified(sent_emails)
    count = len(sent_emails)
    assert auth.resend_verification({"email": "nobody@example.com"}) == {"ok": True}
    assert auth.resend_verification({"email": CUSTOMER["email"]}) == {"ok": True}
    assert len(sent_emails) == count


def test_code_sending_is_rate_limited(sent_emails):
    auth.register(CUSTOMER, "6.6.6.6")
    for _ in range(auth._CODE_SENDS_PER_KEY - 1):
        auth.resend_verification({"email": CUSTOMER["email"]}, "6.6.6.6")
    with pytest.raises(auth.AuthError, match="Trop de tentatives") as exc:
        auth.resend_verification({"email": CUSTOMER["email"]}, "6.6.6.6")
    assert exc.value.status == 429


def test_register_rejects_verified_duplicate_but_restarts_a_pending_sign_up(mock_mongodb, sent_emails):
    auth.register(CUSTOMER)
    auth.register({**CUSTOMER, "name": "Amine B.", "password": "autre-mdp-1"})
    assert mock_mongodb.storefront_customers.count_documents({}) == 1
    session = auth.verify_email({"email": CUSTOMER["email"], "code": _last_code(sent_emails)})
    assert session["customer"]["name"] == "Amine B."
    assert auth.login({"email": CUSTOMER["email"], "password": "autre-mdp-1"}, "1.1.1.1")["token"]

    with pytest.raises(auth.AuthError, match="existe déjà") as exc:
        auth.register({**CUSTOMER, "email": "amine@example.com"})
    assert exc.value.status == 409
    with pytest.raises(auth.AuthError, match="au moins"):
        auth.register({**CUSTOMER, "email": "other@example.com", "password": "short"})


def test_login_accepts_right_password_and_rejects_wrong_one(sent_emails):
    _register_verified(sent_emails)
    assert auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "1.1.1.1")["token"]
    with pytest.raises(auth.AuthError, match="incorrect") as exc:
        auth.login({"email": "amine@example.com", "password": "nope-nope"}, "1.1.1.1")
    assert exc.value.status == 401
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login({"email": "nobody@example.com", "password": "motdepasse1"}, "1.1.1.1")


def test_login_to_an_unverified_account_sends_a_new_code(mock_mongodb, sent_emails):
    auth.register(CUSTOMER)
    with pytest.raises(auth.AuthError) as exc:
        auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "1.1.1.1")
    assert exc.value.status == 403
    assert exc.value.code == auth.EMAIL_UNVERIFIED
    assert len(sent_emails) == 2
    assert mock_mongodb.storefront_sessions.count_documents({}) == 0


def test_accounts_created_before_verification_can_still_log_in(mock_mongodb):
    mock_mongodb.storefront_customers.insert_one({
        "id": 99,
        "name": "Ancien client",
        "email": "ancien@example.com",
        "password_hash": auth.hash_password("motdepasse1"),
    })
    assert auth.login({"email": "ancien@example.com", "password": "motdepasse1"}, "1.1.1.1")["token"]


def test_login_is_rate_limited_after_repeated_failures(sent_emails):
    _register_verified(sent_emails)
    for _ in range(auth._LOGIN_FAILURES_PER_KEY):
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.login({"email": "amine@example.com", "password": "wrong-pass"}, "2.2.2.2")
    with pytest.raises(auth.AuthError, match="Trop de tentatives") as exc:
        auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "2.2.2.2")
    assert exc.value.status == 429


def test_a_live_session_is_not_read_from_mongo_on_every_page(sent_emails, monkeypatch):
    monkeypatch.setattr(auth, "SESSION_CACHE_SECONDS", 30)
    token = _register_verified(sent_emails)["token"]
    assert auth.me(token)["customer"]["email"] == "amine@example.com"
    calls = {"count": 0}
    real = auth._load_customer

    def counting(value):
        calls["count"] += 1
        return real(value)

    monkeypatch.setattr(auth, "_load_customer", counting)
    assert auth.me(token)["ok"] is True
    assert auth.me(token)["ok"] is True
    assert calls["count"] == 0


def test_logout_revokes_the_session(sent_emails):
    token = _register_verified(sent_emails)["token"]
    auth.logout(token)
    with pytest.raises(auth.AuthError) as exc:
        auth.me(token)
    assert exc.value.status == 401


def test_forgot_password_does_not_reveal_unknown_emails(mock_mongodb, sent_emails):
    assert auth.forgot_password({"email": "nobody@example.com"}, "3.3.3.3") == {"ok": True}
    assert sent_emails == []
    assert mock_mongodb.storefront_password_resets.count_documents({}) == 0


def _reset_token(sent_emails):
    message = sent_emails[-1]
    assert message["subject"] == "Nouveau mot de passe"
    link = re.search(r"https://shop\.example\.tn/reinitialiser-mot-de-passe\?token=\S+", message["text"]).group(0)
    return link.split("token=", 1)[1]


def test_reset_flow_changes_password_revokes_sessions_and_is_single_use(sent_emails):
    old_token = _register_verified(sent_emails)["token"]
    assert auth.forgot_password({"email": "AMINE@example.com"}, "4.4.4.4") == {"ok": True}
    assert sent_emails[-1]["to"] == ["amine@example.com"]
    reset_token = _reset_token(sent_emails)

    auth.reset_password({"token": reset_token, "password": "nouveau-mdp"})

    with pytest.raises(auth.AuthError):
        auth.me(old_token)
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "4.4.4.4")
    assert auth.login({"email": "amine@example.com", "password": "nouveau-mdp"}, "4.4.4.4")["token"]
    with pytest.raises(auth.AuthError, match="invalide ou a expiré"):
        auth.reset_password({"token": reset_token, "password": "encore-autre"})


def test_reset_verifies_a_pending_account(sent_emails):
    auth.register(CUSTOMER)
    auth.forgot_password({"email": CUSTOMER["email"]}, "4.4.4.4")
    auth.reset_password({"token": _reset_token(sent_emails), "password": "nouveau-mdp"})
    assert auth.login({"email": CUSTOMER["email"], "password": "nouveau-mdp"}, "4.4.4.4")["token"]


def test_expired_reset_link_is_rejected(mock_mongodb, sent_emails):
    _register_verified(sent_emails)
    auth.forgot_password({"email": "amine@example.com"}, "5.5.5.5")
    reset_token = _reset_token(sent_emails)
    mock_mongodb.storefront_password_resets.update_many({}, {"$set": {"expires_at": 0}})
    with pytest.raises(auth.AuthError, match="invalide ou a expiré"):
        auth.reset_password({"token": reset_token, "password": "nouveau-mdp"})


# ---------------------------------------------------------------------------
# Google sign-in
# ---------------------------------------------------------------------------

GOOGLE_CLIENT = "123-abc.apps.googleusercontent.com"


def _claims(**overrides):
    import time

    return {
        "aud": GOOGLE_CLIENT,
        "iss": "https://accounts.google.com",
        "exp": str(int(time.time()) + 600),
        "sub": "google-sub-1",
        "email": "Sana@Gmail.com",
        "email_verified": "true",
        "name": "Sana Trabelsi",
        **overrides,
    }


@pytest.fixture
def google(monkeypatch):
    """Answer Google's tokeninfo endpoint with the claims the test sets."""
    import io
    import json

    monkeypatch.setenv("GOOGLE_CLIENT_ID", GOOGLE_CLIENT)
    state = {"claims": _claims(), "requests": []}

    def fake_urlopen(request, timeout=0):
        state["requests"].append(request.full_url)
        return io.BytesIO(json.dumps(state["claims"]).encode())

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    return state


def test_google_config_exposes_only_the_client_id(google):
    assert auth.auth_config() == {"ok": True, "google_client_id": GOOGLE_CLIENT}


def test_google_sign_up_creates_a_confirmed_account_without_password(mock_mongodb, google, sent_emails):
    session = auth.google_login({"credential": "id-token"}, "1.1.1.1")

    assert "id_token=id-token" in google["requests"][0]
    customer = session["customer"]
    assert customer["email"] == "sana@gmail.com"
    assert customer["name"] == "Sana Trabelsi"
    assert customer["email_confirmed"] is True
    assert customer["has_password"] is False
    assert customer["google"] is True
    assert auth.me(session["token"])["customer"]["id"] == customer["id"]
    assert sent_emails[-1]["to"] == ["sana@gmail.com"]

    again = auth.google_login({"credential": "id-token"}, "1.1.1.1")
    assert again["customer"]["id"] == customer["id"]
    assert mock_mongodb.storefront_customers.count_documents({}) == 1


def test_google_links_an_existing_password_account(mock_mongodb, google, sent_emails):
    existing = _register_verified(sent_emails, {**CUSTOMER, "email": "sana@gmail.com"})
    sent_emails.clear()

    session = auth.google_login({"credential": "id-token"}, "1.1.1.1")

    assert session["customer"]["id"] == existing["customer"]["id"]
    assert session["customer"]["has_password"] is True
    assert sent_emails == []
    assert auth.login({"email": "sana@gmail.com", "password": CUSTOMER["password"]}, "1.1.1.1")["token"]


def test_google_takes_over_an_unconfirmed_sign_up_and_voids_its_password(mock_mongodb, google, sent_emails):
    auth.register({**CUSTOMER, "email": "sana@gmail.com"})

    session = auth.google_login({"credential": "id-token"}, "1.1.1.1")

    assert session["customer"]["email_confirmed"] is True
    assert session["customer"]["has_password"] is False
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login({"email": "sana@gmail.com", "password": CUSTOMER["password"]}, "1.1.1.1")


def test_google_only_account_can_set_a_first_password(mock_mongodb, google):
    token = auth.google_login({"credential": "id-token"}, "1.1.1.1")["token"]
    auth.change_password(token, {"current_password": "", "new_password": "nouveau-mdp-1"})

    assert auth.login({"email": "sana@gmail.com", "password": "nouveau-mdp-1"}, "1.1.1.1")["token"]
    with pytest.raises(auth.AuthError, match="actuel"):
        auth.change_password(token, {"current_password": "", "new_password": "autre-mdp-22"})


@pytest.mark.parametrize("overrides, status", [
    ({"aud": "someone-else.apps.googleusercontent.com"}, 401),
    ({"iss": "evil.example.com"}, 401),
    ({"exp": "1"}, 401),
    ({"email_verified": "false"}, 403),
])
def test_google_tokens_for_another_app_or_unverified_emails_are_refused(mock_mongodb, google, overrides, status):
    google["claims"] = _claims(**overrides)
    with pytest.raises(auth.AuthError) as refused:
        auth.google_login({"credential": "id-token"}, "1.1.1.1")
    assert refused.value.status == status
    assert mock_mongodb.storefront_customers.count_documents({}) == 0


def test_google_sign_in_is_off_without_a_client_id(mock_mongodb, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(auth.AuthError) as off:
        auth.google_login({"credential": "id-token"}, "1.1.1.1")
    assert off.value.status == 503


def test_invoice_download_is_limited_to_its_owner(mock_mongodb, sent_emails):
    owner = _register_verified(sent_emails)
    stranger = _register_verified(sent_emails, {**CUSTOMER, "email": "sana@example.com"})
    mock_mongodb.storefront_invoices.insert_one({
        "id": 1, "number": "FAC-2026-00001", "cart_reference": "TN-ABC123",
        "customer_id": owner["customer"]["id"], "customer_name": "Amine", "customer_email": "amine@example.com",
        "items": [{"offer_name": "Netflix", "quantity": 1, "unit_millimes": 15000, "total_millimes": 15000}],
        "total_millimes": 15000, "refunded_millimes": 0, "payment_label": "Flouci",
        "paid_at": 1_790_000_000, "issued_at": 1_790_000_000, "seller": {"name": "BLACKMARKET Tunisie"},
    })

    number, pdf = auth.invoice_pdf(owner["token"], "tn-abc123")
    assert number == "FAC-2026-00001" and pdf.startswith(b"%PDF")
    with pytest.raises(auth.AuthError, match="introuvable"):
        auth.invoice_pdf(stranger["token"], "TN-ABC123")
    with pytest.raises(auth.AuthError, match="introuvable"):
        auth.invoice_pdf(owner["token"], "TN-NOPE00")
