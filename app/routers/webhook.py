"""WhatsApp webhook routes.

Two endpoints:

- `POST /webhook/whatsapp` — internal JSON contract `{phone, text}`. Used by
  tests, Postman, and any custom integration. No signature verification.

- `POST /webhook/whatsapp/twilio` — Twilio-shaped inbound. Validates
  `X-Twilio-Signature`, parses the form body, runs the same devotee-flow
  pipeline, then sends the reply back to the user via the Twilio REST API.
  Returns 503 when `TWILIO_ENABLED=false` so a misconfigured deploy fails
  loudly instead of silently dropping messages.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.devotee import BotReply, IncomingWhatsAppMessage
from app.services import devotee_flow, whatsapp

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post(
    "/whatsapp",
    response_model=BotReply,
    status_code=status.HTTP_200_OK,
    summary="Inbound WhatsApp message (internal JSON)",
    description=(
        "Drives the 10-step user journey. The bridge calls this once per "
        "inbound message and sends the returned `text` back to the user.\n\n"
        "**Dispatch order** (per turn, after language selection):\n\n"
        "1. **GPT-4o intent classifier** "
        "([`app.services.intent`](../app/services/intent.py)) — understands "
        "romanized Indic text (*crowd enna*, *epdi varuvadhu*), code-mix, "
        "and free-form questions. Fires only when `OPENAI_ENABLED=true`.\n"
        "2. **Keyword matcher** — runs when the LLM is disabled or returns "
        "`unknown`. Recognises:\n"
        "   - `YYYY-MM-DD` or `DD/MM/YYYY` in text → registers visit + family flags\n"
        "   - `crowd / queue / wait / line / now` → live crowd summary\n"
        "   - `plan / advice / when / best time` → Step 3 recommendation\n"
        "   - `change to <language>` / `switch to <language>` → updates language\n"
        "3. **Translator** — outgoing `text` is rendered in the devotee's "
        "saved language. English replies pass through unchanged. Falls back "
        "to English if the LLM is unavailable.\n\n"
        "**State transitions:**\n\n"
        "```\n"
        "new ── language pick (1-5) ──▶ language_selected\n"
        "                                    │\n"
        "                            visit date in text\n"
        "                                    ▼\n"
        "                              registered\n"
        "```\n\n"
        "**Recognised LLM intents:** `select_language`, `register_visit`, "
        "`ask_crowd`, `ask_plan`, `change_language`, `unknown`.\n\n"
        "**Behaviour without OpenAI:** the bot still works — it just uses "
        "the keyword path and replies in English. No outbound call is made "
        "to OpenAI when `OPENAI_ENABLED=false`."
    ),
    responses={422: {"description": "Invalid phone or empty text"}},
)
def incoming(msg: IncomingWhatsAppMessage, db: Session = Depends(get_db)):
    reply = devotee_flow.handle_incoming(db, msg)
    db.commit()
    return reply


@router.post(
    "/whatsapp/twilio",
    status_code=status.HTTP_200_OK,
    summary="Twilio WhatsApp webhook",
    description=(
        "Form-encoded inbound from Twilio's WhatsApp sandbox or production "
        "number. The route:\n\n"
        "1. Validates `X-Twilio-Signature` (HMAC-SHA1 of URL + sorted form "
        "params). Mismatch → 403.\n"
        "2. Strips `whatsapp:+` from the `From` field → normalised phone.\n"
        "3. Runs the same `devotee_flow.handle_incoming` pipeline as the "
        "internal route.\n"
        "4. Posts the reply back via the Twilio Messages REST API.\n\n"
        "Set `TWILIO_WEBHOOK_URL` to the **exact** URL Twilio is configured "
        "to call (signature is computed over this URL — a mismatch fails "
        "verification). When developing locally, expose `/webhook/whatsapp/"
        "twilio` via ngrok and paste that URL in both Twilio and "
        "`TWILIO_WEBHOOK_URL`.\n\n"
        "Returns 503 when `TWILIO_ENABLED=false`."
    ),
    responses={
        200: {"description": "Inbound accepted; reply sent (or attempted)."},
        403: {"description": "Signature missing or invalid."},
        400: {"description": "Body missing required fields after parse."},
        503: {"description": "Twilio bridge disabled."},
    },
)
async def twilio_inbound(request: Request, db: Session = Depends(get_db)):
    if not whatsapp.is_enabled():
        raise HTTPException(
            status_code=503, detail="Twilio bridge disabled (TWILIO_ENABLED=false)"
        )
    parsed = await whatsapp.parse_inbound(request)
    if parsed is None:
        raise HTTPException(status_code=403, detail="Invalid Twilio request")

    # Idempotency: Twilio retries on 5xx/timeout — skip if we already handled
    # this MessageSid. Returns 200 with `duplicate: true` so Twilio stops.
    if whatsapp.is_duplicate_message(parsed.message_id):
        logger.info(
            "Twilio retry ignored sid=%s to=%s",
            parsed.message_id,
            whatsapp.redact_phone(parsed.phone),
        )
        return {
            "accepted": True,
            "duplicate": True,
            "to": whatsapp.redact_phone(parsed.phone),
        }

    try:
        msg = IncomingWhatsAppMessage(phone=parsed.phone, text=parsed.text)
    except Exception as exc:
        logger.warning("Twilio payload failed validation: %s", exc)
        raise HTTPException(status_code=400, detail="Bad inbound payload")

    reply = devotee_flow.handle_incoming(db, msg)
    db.commit()

    result = whatsapp.send_text(parsed.phone, reply.text)
    return {
        "accepted": True,
        "to": whatsapp.redact_phone(parsed.phone),
        "reply_state": reply.state,
        "send": {
            "sent": result.sent,
            "provider_message_id": result.provider_message_id,
            "error": result.error,
        },
    }
