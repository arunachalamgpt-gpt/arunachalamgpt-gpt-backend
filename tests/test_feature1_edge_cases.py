"""Edge cases that round out the Feature 1 suite.

These aren't needed for line coverage (already 100%) but they protect against
regressions in tricky behaviour: lowercase parser tokens, extra whitespace,
timezone boundaries, profile flag persistence across webhook turns, audit-trail
of admin updates, response payload shape, and sold-out propagation.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.errors import ValidationFailedError
from app.schemas.crowd import CrowdReportIn
from app.schemas.devotee import IncomingWhatsAppMessage
from app.services import crowd as crowd_svc
from app.services import devotee_flow
from app.services import temple_config


# ---------- volunteer message parser ----------


def test_parser_accepts_lowercase_tokens():
    p = crowd_svc.parse_volunteer_message("f:60 t50:5 t200:1")
    assert p.free_wait_min == 60
    assert p.rs50_wait_min == 5
    assert p.rs200_wait_min == 1


def test_parser_accepts_extra_whitespace():
    p = crowd_svc.parse_volunteer_message("   F:60    T50:5  T200:1  ")
    assert p.free_wait_min == 60


def test_parser_rejects_negative_values():
    """Negative values fail the integer regex (only `\\d+` allowed)."""
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("F:-5")


def test_parser_rejects_non_integer():
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("F:abc")


def test_parser_rejects_unknown_line_prefix():
    with pytest.raises(ValidationFailedError):
        crowd_svc.parse_volunteer_message("VIP:30")


# ---------- crowd status fallback ----------


def test_current_status_exactly_at_open_time_is_live(db_session, seed_temple_config):
    """Boundary: at exactly the opening minute we should be inside hours."""
    now = datetime.now(crowd_svc._local_tz()).replace(hour=5, minute=30)
    base_utc = now.astimezone(timezone.utc).replace(tzinfo=None)
    payload = CrowdReportIn(
        reporter_phone="9444444444", free_wait_min=100, rs50_wait_min=20, rs200_wait_min=5
    )
    row = crowd_svc.record_status(db_session, payload)
    row.reported_at = base_utc
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=now)
    assert result.freshness == "live"


def test_current_status_exactly_at_close_time_is_closed(
    db_session, seed_temple_config
):
    now = datetime.now(crowd_svc._local_tz()).replace(hour=21, minute=0)
    result = crowd_svc.current_status(db_session, now=now)
    assert result.freshness == "closed"


def test_record_status_then_change_sold_out_flags(db_session, seed_temple_config):
    """Two consecutive reports — sold-out flags should track the latest."""
    crowd_svc.record_status(
        db_session,
        CrowdReportIn(
            reporter_phone="9444444444",
            free_wait_min=200,
            rs50_sold_out=True,
            rs200_sold_out=True,
        ),
    )
    db_session.commit()
    assert temple_config.get(db_session, "rs50_sold_out").value == "true"
    assert temple_config.get(db_session, "rs200_sold_out").value == "true"

    crowd_svc.record_status(
        db_session,
        CrowdReportIn(
            reporter_phone="9444444444",
            free_wait_min=100,
            rs50_wait_min=10,
            rs200_wait_min=5,
            rs50_sold_out=False,
            rs200_sold_out=False,
        ),
    )
    db_session.commit()
    assert temple_config.get(db_session, "rs50_sold_out").value == "false"
    assert temple_config.get(db_session, "rs200_sold_out").value == "false"


# ---------- devotee state machine ----------


def _msg(text, phone="9876543210"):
    return IncomingWhatsAppMessage(phone=phone, text=text)


def test_webhook_each_language_choice(db_session):
    """All five menu numbers map to the right language code."""
    expected = {"1": "tamil", "2": "telugu", "3": "kannada", "4": "hindi", "5": "english"}
    for idx, code in expected.items():
        phone = f"987654321{idx}"
        devotee_flow.handle_incoming(db_session, _msg("Hi", phone=phone))
        db_session.commit()
        r = devotee_flow.handle_incoming(db_session, _msg(idx, phone=phone))
        db_session.commit()
        assert r.language == code, f"index {idx} should map to {code}"


def test_webhook_visit_date_preserves_flags_across_turns(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    future = date.today() + timedelta(days=10)
    devotee_flow.handle_incoming(
        db_session,
        _msg(
            "Coming with my elderly parent and small children on "
            f"{future.isoformat()}"
        ),
    )
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("plan?"))
    # Recommendation should mention Rs.200 because of elderly+children
    assert "Rs.200" in r.text


def test_webhook_multiple_language_switches(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    for code in ("tamil", "telugu", "english"):
        r = devotee_flow.handle_incoming(db_session, _msg(f"change to {code}"))
        db_session.commit()
        assert r.language == code


# ---------- admin command audit ----------


def test_admin_config_records_updated_by(db_session):
    from app.services import admin_commands

    admin_commands.dispatch(
        db_session,
        sender_phone="9444444444",
        text="ADMIN config rs50_ticket_price 75",
    )
    db_session.commit()
    row = temple_config.get(db_session, "rs50_ticket_price")
    assert row.value == "75"
    assert row.updated_by == "9444444444"


def test_admin_crowd_creates_row_with_admin_source(db_session, seed_temple_config):
    from app.services import admin_commands

    result = admin_commands.dispatch(
        db_session,
        sender_phone="9444444444",
        text="ADMIN crowd F:30 T50:5 T200:2",
    )
    db_session.commit()
    assert result.action == "crowd_report"
    latest = crowd_svc.latest_status(db_session)
    assert latest.source == "admin"
    assert latest.free_wait_min == 30


# ---------- response shape ----------


def test_current_response_carries_age_minutes(db_session, seed_temple_config):
    now = datetime.now(crowd_svc._local_tz()).replace(hour=10, minute=0)
    base_utc = now.astimezone(timezone.utc).replace(tzinfo=None)
    row = crowd_svc.record_status(
        db_session,
        CrowdReportIn(reporter_phone="9444444444", free_wait_min=60),
    )
    row.reported_at = base_utc - timedelta(minutes=45)
    db_session.commit()
    result = crowd_svc.current_status(db_session, now=now)
    # Should report ~45 minutes, within rounding tolerance
    assert result.age_minutes is not None and 40 <= result.age_minutes <= 50


def test_openapi_endpoint_lists_feature1_paths(client):
    """Swagger reflection — confirms tags + paths are mounted."""
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())
    expected = {
        "/crowd/reports",
        "/crowd/reports/structured",
        "/crowd/current",
        "/crowd/predict",
        "/crowd/history",
        "/devotees",
        "/devotees/{phone}",
        "/devotees/{phone}/plan",
        "/webhook/whatsapp",
        "/admin/config",
        "/admin/config/{key}",
        "/admin/commands",
    }
    missing = expected - paths
    assert not missing, f"Missing paths in OpenAPI schema: {missing}"


def test_openapi_endpoint_tags_present(client):
    schema = client.get("/openapi.json").json()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    for required in ("crowd", "devotees", "webhook", "admin"):
        assert required in tag_names
