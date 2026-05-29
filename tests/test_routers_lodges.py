from datetime import date, timedelta
from uuid import uuid4

from app.services import availability as availability_svc


_LODGE_PAYLOAD = {
    "name": "Krishna Lodge",
    "address": "1, Car Street, Tiruvannamalai",
    "phone": "9444444444",
    "walk_minutes_to_temple": 5,
    "room_types": ["double"],
    "price_normal": 600,
    "price_pournami": 900,
    "facilities": ["fan"],
    "payment_accepted": ["cash"],
    "photo_urls": [],
}


def test_create_lodge_forces_verified_false(client):
    res = client.post("/lodges", json={**_LODGE_PAYLOAD, "verified": True})
    assert res.status_code == 201
    assert res.json()["verified"] is False


def test_get_lodge_404(client):
    res = client.get(f"/lodges/{uuid4()}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "lodge_not_found"


def test_get_lodge_200(client, make_lodge):
    lodge = make_lodge()
    res = client.get(f"/lodges/{lodge.id}")
    assert res.status_code == 200
    assert res.json()["name"] == lodge.name


def test_patch_lodge_200_and_404(client, make_lodge):
    lodge = make_lodge(verified=False)
    res = client.patch(f"/lodges/{lodge.id}", json={"verified": True})
    assert res.status_code == 200
    assert res.json()["verified"] is True

    res = client.patch(f"/lodges/{uuid4()}", json={"verified": True})
    assert res.status_code == 404


def test_list_lodges_filters(client, make_lodge):
    make_lodge(name="A", walk_minutes_to_temple=3, price_normal=400)
    make_lodge(name="B", walk_minutes_to_temple=10, price_normal=900)
    make_lodge(name="C", walk_minutes_to_temple=5, verified=False)

    res = client.get("/lodges?verified_only=true&max_walk_minutes=5&max_price=500")
    assert res.status_code == 200
    names = [row["name"] for row in res.json()]
    assert names == ["A"]

    res = client.get("/lodges?verified_only=false")
    assert len(res.json()) == 3


def test_list_lodges_pagination(client, make_lodge):
    for i in range(5):
        make_lodge(name=f"L{i}", walk_minutes_to_temple=i + 1)
    res = client.get("/lodges?limit=2&offset=1")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_search_returns_primary_and_backups(client, db_session, make_lodge):
    target = date.today() + timedelta(days=3)
    a = make_lodge(name="A", walk_minutes_to_temple=3, price_normal=500)
    b = make_lodge(name="B", walk_minutes_to_temple=8, price_normal=900)
    availability_svc.set_availability(db_session, a.id, target, 2)
    availability_svc.set_availability(db_session, b.id, target, 0)
    db_session.commit()

    res = client.get(f"/lodges/search?checkin_date={target.isoformat()}")
    body = res.json()
    assert res.status_code == 200
    assert [p["name"] for p in body["primary"]] == ["A"]
    assert [p["name"] for p in body["backups"]] == ["B"]


def test_search_respects_price_filters(client, db_session, make_lodge):
    target = date.today() + timedelta(days=4)
    a = make_lodge(name="cheap", walk_minutes_to_temple=3, price_normal=200)
    b = make_lodge(name="expensive", walk_minutes_to_temple=4, price_normal=2000)
    availability_svc.set_availability(db_session, a.id, target, 1)
    availability_svc.set_availability(db_session, b.id, target, 1)
    db_session.commit()

    res = client.get(
        f"/lodges/search?checkin_date={target.isoformat()}&min_price=300&max_price=1500"
    )
    names = {p["name"] for p in res.json()["primary"]} | {
        b["name"] for b in res.json()["backups"]
    }
    assert names == set()


def test_search_respects_walk_filter(client, db_session, make_lodge):
    target = date.today() + timedelta(days=4)
    a = make_lodge(name="close", walk_minutes_to_temple=3)
    b = make_lodge(name="far", walk_minutes_to_temple=20)
    availability_svc.set_availability(db_session, a.id, target, 1)
    availability_svc.set_availability(db_session, b.id, target, 1)
    db_session.commit()
    res = client.get(
        f"/lodges/search?checkin_date={target.isoformat()}&max_walk_minutes=10"
    )
    names = [p["name"] for p in res.json()["primary"]]
    assert names == ["close"]


def test_get_availability_404_then_200(client, db_session, make_lodge):
    lodge = make_lodge()
    target = date.today() + timedelta(days=2)
    res = client.get(f"/lodges/{lodge.id}/availability?date={target.isoformat()}")
    assert res.status_code == 404

    availability_svc.set_availability(db_session, lodge.id, target, 4)
    db_session.commit()
    res = client.get(f"/lodges/{lodge.id}/availability?date={target.isoformat()}")
    assert res.status_code == 200
    assert res.json()["rooms_available"] == 4


def test_post_availability_200_and_404(client, make_lodge):
    lodge = make_lodge()
    target = (date.today() + timedelta(days=3)).isoformat()
    res = client.post(
        f"/lodges/{lodge.id}/availability",
        json={"date": target, "rooms_available": 5},
    )
    assert res.status_code == 200
    assert res.json()["rooms_available"] == 5

    res = client.post(
        f"/lodges/{uuid4()}/availability",
        json={"date": target, "rooms_available": 5},
    )
    assert res.status_code == 404
