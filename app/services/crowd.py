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
from app.schemas.crowd import CrowdCurrentResponse, CrowdPredictionResponse, CrowdReportIn
from app.services import lunar_calendar, prediction, temple_config


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


def _predict_now(db: Session, now_local: datetime) -> CrowdPredictionResponse:
    """Run a prediction for the current hour-of-day, with festival/pournami
    flags from the lunar calendar table. Safe — returns NULLs if no history.
    """
    today = now_local.date()
    try:
        return prediction.predict(
            db,
            visit_date=today,
            hour_of_day=now_local.hour,
            is_pournami=lunar_calendar.is_pournami(today),
            is_festival=lunar_calendar.is_karthigai_deepam(today),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Prediction failed: %s", exc)
        return CrowdPredictionResponse(
            visit_date=today,
            hour_of_day=now_local.hour,
            is_pournami=False,
            is_festival=False,
            sample_size=0,
            free_wait_min=None,
            rs50_wait_min=None,
            rs200_wait_min=None,
        )


def _prediction_message(
    pred: CrowdPredictionResponse,
    *,
    reason: str,
    age_hours: Optional[int] = None,
) -> str:
    """Friendly user-facing message for prediction-only branches."""
    # A history row may have all-None wait minutes (e.g. SOLD across the board),
    # so sample_size>0 doesn't guarantee usable numbers. Check both.
    have_numbers = any(
        v is not None
        for v in (pred.free_wait_min, pred.rs50_wait_min, pred.rs200_wait_min)
    )
    if pred.sample_size == 0 or not have_numbers:
        # No history to lean on either — be honest.
        if reason == "stale_volunteer":
            return (
                f"Live volunteer report is {age_hours}h old and we don't yet have "
                "enough historical data for this hour. Best to ask a volunteer at "
                "the gate or check back later."
            )
        return (
            "No fresh volunteer report yet today and not enough history to "
            "estimate — please check back in a bit."
        )
    lead = "Based on past visits at this hour"
    if pred.is_festival:
        lead = "Festival day — based on past Karthigai Deepam observations"
    elif pred.is_pournami:
        lead = "Pournami (full-moon) day — expect heavier crowds; based on past Pournami visits"
    if reason == "stale_volunteer":
        return (
            f"Live volunteer report is {age_hours}h old. {lead} "
            f"(n={pred.sample_size}), here's an estimate:"
        )
    return f"No volunteer report yet today. {lead} (n={pred.sample_size}), here's an estimate:"


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
        pred = _predict_now(db, now_local)
        return CrowdCurrentResponse(
            freshness="prediction_only",
            source="prediction",
            reported_at=None,
            age_minutes=None,
            free_wait_min=pred.free_wait_min,
            rs50_wait_min=pred.rs50_wait_min,
            rs200_wait_min=pred.rs200_wait_min,
            rs50_sold_out=rs50_sold,
            rs200_sold_out=rs200_sold,
            message=_prediction_message(pred, reason="no_volunteer_today"),
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
        pred = _predict_now(db, now_local)
        return CrowdCurrentResponse(
            freshness="prediction_only",
            source="prediction",
            reported_at=reported_at,
            age_minutes=age_minutes,
            free_wait_min=pred.free_wait_min,
            rs50_wait_min=pred.rs50_wait_min,
            rs200_wait_min=pred.rs200_wait_min,
            rs50_sold_out=rs50_sold,
            rs200_sold_out=rs200_sold,
            message=_prediction_message(
                pred, reason="stale_volunteer", age_hours=age_minutes // 60
            ),
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
