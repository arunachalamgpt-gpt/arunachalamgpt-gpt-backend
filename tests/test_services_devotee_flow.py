from datetime import date, datetime, timedelta, timezone

from app.schemas.crowd import CrowdReportIn
from app.schemas.devotee import IncomingWhatsAppMessage
from app.services import crowd as crowd_svc
from app.services import devotee_flow


def _msg(text, phone="9876543210"):
    return IncomingWhatsAppMessage(phone=phone, text=text)


def test_first_contact_shows_language_menu(db_session):
    r = devotee_flow.handle_incoming(db_session, _msg("Hi"))
    db_session.commit()
    assert "language" in r.text.lower()
    assert r.state == "new"


def test_language_pick_advances_state(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("1"))
    db_session.commit()
    assert r.language == "tamil"
    assert r.state == "language_selected"


def test_visit_registration_saves_date(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))  # english
    db_session.commit()
    future = (date.today() + timedelta(days=10)).isoformat()
    r = devotee_flow.handle_incoming(
        db_session, _msg(f"My elderly mother and I will visit on {future}")
    )
    db_session.commit()
    assert r.state == "registered"
    assert r.metadata["planned_visit_date"] == future


def test_visit_registration_with_dmy_format(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    future = date.today() + timedelta(days=14)
    text = f"Coming with my children on {future.day:02d}/{future.month:02d}/{future.year}"
    r = devotee_flow.handle_incoming(db_session, _msg(text))
    db_session.commit()
    assert r.state == "registered"


def test_visit_registration_invalid_date_string(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    # 9999-13-40 matches the YYYY-MM-DD regex but isn't a valid date — should fall through
    r = devotee_flow.handle_incoming(db_session, _msg("date 9999-13-40"))
    db_session.commit()
    # Doesn't register, lands in help text
    assert r.state == "language_selected"


def test_crowd_query_returns_status(db_session, seed_temple_config):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("crowd now?"))
    assert "freshness" in r.metadata


def test_crowd_query_with_live_data(db_session, seed_temple_config):
    # Widen the open window so this test is wall-clock independent.
    from app.services import temple_config as cfg_svc

    cfg_svc.upsert(db_session, "temple_open_time", "00:00")
    cfg_svc.upsert(db_session, "temple_close_time", "23:59")
    db_session.commit()

    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    # Seed a live report at a daytime hour
    payload = CrowdReportIn(
        reporter_phone="9444444444",
        free_wait_min=100,
        rs50_wait_min=20,
        rs200_wait_min=5,
    )
    crowd_svc.record_status(db_session, payload)
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("wait?"))
    assert "Free" in r.text


def test_planning_query_uses_profile(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    future = (date.today() + timedelta(days=4)).isoformat()
    devotee_flow.handle_incoming(
        db_session, _msg(f"elderly mother visiting {future}")
    )
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("plan?"))
    assert "checklist" in r.metadata


def test_language_change(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("change to tamil"))
    assert r.language == "tamil"


def test_unknown_intent_falls_to_help(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("xyzzy"))
    assert "help" in r.text.lower() or "crowd" in r.text.lower()


def test_invalid_language_selection_shows_menu_again(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("9"))
    assert "language" in r.text.lower()
    assert r.state == "new"


def test_crowd_query_no_data_message_passthrough(db_session, seed_temple_config):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("crowd?"))
    assert r.text  # not empty


def test_crowd_query_closed_returns_message(db_session, seed_temple_config, monkeypatch):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    # Force a "closed" response from the crowd service
    from app.schemas.crowd import CrowdCurrentResponse

    def _closed(*args, **kwargs):
        return CrowdCurrentResponse(
            freshness="closed",
            source="prediction",
            reported_at=None,
            age_minutes=None,
            free_wait_min=None,
            rs50_wait_min=None,
            rs200_wait_min=None,
            rs50_sold_out=False,
            rs200_sold_out=False,
            message="Temple closed",
        )

    monkeypatch.setattr(crowd_svc, "current_status", _closed)
    r = devotee_flow.handle_incoming(db_session, _msg("crowd?"))
    assert "closed" in r.text.lower()


def test_crowd_query_includes_sold_out_labels(db_session, seed_temple_config):
    from app.services import temple_config as cfg_svc

    cfg_svc.upsert(db_session, "temple_open_time", "00:00")
    cfg_svc.upsert(db_session, "temple_close_time", "23:59")
    db_session.commit()

    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    crowd_svc.record_status(
        db_session,
        CrowdReportIn(
            reporter_phone="9444444444",
            free_wait_min=100,
            rs50_wait_min=None,
            rs200_wait_min=None,
            rs50_sold_out=True,
            rs200_sold_out=True,
        ),
    )
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("crowd?"))
    assert "SOLD" in r.text


def test_language_change_unrecognised_language_falls_to_help(db_session):
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("change to klingon"))
    assert r.language == "english"
