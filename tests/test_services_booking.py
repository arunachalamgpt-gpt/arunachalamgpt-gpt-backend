from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.errors import (
    BookingNotFoundError,
    ConflictError,
    InvalidBookingStateError,
    LodgeNotFoundError,
    LodgeNotVerifiedError,
)
from app.schemas.lodge import BookingCreate
from app.services import availability as availability_svc
from app.services import booking as booking_svc


def _payload(lodge_id, checkin_date, **overrides):
    data = dict(
        devotee_phone="9876543210",
        devotee_name="Kavitha",
        lodge_id=lodge_id,
        checkin_date=checkin_date,
        checkin_time="early_morning",
        payment_method="gpay",
    )
    data.update(overrides)
    return BookingCreate(**data)


def _seed_rooms(db_session, lodge, when, rooms=3):
    availability_svc.set_availability(db_session, lodge.id, when, rooms)
    db_session.commit()


def test_generate_booking_ref_format():
    ref = booking_svc._generate_booking_ref()
    assert ref.startswith("TVM-LODGE-")
    body = ref.split("-")[-1]
    assert len(body) == booking_svc.BOOKING_REF_LENGTH
    for ch in body:
        assert ch in booking_svc.BOOKING_REF_ALPHABET


def test_create_booking_happy_path(db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()
    assert booking.status == "pending"
    assert booking.room_rent == 800
    assert booking.booking_fee == 49


def test_create_booking_idempotent_replay(db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date, rooms=1)
    first = booking_svc.create_booking(
        db_session, _payload(lodge.id, future_date), idempotency_key="abc"
    )
    db_session.commit()
    second = booking_svc.create_booking(
        db_session, _payload(lodge.id, future_date), idempotency_key="abc"
    )
    assert first.booking_ref == second.booking_ref


def test_create_booking_lodge_not_found(db_session, future_date):
    with pytest.raises(LodgeNotFoundError):
        booking_svc.create_booking(db_session, _payload(uuid4(), future_date))


def test_create_booking_lodge_not_verified(db_session, make_lodge, future_date):
    lodge = make_lodge(verified=False)
    _seed_rooms(db_session, lodge, future_date)
    with pytest.raises(LodgeNotVerifiedError):
        booking_svc.create_booking(db_session, _payload(lodge.id, future_date))


def test_create_booking_ref_conflict_retries_and_fails(
    db_session, make_lodge, future_date, monkeypatch
):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date, rooms=10)
    monkeypatch.setattr(booking_svc, "_generate_booking_ref", lambda: "TVM-LODGE-FIXED")
    booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()

    with pytest.raises(ConflictError):
        booking_svc.create_booking(db_session, _payload(lodge.id, future_date))


def test_confirm_payment_happy_path(db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()
    confirmed = booking_svc.confirm_payment(db_session, booking.booking_ref, "txn-1")
    db_session.commit()
    assert confirmed.status == "confirmed"
    assert confirmed.payment_verified is True
    assert confirmed.lodge_confirmed is True
    assert "txn-1" in (confirmed.notes or "")


def test_confirm_payment_not_found(db_session):
    with pytest.raises(BookingNotFoundError):
        booking_svc.confirm_payment(db_session, "TVM-LODGE-NOPE")


def test_confirm_payment_invalid_state(db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()
    booking_svc.confirm_payment(db_session, booking.booking_ref)
    db_session.commit()
    with pytest.raises(InvalidBookingStateError):
        booking_svc.confirm_payment(db_session, booking.booking_ref)


def test_cancel_booking_full_refund_24h_plus(db_session, make_lodge):
    when = date.today() + timedelta(days=10)
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, when)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, when))
    db_session.commit()
    _, reason = booking_svc.cancel_booking(db_session, booking.booking_ref)
    db_session.commit()
    assert "full refund" in reason.lower()
    db_session.refresh(booking)
    assert booking.status == "cancelled"
    assert booking.refund_amount == 49


def test_cancel_booking_no_refund_within_24h(
    db_session, make_lodge, future_date, monkeypatch
):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()

    from datetime import datetime, timezone
    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            target = datetime.combine(future_date, datetime.min.time(), tzinfo=tz)
            return target - timedelta(hours=2)

    monkeypatch.setattr(booking_svc, "datetime", _FakeDatetime)

    _, reason = booking_svc.cancel_booking(db_session, booking.booking_ref)
    db_session.commit()
    assert "no refund" in reason.lower()
    db_session.refresh(booking)
    assert booking.refund_amount == 0


def test_cancel_booking_by_lodge_always_full_refund(
    db_session, make_lodge, monkeypatch
):
    when = date.today() + timedelta(days=1)
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, when)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, when))
    db_session.commit()

    from datetime import datetime
    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(when, datetime.min.time(), tzinfo=tz)

    monkeypatch.setattr(booking_svc, "datetime", _FakeDatetime)

    _, reason = booking_svc.cancel_booking(
        db_session, booking.booking_ref, cancelled_by_lodge=True
    )
    db_session.commit()
    assert "lodge cancelled" in reason.lower()
    db_session.refresh(booking)
    assert booking.refund_amount == 49


def test_cancel_booking_terminal_state(db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed_rooms(db_session, lodge, future_date)
    booking = booking_svc.create_booking(db_session, _payload(lodge.id, future_date))
    db_session.commit()
    booking_svc.cancel_booking(db_session, booking.booking_ref)
    db_session.commit()
    with pytest.raises(InvalidBookingStateError):
        booking_svc.cancel_booking(db_session, booking.booking_ref)


def test_cancel_booking_not_found(db_session):
    with pytest.raises(BookingNotFoundError):
        booking_svc.cancel_booking(db_session, "TVM-LODGE-NOPE")
