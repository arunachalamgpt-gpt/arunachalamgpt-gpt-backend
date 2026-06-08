from datetime import datetime, timedelta, timezone

import pytest

from app.errors import ValidationFailedError
from app.schemas.crowd import CrowdReportIn
from app.services import crowd as crowd_svc
from app.services import temple_config


def test_parse_volunteer_message_happy_path():
    p = crowd_svc.parse_volunteer_message("F:180 T50:40 T200:15")
    assert p.free_wait_min == 180
    assert p.rs50_wait_min == 40
    assert p.rs200_wait_min == 15
    assert p.rs50_sold_out is False
    assert p.rs200_sold_out is False


def test_parse_volunteer_message_sold():
    p = crowd_svc.parse_volunteer_message("F:200 T50:SOLD T200:SOLD")
    assert p.rs50_wait_min is None
    assert p.rs50_sold_out is True
    assert p.rs200_sold_out is True


def test_parse_volunteer_message_partial_tokens():
    """Only `F:` present — the other two lines stay as `None` (no defaults)."""
    p = crowd_svc.parse_volunteer_message("F:200")
    assert p.free_wait_min == 200
    assert p.rs50_wait_min is None
    assert p.rs50_sold_out is False
    assert p.rs200_wait_min is None
    assert p.rs200_sold_out is False


def test_parse_volunteer_message_empty_raises():
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("   ")


def test_parse_volunteer_message_bad_token():
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("Free:10")


def test_parse_volunteer_message_duplicate_token():
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("F:1 F:2")


def test_record_status_persists_and_syncs_flags(db_session, seed_temple_config):
    payload = CrowdReportIn(
        reporter_phone="9444444444",
        free_wait_min=180,
        rs50_wait_min=None,
        rs200_wait_min=15,
        rs50_sold_out=True,
        rs200_sold_out=False,
        source="volunteer",
    )
    row = crowd_svc.record_status(db_session, payload)
    db_session.commit()
    assert row.id is not None
    assert temple_config.get(db_session, "rs50_sold_out").value == "true"
    assert temple_config.get(db_session, "rs200_sold_out").value == "false"


def _push_status(db, *, base_now, age_minutes=0, **kwargs):
    payload = CrowdReportIn(reporter_phone="9444444444", **kwargs)
    row = crowd_svc.record_status(db, payload)
    # Pin reported_at relative to the test's `base_now` so the test is
    # independent of real wall-clock time.
    base_utc = base_now.astimezone(timezone.utc).replace(tzinfo=None)
    row.reported_at = base_utc - timedelta(minutes=age_minutes)
    db.flush()
    return row


def test_current_status_closed_outside_hours(db_session, seed_temple_config):
    night = datetime.now(crowd_svc._local_tz()).replace(hour=2, minute=0)
    result = crowd_svc.current_status(db_session, now=night)
    assert result.freshness == "closed"


def test_current_status_no_report_returns_prediction_only(
    db_session, seed_temple_config
):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "prediction_only"


def test_current_status_live(db_session, seed_temple_config):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=10,
        free_wait_min=120, rs50_wait_min=20, rs200_wait_min=5,
    )
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "live"
    assert result.free_wait_min == 120


def test_current_status_stale_between_2_and_6_hours(
    db_session, seed_temple_config
):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=12, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=180,
        free_wait_min=80, rs50_wait_min=15, rs200_wait_min=5,
    )
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "stale"


def test_current_status_prediction_only_when_older_than_6h(
    db_session, seed_temple_config
):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=15, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=400,
        free_wait_min=80, rs50_wait_min=15, rs200_wait_min=5,
    )
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "prediction_only"


def test_current_status_handles_admin_source(db_session, seed_temple_config):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=5,
        free_wait_min=60, rs50_wait_min=15, rs200_wait_min=5, source="admin",
    )
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.source == "admin"


def test_parse_hhmm_fallback_on_bad_value():
    from datetime import time

    assert crowd_svc._parse_hhmm(None, time(7, 0)) == time(7, 0)
    assert crowd_svc._parse_hhmm("nonsense", time(7, 0)) == time(7, 0)
    assert crowd_svc._parse_hhmm("09:15", time(7, 0)) == time(9, 15)


def test_current_status_naive_now_assumed_local(db_session, seed_temple_config):
    naive = datetime.now().replace(hour=10, minute=0, tzinfo=None)
    result = crowd_svc.current_status(db_session, now=naive)
    assert result.freshness in {"live", "prediction_only"}
