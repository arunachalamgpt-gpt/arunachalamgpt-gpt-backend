"""Pydantic schemas for the lodge & booking HTTP API.

Grouped by resource:

- Lodge: `LodgeBase`, `LodgeCreate`, `LodgeUpdate`, `LodgeOut`,
  `LodgeWithAvailability`, `LodgeSearchResponse`
- Availability: `AvailabilityUpdate`, `AvailabilityOut`
- Booking: `BookingCreate`, `BookingConfirmPayment`, `BookingOut`,
  `CancellationResponse`

`Literal` aliases (`PaymentMethod`, `BookingStatus`) constrain string enums
so OpenAPI emits a closed set in the schema.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import LOCAL_TZ_OFFSET_MINUTES

PaymentMethod = Literal[
    "gpay", "phonepe", "paytm", "bhim", "bank_transfer", "razorpay", "paypal", "wise"
]
BookingStatus = Literal[
    "pending", "confirmed", "checked_in", "completed", "cancelled", "no_show"
]

PHONE_PATTERN = r"^\+?[1-9]\d{6,14}$"


def _local_today() -> date:
    tz = timezone(timedelta(minutes=LOCAL_TZ_OFFSET_MINUTES))
    return datetime.now(tz).date()


class LodgeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    phone: str = Field(pattern=PHONE_PATTERN)
    walk_minutes_to_temple: int = Field(ge=0, le=240)
    room_types: list[str] = Field(default_factory=list)
    price_normal: int = Field(ge=0)
    price_pournami: int = Field(ge=0)
    price_karthigai: Optional[int] = None
    facilities: list[str] = Field(default_factory=list)
    payment_accepted: list[str] = Field(default_factory=list)
    photo_urls: list[str] = Field(default_factory=list)
    upi_id: Optional[str] = None


class LodgeCreate(LodgeBase):
    verified: bool = False
    listing_fee_monthly: int = 0

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Murugan Residency",
                "address": "12, Car Street, Near East Gopuram, Tiruvannamalai",
                "phone": "9444444444",
                "walk_minutes_to_temple": 8,
                "room_types": ["double", "family", "AC"],
                "price_normal": 800,
                "price_pournami": 1200,
                "price_karthigai": 1800,
                "facilities": ["AC", "hot_water", "parking", "TV"],
                "payment_accepted": ["cash", "upi"],
                "photo_urls": [
                    "https://supabase.example/lodges/murugan-room.jpg",
                    "https://supabase.example/lodges/murugan-bath.jpg",
                ],
                "upi_id": "murugan@ybl",
                "verified": True,
                "listing_fee_monthly": 700,
            }
        }
    )


class LodgeUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    walk_minutes_to_temple: Optional[int] = None
    price_normal: Optional[int] = None
    price_pournami: Optional[int] = None
    price_karthigai: Optional[int] = None
    facilities: Optional[list[str]] = None
    payment_accepted: Optional[list[str]] = None
    photo_urls: Optional[list[str]] = None
    upi_id: Optional[str] = None
    verified: Optional[bool] = None
    listing_fee_monthly: Optional[int] = None


class LodgeOut(LodgeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rating: Decimal
    total_bookings: int
    verified: bool
    listing_fee_monthly: int
    created_at: datetime


class LodgeWithAvailability(LodgeOut):
    rooms_available: int
    is_full: bool
    price_for_date: int


class LodgeSearchResponse(BaseModel):
    date: date
    primary: list[LodgeWithAvailability]
    backups: list[LodgeWithAvailability]


class AvailabilityUpdate(BaseModel):
    date: date
    rooms_available: int = Field(ge=0, le=1000)
    update_source: str = "owner_whatsapp"

    @field_validator("date")
    @classmethod
    def _no_past(cls, v: date) -> date:
        if v < _local_today():
            raise ValueError("date must be today or later")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2026-06-15",
                "rooms_available": 5,
                "update_source": "owner_whatsapp",
            }
        }
    )


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lodge_id: UUID
    date: date
    rooms_available: int
    is_full: bool
    last_updated: datetime
    update_source: Optional[str]


class BookingCreate(BaseModel):
    devotee_phone: str = Field(pattern=PHONE_PATTERN, examples=["9876543210"])
    devotee_name: str = Field(min_length=1, max_length=120, examples=["Kavitha"])
    lodge_id: UUID
    checkin_date: date
    checkin_time: Literal[
        "night_before", "early_morning", "morning", "afternoon_or_later"
    ]
    payment_method: PaymentMethod

    @field_validator("checkin_date")
    @classmethod
    def _no_past(cls, v: date) -> date:
        if v < _local_today():
            raise ValueError("checkin_date cannot be in the past")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "devotee_phone": "9876543210",
                "devotee_name": "Kavitha",
                "lodge_id": "00000000-0000-0000-0000-000000000000",
                "checkin_date": "2026-06-15",
                "checkin_time": "early_morning",
                "payment_method": "gpay",
            }
        }
    )


class BookingConfirmPayment(BaseModel):
    payment_reference: Optional[str] = None
    screenshot_url: Optional[str] = None


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_ref: str
    devotee_phone: str
    devotee_name: str
    lodge_id: UUID
    checkin_date: date
    checkin_time: str
    room_rent: int
    booking_fee: int
    payment_method: str
    payment_verified: bool
    lodge_confirmed: bool
    status: BookingStatus
    refund_amount: int
    created_at: datetime


class CancellationResponse(BaseModel):
    booking_ref: str
    status: BookingStatus
    refund_amount: int
    refund_reason: str
