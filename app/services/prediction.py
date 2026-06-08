"""Average-wait prediction from `crowd_history`.

Used by the morning alert (Step 7) and the planning conversation (Step 3) when
no fresh volunteer report is available. Matches rows by `hour_of_day`,
`is_pournami`, `is_festival`. Returns NULL per line when the bucket is empty.
"""

from datetime import date as date_t
from statistics import mean
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crowd import CrowdHistory
from app.schemas.crowd import CrowdPredictionResponse


def predict(
    db: Session,
    *,
    visit_date: date_t,
    hour_of_day: int,
    is_pournami: bool = False,
    is_festival: bool = False,
) -> CrowdPredictionResponse:
    rows = list(
        db.execute(
            select(CrowdHistory).where(
                CrowdHistory.hour_of_day == hour_of_day,
                CrowdHistory.is_pournami.is_(is_pournami),
                CrowdHistory.is_festival.is_(is_festival),
            )
        ).scalars()
    )

    def _mean(values: list[Optional[int]]) -> Optional[int]:
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        return int(round(mean(clean)))

    return CrowdPredictionResponse(
        visit_date=visit_date,
        hour_of_day=hour_of_day,
        is_pournami=is_pournami,
        is_festival=is_festival,
        sample_size=len(rows),
        free_wait_min=_mean([r.free_wait_min for r in rows]),
        rs50_wait_min=_mean([r.rs50_wait_min for r in rows]),
        rs200_wait_min=_mean([r.rs200_wait_min for r in rows]),
    )


def record_history(db: Session, payload) -> CrowdHistory:
    """Insert a post-darshan observation."""
    row = CrowdHistory(
        visit_date=payload.visit_date,
        hour_of_day=payload.hour_of_day,
        is_pournami=payload.is_pournami,
        is_festival=payload.is_festival,
        free_wait_min=payload.free_wait_min,
        rs50_wait_min=payload.rs50_wait_min,
        rs200_wait_min=payload.rs200_wait_min,
        source=payload.source,
    )
    db.add(row)
    db.flush()
    return row
