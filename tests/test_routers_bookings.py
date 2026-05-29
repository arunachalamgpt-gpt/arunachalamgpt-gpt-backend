from datetime import date, timedelta
from uuid import uuid4

from app.services import availability as availability_svc


def _booking_body(lodge_id, when):
    return {
        "devotee_phone": "9876543210",
        "devotee_name": "Kavitha",
        "lodge_id": str(lodge_id),
        "checkin_date": when.isoformat(),
        "checkin_time": "early_morning",
        "payment_method": "gpay",
    }


def _seed(db_session, lodge, when, rooms=2):
    availability_svc.set_availability(db_session, lodge.id, when, rooms)
    db_session.commit()


def test_create_booking_happy_path(client, db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed(db_session, lodge, future_date)
    res = client.post("/bookings", json=_booking_body(lodge.id, future_date))
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "pending"
    assert body["booking_ref"].startswith("TVM-LODGE-")


def test_create_booking_idempotency(client, db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed(db_session, lodge, future_date, rooms=1)
    body = _booking_body(lodge.id, future_date)
    r1 = client.post("/bookings", json=body, headers={"Idempotency-Key": "k1"})
    r2 = client.post("/bookings", json=body, headers={"Idempotency-Key": "k1"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["booking_ref"] == r2.json()["booking_ref"]


def test_create_booking_unverified_lodge(client, db_session, make_lodge, future_date):
    lodge = make_lodge(verified=False)
    _seed(db_session, lodge, future_date)
    res = client.post("/bookings", json=_booking_body(lodge.id, future_date))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "lodge_not_verified"


def test_create_booking_no_rooms(client, make_lodge, future_date):
    lodge = make_lodge()
    res = client.post("/bookings", json=_booking_body(lodge.id, future_date))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "no_rooms_available"


def test_create_booking_validation_error(client):
    res = client.post(
        "/bookings",
        json={
            "devotee_phone": "abc",
            "devotee_name": "K",
            "lodge_id": str(uuid4()),
            "checkin_date": "2020-01-01",
            "checkin_time": "morning",
            "payment_method": "gpay",
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"


def test_get_booking_404(client):
    res = client.get("/bookings/TVM-LODGE-NOPE")
    assert res.status_code == 404


def test_get_booking_200(client, db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed(db_session, lodge, future_date)
    booking = client.post(
        "/bookings", json=_booking_body(lodge.id, future_date)
    ).json()
    res = client.get(f"/bookings/{booking['booking_ref']}")
    assert res.status_code == 200


def test_list_bookings_filters_and_pagination(
    client, db_session, make_lodge, future_date
):
    lodge = make_lodge()
    _seed(db_session, lodge, future_date, rooms=5)
    refs = []
    for _ in range(3):
        refs.append(
            client.post(
                "/bookings", json=_booking_body(lodge.id, future_date)
            ).json()["booking_ref"]
        )
    res = client.get("/bookings?phone=9876543210&limit=2")
    assert res.status_code == 200
    assert len(res.json()) == 2

    res = client.get("/bookings?status=pending")
    assert all(row["status"] == "pending" for row in res.json())


def test_confirm_payment(client, db_session, make_lodge, future_date):
    lodge = make_lodge()
    _seed(db_session, lodge, future_date)
    booking = client.post(
        "/bookings", json=_booking_body(lodge.id, future_date)
    ).json()
    res = client.post(
        f"/bookings/{booking['booking_ref']}/confirm-payment",
        json={"payment_reference": "TXN42"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"


def test_confirm_payment_404(client):
    res = client.post(
        "/bookings/TVM-LODGE-NOPE/confirm-payment", json={}
    )
    assert res.status_code == 404


def test_cancel_booking_full_refund(client, db_session, make_lodge):
    when = date.today() + timedelta(days=10)
    lodge = make_lodge()
    _seed(db_session, lodge, when)
    booking = client.post("/bookings", json=_booking_body(lodge.id, when)).json()
    res = client.post(f"/bookings/{booking['booking_ref']}/cancel")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "cancelled"
    assert body["refund_amount"] == 49
