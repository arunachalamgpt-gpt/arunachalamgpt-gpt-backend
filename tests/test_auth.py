"""Tests for the optional X-API-Key guard.

Default (`API_KEY=""`) — the dependency is a no-op; existing tests don't
need to send the header. When `API_KEY` is set, the guarded routes return
401 without the header and 200/201 with the correct one.
"""

from app import auth, config


def _set_key(monkeypatch, value: str) -> None:
    monkeypatch.setattr(config, "API_KEY", value)


def test_require_api_key_noop_when_unset():
    # Should NOT raise even with no header.
    auth.require_api_key(x_api_key=None)


def test_require_api_key_rejects_missing_header(monkeypatch):
    _set_key(monkeypatch, "secret-key")
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key=None)
    assert exc.value.status_code == 401


def test_require_api_key_rejects_wrong_header(monkeypatch):
    _set_key(monkeypatch, "secret-key")
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key="not-it")
    assert exc.value.status_code == 401


def test_require_api_key_accepts_correct_header(monkeypatch):
    _set_key(monkeypatch, "secret-key")
    # Should not raise.
    auth.require_api_key(x_api_key="secret-key")


# ---------- end-to-end via TestClient ----------


def test_devotee_post_blocked_without_key(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/devotees",
        json={"phone": "9876543210", "name": "Kavitha", "language": "english"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "http_401"


def test_devotee_post_allowed_with_key(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/devotees",
        json={"phone": "9876543210", "name": "Kavitha", "language": "english"},
        headers={"X-API-Key": "secret-key"},
    )
    assert res.status_code == 201


def test_crowd_reports_blocked_without_key(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/crowd/reports",
        json={"reporter_phone": "9444444444", "text": "F:60 T50:5 T200:1"},
    )
    assert res.status_code == 401


def test_crowd_reports_structured_blocked(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/crowd/reports/structured",
        json={"reporter_phone": "9444444444", "free_wait_min": 60},
    )
    assert res.status_code == 401


def test_crowd_history_blocked(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/crowd/history",
        json={
            "visit_date": "2026-06-15",
            "hour_of_day": 9,
            "free_wait_min": 60,
        },
    )
    assert res.status_code == 401


def test_internal_webhook_blocked_without_key(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/webhook/whatsapp", json={"phone": "9876543210", "text": "Hi"}
    )
    assert res.status_code == 401


def test_internal_webhook_allowed_with_key(client, monkeypatch):
    _set_key(monkeypatch, "secret-key")
    res = client.post(
        "/webhook/whatsapp",
        json={"phone": "9876543210", "text": "Hi"},
        headers={"X-API-Key": "secret-key"},
    )
    assert res.status_code == 200


def test_get_endpoints_not_guarded(client, monkeypatch):
    """Read-only endpoints stay open — guard is on the POSTs only."""
    _set_key(monkeypatch, "secret-key")
    assert client.get("/health").status_code == 200
    assert client.get("/lodges").status_code == 200
