from app.services import admin_commands


def test_dispatch_non_admin_text(db_session):
    r = admin_commands.dispatch(db_session, sender_phone="9444444444", text="hello")
    assert r.action == "unknown"


def test_dispatch_admin_only(db_session):
    r = admin_commands.dispatch(db_session, sender_phone="9444444444", text="ADMIN")
    assert r.action == "unknown"


def test_dispatch_unknown_verb(db_session):
    r = admin_commands.dispatch(
        db_session, sender_phone="9444444444", text="ADMIN reboot"
    )
    assert r.action == "unknown"


def test_dispatch_config_set(db_session):
    r = admin_commands.dispatch(
        db_session,
        sender_phone="9444444444",
        text="ADMIN config rs50_sold_out true",
    )
    db_session.commit()
    assert r.action == "config_set"
    assert r.payload["key"] == "rs50_sold_out"
    assert r.payload["value"] == "true"


def test_dispatch_config_missing_value(db_session):
    r = admin_commands.dispatch(
        db_session, sender_phone="9444444444", text="ADMIN config onlykey"
    )
    assert r.action == "unknown"


def test_dispatch_crowd_happy(db_session, seed_temple_config):
    r = admin_commands.dispatch(
        db_session,
        sender_phone="9444444444",
        text="ADMIN crowd F:60 T50:15 T200:5",
    )
    db_session.commit()
    assert r.action == "crowd_report"
    assert "id" in r.payload


def test_dispatch_crowd_missing_payload(db_session):
    r = admin_commands.dispatch(
        db_session, sender_phone="9444444444", text="ADMIN crowd"
    )
    assert r.action == "unknown"


def test_dispatch_crowd_bad_payload(db_session):
    r = admin_commands.dispatch(
        db_session, sender_phone="9444444444", text="ADMIN crowd not-valid"
    )
    assert r.action == "unknown"


def test_dispatch_broadcast(db_session):
    r = admin_commands.dispatch(
        db_session,
        sender_phone="9444444444",
        text="ADMIN broadcast Tamil Crowd is low now!",
    )
    assert r.action == "broadcast"
    assert r.payload["language"] == "tamil"
    assert "Crowd is low" in r.payload["message"]


def test_dispatch_broadcast_missing_message(db_session):
    r = admin_commands.dispatch(
        db_session, sender_phone="9444444444", text="ADMIN broadcast Tamil"
    )
    assert r.action == "unknown"
