"""End-to-end tests for `POST /webhook/whatsapp/twilio`.

Uses the existing TestClient fixture. The `whatsapp` module's send/parse
helpers are monkey-patched so no real network call leaves the process.
"""

import base64
import hashlib
import hmac

from app.services import whatsapp


def _twilio_sig(url: str, params: dict[str, str], token: str = "test-token") -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _force_enabled(monkeypatch, **overrides):
    defaults = {
        "TWILIO_ENABLED": True,
        "TWILIO_ACCOUNT_SID": "ACtest",
        "TWILIO_AUTH_TOKEN": "test-token",
        "TWILIO_FROM_NUMBER": "+14155238886",
        "TWILIO_WEBHOOK_URL": "http://testserver/webhook/whatsapp/twilio",
        "TWILIO_TIMEOUT_SECONDS": 5.0,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(whatsapp, key, value)


def test_twilio_route_503_when_disabled(client):
    res = client.post(
        "/webhook/whatsapp/twilio", data={"From": "x", "Body": "y"}
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "http_503"


def test_twilio_route_403_on_bad_signature(client, monkeypatch):
    _force_enabled(monkeypatch)
    res = client.post(
        "/webhook/whatsapp/twilio",
        data={"From": "whatsapp:+919876543210", "Body": "Hi"},
        headers={"X-Twilio-Signature": "wrong"},
    )
    assert res.status_code == 403


def test_twilio_route_400_on_unparseable_phone(client, monkeypatch):
    """Signature OK but phone fails Pydantic validation (e.g. letters)."""
    _force_enabled(monkeypatch)
    url = "http://testserver/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+abc", "Body": "Hi"}
    sig = _twilio_sig(url, form)
    res = client.post(
        "/webhook/whatsapp/twilio",
        data=form,
        headers={"X-Twilio-Signature": sig},
    )
    assert res.status_code == 400


def test_twilio_route_happy_path_sends_reply(client, monkeypatch):
    _force_enabled(monkeypatch)
    url = "http://testserver/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+919876543210", "Body": "Hi", "MessageSid": "SM1"}
    sig = _twilio_sig(url, form)

    captured = {}

    class _Resp:
        status_code = 201

        def raise_for_status(self):
            pass

        def json(self):
            return {"sid": "SMreply"}

    def _fake_post(post_url, data, auth, timeout):
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(whatsapp.httpx, "post", _fake_post)

    res = client.post(
        "/webhook/whatsapp/twilio",
        data=form,
        headers={"X-Twilio-Signature": sig},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] is True
    # Response carries the *redacted* phone, not the raw one (PII hygiene)
    assert body["to"] == "91********10"
    assert body["send"]["sent"] is True
    assert body["send"]["provider_message_id"] == "SMreply"
    # Outbound was sent back to the same number (un-redacted)
    assert captured["data"]["To"] == "whatsapp:+919876543210"


def test_twilio_route_dedups_repeat_message_sid(client, monkeypatch):
    """Twilio retries within minutes — second call with same MessageSid should
    return immediately without re-running the state machine or sending again.
    """
    _force_enabled(monkeypatch)
    url = "http://testserver/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+919876543210", "Body": "Hi", "MessageSid": "SMretry"}
    sig = _twilio_sig(url, form)

    send_calls = {"count": 0}

    class _Resp:
        status_code = 201

        def raise_for_status(self):
            pass

        def json(self):
            return {"sid": "SMok"}

    def _fake_post(*a, **kw):
        send_calls["count"] += 1
        return _Resp()

    monkeypatch.setattr(whatsapp.httpx, "post", _fake_post)

    first = client.post(
        "/webhook/whatsapp/twilio", data=form, headers={"X-Twilio-Signature": sig}
    )
    second = client.post(
        "/webhook/whatsapp/twilio", data=form, headers={"X-Twilio-Signature": sig}
    )

    assert first.status_code == 200
    assert "duplicate" not in first.json()
    assert second.status_code == 200
    assert second.json().get("duplicate") is True
    assert send_calls["count"] == 1  # second call did NOT re-send


def test_twilio_route_continues_when_send_fails(client, monkeypatch):
    """If the outbound send fails, we still return 200 — the inbound is processed."""
    _force_enabled(monkeypatch)
    url = "http://testserver/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+919876543210", "Body": "Hi"}
    sig = _twilio_sig(url, form)

    def _boom(*a, **kw):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(whatsapp.httpx, "post", _boom)

    res = client.post(
        "/webhook/whatsapp/twilio",
        data=form,
        headers={"X-Twilio-Signature": sig},
    )
    assert res.status_code == 200
    assert res.json()["send"]["sent"] is False
    assert "upstream down" in res.json()["send"]["error"]
