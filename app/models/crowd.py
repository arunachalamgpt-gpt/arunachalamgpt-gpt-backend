"""SQLModel tables for crowd reporting and history.

`CrowdStatus` is the running ledger of per-hour volunteer reports; the latest
row drives the live answer surfaced via `/crowd/current`. `SOLD` from the
volunteer text becomes `NULL` in `*_wait_min` with the corresponding
`*_sold_out` flag flipped, keeping the wait columns purely numeric.

`CrowdHistory` is the long-term observation set used for predictions when no
recent volunteer report is available. Rows are inserted post-darshan from user
crowdsourcing (Step 10 of the user journey) and via periodic rollups.
"""

import uuid
from datetime import date as date_t
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CrowdStatus(SQLModel, table=True):
    """A single volunteer (or admin) snapshot of East-gate line waits."""

    __tablename__ = "crowd_status"
    __table_args__ = (
        CheckConstraint(
            "free_wait_min IS NULL OR free_wait_min >= 0", name="ck_free_wait_nonneg"
        ),
        CheckConstraint(
            "rs50_wait_min IS NULL OR rs50_wait_min >= 0", name="ck_rs50_wait_nonneg"
        ),
        CheckConstraint(
            "rs200_wait_min IS NULL OR rs200_wait_min >= 0", name="ck_rs200_wait_nonneg"
        ),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    reported_at: datetime = Field(default_factory=_utcnow, index=True)
    reported_by: str = Field(max_length=20)
    free_wait_min: Optional[int] = None
    rs50_wait_min: Optional[int] = None
    rs200_wait_min: Optional[int] = None
    rs50_sold_out: bool = False
    rs200_sold_out: bool = False
    notes: Optional[str] = None
    source: str = Field(default="volunteer", max_length=20)


class CrowdHistory(SQLModel, table=True):
    """Hourly observations used to predict waits when volunteer data is stale."""

    __tablename__ = "crowd_history"
    __table_args__ = (
        CheckConstraint(
            "hour_of_day BETWEEN 0 AND 23", name="ck_history_hour_range"
        ),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    visit_date: date_t = Field(index=True)
    hour_of_day: int = Field(index=True)
    is_pournami: bool = False
    is_festival: bool = False
    free_wait_min: Optional[int] = None
    rs50_wait_min: Optional[int] = None
    rs200_wait_min: Optional[int] = None
    source: str = Field(default="post_visit", max_length=20)
    created_at: datetime = Field(default_factory=_utcnow)
