"""SQLModel table for cross-process idempotency.

Twilio retries on 5xx/timeout. The in-memory LRU we had earlier only protects
a single worker; with Render's autoscaler or multiple uvicorn workers, a
retry can land on a different process and re-run the state machine.

This table is the single source of truth. We INSERT the `message_id` on
first sight; the unique index makes the second concurrent INSERT fail, which
we treat as "duplicate, skip".

`first_seen_at` is for ops debugging only — there's no scheduled cleanup
yet. Rows are tiny (~80 bytes); even at 10k WhatsApp messages/day, the table
grows ~3 MB/year. A `DELETE WHERE first_seen_at < now() - interval '30 days'`
cron can come later when it matters.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProcessedMessage(SQLModel, table=True):
    __tablename__ = "processed_messages"

    # Twilio MessageSid (`SM...` / `MM...`) — primary key for natural dedup.
    message_id: str = Field(primary_key=True, max_length=64)
    first_seen_at: datetime = Field(default_factory=_utcnow, index=True)
    source: str = Field(default="twilio", max_length=20)
