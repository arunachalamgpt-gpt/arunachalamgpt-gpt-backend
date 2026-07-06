"""Per-user conversation memory.

Stores each user message and each bot reply in `conversation_turns`, and
exposes helpers to load the recent history back as OpenAI-shaped chat
messages that the intent classifier and Q&A service can prepend to their
prompts. Bot replies are stored in ENGLISH (pre-translation) so the LLM
history stays consistent regardless of the user's language.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation_turn import ConversationTurn

# How many prior turns to include in the LLM context. 6 = ~3 exchanges, enough
# for a follow-up ("what about tomorrow?") without bloating token cost.
DEFAULT_HISTORY_TURNS = 6

# Cap per-user retention. Older rows are purged by `purge_old`, called
# out-of-band from a cron/admin path.
DEFAULT_RETENTION_DAYS = 30


def record_turn(
    db: Session,
    *,
    phone: str,
    role: str,
    text: str,
    intent: Optional[str] = None,
) -> ConversationTurn:
    """Persist a single conversation turn. Silently truncates over-long text."""
    row = ConversationTurn(
        phone=phone,
        role=role,
        text=text[:2000],
        intent=intent,
    )
    db.add(row)
    db.flush()
    return row


def load_recent(
    db: Session, *, phone: str, limit: int = DEFAULT_HISTORY_TURNS
) -> list[dict]:
    """Return the last `limit` turns as OpenAI-format chat messages.

    Ordered oldest-first so callers can splice them between the system prompt
    and the current user message.
    """
    rows = list(
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.phone == phone)
            .order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc())
            .limit(limit)
        ).scalars()
    )
    rows.reverse()
    messages: list[dict] = []
    for row in rows:
        openai_role = "assistant" if row.role == "bot" else "user"
        messages.append({"role": openai_role, "content": row.text})
    return messages


def last_turn(
    db: Session, *, phone: str, role: str
) -> Optional[ConversationTurn]:
    """Return the most recent turn for `phone` with the given `role`, or None."""
    return db.execute(
        select(ConversationTurn)
        .where(
            ConversationTurn.phone == phone,
            ConversationTurn.role == role,
        )
        .order_by(
            ConversationTurn.created_at.desc(),
            ConversationTurn.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def clear_for_phone(db: Session, phone: str) -> int:
    """Delete all conversation turns for a phone. Used by `/reset`."""
    result = db.execute(
        ConversationTurn.__table__.delete().where(
            ConversationTurn.phone == phone
        )
    )
    db.flush()
    return result.rowcount or 0


def purge_old(
    db: Session, *, older_than_days: int = DEFAULT_RETENTION_DAYS
) -> int:
    """Delete `conversation_turns` rows older than the cutoff.

    Retention keeps the table bounded — a chatty user shouldn't fill the DB.
    Intended for a cron/admin call, NOT the request path.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    cutoff_naive = cutoff.replace(tzinfo=None)
    result = db.execute(
        ConversationTurn.__table__.delete().where(
            ConversationTurn.created_at < cutoff_naive
        )
    )
    db.flush()
    return result.rowcount or 0
