"""Crowd reporting + live status + prediction endpoints (Feature 1).

Routes mounted under `/crowd`:

- `POST /crowd/reports` — volunteer raw `F:180 T50:40 T200:15` text
- `POST /crowd/reports/structured` — same as above but caller pre-parses
- `GET  /crowd/current` — live answer with fallback rules applied
- `GET  /crowd/predict` — average wait times from history
- `POST /crowd/history` — post-darshan crowdsourced observation (Step 10)
- `GET  /crowd/history` — paginated history listing
"""

import logging
from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models.crowd import CrowdHistory
from app.schemas.crowd import (
    CrowdCurrentResponse,
    CrowdHistoryIn,
    CrowdHistoryOut,
    CrowdPredictionResponse,
    CrowdReportIn,
    CrowdStatusOut,
    VolunteerRawMessage,
)
from app.services import crowd as crowd_svc
from app.services import prediction as prediction_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crowd", tags=["crowd"])


@router.post(
    "/reports",
    response_model=CrowdStatusOut,
    status_code=status.HTTP_201_CREATED,
    summary="Volunteer raw WhatsApp message",
    description=(
        "Body carries the verbatim `F:180 T50:40 T200:15` string the volunteer sent. "
        "Server parses it and persists a `crowd_status` row. `SOLD` flips the "
        "corresponding sold-out flag and stores NULL in the wait column.\n\n"
        "**Tokens:**\n"
        "- `F:<minutes>` — free line wait (required for live status)\n"
        "- `T50:<minutes|SOLD>` — Rs.50 line\n"
        "- `T200:<minutes|SOLD>` — Rs.200 line\n\n"
        "Tokens may appear in any order; missing tokens are recorded as NULL."
    ),
    responses={
        400: {"description": "Unparseable text or invalid phone"},
        401: {"description": "Missing or invalid X-API-Key (when API_KEY is set)"},
        422: {"description": "Validation failed on the request body"},
    },
    dependencies=[Depends(require_api_key)],
)
def submit_raw(payload: VolunteerRawMessage, db: Session = Depends(get_db)):
    fields = crowd_svc.parse_volunteer_message(payload.text)
    structured = CrowdReportIn(
        reporter_phone=payload.reporter_phone,
        free_wait_min=fields.free_wait_min,
        rs50_wait_min=fields.rs50_wait_min,
        rs200_wait_min=fields.rs200_wait_min,
        rs50_sold_out=fields.rs50_sold_out,
        rs200_sold_out=fields.rs200_sold_out,
        notes=payload.notes,
        source="volunteer",
    )
    row = crowd_svc.record_status(db, structured)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/reports/structured",
    response_model=CrowdStatusOut,
    status_code=status.HTTP_201_CREATED,
    summary="Structured volunteer report",
    description=(
        "Same as `/crowd/reports` but the client has already extracted the "
        "wait minutes and sold-out flags — useful for the admin dashboard "
        "and tests."
    ),
    responses={
        401: {"description": "Missing or invalid X-API-Key (when API_KEY is set)"},
        422: {"description": "Validation failed on the request body"},
    },
    dependencies=[Depends(require_api_key)],
)
def submit_structured(payload: CrowdReportIn, db: Session = Depends(get_db)):
    row = crowd_svc.record_status(db, payload)
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/current",
    response_model=CrowdCurrentResponse,
    summary="Live East-gate crowd status",
    description=(
        "Applies the fallback rules from Section 9 of the design doc:\n\n"
        "| Age of latest report | `freshness` value |\n"
        "|----------------------|-------------------|\n"
        "| < 2 hours            | `live`            |\n"
        "| 2 – 6 hours          | `stale`           |\n"
        "| > 6 hours            | `prediction_only` |\n"
        "| Outside opening hrs  | `closed`          |\n\n"
        "Opening hours come from `temple_open_time` and `temple_close_time` in "
        "`temple_config` and can be changed at runtime via "
        "`PUT /admin/config/{key}`."
    ),
)
def current(db: Session = Depends(get_db)):
    return crowd_svc.current_status(db)


@router.get(
    "/predict",
    response_model=CrowdPredictionResponse,
    summary="Average waits from history",
    description=(
        "Returns the mean wait per line for matching `(hour_of_day, is_pournami, "
        "is_festival)` rows in `crowd_history`. `sample_size=0` means no data — "
        "the bot should fall back to a generic disclaimer."
    ),
)
def predict(
    visit_date: date_t = Query(...),
    hour_of_day: int = Query(..., ge=0, le=23),
    is_pournami: bool = Query(False),
    is_festival: bool = Query(False),
    db: Session = Depends(get_db),
):
    return prediction_svc.predict(
        db,
        visit_date=visit_date,
        hour_of_day=hour_of_day,
        is_pournami=is_pournami,
        is_festival=is_festival,
    )


@router.post(
    "/history",
    response_model=CrowdHistoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a post-darshan observation (Step 10)",
    description=(
        "Stores the wait the devotee experienced. Aggregations of this table "
        "back the `/crowd/predict` endpoint."
    ),
    responses={
        401: {"description": "Missing or invalid X-API-Key (when API_KEY is set)"},
        422: {"description": "Validation failed (e.g. hour_of_day out of range)"},
    },
    dependencies=[Depends(require_api_key)],
)
def add_history(payload: CrowdHistoryIn, db: Session = Depends(get_db)):
    row = prediction_svc.record_history(db, payload)
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/history",
    response_model=list[CrowdHistoryOut],
    summary="List crowd history",
    description="Filter by `visit_date` and/or `is_pournami`. Newest first; paginated.",
)
def list_history(
    visit_date: Optional[date_t] = Query(None),
    is_pournami: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(CrowdHistory)
    if visit_date is not None:
        stmt = stmt.where(CrowdHistory.visit_date == visit_date)
    if is_pournami is not None:
        stmt = stmt.where(CrowdHistory.is_pournami.is_(is_pournami))
    stmt = stmt.order_by(CrowdHistory.created_at.desc()).limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()
