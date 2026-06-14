"""Twilio WhatsApp bridge.

Handles three things:

1. **Inbound webhook parsing.** Twilio POSTs form-encoded
   `From=whatsapp:+919876543210`, `Body=...`, `MessageSid=...` to our route.
   `parse_inbound()` validates the `X-Twilio-Signature` header (HMAC-SHA1 of
   URL + sorted params), then returns a typed `ParsedInbound`. An invalid
   or missing signature returns `None` so the router replies 403 without
   touching the DB — protects against spoofed messages.

2. **Outbound send.** After `devotee_flow.handle_incoming()` produces a
   reply, the route calls `send_text(phone, body)` which POSTs to the
   Twilio Messages API with HTTP Basic auth.

3. **Disabled mode.** When `TWILIO_ENABLED=false` (default in dev/tests),
   `is_enabled()` returns False; the bridge is a no-op so the rest of the
   app boots and runs without Twilio credentials.

References
- Inbound signature: https://www.twilio.com/docs/usage/security#validating-requests
- Outbound API: https://www.twilio.com/docs/messaging/api/message-resource
"""

import base64
import hashlib
import hmac
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Request

from app.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_ENABLED,
    TWILIO_FROM_NUMBER,
    TWILIO_TIMEOUT_SECONDS,
    TWILIO_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)

# WhatsApp/Twilio rejects bodies > 1600 chars. Keep margin for safety.
MAX_OUTBOUND_BODY = 1500

# In-process LRU for Twilio MessageSid dedup. Twilio retries on 5xx/timeout
# within minutes; this stops us from re-running the state machine for a
# message we already processed. Per-process only — use Redis for multi-worker
# deployments.
_SEEN_CAP = 2048
_seen_message_ids: "OrderedDict[str, None]" = OrderedDict()
_seen_lock = threading.Lock()


@dataclass
class ParsedInbound:
    phone: str
    text: str
    message_id: Optional[str] = None


@dataclass
class SendResult:
    sent: bool
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


def redact_phone(phone: Optional[str]) -> str:
    """Mask middle digits of a phone for logs (PII hygiene)."""
    if not phone:
        return "***"
    cleaned = phone.lstrip("+")
    if len(cleaned) <= 4:
        return "*" * len(cleaned)
    return cleaned[:2] + "*" * (len(cleaned) - 4) + cleaned[-2:]


def is_duplicate_message(message_id: Optional[str]) -> bool:
    """Idempotent guard against Twilio retries. Returns True if already seen."""
    if not message_id:
        return False
    with _seen_lock:
        if message_id in _seen_message_ids:
            _seen_message_ids.move_to_end(message_id)
            return True
        _seen_message_ids[message_id] = None
        if len(_seen_message_ids) > _SEEN_CAP:
            _seen_message_ids.popitem(last=False)
        return False


def _reset_seen_for_tests() -> None:
    with _seen_lock:
        _seen_message_ids.clear()


def truncate_for_whatsapp(text: str) -> str:
    """Clamp `text` to the WhatsApp/Twilio body limit. Adds an ellipsis when cut.

    Public so callers (like `devotee_flow`) can truncate *before* sending the
    text through the translator — we'd otherwise pay LLM cost translating
    characters we'd just discard.
    """
    if len(text) <= MAX_OUTBOUND_BODY:
        return text
    return text[: MAX_OUTBOUND_BODY - 1] + "…"


def is_enabled() -> bool:
    """Twilio is wired only when explicitly enabled AND core creds are set."""
    return bool(
        TWILIO_ENABLED and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
    )


def _verify_signature(url: str, params: dict[str, str], header_value: str) -> bool:
    """Re-compute Twilio's signature and compare in constant time.

    Algorithm: concatenate the full URL Twilio called with the form params
    sorted alphabetically by key (key then value, no separator), HMAC-SHA1
    with the auth token, base64-encode the digest, compare.

    Explicit-reject path: missing header OR empty auth token — never trust
    an HMAC computed with an empty key.
    """
    if not header_value or not TWILIO_AUTH_TOKEN:
        return False
    payload = url
    for key in sorted(params):
        payload += key + params[key]
    digest = hmac.new(
        TWILIO_AUTH_TOKEN.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, header_value)


async def parse_inbound(request: Request) -> Optional[ParsedInbound]:
    """Verify signature, parse form body, return normalised inbound.

    Returns `None` when the signature is missing/invalid, the body is
    malformed, or required fields are absent — the caller should respond
    403/400.
    """
    if not is_enabled():
        return None
    try:
        form = await request.form()
    except Exception as exc:  # malformed body, wrong content-type, etc.
        logger.warning("Twilio form parse failed: %s", exc)
        return None
    params: dict[str, str] = {k: str(v) for k, v in form.items()}
    signature = request.headers.get("X-Twilio-Signature", "")
    webhook_url = TWILIO_WEBHOOK_URL or str(request.url)
    if not _verify_signature(webhook_url, params, signature):
        logger.warning("Twilio signature mismatch for %s", request.url)
        return None

    from_field = params.get("From", "")
    body_field = params.get("Body", "").strip()
    if not from_field or not body_field:
        logger.info("Twilio inbound missing From/Body")
        return None

    # "whatsapp:+919876543210" → "919876543210"
    phone = from_field.replace("whatsapp:", "").lstrip("+").strip()
    if not phone:
        return None

    return ParsedInbound(
        phone=phone,
        text=body_field,
        message_id=params.get("MessageSid"),
    )


def send_text(phone: str, text: str) -> SendResult:
    """Send an outbound WhatsApp text via the Twilio REST API.

    No-op when Twilio is disabled — returns `SendResult(sent=False, ...)` so
    callers can log without raising. On HTTP failure, logs and returns the
    error string; never propagates.
    """
    if not is_enabled():
        return SendResult(sent=False, error="twilio_disabled")
    if not TWILIO_FROM_NUMBER:
        return SendResult(sent=False, error="missing_from_number")
    if not text:
        return SendResult(sent=False, error="empty_body")

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{TWILIO_ACCOUNT_SID}/Messages.json"
    )
    body = truncate_for_whatsapp(text)
    data = {
        "From": f"whatsapp:{TWILIO_FROM_NUMBER}",
        "To": f"whatsapp:+{phone.lstrip('+')}",
        "Body": body,
    }
    redacted = redact_phone(phone)
    try:
        response = httpx.post(
            url,
            data=data,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=TWILIO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        provider_id = response.json().get("sid")
        logger.info("Twilio sent to=%s sid=%s", redacted, provider_id)
        return SendResult(sent=True, provider_message_id=provider_id)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Twilio HTTP %s for to=%s: %s",
            exc.response.status_code,
            redacted,
            exc.response.text,
        )
        return SendResult(sent=False, error=f"http_{exc.response.status_code}")
    except Exception as exc:  # network / timeout / dns
        logger.warning("Twilio send failed for to=%s: %s", redacted, exc)
        return SendResult(sent=False, error=str(exc))
