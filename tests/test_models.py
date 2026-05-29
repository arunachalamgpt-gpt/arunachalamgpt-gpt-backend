from datetime import date, timedelta

from app.models.lodge import Lodge, LodgeAvailability, LodgeBooking
from app.models.types import StringArray


def test_string_array_persists_on_sqlite(db_session, make_lodge):
    lodge = make_lodge(facilities=["AC", "wifi"], room_types=["family"])
    fetched = db_session.get(Lodge, lodge.id)
    assert fetched.facilities == ["AC", "wifi"]
    assert fetched.room_types == ["family"]


def test_string_array_dialect_dispatch_for_postgres():
    arr = StringArray()
    pg = arr.load_dialect_impl(_FakeDialect("postgresql"))
    sqlite = arr.load_dialect_impl(_FakeDialect("sqlite"))
    assert pg is not None
    assert sqlite is not None


def test_lodge_booking_and_availability_relations(db_session, make_lodge):
    lodge = make_lodge()
    avail = LodgeAvailability(
        lodge_id=lodge.id,
        date=date.today() + timedelta(days=1),
        rooms_available=5,
    )
    booking = LodgeBooking(
        booking_ref="TVM-LODGE-XYZ001",
        devotee_phone="9876543210",
        devotee_name="K",
        lodge_id=lodge.id,
        checkin_date=date.today() + timedelta(days=1),
        checkin_time="morning",
        room_rent=500,
        payment_method="gpay",
    )
    db_session.add_all([avail, booking])
    db_session.commit()

    db_session.refresh(lodge)
    assert any(b.booking_ref == "TVM-LODGE-XYZ001" for b in lodge.bookings)
    assert any(a.rooms_available == 5 for a in lodge.availability)


class _FakeDialect:
    def __init__(self, name: str):
        self.name = name

    def type_descriptor(self, type_):
        return type_
