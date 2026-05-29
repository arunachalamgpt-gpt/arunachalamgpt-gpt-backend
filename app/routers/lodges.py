"""Lodge directory and availability HTTP endpoints.

Routes mounted under `/lodges`:

- `GET /lodges` — directory list with filters + pagination
- `GET /lodges/search` — verified lodges + backups for a target check-in date
- `GET /lodges/{id}` — single lodge details
- `POST /lodges` — admin: create a lodge
- `PATCH /lodges/{id}` — admin: toggle `verified`, change prices
- `GET /lodges/{id}/availability` — read availability for a date
- `POST /lodges/{id}/availability` — owner's daily `AVAIL N` update
"""

import logging
from datetime import date as date_t
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AvailabilityNotFoundError, LodgeNotFoundError
from app.models.lodge import Lodge
from app.schemas.lodge import (
    AvailabilityOut,
    AvailabilityUpdate,
    LodgeCreate,
    LodgeOut,
    LodgeSearchResponse,
    LodgeUpdate,
    LodgeWithAvailability,
)
from app.services import availability as availability_svc
from app.services.pricing import price_for_date

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lodges", tags=["lodges"])

ERROR_RESPONSES_NOT_FOUND = {404: {"description": "Lodge not found"}}


@router.get(
    "",
    response_model=list[LodgeOut],
    summary="List lodges",
    description=(
        "Returns verified lodges by default. Use `verified_only=false` for the "
        "full directory. Pagination via `limit` (max 200) and `offset`."
    ),
)
def list_lodges(
    verified_only: bool = True,
    max_walk_minutes: Optional[int] = Query(None, ge=0, le=240),
    max_price: Optional[int] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Lodge)
    if verified_only:
        stmt = stmt.where(Lodge.verified.is_(True))
    if max_walk_minutes is not None:
        stmt = stmt.where(Lodge.walk_minutes_to_temple <= max_walk_minutes)
    if max_price is not None:
        stmt = stmt.where(Lodge.price_normal <= max_price)
    stmt = stmt.order_by(Lodge.walk_minutes_to_temple).limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


@router.get(
    "/search",
    response_model=LodgeSearchResponse,
    summary="Search verified lodges with availability + backups",
    description=(
        "Primary list contains lodges with rooms free for the given date.\n\n"
        "When a lodge is full, it falls into the **backups** list — these are "
        "suggested when the devotee's preferred lodge is unavailable "
        "(per Method 3 in the design doc). Lodges with no availability row "
        "for the date are treated as full."
    ),
)
def search_with_availability(
    checkin_date: date_t = Query(..., description="Target arrival date"),
    max_walk_minutes: Optional[int] = Query(None, ge=0, le=240),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    limit_primary: int = Query(3, ge=1, le=10),
    limit_backups: int = Query(2, ge=0, le=10),
    db: Session = Depends(get_db),
):
    stmt = select(Lodge).where(Lodge.verified.is_(True))
    if max_walk_minutes is not None:
        stmt = stmt.where(Lodge.walk_minutes_to_temple <= max_walk_minutes)
    lodges: list[Lodge] = list(
        db.execute(stmt.order_by(Lodge.walk_minutes_to_temple)).scalars()
    )

    primary: list[LodgeWithAvailability] = []
    backups: list[LodgeWithAvailability] = []
    for lodge in lodges:
        avail = availability_svc.get_availability(db, lodge.id, checkin_date)
        rooms = avail.rooms_available if avail else 0
        is_full = rooms == 0
        price = price_for_date(lodge, checkin_date)
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue

        item = LodgeWithAvailability(
            **LodgeOut.model_validate(lodge).model_dump(),
            rooms_available=rooms,
            is_full=is_full,
            price_for_date=price,
        )
        if not item.is_full and len(primary) < limit_primary:
            primary.append(item)
        elif len(backups) < limit_backups:
            backups.append(item)

    return LodgeSearchResponse(date=checkin_date, primary=primary, backups=backups)


@router.get(
    "/{lodge_id}",
    response_model=LodgeOut,
    summary="Get lodge details",
    responses=ERROR_RESPONSES_NOT_FOUND,
)
def get_lodge(lodge_id: UUID, db: Session = Depends(get_db)):
    lodge = db.get(Lodge, lodge_id)
    if lodge is None:
        raise LodgeNotFoundError(details={"lodge_id": str(lodge_id)})
    return lodge


@router.post(
    "",
    response_model=LodgeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create lodge (admin)",
    description=(
        "Adds a new lodge to the directory. `verified` is forced to `False` here "
        "regardless of input — set it via `PATCH /lodges/{id}` only after a "
        "personal site visit per the design doc checklist."
    ),
)
def create_lodge(payload: LodgeCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["verified"] = False
    lodge = Lodge(**data)
    db.add(lodge)
    db.commit()
    db.refresh(lodge)
    logger.info("Lodge created id=%s name=%s", lodge.id, lodge.name)
    return lodge


@router.patch(
    "/{lodge_id}",
    response_model=LodgeOut,
    summary="Update lodge (admin)",
    description="Partial update — pass only the fields to change.",
    responses=ERROR_RESPONSES_NOT_FOUND,
)
def update_lodge(
    lodge_id: UUID, payload: LodgeUpdate, db: Session = Depends(get_db)
):
    lodge = db.get(Lodge, lodge_id)
    if lodge is None:
        raise LodgeNotFoundError(details={"lodge_id": str(lodge_id)})
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(lodge, key, value)
    db.commit()
    db.refresh(lodge)
    return lodge


@router.get(
    "/{lodge_id}/availability",
    response_model=AvailabilityOut,
    summary="Read availability for a date",
    responses={404: {"description": "No availability record for that lodge/date"}},
)
def get_availability(
    lodge_id: UUID, date: date_t, db: Session = Depends(get_db)
):
    row = availability_svc.get_availability(db, lodge_id, date)
    if row is None:
        raise AvailabilityNotFoundError(
            details={"lodge_id": str(lodge_id), "date": date.isoformat()}
        )
    return row


@router.post(
    "/{lodge_id}/availability",
    response_model=AvailabilityOut,
    summary="Lodge owner's daily availability update (admin)",
    description=(
        "Sets `rooms_available` for a given date. In production this is invoked "
        "by the WhatsApp bot bridge when the owner replies `AVAIL 5` "
        "(Method 1 in the design doc)."
    ),
    responses=ERROR_RESPONSES_NOT_FOUND,
)
def update_availability(
    lodge_id: UUID, payload: AvailabilityUpdate, db: Session = Depends(get_db)
):
    row = availability_svc.set_availability(
        db,
        lodge_id,
        payload.date,
        payload.rooms_available,
        payload.update_source,
    )
    db.commit()
    db.refresh(row)
    return row
