"""Tests for the Twilio WhatsApp service.

No real Twilio calls are made — `httpx.post` is monkey-patched and the
inbound parser is fed a fake `Request` object so the signature-verify path
runs against known inputs.
"""

import base64
import hashlib
import hmac

import pytest

from app.services import whatsapp


# ---------- helpers ----------


class _FakeForm(dict):
    """Mimic Starlette's FormData enough for `dict(form.items())`."""


class _FakeURL:
    def __init__(self, raw: str):
        self._raw = raw

    def __str__(self) -> str:
        return self._raw


class _FakeRequest:
    def __init__(
        self,
        *,
        form: dict,
        headers: dict | None = None,
        url: str = "https://example.com/webhook/whatsapp/twilio",
    ):
        self._form = _FakeForm(form)
        self.headers = headers or {}
        self.url = _FakeURL(url)

    async def form(self):
        return self._form


def _force_enabled(monkeypatch, **overrides):
    defaults = {
        "TWILIO_ENABLED": True,
        "TWILIO_ACCOUNT_SID": "ACtestsid",
        "TWILIO_AUTH_TOKEN": "test-token",
        "TWILIO_FROM_NUMBER": "+14155238886",
        "TWILIO_WEBHOOK_URL": "",
        "TWILIO_TIMEOUT_SECONDS": 5.0,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(whatsapp, key, value)


def _twilio_sig(url: str, params: dict[str, str], token: str = "test-token") -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


# ---------- is_enabled / send_text disabled paths ----------


def test_is_enabled_default_false():
    assert whatsapp.is_enabled() is False


def test_send_text_when_disabled():
    r = whatsapp.send_text("919876543210", "hello")
    assert r.sent is False
    assert r.error == "twilio_disabled"


def test_send_text_missing_from_number(monkeypatch):
    _force_enabled(monkeypatch, TWILIO_FROM_NUMBER="")
    r = whatsapp.send_text("919876543210", "hello")
    assert r.sent is False
    assert r.error == "missing_from_number"


def test_send_text_empty_body(monkeypatch):
    _force_enabled(monkeypatch)
    r = whatsapp.send_text("919876543210", "")
    assert r.sent is False
    assert r.error == "empty_body"


# ---------- send_text happy + failure paths ----------


def test_send_text_happy_path(monkeypatch):
    _force_enabled(monkeypatch)
    captured = {}

    class _Resp:
        status_code = 201

        def raise_for_status(self):
            pass

        def json(self):
            return {"sid": "SMfake123"}

    def _fake_post(url, data, auth, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["auth"] = auth
        captured["timeout"] = timeout
        return _Resp()

    import app.services.whatsapp as mod

    monkeypatch.setattr(mod.httpx, "post", _fake_post)
    r = whatsapp.send_text("+919876543210", "vanakkam")
    assert r.sent is True
    assert r.provider_message_id == "SMfake123"
    assert captured["auth"] == ("ACtestsid", "test-token")
    assert captured["data"]["To"] == "whatsapp:+919876543210"
    assert captured["data"]["From"] == "whatsapp:+14155238886"
    assert captured["data"]["Body"] == "vanakkam"


def test_send_text_http_error(monkeypatch):
    _force_enabled(monkeypatch)

    import httpx as real_httpx

    class _Resp:
        status_code = 401
        text = "Unauthorized"

        def raise_for_status(self):
            raise real_httpx.HTTPStatusError("401", request=None, response=self)

    monkeypatch.setattr(
        whatsapp.httpx, "post", lambda *a, **kw: _Resp()
    )
    r = whatsapp.send_text("919876543210", "hi")
    assert r.sent is False
    assert r.error == "http_401"


def test_send_text_network_error(monkeypatch):
    _force_enabled(monkeypatch)

    def _boom(*a, **kw):
        raise RuntimeError("dns failure")

    monkeypatch.setattr(whatsapp.httpx, "post", _boom)
    r = whatsapp.send_text("919876543210", "hi")
    assert r.sent is False
    assert "dns failure" in r.error


# ---------- parse_inbound ----------


@pytest.mark.asyncio
async def test_parse_inbound_when_disabled_returns_none():
    req = _FakeRequest(form={"From": "whatsapp:+919876543210", "Body": "Hi"})
    assert await whatsapp.parse_inbound(req) is None


@pytest.mark.asyncio
async def test_parse_inbound_valid_signature(monkeypatch):
    _force_enabled(monkeypatch)
    url = "https://example.com/webhook/whatsapp/twilio"
    form = {
        "From": "whatsapp:+919876543210",
        "Body": "Hi",
        "MessageSid": "SM123",
    }
    sig = _twilio_sig(url, form)
    req = _FakeRequest(
        form=form, headers={"X-Twilio-Signature": sig}, url=url
    )
    parsed = await whatsapp.parse_inbound(req)
    assert parsed is not None
    assert parsed.phone == "919876543210"
    assert parsed.text == "Hi"
    assert parsed.message_id == "SM123"


@pytest.mark.asyncio
async def test_parse_inbound_uses_configured_webhook_url(monkeypatch):
    _force_enabled(monkeypatch, TWILIO_WEBHOOK_URL="https://prod.example/wh")
    form = {"From": "whatsapp:+919876543210", "Body": "Hi"}
    sig = _twilio_sig("https://prod.example/wh", form)
    req = _FakeRequest(
        form=form,
        headers={"X-Twilio-Signature": sig},
        url="https://internal.local/wh",  # different — should be ignored
    )
    parsed = await whatsapp.parse_inbound(req)
    assert parsed is not None


@pytest.mark.asyncio
async def test_parse_inbound_signature_mismatch(monkeypatch):
    _force_enabled(monkeypatch)
    req = _FakeRequest(
        form={"From": "whatsapp:+919876543210", "Body": "Hi"},
        headers={"X-Twilio-Signature": "wrong-sig"},
    )
    assert await whatsapp.parse_inbound(req) is None


@pytest.mark.asyncio
async def test_parse_inbound_missing_signature_header(monkeypatch):
    _force_enabled(monkeypatch)
    req = _FakeRequest(form={"From": "whatsapp:+919876543210", "Body": "Hi"})
    assert await whatsapp.parse_inbound(req) is None


@pytest.mark.asyncio
async def test_parse_inbound_missing_from_or_body(monkeypatch):
    _force_enabled(monkeypatch)
    url = "https://example.com/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+919876543210", "Body": ""}
    sig = _twilio_sig(url, form)
    req = _FakeRequest(form=form, headers={"X-Twilio-Signature": sig}, url=url)
    assert await whatsapp.parse_inbound(req) is None


@pytest.mark.asyncio
async def test_parse_inbound_blank_phone_after_strip(monkeypatch):
    _force_enabled(monkeypatch)
    url = "https://example.com/webhook/whatsapp/twilio"
    form = {"From": "whatsapp:+", "Body": "Hi"}
    sig = _twilio_sig(url, form)
    req = _FakeRequest(form=form, headers={"X-Twilio-Signature": sig}, url=url)
    assert await whatsapp.parse_inbound(req) is None


@pytest.mark.asyncio
async def test_parse_inbound_handles_form_parse_exception(monkeypatch):
    _force_enabled(monkeypatch)

    class _BadRequest:
        headers = {}
        url = _FakeURL("https://example.com/wh")

        async def form(self):
            raise RuntimeError("malformed body")

    assert await whatsapp.parse_inbound(_BadRequest()) is None


def test_verify_signature_rejects_empty_token(monkeypatch):
    """Defense in depth: empty auth token must not validate any signature."""
    monkeypatch.setattr(whatsapp, "TWILIO_AUTH_TOKEN", "")
    assert (
        whatsapp._verify_signature(
            "https://example.com/wh", {"From": "x", "Body": "y"}, "any-sig"
        )
        is False
    )


# ---------- phone redaction ----------


def test_redact_phone_masks_middle_digits():
    assert whatsapp.redact_phone("919876543210") == "91********10"
    assert whatsapp.redact_phone("+919876543210") == "91********10"


def test_redact_phone_short_inputs():
    assert whatsapp.redact_phone(None) == "***"
    assert whatsapp.redact_phone("") == "***"
    assert whatsapp.redact_phone("123") == "***"


# ---------- idempotency LRU ----------


def test_is_duplicate_message_returns_false_for_none(db_session):
    assert whatsapp.is_duplicate_message(db_session, None) is False
    assert whatsapp.is_duplicate_message(db_session, "") is False


def test_is_duplicate_message_dedups_repeats(db_session):
    assert whatsapp.is_duplicate_message(db_session, "SM1") is False
    db_session.commit()
    assert whatsapp.is_duplicate_message(db_session, "SM1") is True
    assert whatsapp.is_duplicate_message(db_session, "SM2") is False


def test_purge_old_processed_messages_deletes_only_stale_rows(db_session):
    from datetime import datetime, timedelta
    from app.models.processed_message import ProcessedMessage

    # Two old rows + one fresh row
    db_session.add(ProcessedMessage(
        message_id="SMold1", source="twilio",
        first_seen_at=datetime.utcnow() - timedelta(days=10),
    ))
    db_session.add(ProcessedMessage(
        message_id="SMold2", source="twilio",
        first_seen_at=datetime.utcnow() - timedelta(hours=72),
    ))
    db_session.add(ProcessedMessage(
        message_id="SMfresh", source="twilio",
        first_seen_at=datetime.utcnow() - timedelta(hours=1),
    ))
    db_session.commit()

    n = whatsapp.purge_old_processed_messages(db_session, older_than_hours=48)
    db_session.commit()
    assert n == 2
    assert db_session.get(ProcessedMessage, "SMold1") is None
    assert db_session.get(ProcessedMessage, "SMold2") is None
    assert db_session.get(ProcessedMessage, "SMfresh") is not None


def test_purge_old_processed_messages_empty_table(db_session):
    n = whatsapp.purge_old_processed_messages(db_session)
    assert n == 0


def test_is_duplicate_message_handles_concurrent_insert(db_session, monkeypatch):
    """If another worker beat us to the INSERT between our SELECT and INSERT,
    the unique constraint trips IntegrityError. We treat that as "duplicate".
    """
    from sqlalchemy.exc import IntegrityError

    # Force the "not seen yet" branch even though we'll make INSERT fail —
    # this simulates the race window where SELECT saw nothing but another
    # worker inserted the same id before our INSERT reached the DB.
    monkeypatch.setattr(db_session, "get", lambda *a, **kw: None)

    def _raise():
        raise IntegrityError("stmt", {}, Exception("dup"))

    monkeypatch.setattr(db_session, "flush", _raise)
    assert whatsapp.is_duplicate_message(db_session, "SMconcurrent") is True


# ---------- outbound truncation ----------


def test_send_text_truncates_oversize_body(monkeypatch):
    _force_enabled(monkeypatch)

    captured = {}

    class _Resp:
        status_code = 201

        def raise_for_status(self):
            pass

        def json(self):
            return {"sid": "SMlong"}

    def _fake_post(url, data, auth, timeout):
        captured["body"] = data["Body"]
        return _Resp()

    monkeypatch.setattr(whatsapp.httpx, "post", _fake_post)
    huge = "x" * 5000
    r = whatsapp.send_text("919876543210", huge)
    assert r.sent is True
    assert len(captured["body"]) <= whatsapp.MAX_OUTBOUND_BODY
    assert captured["body"].endswith("…")


def test_truncate_pass_through_small_body():
    assert whatsapp.truncate_for_whatsapp("short") == "short"


def test_truncate_clamps_long_body():
    huge = "x" * (whatsapp.MAX_OUTBOUND_BODY + 50)
    out = whatsapp.truncate_for_whatsapp(huge)
    assert len(out) == whatsapp.MAX_OUTBOUND_BODY
    assert out.endswith("…")
