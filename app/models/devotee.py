"""SQLModel table for devotee profiles.

Each WhatsApp number is one row. `onboarding_state` advances along the
10-step user journey: `new → language_selected → profile_complete →
registered → visited`. `language` is captured once on first interaction and
honoured for every future reply.
"""

from datetime import date as date_t
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DevoteeProfile(SQLModel, table=True):
    """A devotee identified by their WhatsApp phone number."""

    __tablename__ = "devotee_profiles"

    phone: str = Field(primary_key=True, max_length=20)
    name: Optional[str] = Field(default=None, max_length=120)
    language: Optional[str] = Field(default=None, max_length=10)
    has_elderly: bool = False
    has_children: bool = False
    planned_visit_date: Optional[date_t] = None
    home_city: Optional[str] = Field(default=None, max_length=80)
    onboarding_state: str = Field(default="new", max_length=24)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    # Loop-detection: hash of the last English reply we sent + how many times
    # in a row we've sent it. Lets us vary the response when a user keeps
    # asking the same thing instead of mechanically repeating ourselves.
    last_reply_hash: Optional[str] = Field(default=None, max_length=64)
    last_reply_at: Optional[datetime] = None
    repeat_count: int = Field(default=0)
