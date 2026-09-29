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


def test_post_without_an_api_key_only_logs(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_xxxxxxxxx")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    email_service._post({"to": ["a@b.tn"], "subject": "Sujet", "html": "", "text": "x"})
