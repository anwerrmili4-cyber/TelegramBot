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


def test_review_form_uses_play_store_stars_and_a_white_field():
    html, text = email_service.review_form_parts("12.1800000000." + "ab" * 16)
    form = html.split("<form", 1)[1].split("</form>", 1)[0]
    assert 'class="bm-stars"' in form
    assert 'name="score"' in form
    assert "☆" in form and "★" in form
    assert "background-color:#ffffff" in form
    assert "color:#1f1f1f" in form
    assert 'name="send" value="1"' in form
    assert 'type="submit"' in form
    assert "<a " not in form
    assert "Si ton application" not in html
    assert "Rien n'est envoyé avant ce bouton." in text

    _subject, message, _plain = email_service.review_request_content("Amine", "TN-1", "12.1800000000." + "ab" * 16)
    head, _, _body = message.partition("</head>")
    assert ".bm-stars input:checked ~ label .bm-on" in head
    assert "background-color:#ffffff" in message


def test_post_without_an_api_key_only_logs(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_xxxxxxxxx")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    email_service._post({"to": ["a@b.tn"], "subject": "Sujet", "html": "", "text": "x"})
