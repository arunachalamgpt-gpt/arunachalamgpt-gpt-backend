from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.errors import LodgeNotFoundError, NoRoomsAvailableError
from app.services import availability as availability_svc


def test_get_availability_returns_none_when_missing(db_session, make_lodge):
    lodge = make_lodge()
    row = availability_svc.get_availability(
        db_session, lodge.id, date.today() + timedelta(days=2)
    )
    assert row is None


def test_set_availability_creates_row(db_session, make_lodge, future_date):
    lodge = make_lodge()
    row = availability_svc.set_availability(db_session, lodge.id, future_date, 3)
    db_session.commit()
    assert row.rooms_available == 3
    assert row.is_full is False
    assert row.update_source == "owner_whatsapp"


def test_set_availability_to_zero_marks_full(db_session, make_lodge, future_date):
    lodge = make_lodge()
    row = availability_svc.set_availability(db_session, lodge.id, future_date, 0)
    db_session.commit()
    assert row.is_full is True


def test_set_availability_updates_existing(db_session, make_lodge, future_date):
    lodge = make_lodge()
    availability_svc.set_availability(db_session, lodge.id, future_date, 5)
    db_session.commit()
    row = availability_svc.set_availability(db_session, lodge.id, future_date, 2, "manual")
    db_session.commit()
    assert row.rooms_available == 2
    assert row.update_source == "manual"


def test_set_availability_raises_for_unknown_lodge(db_session, future_date):
    with pytest.raises(LodgeNotFoundError):
        availability_svc.set_availability(db_session, uuid4(), future_date, 5)


def test_decrement_raises_when_empty(db_session, make_lodge, future_date):
    lodge = make_lodge()
    with pytest.raises(NoRoomsAvailableError):
        availability_svc.decrement(db_session, lodge.id, future_date)


def test_decrement_reduces_count(db_session, make_lodge, future_date):
    lodge = make_lodge()
    availability_svc.set_availability(db_session, lodge.id, future_date, 2)
    db_session.commit()
    row = availability_svc.decrement(db_session, lodge.id, future_date)
    db_session.commit()
    assert row.rooms_available == 1
    assert row.is_full is False
    row = availability_svc.decrement(db_session, lodge.id, future_date)
    db_session.commit()
    assert row.rooms_available == 0
    assert row.is_full is True


def test_increment_restores_rooms(db_session, make_lodge, future_date):
    lodge = make_lodge()
    availability_svc.set_availability(db_session, lodge.id, future_date, 0)
    db_session.commit()
    row = availability_svc.increment(db_session, lodge.id, future_date)
    db_session.commit()
    assert row.rooms_available == 1
    assert row.is_full is False
    assert row.update_source == "booking_cancel_increment"
