"""Tunisian storefront customer accounts: sign-up, login, sessions and password reset."""

import pytest

from app.domain import storefront_auth_service as auth

CUSTOMER = {"name": "Amine Ben Salah", "email": "Amine@Example.com", "password": "motdepasse1"}


@pytest.fixture(autouse=True)
def _isolated(mock_mongodb, monkeypatch):
    mock_mongodb.storefront_customers.create_index("email", unique=True)
    monkeypatch.setattr(auth, "_attempts", {})
    monkeypatch.setenv("STOREFRONT_PUBLIC_URL", "https://shop.example.tn")
    sent = []
    monkeypatch.setattr(auth, "_send_reset_email", lambda *args: sent.append(args))

    class _Inline:
        def __init__(self, target, args=(), daemon=None):
            self._run = lambda: target(*args)

        def start(self):
            self._run()

    monkeypatch.setattr(auth.threading, "Thread", _Inline)
    return sent


def test_password_hash_round_trip_and_rejects_wrong_password():
    stored = auth.hash_password("secret-123")
    assert stored.startswith("scrypt$")
    assert "secret-123" not in stored
    assert auth.verify_password("secret-123", stored)
    assert not auth.verify_password("secret-124", stored)
    assert not auth.verify_password("secret-123", "garbage")


def test_register_normalises_email_and_opens_a_session(mock_mongodb):
    session = auth.register(CUSTOMER)
    assert session["customer"]["email"] == "amine@example.com"
    assert "password_hash" not in session["customer"]
    stored = mock_mongodb.storefront_sessions.find_one({})
    assert stored["token_hash"] != session["token"]
    assert auth.me(session["token"])["customer"]["name"] == "Amine Ben Salah"


def test_register_rejects_duplicate_email_and_short_password():
    auth.register(CUSTOMER)
    with pytest.raises(auth.AuthError, match="existe déjà") as exc:
        auth.register({**CUSTOMER, "email": "amine@example.com"})
    assert exc.value.status == 409
    with pytest.raises(auth.AuthError, match="au moins"):
        auth.register({**CUSTOMER, "email": "other@example.com", "password": "short"})


def test_login_accepts_right_password_and_rejects_wrong_one():
    auth.register(CUSTOMER)
    assert auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "1.1.1.1")["token"]
    with pytest.raises(auth.AuthError, match="incorrect") as exc:
        auth.login({"email": "amine@example.com", "password": "nope-nope"}, "1.1.1.1")
    assert exc.value.status == 401
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login({"email": "nobody@example.com", "password": "motdepasse1"}, "1.1.1.1")


def test_login_is_rate_limited_after_repeated_failures():
    auth.register(CUSTOMER)
    for _ in range(auth._LOGIN_FAILURES_PER_KEY):
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.login({"email": "amine@example.com", "password": "wrong-pass"}, "2.2.2.2")
    with pytest.raises(auth.AuthError, match="Trop de tentatives") as exc:
        auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "2.2.2.2")
    assert exc.value.status == 429


def test_logout_revokes_the_session():
    token = auth.register(CUSTOMER)["token"]
    auth.logout(token)
    with pytest.raises(auth.AuthError) as exc:
        auth.me(token)
    assert exc.value.status == 401


def test_forgot_password_does_not_reveal_unknown_emails(_isolated, mock_mongodb):
    assert auth.forgot_password({"email": "nobody@example.com"}, "3.3.3.3") == {"ok": True}
    assert _isolated == []
    assert mock_mongodb.storefront_password_resets.count_documents({}) == 0


def test_reset_flow_changes_password_revokes_sessions_and_is_single_use(_isolated):
    old_token = auth.register(CUSTOMER)["token"]
    assert auth.forgot_password({"email": "AMINE@example.com"}, "4.4.4.4") == {"ok": True}
    (email, _name, link), = _isolated
    assert email == "amine@example.com"
    assert link.startswith("https://shop.example.tn/reinitialiser-mot-de-passe?token=")
    reset_token = link.split("token=", 1)[1]

    auth.reset_password({"token": reset_token, "password": "nouveau-mdp"})

    with pytest.raises(auth.AuthError):
        auth.me(old_token)
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login({"email": "amine@example.com", "password": "motdepasse1"}, "4.4.4.4")
    assert auth.login({"email": "amine@example.com", "password": "nouveau-mdp"}, "4.4.4.4")["token"]
    with pytest.raises(auth.AuthError, match="invalide ou a expiré"):
        auth.reset_password({"token": reset_token, "password": "encore-autre"})


def test_expired_reset_link_is_rejected(_isolated, mock_mongodb):
    auth.register(CUSTOMER)
    auth.forgot_password({"email": "amine@example.com"}, "5.5.5.5")
    reset_token = _isolated[0][2].split("token=", 1)[1]
    mock_mongodb.storefront_password_resets.update_many({}, {"$set": {"expires_at": 0}})
    with pytest.raises(auth.AuthError, match="invalide ou a expiré"):
        auth.reset_password({"token": reset_token, "password": "nouveau-mdp"})
