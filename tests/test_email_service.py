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


def test_review_form_is_filled_inside_the_email():
    token = "12.1800000000." + "ab" * 16
    html, text = email_service.review_form_parts(token)
    action = f"{email_service.site_url()}{email_service.REVIEW_EMAIL_PATH}?token={token}"
    assert "☆" in html
    assert "<form " in html
    assert 'method="post"' in html
    assert f'action="{action}"' in html
    assert "send=1" not in action
    assert 'name="send" value="1"' in html
    assert 'name="comment"' in html
    assert 'name="score"' in html
    assert 'type="radio"' in html
    assert 'type="submit"' in html
    assert "width:1px" not in html
    assert "clip:rect" not in html
    assert "<a " not in html
    assert "&score=" not in html
    assert "Rien n'est envoyé avant ce bouton." in text
    for score in range(1, 6):
        assert f'value="{score}"' in html
        assert f"score={score}" not in text

    _subject, message, _plain = email_service.review_request_content("Amine", "TN-1", token)
    assert 'name="comment"' in message
    assert 'value="4"' in message
    assert "&score=" not in message
    assert 'name="send" value="1"' in message


def test_post_without_an_api_key_only_logs(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_xxxxxxxxx")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    email_service._post({"to": ["a@b.tn"], "subject": "Sujet", "html": "", "text": "x"})
