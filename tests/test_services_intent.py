from app.services import intent as intent_svc
from app.services import llm


def test_classify_returns_unknown_when_disabled():
    r = intent_svc.classify("crowd enna")
    assert r.intent == "unknown"


def test_classify_returns_unknown_when_llm_raises(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)

    def _raise(**_):
        raise llm.LLMUnavailableError("nope")

    monkeypatch.setattr(llm, "chat_json", _raise)
    r = intent_svc.classify("crowd enna")
    assert r.intent == "unknown"


def _stub_llm(monkeypatch, payload):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda **_: payload)


def test_classify_select_language_valid(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "select_language", "slots": {"language_code": "2"}})
    r = intent_svc.classify("2")
    assert r.intent == "select_language"
    assert r.slots["language_code"] == "2"


def test_classify_select_language_invalid_code_becomes_unknown(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "select_language", "slots": {"language_code": "9"}})
    r = intent_svc.classify("9")
    assert r.intent == "unknown"


def test_classify_register_visit_full(monkeypatch):
    _stub_llm(
        monkeypatch,
        {
            "intent": "register_visit",
            "slots": {
                "visit_date": "2026-06-15",
                "has_elderly": True,
                "has_children": False,
            },
        },
    )
    r = intent_svc.classify("Visiting with elderly mother on 15th June")
    assert r.intent == "register_visit"
    assert r.slots["visit_date"] == "2026-06-15"
    assert r.slots["has_elderly"] is True


def test_classify_register_visit_drops_bad_date(monkeypatch):
    _stub_llm(
        monkeypatch,
        {"intent": "register_visit", "slots": {"visit_date": "not-a-date"}},
    )
    r = intent_svc.classify("visiting soon")
    assert r.intent == "register_visit"
    assert "visit_date" not in r.slots


def test_classify_ask_crowd(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "ask_crowd", "slots": {}})
    r = intent_svc.classify("crowd enna ippo?")
    assert r.intent == "ask_crowd"


def test_classify_ask_plan_no_slots(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "ask_plan"})  # missing slots key
    r = intent_svc.classify("when should I come?")
    assert r.intent == "ask_plan"
    assert r.slots == {}


def test_classify_change_language_valid(monkeypatch):
    _stub_llm(
        monkeypatch,
        {"intent": "change_language", "slots": {"target_language": "Tamil"}},
    )
    r = intent_svc.classify("switch me to Tamil please")
    assert r.intent == "change_language"
    assert r.slots["target_language"] == "tamil"


def test_classify_change_language_unknown_target(monkeypatch):
    _stub_llm(
        monkeypatch,
        {"intent": "change_language", "slots": {"target_language": "klingon"}},
    )
    r = intent_svc.classify("switch")
    assert r.intent == "unknown"


def test_classify_bogus_intent_returns_unknown(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "fly_to_the_moon"})
    r = intent_svc.classify("???")
    assert r.intent == "unknown"


def test_classify_handles_slots_not_a_dict(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "ask_crowd", "slots": "not-a-dict"})
    r = intent_svc.classify("crowd?")
    assert r.intent == "ask_crowd"
    assert r.slots == {}


def test_classify_general_question_with_explicit_slot(monkeypatch):
    _stub_llm(
        monkeypatch,
        {
            "intent": "general_question",
            "slots": {"question": "Which deity is here?"},
        },
    )
    r = intent_svc.classify("which god?")
    assert r.intent == "general_question"
    assert r.slots["question"] == "Which deity is here?"


def test_classify_general_question_falls_back_to_raw_text(monkeypatch):
    """When LLM picks general_question but forgets the question slot, we use
    the raw user text as the question so the QA layer still has something."""
    _stub_llm(monkeypatch, {"intent": "general_question", "slots": {}})
    r = intent_svc.classify("tell me history")
    assert r.intent == "general_question"
    assert r.slots["question"] == "tell me history"


def test_classify_ask_smalltalk(monkeypatch):
    _stub_llm(monkeypatch, {"intent": "ask_smalltalk", "slots": {}})
    r = intent_svc.classify("how are you?")
    assert r.intent == "ask_smalltalk"


def test_classify_ask_plan_carries_follow_up_slots(monkeypatch):
    """Follow-up like "with elderly and kids" after a plan turn should carry
    has_elderly / has_children through."""
    _stub_llm(
        monkeypatch,
        {
            "intent": "ask_plan",
            "slots": {"has_elderly": True, "has_children": True},
        },
    )
    r = intent_svc.classify("with parents and one kid")
    assert r.intent == "ask_plan"
    assert r.slots["has_elderly"] is True
    assert r.slots["has_children"] is True


def test_classify_ask_plan_without_slots_stays_empty(monkeypatch):
    """When the LLM omits family slots, we don't invent them."""
    _stub_llm(monkeypatch, {"intent": "ask_plan", "slots": {}})
    r = intent_svc.classify("when should I come?")
    assert r.intent == "ask_plan"
    assert "has_elderly" not in r.slots
    assert "has_children" not in r.slots


def test_system_prompt_documents_follow_up_handling():
    """Guard against someone editing the prompt and dropping follow-up rules."""
    prompt = intent_svc.SYSTEM_PROMPT.lower()
    assert "follow-up" in prompt
    assert "inherit" in prompt
    assert "what about tomorrow" in prompt or "and in the evening" in prompt


def test_classify_forwards_history_to_llm(monkeypatch):
    """Prior turns must reach the LLM so follow-ups resolve in context."""
    captured = {}
    monkeypatch.setattr(llm, "is_enabled", lambda: True)

    def _capture(**kwargs):
        captured.update(kwargs)
        return {"intent": "ask_crowd", "slots": {}}

    monkeypatch.setattr(llm, "chat_json", _capture)
    history = [
        {"role": "user", "content": "crowd?"},
        {"role": "assistant", "content": "80 min"},
    ]
    intent_svc.classify("what about tomorrow?", history=history)
    assert captured["history"] == history
