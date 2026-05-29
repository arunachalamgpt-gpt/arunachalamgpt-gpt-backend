"""Booking lifecycle HTTP endpoints.

Routes mounted under `/bookings`:

- `POST /bookings` — create a pending booking (decrements availability).
  Supports `Idempotency-Key` header to dedupe accidental retries.
- `GET /bookings` — list bookings, filterable by phone and status, paginated
- `GET /bookings/{ref}` — single booking by `TVM-LODGE-XXXXXX` reference
- `POST /bookings/{ref}/confirm-payment` — verify Rs.49 booking fee
- `POST /bookings/{ref}/cancel` — cancel with 24-hour refund rule
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import BookingNotFoundError
from app.models.lodge import LodgeBooking
from app.schemas.lodge import (
    BookingConfirmPayment,
    BookingCreate,
    BookingOut,
    CancellationResponse,
)
from app.services import booking as booking_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])

COMMON_ERRORS = {
    400: {"description": "Validation failed or business rule violated"},
    404: {"description": "Booking or lodge not found"},
    409: {"description": "Conflicting state (e.g. no rooms, invalid status)"},
}


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a booking (pending payment)",
    description=(
        "Generates a `TVM-LODGE-XXXXXX` reference and decrements the lodge's "
        "`rooms_available` for the check-in date. Booking starts in `pending` "
        "status until payment is confirmed via "
        "`/bookings/{ref}/confirm-payment`.\n\n"
        "Pass an `Idempotency-Key` header (any unique-per-attempt string) to "
        "make the operation safe to retry — duplicate requests return the "
        "original booking instead of creating a second hold."
    ),
    responses=COMMON_ERRORS,
)
def create_booking(
    payload: BookingCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    booking = booking_svc.create_booking(db, payload, idempotency_key=idempotency_key)
    db.commit()
    db.refresh(booking)
    return booking


@router.get(
    "",
    response_model=list[BookingOut],
    summary="List bookings",
    description="Filter by devotee phone and/or status. Paginated, newest first.",
)
def list_bookings(
    phone: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(LodgeBooking)
    if phone:
        stmt = stmt.where(LodgeBooking.devotee_phone == phone)
    if status_filter:
        stmt = stmt.where(LodgeBooking.status == status_filter)
    stmt = (
        stmt.order_by(LodgeBooking.created_at.desc()).limit(limit).offset(offset)
    )
    return db.execute(stmt).scalars().all()


@router.get(
    "/{booking_ref}",
    response_model=BookingOut,
    summary="Get one booking by reference",
    responses={404: {"description": "Booking not found"}},
)
def get_booking(booking_ref: str, db: Session = Depends(get_db)):
    booking = db.execute(
        select(LodgeBooking).where(LodgeBooking.booking_ref == booking_ref)
    ).scalar_one_or_none()
    if booking is None:
        raise BookingNotFoundError(details={"booking_ref": booking_ref})
    return booking


@router.post(
    "/{booking_ref}/confirm-payment",
    response_model=BookingOut,
    summary="Confirm Rs.49 booking fee received",
    description=(
        "Marks `payment_verified=true` and `lodge_confirmed=true`, transitions "
        "status to `confirmed`, and increments the lodge's `total_bookings`."
    ),
    responses=COMMON_ERRORS,
)
def confirm_payment(
    booking_ref: str,
    payload: BookingConfirmPayment,
    db: Session = Depends(get_db),
):
    booking = booking_svc.confirm_payment(db, booking_ref, payload.payment_reference)
    db.commit()
    db.refresh(booking)
    return booking


@router.post(
    "/{booking_ref}/cancel",
    response_model=CancellationResponse,
    summary="Cancel a booking (24h refund rule applies)",
    description=(
        "Refund rules (window computed in IST):\n"
        "- Cancelled **24+ hours** before check-in → full Rs.49 refund.\n"
        "- Cancelled **<24 hours** before → no refund.\n"
        "- Pass `cancelled_by_lodge=true` to force a full refund."
    ),
    responses=COMMON_ERRORS,
)
def cancel_booking(
    booking_ref: str,
    cancelled_by_lodge: bool = Query(False),
    db: Session = Depends(get_db),
):
    booking, reason = booking_svc.cancel_booking(
        db, booking_ref, cancelled_by_lodge=cancelled_by_lodge
    )
    db.commit()
    db.refresh(booking)
    return CancellationResponse(
        booking_ref=booking.booking_ref,
        status=booking.status,
        refund_amount=booking.refund_amount or 0,
        refund_reason=reason,
    )
