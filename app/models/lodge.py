"""SQLModel tables for Feature 6 — Verified Lodge Booking.

Three tables mirror the design doc:

- `Lodge` — directory of verified lodges (price, walk time, facilities, photos,
  ratings, listing fee).
- `LodgeBooking` — devotee bookings with payment + lodge confirmation flags,
  status machine (`pending → confirmed → checked_in / completed / cancelled / no_show`),
  and refund accounting.
- `LodgeAvailability` — per-lodge per-date room count, with the `lodge_id+date`
  unique constraint that powers idempotent updates.

Postgres `TEXT[]` arrays are declared via `sa_column=Column(StringArray)` since
SQLModel does not yet expose array typing natively.
"""

import uuid
from datetime import date as date_t
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Column, Field, Relationship, SQLModel

from app.models.types import StringArray


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lodge(SQLModel, table=True):
    """A lodge in the verified directory.

    `verified=True` is set only after an in-person site visit per the checklist
    in the design doc. `price_normal` is the default rate; `price_pournami`
    and `price_karthigai` are applied when the check-in date falls on those
    special days (lunar-calendar wiring lives in the booking service).
    """

    __tablename__ = "lodges"

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    address: str
    phone: str = Field(max_length=20)
    walk_minutes_to_temple: int
    room_types: list[str] = Field(default_factory=list, sa_column=Column(StringArray))
    price_normal: int
    price_pournami: int
    price_karthigai: Optional[int] = None
    facilities: list[str] = Field(default_factory=list, sa_column=Column(StringArray))
    payment_accepted: list[str] = Field(
        default_factory=list, sa_column=Column(StringArray)
    )
    rating: Decimal = Field(default=Decimal("0"), max_digits=3, decimal_places=2)
    total_bookings: int = 0
    verified: bool = False
    listing_fee_monthly: int = 0
    photo_urls: list[str] = Field(default_factory=list, sa_column=Column(StringArray))
    upi_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    bookings: list["LodgeBooking"] = Relationship(back_populates="lodge")
    availability: list["LodgeAvailability"] = Relationship(back_populates="lodge")


class LodgeBooking(SQLModel, table=True):
    """A devotee's booking against one lodge for one check-in date.

    Status transitions:
    `pending → confirmed → checked_in → completed`, with `cancelled` and
    `no_show` as terminal off-ramps. `payment_verified` tracks the Rs.49
    booking fee; `lodge_confirmed` tracks that the lodge agreed to hold the
    room. `refund_amount` is populated at cancellation time.

    `idempotency_key` is supplied by the client (typically the WhatsApp bot)
    to dedupe accidental retries.
    """

    __tablename__ = "lodge_bookings"
    __table_args__ = (
        CheckConstraint("refund_amount >= 0", name="ck_booking_refund_nonneg"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    booking_ref: str = Field(unique=True, index=True)
    devotee_phone: str = Field(max_length=20, index=True)
    devotee_name: str
    lodge_id: UUID = Field(foreign_key="lodges.id")
    checkin_date: date_t = Field(index=True)
    checkin_time: str
    room_rent: int
    booking_fee: int = 49
    payment_method: str
    payment_verified: bool = False
    lodge_confirmed: bool = False
    status: str = Field(default="pending", index=True)
    cancelled_at: Optional[datetime] = None
    refund_amount: int = 0
    idempotency_key: Optional[str] = Field(default=None, unique=True, index=True)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    lodge: Optional[Lodge] = Relationship(back_populates="bookings")


class LodgeAvailability(SQLModel, table=True):
    """Per-lodge per-date room count.

    Unique constraint on `(lodge_id, date)` allows idempotent upserts from the
    daily owner update and prevents two booking flows from creating duplicate
    rows. `update_source` records *how* the row was last touched
    (`owner_whatsapp`, `booking_decrement`, `booking_cancel_increment`, ...).
    """

    __tablename__ = "lodge_availability"
    __table_args__ = (
        UniqueConstraint("lodge_id", "date", name="uq_lodge_date"),
        CheckConstraint("rooms_available >= 0", name="ck_rooms_nonneg"),
    )

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lodge_id: UUID = Field(foreign_key="lodges.id", index=True)
    date: date_t = Field(index=True)
    rooms_available: int = 0
    last_updated: datetime = Field(default_factory=_utcnow)
    is_full: bool = False
    update_source: Optional[str] = "owner_whatsapp"

    lodge: Optional[Lodge] = Relationship(back_populates="availability")
