"""Webhook flow with the LLM layer **enabled**.

Uses monkeypatched intent classifier + translator so the real OpenAI client
is never called. Covers the LLM-driven dispatch branches that the existing
keyword-only tests don't reach.
"""

from datetime import date, timedelta

from app.schemas.devotee import IncomingWhatsAppMessage
from app.services import crowd as crowd_svc
from app.services import devotee_flow
from app.services import intent as intent_svc
from app.services import translator as translator_svc
from app.schemas.crowd import CrowdReportIn


def _msg(text, phone="9876543210"):
    return IncomingWhatsAppMessage(phone=phone, text=text)


def _enable_translator(monkeypatch, prefix="[TR] "):
    def _fake_translate(text, target):
        if not target or target == "english":
            return text
        return prefix + text

    monkeypatch.setattr(translator_svc, "translate", _fake_translate)


def _stub_intent(monkeypatch, mapping: dict[str, intent_svc.IntentResult]):
    def _classify(text: str) -> intent_svc.IntentResult:
        return mapping.get(text.strip(), intent_svc.IntentResult(intent="unknown"))

    monkeypatch.setattr(intent_svc, "classify", _classify)


def test_language_pick_via_llm_slot(db_session, monkeypatch):
    """LLM returns select_language with code 2 — should land on Telugu."""
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "iru": intent_svc.IntentResult(
                intent="select_language", slots={"language_code": "2"}
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("iru"))
    db_session.commit()
    assert r.language == "telugu"
    # Translator was called for non-english language
    assert r.text.startswith("[TR] ")


def test_register_visit_via_llm_slot(db_session, monkeypatch, seed_temple_config):
    _enable_translator(monkeypatch)
    future = (date.today() + timedelta(days=10)).isoformat()
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "I'll come with mother and kids": intent_svc.IntentResult(
                intent="register_visit",
                slots={
                    "visit_date": future,
                    "has_elderly": True,
                    "has_children": True,
                },
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))  # english
    db_session.commit()
    r = devotee_flow.handle_incoming(
        db_session, _msg("I'll come with mother and kids")
    )
    db_session.commit()
    assert r.state == "registered"
    assert r.metadata["planned_visit_date"] == future
    # Profile should record both flags from the slots
    from app.models.devotee import DevoteeProfile

    profile = db_session.get(DevoteeProfile, "9876543210")
    assert profile.has_elderly is True
    assert profile.has_children is True


def test_register_visit_invalid_iso_falls_through_to_keywords(
    db_session, monkeypatch, seed_temple_config
):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "soon": intent_svc.IntentResult(
                intent="register_visit", slots={"visit_date": "2026-13-40"}
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("soon"))
    # falls through to keywords → help text
    assert "crowd" in r.text.lower()


def test_register_visit_without_date_slot_falls_through(
    db_session, monkeypatch, seed_temple_config
):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "want to come": intent_svc.IntentResult(
                intent="register_visit", slots={"has_elderly": True}
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("want to come"))
    # No visit_date → fall through
    assert "crowd" in r.text.lower() or "plan" in r.text.lower()


def test_ask_crowd_via_llm(db_session, monkeypatch, seed_temple_config):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "kuthukal enna": intent_svc.IntentResult(intent="ask_crowd"),
        },
    )
    crowd_svc.record_status(
        db_session,
        CrowdReportIn(
            reporter_phone="9444444444",
            free_wait_min=80,
            rs50_wait_min=10,
            rs200_wait_min=5,
        ),
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("kuthukal enna"))
    assert r.metadata.get("freshness") in {"live", "stale", "prediction_only", "closed"}


def test_ask_plan_via_llm(db_session, monkeypatch):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "advice please": intent_svc.IntentResult(intent="ask_plan"),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("advice please"))
    assert "checklist" in r.metadata


def test_change_language_via_llm(db_session, monkeypatch):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "tamil la pesu": intent_svc.IntentResult(
                intent="change_language", slots={"target_language": "tamil"}
            ),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("tamil la pesu"))
    assert r.language == "tamil"
    # translator should have run for non-english
    assert r.text.startswith("[TR] ")


def test_change_language_without_target_falls_through(
    db_session, monkeypatch, seed_temple_config
):
    _enable_translator(monkeypatch)
    _stub_intent(
        monkeypatch,
        {
            "Hi": intent_svc.IntentResult(intent="unknown"),
            "5": intent_svc.IntentResult(intent="unknown"),
            "switch": intent_svc.IntentResult(intent="change_language", slots={}),
        },
    )
    devotee_flow.handle_incoming(db_session, _msg("Hi"))
    devotee_flow.handle_incoming(db_session, _msg("5"))
    db_session.commit()
    r = devotee_flow.handle_incoming(db_session, _msg("switch"))
    # Falls through to keywords → help text (no "change to <lang>" present)
    assert "help" in r.text.lower() or "crowd" in r.text.lower()
