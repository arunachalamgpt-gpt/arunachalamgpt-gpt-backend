"""WhatsApp webhook stub.

Accepts a normalised `{phone, text}` body from the WhatsApp bridge
(Twilio / 360dialog adaptor — not implemented here). Runs the devotee-flow
state machine and returns a `BotReply` the bridge should send back to the
user. Persisting state changes (language selected, visit date saved) happens
inside `devotee_flow.handle_incoming` and is committed before the response.
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.devotee import BotReply, IncomingWhatsAppMessage
from app.services import devotee_flow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post(
    "/whatsapp",
    response_model=BotReply,
    status_code=status.HTTP_200_OK,
    summary="Inbound WhatsApp message",
    description=(
        "Drives the 10-step user journey. The bridge calls this once per "
        "inbound message and sends the returned `text` back to the user.\n\n"
        "**State transitions:**\n\n"
        "```\n"
        "new ── language pick (1-5) ──▶ language_selected\n"
        "                                    │\n"
        "                            visit date in text\n"
        "                                    ▼\n"
        "                              registered\n"
        "```\n\n"
        "**Recognised intents** (after language selection):\n"
        "- `YYYY-MM-DD` or `DD/MM/YYYY` in text → registers visit + family flags\n"
        "- Keywords `crowd / queue / wait / line / now` → returns `/crowd/current` summary\n"
        "- Keywords `plan / advice / when / best time` → returns Step 3 recommendation\n"
        "- `change to <language>` or `switch to <language>` → updates `language`"
    ),
    responses={422: {"description": "Invalid phone or empty text"}},
)
def incoming(msg: IncomingWhatsAppMessage, db: Session = Depends(get_db)):
    reply = devotee_flow.handle_incoming(db, msg)
    db.commit()
    return reply
