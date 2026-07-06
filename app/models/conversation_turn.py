"""One row per user or bot turn in a WhatsApp conversation.

The `intent` classifier and `temple_qa` service load the last few turns for
the sender's phone and pass them as prior messages to the LLM, so follow-up
questions like "what about tomorrow?" or "yes, with kids" are understood in
context of what was just said.

Kept minimal on purpose: no separate `session_id` — a WhatsApp thread is
identified by the phone number, and we cap retention with
`conversation.purge_old`.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationTurn(SQLModel, table=True):
    """A single turn — either a user message or a bot reply — persisted for context."""

    __tablename__ = "conversation_turns"

    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(max_length=20, index=True)
    role: str = Field(max_length=10)  # "user" | "bot"
    text: str = Field(max_length=2000)
    intent: Optional[str] = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
