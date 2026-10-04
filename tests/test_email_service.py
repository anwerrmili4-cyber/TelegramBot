"""Resend transport for storefront emails."""

import json

from app.domain import email_service


def test_post_sends_a_user_agent_and_the_configured_sender(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data)
        return _Response()

    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "BLACKMARKET <noreply@ourblackmarket.com>")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", fake_urlopen)

    email_service._post({"to": ["a@b.tn"], "subject": "Sujet", "html": "<p>x</p>", "text": "x"})

    assert captured["headers"]["authorization"] == "Bearer re_test"
    assert captured["headers"]["user-agent"].startswith("blackmarket-storefront")
    assert captured["body"]["from"] == "BLACKMARKET <noreply@ourblackmarket.com>"
    assert captured["body"]["to"] == ["a@b.tn"]


def test_review_form_uses_tappable_stars_that_do_not_send():
    token = "12.1800000000." + "ab" * 16
    html, text = email_service.review_form_parts(token)
    assert "☆" in html
    assert "<a " in html
    assert "Si ton application" not in html
    assert "Rien n'est envoyé avant ce bouton." in text
    for score in range(1, 6):
        href = f"/api/storefront/reviews/email?token={token}&amp;score={score}"
        assert href in html
        assert f"score={score}" in text
    assert "send=1" not in html
    assert 'type="radio"' not in html

    _subject, message, _plain = email_service.review_request_content("Amine", "TN-1", token)
    assert "score=4" in message
    assert "send=1" not in message


def test_post_without_an_api_key_only_logs(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_xxxxxxxxx")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    email_service._post({"to": ["a@b.tn"], "subject": "Sujet", "html": "", "text": "x"})
