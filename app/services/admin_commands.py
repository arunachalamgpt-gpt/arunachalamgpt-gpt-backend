"""Admin command parser (Section 8 of the design doc).

Forms supported:

- `ADMIN config <key> <value>`           → upsert temple_config
- `ADMIN crowd F:60 T50:15 T200:5`       → manual crowd report (source=admin)
- `ADMIN broadcast <language> <message>` → queued broadcast (returns payload;
  actual send-out is the WhatsApp bridge's job, out of scope here)

All other forms return `action="unknown"` instead of raising so the bot can
reply with a help message.
"""

import logging

from sqlalchemy.orm import Session

from app.errors import ValidationFailedError
from app.schemas.crowd import CrowdReportIn
from app.schemas.temple_config import AdminCommandResult
from app.services import crowd as crowd_svc
from app.services import temple_config

logger = logging.getLogger(__name__)

ADMIN_PREFIX = "ADMIN"


def _split_first(text: str, n: int) -> list[str]:
    return text.strip().split(maxsplit=n)


def dispatch(db: Session, *, sender_phone: str, text: str) -> AdminCommandResult:
    parts = _split_first(text, 1)
    if not parts or parts[0].upper() != ADMIN_PREFIX:
        return AdminCommandResult(
            action="unknown",
            detail="Message did not begin with ADMIN.",
        )

    if len(parts) < 2:
        return AdminCommandResult(
            action="unknown", detail="Missing sub-command after ADMIN."
        )

    remainder = parts[1].strip()
    head = remainder.split(maxsplit=1)
    verb = head[0].lower()
    tail = head[1] if len(head) > 1 else ""

    if verb == "config":
        return _handle_config(db, sender_phone=sender_phone, tail=tail)
    if verb == "crowd":
        return _handle_crowd(db, sender_phone=sender_phone, tail=tail)
    if verb == "broadcast":
        return _handle_broadcast(tail=tail)

    return AdminCommandResult(
        action="unknown", detail=f"Unknown ADMIN sub-command '{verb}'."
    )


def _handle_config(
    db: Session, *, sender_phone: str, tail: str
) -> AdminCommandResult:
    parts = tail.split(maxsplit=1)
    if len(parts) != 2:
        return AdminCommandResult(
            action="unknown",
            detail="Usage: ADMIN config <key> <value>",
        )
    key, value = parts[0], parts[1].strip()
    row = temple_config.upsert(db, key, value, updated_by=sender_phone)
    db.flush()
    logger.info("Admin config update key=%s value=%s by=%s", key, value, sender_phone)
    return AdminCommandResult(
        action="config_set",
        detail=f"{key} → {value}",
        payload={"key": row.key, "value": row.value},
    )


def _handle_crowd(
    db: Session, *, sender_phone: str, tail: str
) -> AdminCommandResult:
    if not tail:
        return AdminCommandResult(
            action="unknown",
            detail="Usage: ADMIN crowd F:N T50:N T200:N",
        )
    try:
        fields = crowd_svc.parse_volunteer_message(tail)
    except ValidationFailedError as exc:
        return AdminCommandResult(action="unknown", detail=exc.message)
    payload = CrowdReportIn(
        reporter_phone=sender_phone,
        free_wait_min=fields.free_wait_min,
        rs50_wait_min=fields.rs50_wait_min,
        rs200_wait_min=fields.rs200_wait_min,
        rs50_sold_out=fields.rs50_sold_out,
        rs200_sold_out=fields.rs200_sold_out,
        source="admin",
    )
    row = crowd_svc.record_status(db, payload)
    return AdminCommandResult(
        action="crowd_report",
        detail="Crowd snapshot recorded.",
        payload={"id": str(row.id)},
    )


def _handle_broadcast(*, tail: str) -> AdminCommandResult:
    parts = tail.split(maxsplit=1)
    if len(parts) != 2:
        return AdminCommandResult(
            action="unknown",
            detail="Usage: ADMIN broadcast <language> <message>",
        )
    language, message = parts[0].lower(), parts[1].strip()
    return AdminCommandResult(
        action="broadcast",
        detail=f"Broadcast queued ({language}).",
        payload={"language": language, "message": message},
    )
