from datetime import date, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.lodge import (
    AvailabilityUpdate,
    BookingCreate,
    LodgeCreate,
    LodgeUpdate,
    _local_today,
)


def test_local_today_returns_date():
    assert isinstance(_local_today(), date)


def test_lodge_create_accepts_valid_phone():
    payload = LodgeCreate(
        name="X",
        address="Y",
        phone="9876543210",
        walk_minutes_to_temple=5,
        price_normal=500,
        price_pournami=800,
    )
    assert payload.phone == "9876543210"


def test_lodge_create_rejects_bad_phone():
    with pytest.raises(ValidationError):
        LodgeCreate(
            name="X",
            address="Y",
            phone="abc",
            walk_minutes_to_temple=5,
            price_normal=500,
            price_pournami=800,
        )


def test_lodge_update_partial():
    upd = LodgeUpdate(verified=True)
    dumped = upd.model_dump(exclude_unset=True)
    assert dumped == {"verified": True}


def test_booking_create_rejects_past_date():
    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(ValidationError):
        BookingCreate(
            devotee_phone="9876543210",
            devotee_name="Kavitha",
            lodge_id=uuid4(),
            checkin_date=yesterday,
            checkin_time="morning",
            payment_method="gpay",
        )


def test_booking_create_rejects_bad_phone():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError):
        BookingCreate(
            devotee_phone="not-a-phone",
            devotee_name="K",
            lodge_id=uuid4(),
            checkin_date=tomorrow,
            checkin_time="morning",
            payment_method="gpay",
        )


def test_booking_create_happy_path():
    tomorrow = date.today() + timedelta(days=1)
    payload = BookingCreate(
        devotee_phone="9876543210",
        devotee_name="K",
        lodge_id=uuid4(),
        checkin_date=tomorrow,
        checkin_time="early_morning",
        payment_method="gpay",
    )
    assert payload.payment_method == "gpay"


def test_availability_update_rejects_past_date():
    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(ValidationError):
        AvailabilityUpdate(date=yesterday, rooms_available=5)


def test_availability_update_today_or_future_ok():
    AvailabilityUpdate(date=date.today(), rooms_available=0)
    AvailabilityUpdate(date=date.today() + timedelta(days=1), rooms_available=10)
