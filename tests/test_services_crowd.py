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


# ---------- prediction-backed messages for stale / missing data ----------


def _seed_history(db, *, hour, free=None, rs50=None, rs200=None,
                  is_pournami=False, is_festival=False):
    """Insert a CrowdHistory row so prediction.predict() has data."""
    from app.models.crowd import CrowdHistory
    from datetime import date as _d

    db.add(
        CrowdHistory(
            visit_date=_d.today(),
            hour_of_day=hour,
            is_pournami=is_pournami,
            is_festival=is_festival,
            free_wait_min=free,
            rs50_wait_min=rs50,
            rs200_wait_min=rs200,
            source="post_visit",
        )
    )
    db.flush()


def test_current_status_no_report_uses_prediction(db_session, seed_temple_config):
    """When no volunteer report exists, message should carry actual numbers."""
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _seed_history(db_session, hour=10, free=90, rs50=20, rs200=5)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "prediction_only"
    assert result.free_wait_min == 90
    assert result.rs50_wait_min == 20
    assert result.rs200_wait_min == 5
    assert "Based on past visits" in result.message
    assert "n=1" in result.message


def test_current_status_stale_over_6h_uses_prediction(
    db_session, seed_temple_config
):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=15, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=420,
        free_wait_min=80, rs50_wait_min=15, rs200_wait_min=5,
    )
    _seed_history(db_session, hour=15, free=70, rs50=18, rs200=6)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "prediction_only"
    assert result.free_wait_min == 70
    assert "7h old" in result.message  # 420 // 60
    assert "Based on past visits" in result.message


def test_current_status_no_history_falls_back_to_honest_message(
    db_session, seed_temple_config
):
    """If neither volunteer data nor history exists, we don't fabricate."""
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.free_wait_min is None
    assert "check back" in result.message.lower()


def test_current_status_stale_no_history_says_so_honestly(
    db_session, seed_temple_config
):
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=15, minute=0)
    _push_status(
        db_session, base_now=midmorning, age_minutes=420,
        free_wait_min=80, rs50_wait_min=15, rs200_wait_min=5,
    )
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.freshness == "prediction_only"
    assert "7h old" in result.message
    assert "not yet have enough" in result.message.lower() or \
        "ask a volunteer" in result.message.lower()


def test_current_status_pournami_message_when_in_lunar_table(
    db_session, seed_temple_config, monkeypatch
):
    """When today is a Pournami, the message should call it out."""
    from app.services import lunar_calendar
    monkeypatch.setattr(lunar_calendar, "is_pournami", lambda d: True)
    monkeypatch.setattr(lunar_calendar, "is_karthigai_deepam", lambda d: False)

    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _seed_history(db_session, hour=10, free=150, is_pournami=True)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert "Pournami" in result.message
    assert result.free_wait_min == 150


def test_current_status_festival_message(
    db_session, seed_temple_config, monkeypatch
):
    """Karthigai Deepam day should be called out explicitly."""
    from app.services import lunar_calendar
    monkeypatch.setattr(lunar_calendar, "is_pournami", lambda d: False)
    monkeypatch.setattr(lunar_calendar, "is_karthigai_deepam", lambda d: True)

    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _seed_history(db_session, hour=10, free=200, is_festival=True)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert "Karthigai Deepam" in result.message
    assert result.free_wait_min == 200


def test_current_status_history_with_all_none_falls_to_honest_message(
    db_session, seed_temple_config
):
    """Edge case: history rows exist but every wait-min is None (e.g. SOLD
    across the board). We must NOT promise "here's an estimate" then show
    blank numbers — fall back to the honest message."""
    midmorning = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    _seed_history(db_session, hour=10, free=None, rs50=None, rs200=None)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=midmorning)
    assert result.free_wait_min is None
    assert "check back" in result.message.lower()
