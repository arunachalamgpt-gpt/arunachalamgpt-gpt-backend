"""Tests for the new devotee_flow features:
- /menu and /reset commands
- greet by name in language ack
- general_question + ask_smalltalk intent dispatch
- natural-language date parsing
- repeat-loop detection
"""

from datetime import date, datetime, timedelta, timezone

from app.models.devotee import DevoteeProfile
from app.schemas.devotee import IncomingWhatsAppMessage
from app.services import devotee_flow
from app.services import intent as intent_svc
from app.services import temple_qa as qa_svc
from app.services import translator as translator_svc


def _msg(text, phone="9876543210"):
    return IncomingWhatsAppMessage(phone=phone, text=text)


def _passthrough_translate(monkeypatch):
    monkeypatch.setattr(translator_svc, "translate", lambda text, lang: text)


def _stub_intent(monkeypatch, mapping):
    def _classify(text, **_kwargs):
        return mapping.get(text.strip(), intent_svc.IntentResult(intent="unknown"))

    monkeypatch.setattr(intent_svc, "classify", _classify)


# ---------- /menu and /reset ----------


def test_reset_command_clears_language(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    profile = db_session.get(DevoteeProfile, "9876543210")
    assert profile.language == "english"

    r = devotee_flow.handle_incoming(db_session, _msg("/reset"))
    db_session.commit()
    assert "Welcome" in r.text  # language menu
    assert r.state == "new"
    profile = db_session.get(DevoteeProfile, "9876543210")
    assert profile.language is None


def test_reset_aliases(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    for alias in ("reset", "restart", "start over", "/start"):
        phone = f"912000000{abs(hash(alias)) % 1000:03d}"
        # First contact + pick language
        devotee_flow.handle_incoming(db_session, _msg("Hi", phone=phone))
        devotee_flow.handle_incoming(db_session, _msg("5", phone=phone))
        db_session.commit()
        r = devotee_flow.handle_incoming(db_session, _msg(alias, phone=phone))
        assert "Welcome" in r.text, f"alias {alias!r} did not trigger reset"


def test_menu_command_returns_help(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("/menu"))
    assert "crowd" in r.text
    assert "plan" in r.text


def test_menu_aliases(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    for alias in ("menu", "/help", "help", "options"):
        r = devotee_flow.handle_incoming(db_session, _msg(alias))
        assert "crowd" in r.text


# ---------- greet by name ----------


def test_greet_by_name_in_language_ack(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    # Pre-create profile with a name set
    profile = DevoteeProfile(phone="9876543211", name="Kavitha")
    db_session.add(profile)
    db_session.commit()

    devotee_flow.handle_incoming(db_session, _msg("Hi", phone="9876543211"))
    r = devotee_flow.handle_incoming(db_session, _msg("5", phone="9876543211"))
    db_session.commit()
    assert "Kavitha" in r.text


def test_no_name_omits_greeting(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    devotee_flow.handle_incoming(db_session, _msg("Hi", phone="9876543212"))
    r = devotee_flow.handle_incoming(db_session, _msg("5", phone="9876543212"))
    assert "Got it — " in r.text


# ---------- general_question dispatch ----------


def test_general_question_calls_qa(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    monkeypatch.setattr(
        qa_svc, "answer", lambda q, **_: f"FAKE QA: {q}"
    )
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "which god": intent_svc.IntentResult(
                intent="general_question",
                slots={"question": "Which god is at Arunachaleswarar?"},
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("which god"))
    assert r.text.startswith("FAKE QA:")
    assert r.metadata.get("qa") is True


def test_general_question_empty_slot_falls_through(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "?": intent_svc.IntentResult(
                intent="general_question", slots={"question": ""}
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("?"))
    # Falls through to help text
    assert "crowd" in r.text.lower() or "help" in r.text.lower()


def test_general_question_qa_unavailable_returns_polite_fallback(db_session, monkeypatch):
    """When LLM classifies as factual Q&A but QA backend is down, we send a
    polite "try again" message instead of silently dropping the message or
    mis-parsing it as a visit date."""
    _passthrough_translate(monkeypatch)
    monkeypatch.setattr(qa_svc, "answer", lambda q, **_: None)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "tell me history": intent_svc.IntentResult(
                intent="general_question",
                slots={"question": "tell me history"},
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("tell me history"))
    assert "try again" in r.text.lower() or "menu" in r.text.lower()
    assert r.metadata.get("qa") is False


# ---------- ask_smalltalk dispatch ----------


def test_smalltalk_returns_polite_redirect(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "how are you": intent_svc.IntentResult(intent="ask_smalltalk"),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("how are you"))
    assert "ArunachalamGPT" in r.text
    assert r.metadata.get("smalltalk") is True


def test_smalltalk_uses_name_when_known(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    profile = DevoteeProfile(
        phone="9876543220",
        name="Kavitha",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    db_session.commit()

    _stub_intent(
        monkeypatch,
        {"hi there": intent_svc.IntentResult(intent="ask_smalltalk")},
    )
    r = devotee_flow.handle_incoming(
        db_session, _msg("hi there", phone="9876543220")
    )
    assert "Kavitha" in r.text


# ---------- natural-language date parsing ----------


def test_parse_date_handles_iso():
    target = date.today() + timedelta(days=7)
    assert devotee_flow._parse_date(target.isoformat()) == target


def test_parse_date_handles_dmy_slash():
    target = date.today() + timedelta(days=14)
    text = f"{target.day:02d}/{target.month:02d}/{target.year}"
    assert devotee_flow._parse_date(text) == target


def test_parse_date_handles_natural_tomorrow():
    """`dateparser` should resolve "tomorrow" to date.today() + 1 day."""
    result = devotee_flow._parse_date("I'm visiting tomorrow")
    assert result == date.today() + timedelta(days=1)


def test_parse_date_rejects_past_dates():
    # "yesterday" is in the past — should be None
    assert devotee_flow._parse_date("I was there yesterday") is None


def test_parse_date_returns_none_for_no_date():
    assert devotee_flow._parse_date("how is the weather") is None


def test_parse_date_search_dates_raises_falls_back_to_parse(monkeypatch):
    """If `search_dates` blows up (it has been known to on certain locales),
    we fall back to plain `dateparser.parse`."""

    def _boom(*a, **kw):
        raise RuntimeError("search_dates exploded")

    monkeypatch.setattr(devotee_flow, "search_dates", _boom)
    # Trigger word ("on") not in our gate, so use a real one. Plain
    # dateparser.parse handles a whole-text date string (no surrounding words).
    target = date.today() + timedelta(days=2)
    text = target.strftime("%B %d, %Y")  # e.g. "July 01, 2026"
    # July/August/etc all match the month-name trigger in _DATE_TRIGGER_RE.
    assert devotee_flow._parse_date(text) == target


def test_parse_date_both_paths_return_none(monkeypatch):
    """Trigger word present but search_dates finds nothing AND dateparser.parse
    returns None — we should return None without exploding."""
    import dateparser as dp

    monkeypatch.setattr(devotee_flow, "search_dates", lambda *a, **kw: None)
    monkeypatch.setattr(dp, "parse", lambda *a, **kw: None)
    assert devotee_flow._parse_date("next something unparseable") is None


def test_parse_date_dateparser_parse_raises_returns_none(monkeypatch):
    """Trigger word present, search_dates returns nothing, dateparser.parse
    raises — we swallow and return None."""
    import dateparser as dp

    monkeypatch.setattr(devotee_flow, "search_dates", lambda *a, **kw: None)

    def _boom(*a, **kw):
        raise RuntimeError("dateparser exploded")

    monkeypatch.setattr(dp, "parse", _boom)
    assert devotee_flow._parse_date("next gibberish text") is None


# ---------- repeat-loop detection ----------


def _make_profile(**kwargs) -> DevoteeProfile:
    defaults = dict(
        phone="9000000001",
        language="english",
        onboarding_state="language_selected",
    )
    defaults.update(kwargs)
    return DevoteeProfile(**defaults)


def test_repeat_first_time_no_prefix():
    profile = _make_profile()
    out = devotee_flow._maybe_break_repeat_loop(profile, "hello")
    assert out == "hello"
    assert profile.repeat_count == 0
    assert profile.last_reply_hash == devotee_flow._hash_reply("hello")


def test_repeat_second_identical_adds_acknowledgement():
    profile = _make_profile()
    devotee_flow._maybe_break_repeat_loop(profile, "Crowd 80 min")
    out = devotee_flow._maybe_break_repeat_loop(profile, "Crowd 80 min")
    assert profile.repeat_count == 1
    assert "same question" in out.lower()
    assert "Crowd 80 min" in out


def test_repeat_third_identical_escalates_to_circles():
    profile = _make_profile()
    devotee_flow._maybe_break_repeat_loop(profile, "X")
    devotee_flow._maybe_break_repeat_loop(profile, "X")
    out = devotee_flow._maybe_break_repeat_loop(profile, "X")
    assert profile.repeat_count == 2
    assert "circles" in out.lower()
    assert "menu" in out.lower() or "reset" in out.lower()


def test_repeat_resets_when_reply_differs():
    profile = _make_profile()
    devotee_flow._maybe_break_repeat_loop(profile, "A")
    devotee_flow._maybe_break_repeat_loop(profile, "A")
    assert profile.repeat_count == 1
    out = devotee_flow._maybe_break_repeat_loop(profile, "B")
    assert profile.repeat_count == 0
    assert out == "B"


def test_repeat_resets_when_window_expires():
    profile = _make_profile()
    devotee_flow._maybe_break_repeat_loop(profile, "A")
    # Move last_reply_at into the past beyond the 10-min window.
    profile.last_reply_at = datetime.now(timezone.utc) - timedelta(hours=1)
    out = devotee_flow._maybe_break_repeat_loop(profile, "A")
    assert profile.repeat_count == 0
    assert out == "A"


def test_repeat_naive_last_reply_at_is_assumed_utc():
    """Defensive: if the DB hands back a naive datetime, treat it as UTC."""
    profile = _make_profile()
    profile.last_reply_hash = devotee_flow._hash_reply("A")
    # Naive timestamp inside the window.
    profile.last_reply_at = datetime.utcnow()
    out = devotee_flow._maybe_break_repeat_loop(profile, "A")
    assert profile.repeat_count == 1
    assert "same question" in out.lower()


def test_repeat_wrap_truncates_inner_to_preserve_menu_hint():
    """If the underlying reply is huge, the wrapper still keeps its 'menu' hint."""
    from app.services import whatsapp as whatsapp_svc
    profile = _make_profile()
    huge = "x" * whatsapp_svc.MAX_OUTBOUND_BODY
    devotee_flow._maybe_break_repeat_loop(profile, huge)
    out = devotee_flow._maybe_break_repeat_loop(profile, huge)
    assert len(out) <= whatsapp_svc.MAX_OUTBOUND_BODY
    assert "menu" in out.lower()  # hint survived
    assert out.startswith("Got the same question")


# ---------- /reset clears loop state ----------


def test_reset_clears_loop_counter(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    profile = DevoteeProfile(
        phone="9888777666",
        language="english",
        onboarding_state="language_selected",
        last_reply_hash="abc123",
        repeat_count=2,
        last_reply_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    db_session.commit()

    devotee_flow.handle_incoming(
        db_session, _msg("/reset", phone="9888777666")
    )
    db_session.commit()
    fresh = db_session.get(DevoteeProfile, "9888777666")
    assert fresh.last_reply_hash is None
    assert fresh.repeat_count == 0
    assert fresh.last_reply_at is None


# ---------- /menu translation ----------


def test_menu_is_translated_for_non_english(db_session, monkeypatch):
    """Tamil users should get the help body translated, not raw English."""
    from app.services import translator as translator_svc

    captured = {}

    def _capture_translate(text, lang):
        captured["lang"] = lang
        return f"[TAMIL]{text}"

    monkeypatch.setattr(translator_svc, "translate", _capture_translate)

    profile = DevoteeProfile(
        phone="9111000111",
        language="tamil",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    db_session.commit()

    r = devotee_flow.handle_incoming(
        db_session, _msg("/menu", phone="9111000111")
    )
    assert r.text.startswith("[TAMIL]")
    assert captured["lang"] == "tamil"


# ---------- inner-loop input dedup ----------


def test_inner_loop_reuses_previous_bot_reply_within_window(
    db_session, monkeypatch
):
    """User re-sends the exact same message a moment later → reuse last reply,
    skip the LLM chain entirely."""
    from app.services import conversation as conv_svc

    _passthrough_translate(monkeypatch)

    profile = DevoteeProfile(
        phone="9040404040",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    # Seed a recent user+bot exchange.
    conv_svc.record_turn(
        db_session, phone="9040404040", role="user", text="crowd?"
    )
    conv_svc.record_turn(
        db_session, phone="9040404040", role="bot",
        text="Live report: Free 80 min",
    )
    db_session.commit()

    calls = {"intent": 0}

    def _classify(text, **_):
        calls["intent"] += 1
        return intent_svc.IntentResult(intent="ask_crowd")

    monkeypatch.setattr(intent_svc, "classify", _classify)

    r = devotee_flow.handle_incoming(
        db_session, _msg("crowd?", phone="9040404040")
    )
    # Cached reply reused, no LLM call.
    assert calls["intent"] == 0
    assert "Free 80 min" in r.text
    assert r.metadata.get("cached_from") == "recent_bot_turn"


def test_inner_loop_ignored_when_input_differs(db_session, monkeypatch):
    from app.services import conversation as conv_svc
    _passthrough_translate(monkeypatch)

    profile = DevoteeProfile(
        phone="9050505050",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    conv_svc.record_turn(db_session, phone="9050505050", role="user", text="crowd?")
    conv_svc.record_turn(db_session, phone="9050505050", role="bot", text="80 min")
    db_session.commit()

    calls = {"intent": 0}

    def _classify(text, **_):
        calls["intent"] += 1
        return intent_svc.IntentResult(intent="ask_crowd")

    monkeypatch.setattr(intent_svc, "classify", _classify)
    devotee_flow.handle_incoming(
        db_session, _msg("plan?", phone="9050505050")
    )
    assert calls["intent"] == 1  # LLM ran normally


def test_inner_loop_ignored_when_window_expired(db_session, monkeypatch):
    from app.services import conversation as conv_svc
    from datetime import timedelta
    _passthrough_translate(monkeypatch)

    profile = DevoteeProfile(
        phone="9060606060",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    conv_svc.record_turn(db_session, phone="9060606060", role="user", text="crowd?")
    conv_svc.record_turn(db_session, phone="9060606060", role="bot", text="80 min")
    db_session.commit()

    # Push both turns beyond the dedup window.
    for t in db_session.query(devotee_flow.conversation_svc.ConversationTurn if False else __import__("app.models.conversation_turn", fromlist=["ConversationTurn"]).ConversationTurn).filter_by(phone="9060606060"):
        t.created_at = datetime.utcnow() - timedelta(minutes=5)
    db_session.commit()

    calls = {"intent": 0}

    def _classify(text, **_):
        calls["intent"] += 1
        return intent_svc.IntentResult(intent="ask_crowd")

    monkeypatch.setattr(intent_svc, "classify", _classify)
    devotee_flow.handle_incoming(
        db_session, _msg("crowd?", phone="9060606060")
    )
    assert calls["intent"] == 1  # window expired → LLM ran


def test_inner_loop_no_last_bot_returns_none(db_session):
    """User has sent a message but bot never replied — no cache to reuse."""
    from app.services import conversation as conv_svc
    conv_svc.record_turn(
        db_session, phone="9070707070", role="user", text="hi"
    )
    db_session.commit()
    assert devotee_flow._maybe_reuse_recent_bot_reply(
        db_session, "9070707070", "hi"
    ) is None


def test_inner_loop_no_history_returns_none(db_session):
    """Fresh phone with no turns — nothing to dedup against."""
    assert devotee_flow._maybe_reuse_recent_bot_reply(
        db_session, "9080808080", "anything"
    ) is None


def test_inner_loop_bot_before_user_returns_none(db_session):
    """Defensive: if somehow the last bot turn predates the last user turn,
    don't reuse it (stale reply for a newer question)."""
    from app.services import conversation as conv_svc
    from datetime import timedelta
    conv_svc.record_turn(
        db_session, phone="9090909090", role="bot", text="old reply"
    )
    conv_svc.record_turn(
        db_session, phone="9090909090", role="user", text="new question"
    )
    # Make the bot turn OLDER than the user turn.
    bot_row = conv_svc.last_turn(db_session, phone="9090909090", role="bot")
    bot_row.created_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.flush()
    db_session.commit()
    assert devotee_flow._maybe_reuse_recent_bot_reply(
        db_session, "9090909090", "new question"
    ) is None


# ---------- ask_plan follow-up slots ----------


def test_ask_plan_follow_up_updates_profile_flags(db_session, monkeypatch):
    _passthrough_translate(monkeypatch)
    profile = DevoteeProfile(
        phone="9012340000",
        language="english",
        onboarding_state="language_selected",
        has_elderly=False,
        has_children=False,
    )
    db_session.add(profile)
    db_session.commit()

    _stub_intent(
        monkeypatch,
        {
            "with elderly": intent_svc.IntentResult(
                intent="ask_plan",
                slots={"has_elderly": True, "has_children": False},
            ),
        },
    )
    r = devotee_flow.handle_incoming(
        db_session, _msg("with elderly", phone="9012340000")
    )
    db_session.commit()
    fresh = db_session.get(DevoteeProfile, "9012340000")
    assert fresh.has_elderly is True
    assert "Rs.200" in r.text  # early-arrival recommendation kicked in


# ---------- conversation memory ----------


def test_handle_incoming_records_user_and_bot_turns(db_session, monkeypatch):
    from app.services import conversation as conv_svc
    _passthrough_translate(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "crowd?": intent_svc.IntentResult(intent="unknown"),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi", phone="9010101010"))
    devotee_flow.handle_incoming(db_session, _msg("5", phone="9010101010"))
    devotee_flow.handle_incoming(db_session, _msg("crowd?", phone="9010101010"))
    db_session.commit()

    turns = conv_svc.load_recent(db_session, phone="9010101010", limit=20)
    # We only start recording once the LLM path runs (after language pick).
    assert any(t["content"] == "crowd?" for t in turns)
    # Bot reply also stored (as assistant).
    assistants = [t for t in turns if t["role"] == "assistant"]
    assert len(assistants) >= 1


def test_handle_incoming_passes_history_to_intent(db_session, monkeypatch):
    """The classifier must receive prior turns for context-aware follow-ups."""
    from app.services import conversation as conv_svc
    _passthrough_translate(monkeypatch)
    seen_histories = []

    def _classify(text, **kwargs):
        seen_histories.append(kwargs.get("history"))
        return intent_svc.IntentResult(intent="unknown")

    monkeypatch.setattr(intent_svc, "classify", _classify)

    # Seed a prior turn in the DB.
    profile = DevoteeProfile(
        phone="9020202020",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    conv_svc.record_turn(
        db_session, phone="9020202020", role="user", text="crowd?"
    )
    conv_svc.record_turn(
        db_session, phone="9020202020", role="bot", text="80 min"
    )
    db_session.commit()

    devotee_flow.handle_incoming(
        db_session, _msg("what about tomorrow?", phone="9020202020")
    )
    # First call from handle_incoming — the language-selection stub uses
    # `LANGUAGE_BY_INDEX` fast-path for the "5" input; here we start already
    # past selection so intent.classify fires once with history.
    assert seen_histories, "intent.classify was never called"
    hist = seen_histories[0]
    assert hist is not None
    assert {"role": "user", "content": "crowd?"} in hist


def test_reset_clears_conversation_memory(db_session, monkeypatch):
    from app.services import conversation as conv_svc
    _passthrough_translate(monkeypatch)

    profile = DevoteeProfile(
        phone="9030303030",
        language="english",
        onboarding_state="language_selected",
    )
    db_session.add(profile)
    conv_svc.record_turn(
        db_session, phone="9030303030", role="user", text="old stuff"
    )
    db_session.commit()
    assert conv_svc.load_recent(db_session, phone="9030303030")

    devotee_flow.handle_incoming(
        db_session, _msg("/reset", phone="9030303030")
    )
    db_session.commit()
    assert conv_svc.load_recent(db_session, phone="9030303030") == []


def test_menu_skips_translation_when_no_language(db_session, monkeypatch):
    """Pre-language users shouldn't get translation attempted (no target lang)."""
    from app.services import translator as translator_svc
    calls = {"n": 0}

    def _count(text, lang):
        calls["n"] += 1
        return text

    monkeypatch.setattr(translator_svc, "translate", _count)
    profile = DevoteeProfile(phone="9111000222")
    db_session.add(profile)
    db_session.commit()
    r = devotee_flow.handle_incoming(
        db_session, _msg("/menu", phone="9111000222")
    )
    assert "crowd" in r.text  # raw English
    assert calls["n"] == 0  # translator never called
