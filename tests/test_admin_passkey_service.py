from __future__ import annotations

import pytest

from app.domain import admin_passkey_service as service


def test_registration_options_require_platform_biometrics_and_limit_devices(monkeypatch, mock_mongodb):
    monkeypatch.setattr(service, "public_base_url_from_environment", lambda: "https://admin.example.com")
    result = service.registration_options()

    assert result["ok"] is True
    assert result["challenge_id"]
    assert result["publicKey"]["rp"]["id"] == "admin.example.com"
    assert result["publicKey"]["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert result["publicKey"]["authenticatorSelection"]["userVerification"] == "required"
    assert mock_mongodb.admin_webauthn_challenges.count_documents({"kind": "register"}) == 1

    for index in range(2):
        mock_mongodb.admin_passkeys.insert_one({
            "credential_id": f"credential-{index}",
            "public_key": b"key",
        })
    with pytest.raises(service.PasskeyError, match="Deux appareils"):
        service.registration_options()


def test_expired_or_replayed_challenge_is_rejected(mock_mongodb):
    with pytest.raises(service.PasskeyError, match="expiré"):
        service.authenticate("missing", {})
