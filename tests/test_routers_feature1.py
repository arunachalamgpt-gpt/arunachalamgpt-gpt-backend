from datetime import date, timedelta


def _bootstrap(client):
    # Seed temple_config via API to exercise the config endpoint as well.
    for key, (val, desc) in [
        ("ticket_sale_start_time", ("08:00", "")),
        ("rs50_ticket_price", ("50", "")),
        ("rs200_ticket_price", ("200", "")),
        ("rs50_sold_out", ("false", "")),
        ("rs200_sold_out", ("false", "")),
        ("temple_open_time", ("05:30", "")),
        ("temple_close_time", ("21:00", "")),
        ("volunteer_phone", ("", "")),
    ]:
        client.put(f"/admin/config/{key}", json={"value": val, "description": desc})


def test_crowd_raw_report_and_current(client):
    _bootstrap(client)
    r = client.post(
        "/crowd/reports",
        json={"reporter_phone": "9444444444", "text": "F:180 T50:40 T200:15"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["free_wait_min"] == 180

    cur = client.get("/crowd/current")
    assert cur.status_code == 200


def test_crowd_structured_report(client):
    _bootstrap(client)
    r = client.post(
        "/crowd/reports/structured",
        json={
            "reporter_phone": "9444444444",
            "free_wait_min": 60,
            "rs50_wait_min": 10,
            "rs200_wait_min": 5,
        },
    )
    assert r.status_code == 201


def test_crowd_predict_endpoint(client):
    target = date.today() + timedelta(days=1)
    r = client.get(
        f"/crowd/predict?visit_date={target.isoformat()}&hour_of_day=8&is_pournami=false"
    )
    assert r.status_code == 200
    assert r.json()["sample_size"] == 0


def test_crowd_history_post_and_list(client):
    payload = {
        "visit_date": date.today().isoformat(),
        "hour_of_day": 10,
        "free_wait_min": 60,
        "rs50_wait_min": 15,
        "rs200_wait_min": 5,
    }
    r = client.post("/crowd/history", json=payload)
    assert r.status_code == 201
    res = client.get(f"/crowd/history?visit_date={date.today().isoformat()}")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    res = client.get("/crowd/history?is_pournami=false&limit=10&offset=0")
    assert res.status_code == 200


def test_devotee_upsert_get_patch(client):
    body = {"phone": "9876543210", "name": "Kavitha", "language": "tamil"}
    r = client.post("/devotees", json=body)
    assert r.status_code == 201

    r = client.get("/devotees/9876543210")
    assert r.status_code == 200

    r = client.patch("/devotees/9876543210", json={"has_elderly": True})
    assert r.status_code == 200
    assert r.json()["has_elderly"] is True

    r = client.post("/devotees", json={**body, "name": "Kavitha S."})
    assert r.status_code == 201
    assert r.json()["name"] == "Kavitha S."


def test_devotee_404s(client):
    assert client.get("/devotees/9000000000").status_code == 404
    assert (
        client.patch("/devotees/9000000000", json={"has_elderly": True}).status_code
        == 404
    )
    assert client.get("/devotees/9000000000/plan").status_code == 404


def test_devotee_plan(client):
    client.post(
        "/devotees",
        json={
            "phone": "9876543210",
            "language": "english",
            "has_elderly": True,
            "planned_visit_date": (date.today() + timedelta(days=3)).isoformat(),
        },
    )
    r = client.get("/devotees/9876543210/plan")
    assert r.status_code == 200
    assert "Rs.200" in r.json()["recommended_line"]


def test_config_get_404_and_upsert(client):
    assert client.get("/admin/config/missing").status_code == 404
    r = client.put(
        "/admin/config/rs50_ticket_price",
        json={"value": "75", "description": "bumped"},
    )
    assert r.status_code == 200
    assert r.json()["value"] == "75"
    fetched = client.get("/admin/config/rs50_ticket_price")
    assert fetched.status_code == 200
    assert fetched.json()["value"] == "75"


def test_config_list(client):
    client.put("/admin/config/foo", json={"value": "bar"})
    r = client.get("/admin/config")
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert "foo" in keys


def test_admin_command_via_endpoint(client):
    r = client.post(
        "/admin/commands",
        json={
            "sender_phone": "9444444444",
            "text": "ADMIN config rs200_sold_out true",
        },
    )
    assert r.status_code == 200
    assert r.json()["action"] == "config_set"


def test_webhook_language_then_query(client):
    _bootstrap(client)
    r = client.post(
        "/webhook/whatsapp", json={"phone": "9876543210", "text": "Hi"}
    )
    assert r.status_code == 200
    assert "language" in r.json()["text"].lower()

    r = client.post(
        "/webhook/whatsapp", json={"phone": "9876543210", "text": "1"}
    )
    assert r.json()["language"] == "tamil"
