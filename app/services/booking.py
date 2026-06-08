"""Booking lifecycle business logic.

Three entry points correspond to the devotee's journey:

- `create_booking` — verifies the lodge, decrements availability (with row
  lock for anti-oversell), generates a `TVM-LODGE-XXXXXX` reference, and
  stores the booking in `pending` status. Supports idempotency: passing the
  same `idempotency_key` returns the original booking instead of double-holding.
- `confirm_payment` — devotee replies PAID; flips `payment_verified` +
  `lodge_confirmed`, moves status to `confirmed`, bumps the lodge counter.
- `cancel_booking` — applies the 24-hour refund rule (in IST), restores
  availability.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import LOCAL_TZ_OFFSET_MINUTES
from app.errors import (
    BookingNotFoundError,
    ConflictError,
    InvalidBookingStateError,
    LodgeNotFoundError,
    LodgeNotVerifiedError,
)
from app.models.lodge import Lodge, LodgeBooking
from app.schemas.lodge import BookingCreate
from app.services import availability as availability_svc
from app.services.pricing import price_for_date

logger = logging.getLogger(__name__)

BOOKING_FEE = 49
BOOKING_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
BOOKING_REF_LENGTH = 6
BOOKING_REF_MAX_RETRIES = 5


def _generate_booking_ref() -> str:
    body = "".join(
        secrets.choice(BOOKING_REF_ALPHABET) for _ in range(BOOKING_REF_LENGTH)
    )
    return f"TVM-LODGE-{body}"


def _local_tz() -> timezone:
    return timezone(timedelta(minutes=LOCAL_TZ_OFFSET_MINUTES))


def _get_booking_or_raise(db: Session, booking_ref: str) -> LodgeBooking:
    booking = db.execute(
        select(LodgeBooking).where(LodgeBooking.booking_ref == booking_ref)
    ).scalar_one_or_none()
    if booking is None:
        raise BookingNotFoundError(details={"booking_ref": booking_ref})
    return booking


def _find_by_idempotency_key(
    db: Session, idempotency_key: str
) -> Optional[LodgeBooking]:
    return db.execute(
        select(LodgeBooking).where(LodgeBooking.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def create_booking(
    db: Session,
    payload: BookingCreate,
    idempotency_key: Optional[str] = None,
) -> LodgeBooking:
    """Create a `pending` booking and hold a room.

    Raises `LodgeNotFoundError`, `LodgeNotVerifiedError`, or
    `NoRoomsAvailableError`. When `idempotency_key` matches an existing
    booking, that booking is returned (no new hold). Caller commits.
    """
    if idempotency_key:
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotent replay: key=%s -> ref=%s",
                idempotency_key,
                existing.booking_ref,
            )
            return existing

    lodge = db.get(Lodge, payload.lodge_id)
    if lodge is None:
        raise LodgeNotFoundError(details={"lodge_id": str(payload.lodge_id)})
    if not lodge.verified:
        raise LodgeNotVerifiedError(details={"lodge_id": str(payload.lodge_id)})

    availability_svc.decrement(db, payload.lodge_id, payload.checkin_date)

    last_error: Optional[Exception] = None
    for attempt in range(BOOKING_REF_MAX_RETRIES):
        # Use a SAVEPOINT so a unique-key collision only rolls back this
        # INSERT — not the availability decrement above.
        savepoint = db.begin_nested()
        booking = LodgeBooking(
            id=uuid.uuid4(),
            booking_ref=_generate_booking_ref(),
            devotee_phone=payload.devotee_phone,
            devotee_name=payload.devotee_name,
            lodge_id=payload.lodge_id,
            checkin_date=payload.checkin_date,
            checkin_time=payload.checkin_time,
            room_rent=price_for_date(lodge, payload.checkin_date),
            booking_fee=BOOKING_FEE,
            payment_method=payload.payment_method,
            status="pending",
            idempotency_key=idempotency_key,
        )
        db.add(booking)
        try:
            db.flush()
        except IntegrityError as exc:
            savepoint.rollback()
            last_error = exc
            logger.warning(
                "Booking ref collision (attempt %s/%s) — retrying",
                attempt + 1,
                BOOKING_REF_MAX_RETRIES,
            )
            continue
        savepoint.commit()
        logger.info(
            "Booking created ref=%s lodge=%s date=%s",
            booking.booking_ref,
            booking.lodge_id,
            booking.checkin_date,
        )
        return booking
    raise ConflictError(
        "Could not allocate a unique booking reference after retries"
    ) from last_error


def confirm_payment(
    db: Session, booking_ref: str, payment_reference: Optional[str] = None
) -> LodgeBooking:
    """Mark the Rs.49 booking fee as received and move status to `confirmed`."""
    booking = _get_booking_or_raise(db, booking_ref)
    if booking.status != "pending":
        raise InvalidBookingStateError(
            f"Cannot confirm payment when status is '{booking.status}'",
            details={"booking_ref": booking_ref, "status": booking.status},
        )

    booking.payment_verified = True
    booking.lodge_confirmed = True
    booking.status = "confirmed"
    if payment_reference:
        booking.notes = f"payment_ref={payment_reference}"

    lodge = db.get(Lodge, booking.lodge_id)
    if lodge is not None:
        lodge.total_bookings = (lodge.total_bookings or 0) + 1

    db.flush()
    logger.info("Booking confirmed ref=%s", booking.booking_ref)
    return booking


def cancel_booking(
    db: Session, booking_ref: str, cancelled_by_lodge: bool = False
) -> tuple[LodgeBooking, str]:
    """Cancel a booking and compute the refund.

    The 24-hour window is computed in the configured local timezone
    (IST by default) so a check-in date is interpreted as "midnight in
    Tiruvannamalai" rather than UTC.
    """
    booking = _get_booking_or_raise(db, booking_ref)
    if booking.status in ("cancelled", "completed", "no_show"):
        raise InvalidBookingStateError(
            f"Booking already in terminal status '{booking.status}'",
            details={"booking_ref": booking_ref, "status": booking.status},
        )

    tz = _local_tz()
    now_local = datetime.now(tz)
    checkin_local = datetime.combine(
        booking.checkin_date, datetime.min.time(), tzinfo=tz
    )
    hours_until_checkin = (checkin_local - now_local) / timedelta(hours=1)

    if cancelled_by_lodge:
        refund = booking.booking_fee
        reason = "Lodge cancelled — full refund"
    elif hours_until_checkin >= 24:
        refund = booking.booking_fee
        reason = "Cancelled 24+ hours in advance — full refund"
    else:
        refund = 0
        reason = "Cancelled within 24 hours — no refund"

    booking.status = "cancelled"
    booking.cancelled_at = datetime.now(timezone.utc)
    booking.refund_amount = refund

    availability_svc.increment(db, booking.lodge_id, booking.checkin_date)

    db.flush()
    logger.info(
        "Booking cancelled ref=%s refund=%s reason=%s",
        booking.booking_ref,
        refund,
        reason,
    )
    return booking, reason
