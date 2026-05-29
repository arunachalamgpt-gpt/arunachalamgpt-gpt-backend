"""Room-availability business logic.

Backs three operational flows from the design doc:

- Method 1 (lodge owner daily update) → `set_availability`
- Method 2 (auto-reduce on booking / auto-restore on cancel) →
  `decrement` / `increment`, called by the booking service
- Method 3 (backups when full) → consumers read `is_full` from the row

Read-only callers use `get_availability` (returns None if missing).
Write callers use `_get_or_create_availability_locked`, which takes a
`SELECT ... FOR UPDATE` on the row to serialize concurrent bookings against
the same (lodge, date) and prevent oversell.
"""

import logging
from datetime import date as date_t
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import LodgeNotFoundError, NoRoomsAvailableError
from app.models.lodge import Lodge, LodgeAvailability

logger = logging.getLogger(__name__)


def get_availability(
    db: Session, lodge_id: UUID, target_date: date_t
) -> Optional[LodgeAvailability]:
    """Read-only lookup — returns None if no row exists.

    Use this on GET paths so reads don't pollute the table with zero-rows.
    """
    return db.execute(
        select(LodgeAvailability).where(
            LodgeAvailability.lodge_id == lodge_id,
            LodgeAvailability.date == target_date,
        )
    ).scalar_one_or_none()


def _get_or_create_availability_locked(
    db: Session, lodge_id: UUID, target_date: date_t
) -> LodgeAvailability:
    """Fetch (or insert) the row with a row-level lock for the txn.

    `SELECT ... FOR UPDATE` blocks concurrent writers until this transaction
    commits or rolls back — the core anti-oversell guarantee.
    """
    row = db.execute(
        select(LodgeAvailability)
        .where(
            LodgeAvailability.lodge_id == lodge_id,
            LodgeAvailability.date == target_date,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if row is None:
        row = LodgeAvailability(
            lodge_id=lodge_id, date=target_date, rooms_available=0, is_full=True
        )
        db.add(row)
        db.flush()
    return row


def set_availability(
    db: Session,
    lodge_id: UUID,
    target_date: date_t,
    rooms_available: int,
    source: str = "owner_whatsapp",
) -> LodgeAvailability:
    """Overwrite the room count for a date — the daily owner update path."""
    lodge = db.get(Lodge, lodge_id)
    if lodge is None:
        raise LodgeNotFoundError(details={"lodge_id": str(lodge_id)})

    row = _get_or_create_availability_locked(db, lodge_id, target_date)
    row.rooms_available = rooms_available
    row.is_full = rooms_available == 0
    row.update_source = source
    db.flush()
    logger.info(
        "Availability set: lodge=%s date=%s rooms=%s source=%s",
        lodge_id,
        target_date,
        rooms_available,
        source,
    )
    return row


def decrement(db: Session, lodge_id: UUID, target_date: date_t) -> LodgeAvailability:
    """Hold one room — called when a booking is created.

    Locks the row first, so two concurrent bookings cannot both see the same
    `rooms_available` count and double-decrement.
    """
    row = _get_or_create_availability_locked(db, lodge_id, target_date)
    if row.rooms_available <= 0:
        raise NoRoomsAvailableError(
            details={"lodge_id": str(lodge_id), "date": target_date.isoformat()}
        )
    row.rooms_available -= 1
    row.is_full = row.rooms_available == 0
    row.update_source = "booking_decrement"
    db.flush()
    return row


def increment(db: Session, lodge_id: UUID, target_date: date_t) -> LodgeAvailability:
    """Release one room back to the pool — called on cancellation."""
    row = _get_or_create_availability_locked(db, lodge_id, target_date)
    row.rooms_available += 1
    row.is_full = False
    row.update_source = "booking_cancel_increment"
    db.flush()
    return row
