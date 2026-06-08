"""Crowd reporting: volunteer message parser + current-status fallback.

Volunteer message format (Section 3 of the design doc):

    F:180 T50:40 T200:15

`F` is the free line, `T50` is the Rs.50 line, `T200` is the Rs.200 line.
Each value is a non-negative integer (minutes) **or** the literal `SOLD`
which flips the sold-out flag and leaves the wait minute as NULL.

Fallback rules (Section 9):

| age of latest report     | freshness         |
|--------------------------|-------------------|
| < 2 h                    | `live`            |
| 2 h – 6 h                | `stale`           |
| > 6 h                    | `prediction_only` |
| before open / after close| `closed`          |
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import LOCAL_TZ_OFFSET_MINUTES
from app.errors import ValidationFailedError
from app.models.crowd import CrowdStatus
from app.schemas.crowd import CrowdCurrentResponse, CrowdReportIn
from app.services import temple_config


@dataclass
class ParsedCrowdFields:
    """Internal carrier for parser output — no Pydantic validation overhead."""

    free_wait_min: Optional[int] = None
    rs50_wait_min: Optional[int] = None
    rs200_wait_min: Optional[int] = None
    rs50_sold_out: bool = False
    rs200_sold_out: bool = False

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"^(F|T50|T200):(\d+|SOLD)$", re.IGNORECASE)


def parse_volunteer_message(text: str) -> ParsedCrowdFields:
    """Parse `F:180 T50:40 T200:15` into a `ParsedCrowdFields`.

    Raises `ValidationFailedError` if the format is broken or duplicate
    tokens appear. The caller composes a `CrowdReportIn` from this plus the
    sender's phone.
    """
    tokens = [t for t in text.strip().split() if t]
    if not tokens:
        raise ValidationFailedError("Empty crowd report")

    seen: dict[str, str] = {}
    for tok in tokens:
        m = _TOKEN_RE.match(tok)
        if not m:
            raise ValidationFailedError(
                f"Unrecognised token '{tok}'. Expected F:N, T50:N or T200:N."
            )
        key = m.group(1).upper()
        if key in seen:
            raise ValidationFailedError(f"Token '{key}' appears more than once")
        seen[key] = m.group(2).upper()

    def _as_wait(raw: Optional[str]) -> tuple[Optional[int], bool]:
        if raw is None:
            return None, False
        if raw == "SOLD":
            return None, True
        return int(raw), False

    free_wait, _ = _as_wait(seen.get("F"))
    rs50_wait, rs50_sold = _as_wait(seen.get("T50"))
    rs200_wait, rs200_sold = _as_wait(seen.get("T200"))

    return ParsedCrowdFields(
        free_wait_min=free_wait,
        rs50_wait_min=rs50_wait,
        rs200_wait_min=rs200_wait,
        rs50_sold_out=rs50_sold,
        rs200_sold_out=rs200_sold,
    )


def record_status(db: Session, payload: CrowdReportIn) -> CrowdStatus:
    """Persist a `CrowdStatus` row and reflect sold-out flags into `temple_config`."""
    row = CrowdStatus(
        reported_by=payload.reporter_phone,
        free_wait_min=payload.free_wait_min,
        rs50_wait_min=payload.rs50_wait_min,
        rs200_wait_min=payload.rs200_wait_min,
        rs50_sold_out=payload.rs50_sold_out,
        rs200_sold_out=payload.rs200_sold_out,
        notes=payload.notes,
        source=payload.source,
    )
    db.add(row)
    temple_config.upsert(
        db,
        "rs50_sold_out",
        "true" if payload.rs50_sold_out else "false",
        updated_by=payload.reporter_phone,
    )
    temple_config.upsert(
        db,
        "rs200_sold_out",
        "true" if payload.rs200_sold_out else "false",
        updated_by=payload.reporter_phone,
    )
    db.flush()
    logger.info(
        "Crowd report recorded by=%s F=%s T50=%s T200=%s source=%s",
        payload.reporter_phone,
        payload.free_wait_min,
        payload.rs50_wait_min,
        payload.rs200_wait_min,
        payload.source,
    )
    return row


def _local_tz() -> timezone:
    return timezone(timedelta(minutes=LOCAL_TZ_OFFSET_MINUTES))


def _parse_hhmm(value: Optional[str], default: time) -> time:
    if not value:
        return default
    try:
        hh, mm = value.strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return default


def latest_status(db: Session) -> Optional[CrowdStatus]:
    return db.execute(
        select(CrowdStatus).order_by(CrowdStatus.reported_at.desc()).limit(1)
    ).scalar_one_or_none()


def current_status(
    db: Session, *, now: Optional[datetime] = None
) -> CrowdCurrentResponse:
    """Return the live status, applying the open/close + freshness fallback rules."""
    tz = _local_tz()
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    now_local = now.astimezone(tz)

    open_time = _parse_hhmm(
        (cfg := temple_config.get(db, "temple_open_time")) and cfg.value, time(5, 30)
    )
    close_time = _parse_hhmm(
        (cfg := temple_config.get(db, "temple_close_time")) and cfg.value, time(21, 0)
    )

    latest = latest_status(db)
    rs50_sold = temple_config.is_truthy(
        (cfg := temple_config.get(db, "rs50_sold_out")) and cfg.value
    )
    rs200_sold = temple_config.is_truthy(
        (cfg := temple_config.get(db, "rs200_sold_out")) and cfg.value
    )

    current_time = now_local.time()
    if current_time < open_time or current_time >= close_time:
        return CrowdCurrentResponse(
            freshness="closed",
            source="prediction",
            reported_at=None,
            age_minutes=None,
            free_wait_min=None,
            rs50_wait_min=None,
            rs200_wait_min=None,
            rs50_sold_out=rs50_sold,
            rs200_sold_out=rs200_sold,
            message=(
                f"Temple closed (opens {open_time.strftime('%H:%M')}). "
                "Predictions for tomorrow available via /crowd/predict."
            ),
        )

    if latest is None:
        return CrowdCurrentResponse(
            freshness="prediction_only",
            source="prediction",
            reported_at=None,
            age_minutes=None,
            free_wait_min=None,
            rs50_wait_min=None,
            rs200_wait_min=None,
            rs50_sold_out=rs50_sold,
            rs200_sold_out=rs200_sold,
            message="No volunteer report yet today — use /crowd/predict for an estimate.",
        )

    reported_at = latest.reported_at
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)
    age = now.astimezone(timezone.utc) - reported_at.astimezone(timezone.utc)
    age_minutes = max(0, int(age.total_seconds() // 60))

    if age_minutes < 120:
        freshness = "live"
        message = "Live volunteer report."
    elif age_minutes < 360:
        freshness = "stale"
        message = (
            "Volunteer report is over 2 hours old — values may be outdated; "
            "consider /crowd/predict."
        )
    else:
        return CrowdCurrentResponse(
            freshness="prediction_only",
            source="prediction",
            reported_at=reported_at,
            age_minutes=age_minutes,
            free_wait_min=None,
            rs50_wait_min=None,
            rs200_wait_min=None,
            rs50_sold_out=rs50_sold,
            rs200_sold_out=rs200_sold,
            message="Latest volunteer data is over 6 hours old — using prediction.",
        )

    return CrowdCurrentResponse(
        freshness=freshness,
        source=latest.source if latest.source in ("volunteer", "admin") else "volunteer",
        reported_at=reported_at,
        age_minutes=age_minutes,
        free_wait_min=latest.free_wait_min,
        rs50_wait_min=latest.rs50_wait_min,
        rs200_wait_min=latest.rs200_wait_min,
        rs50_sold_out=latest.rs50_sold_out or rs50_sold,
        rs200_sold_out=latest.rs200_sold_out or rs200_sold,
        message=message,
    )
