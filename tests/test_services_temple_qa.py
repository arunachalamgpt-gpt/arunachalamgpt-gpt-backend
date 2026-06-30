from app.services import llm, temple_qa


def test_answer_when_llm_disabled_returns_none():
    assert temple_qa.answer("which god?") is None


def test_answer_happy_path(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        llm, "chat_text",
        lambda **_: "Lord Shiva, worshipped here as Annamalaiyar.",
    )
    assert "Annamalaiyar" in temple_qa.answer("Which deity?")


def test_answer_returns_none_on_llm_error(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)

    def _raise(**_):
        raise llm.LLMUnavailableError("network")

    monkeypatch.setattr(llm, "chat_text", _raise)
    assert temple_qa.answer("Tell me about Karthigai") is None


def test_answer_returns_none_on_empty_response(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_text", lambda **_: "")
    assert temple_qa.answer("?") is None


def test_answer_uses_temperature_zero_for_faithfulness(monkeypatch):
    """Q&A must run at temperature 0 — variety/style risks hallucination."""
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return "some answer"

    monkeypatch.setattr(llm, "chat_text", _capture)
    temple_qa.answer("Where is the temple?")
    assert captured["temperature"] == 0.0


def test_system_prompt_enforces_grounding_rules():
    """Static check: the prompt explicitly forbids invention and defines
    the redirect line. If someone edits the prompt and removes these rules,
    this test fails — preventing silent regressions in answer faithfulness."""
    prompt = temple_qa.SYSTEM_PROMPT.lower()
    # 1. Grounding clause exists
    assert "grounded facts" in prompt
    assert "never invent" in prompt
    # 2. Off-domain redirect is exact
    assert temple_qa.REDIRECT_REPLY in temple_qa.SYSTEM_PROMPT
    # 3. Unknown-temple-fact rule exists
    assert "don't have a confident answer" in prompt
    # 4. No-future-festival-dates rule
    assert "future year" in prompt
