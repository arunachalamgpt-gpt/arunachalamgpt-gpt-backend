"""Tests for `app.services.conversation` — per-user chat memory."""

from datetime import datetime, timedelta

from app.models.conversation_turn import ConversationTurn
from app.services import conversation


def test_record_turn_persists_row(db_session):
    row = conversation.record_turn(
        db_session, phone="9111111111", role="user", text="hi", intent="unknown"
    )
    db_session.commit()
    assert row.id is not None
    assert row.phone == "9111111111"
    assert row.intent == "unknown"


def test_record_turn_truncates_over_long_text(db_session):
    huge = "x" * 5000
    row = conversation.record_turn(
        db_session, phone="9111111112", role="user", text=huge
    )
    db_session.commit()
    assert len(row.text) == 2000


def test_load_recent_returns_openai_format(db_session):
    for text, role, intent in [
        ("hi", "user", "unknown"),
        ("Hello!", "bot", None),
        ("crowd?", "user", "ask_crowd"),
        ("Live report: 80 min", "bot", None),
    ]:
        conversation.record_turn(
            db_session, phone="9222222222",
            role=role, text=text, intent=intent,
        )
    db_session.commit()

    msgs = conversation.load_recent(db_session, phone="9222222222")
    assert msgs == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "crowd?"},
        {"role": "assistant", "content": "Live report: 80 min"},
    ]


def test_load_recent_honours_limit(db_session):
    for i in range(10):
        conversation.record_turn(
            db_session, phone="9333333333", role="user", text=f"msg {i}"
        )
    db_session.commit()
    msgs = conversation.load_recent(db_session, phone="9333333333", limit=3)
    assert len(msgs) == 3
    # Newest three preserved, in chronological order.
    assert [m["content"] for m in msgs] == ["msg 7", "msg 8", "msg 9"]


def test_load_recent_empty_for_new_phone(db_session):
    assert conversation.load_recent(db_session, phone="9444444444") == []


def test_load_recent_scopes_to_phone(db_session):
    """One user's turns must not leak into another user's context."""
    conversation.record_turn(
        db_session, phone="9555555555", role="user", text="A's message"
    )
    conversation.record_turn(
        db_session, phone="9666666666", role="user", text="B's message"
    )
    db_session.commit()
    msgs = conversation.load_recent(db_session, phone="9555555555")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "A's message"


def test_clear_for_phone_deletes_only_that_users_turns(db_session):
    conversation.record_turn(
        db_session, phone="9777777770", role="user", text="mine 1"
    )
    conversation.record_turn(
        db_session, phone="9777777770", role="bot", text="mine 2"
    )
    conversation.record_turn(
        db_session, phone="9888888880", role="user", text="theirs"
    )
    db_session.commit()

    n = conversation.clear_for_phone(db_session, "9777777770")
    db_session.commit()
    assert n == 2
    assert conversation.load_recent(db_session, phone="9777777770") == []
    remaining = conversation.load_recent(db_session, phone="9888888880")
    assert len(remaining) == 1


def test_clear_for_phone_empty_is_zero(db_session):
    assert conversation.clear_for_phone(db_session, "9nonexistent") == 0


def test_purge_old_deletes_stale_rows(db_session):
    # Fresh row
    conversation.record_turn(
        db_session, phone="9999999990", role="user", text="fresh"
    )
    # Stale row (hand-set created_at)
    old = conversation.record_turn(
        db_session, phone="9999999990", role="user", text="stale"
    )
    old.created_at = datetime.utcnow() - timedelta(days=45)
    db_session.flush()
    db_session.commit()

    n = conversation.purge_old(db_session, older_than_days=30)
    db_session.commit()
    assert n == 1
    remaining = conversation.load_recent(db_session, phone="9999999990")
    assert len(remaining) == 1
    assert remaining[0]["content"] == "fresh"


def test_purge_old_empty_table_is_zero(db_session):
    assert conversation.purge_old(db_session) == 0


def test_last_turn_returns_most_recent_of_role(db_session):
    conversation.record_turn(
        db_session, phone="9aa0000000", role="user", text="hi"
    )
    conversation.record_turn(
        db_session, phone="9aa0000000", role="bot", text="hello"
    )
    conversation.record_turn(
        db_session, phone="9aa0000000", role="user", text="crowd?"
    )
    conversation.record_turn(
        db_session, phone="9aa0000000", role="bot", text="80 min"
    )
    db_session.commit()

    last_u = conversation.last_turn(db_session, phone="9aa0000000", role="user")
    last_b = conversation.last_turn(db_session, phone="9aa0000000", role="bot")
    assert last_u is not None and last_u.text == "crowd?"
    assert last_b is not None and last_b.text == "80 min"


def test_last_turn_none_when_no_history(db_session):
    assert conversation.last_turn(db_session, phone="9zzzzzzzzz", role="user") is None
