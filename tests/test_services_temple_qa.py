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


# ---------- partial answer validation ----------


def _stub_answer(monkeypatch, reply):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(llm, "chat_text", lambda **_: reply)


def test_answer_rejects_stub_that_is_too_short(monkeypatch):
    _stub_answer(monkeypatch, "ok")
    assert temple_qa.answer("Which god?") is None


def test_answer_rejects_pure_whitespace_stub(monkeypatch):
    _stub_answer(monkeypatch, "   \n   ")
    assert temple_qa.answer("Which god?") is None


def test_answer_rejects_short_clarifying_question_back(monkeypatch):
    _stub_answer(monkeypatch, "Which festival do you mean?")
    assert temple_qa.answer("when is it?") is None


def test_answer_rejects_multi_question_reply(monkeypatch):
    _stub_answer(monkeypatch, "Which festival? Or do you mean the temple?")
    assert temple_qa.answer("when?") is None


def test_answer_accepts_long_reply_ending_with_question(monkeypatch):
    """A long, informative answer that ends with an optional follow-up is fine."""
    reply = (
        "Karthigai Deepam happens in the Karthigai Tamil month (Nov/Dec), "
        "when a great flame is lit atop Arunachala hill and can be seen for "
        "kilometres. It's the temple's biggest festival. Would you like to "
        "know more about the rituals?"
    )
    _stub_answer(monkeypatch, reply)
    assert temple_qa.answer("tell me about Karthigai Deepam") == reply


def test_answer_rejects_verbatim_echo_of_question(monkeypatch):
    """Reply that just parrots the question back — declares nothing."""
    long_echo = (
        "Tell me about Karthigai Deepam and the flame on Arunachala hill"
    )
    _stub_answer(monkeypatch, long_echo)
    assert temple_qa.answer(long_echo) is None


def test_answer_accepts_intentional_redirect(monkeypatch):
    _stub_answer(monkeypatch, temple_qa.REDIRECT_REPLY)
    assert temple_qa.answer("What's the weather in Delhi?") == temple_qa.REDIRECT_REPLY


def test_answer_accepts_honest_dont_know_reply(monkeypatch):
    _stub_answer(
        monkeypatch,
        "I don't have a confident answer for that — please ask a temple guide.",
    )
    result = temple_qa.answer("what year did the Chola king X build the mandapam?")
    assert result and "confident answer" in result


# ---------- retrieval augmentation ----------


def test_answer_injects_retrieved_context_into_user_message(monkeypatch):
    """The user message reaching the LLM should include the retrieved facts."""
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return "Lord Shiva as Annamalaiyar."

    monkeypatch.setattr(llm, "chat_text", _capture)
    temple_qa.answer("which god is at the temple?")
    user_msg = captured["user"]
    assert "Extra grounded context" in user_msg
    assert "Annamalaiyar" in user_msg  # retrieved fact text made it in
    assert user_msg.endswith("Question: which god is at the temple?")


def test_answer_passes_raw_question_when_nothing_retrieved(monkeypatch):
    """Off-topic-for-KB question → no retrieval → user message unchanged."""
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return "I can only help with the temple, crowd status, ticket queues, and your visit planning. Ask me about those!"

    monkeypatch.setattr(llm, "chat_text", _capture)
    temple_qa.answer("cricket world cup?")
    # No retrieval → raw question, no wrapper.
    assert captured["user"] == "cricket world cup?"


def test_answer_logs_all_metrics_when_retrieval_hit(monkeypatch, caplog):
    """After answering, we log utilization + relevancy + faithfulness."""
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        llm, "chat_text",
        lambda **_: (
            "The primary deity is Lord Shiva, worshipped here as Annamalaiyar."
        ),
    )
    caplog.set_level("INFO", logger="app.services.temple_qa")
    result = temple_qa.answer("which god is at the temple?")
    assert result and "Annamalaiyar" in result
    combined = [
        r for r in caplog.records
        if "utilization=" in r.message
        and "relevancy=" in r.message
        and "faithfulness=" in r.message
    ]
    assert combined, "expected combined utilization+relevancy+faithfulness log"


def test_answer_short_circuits_metrics_for_redirect(monkeypatch, caplog):
    """The fixed off-topic redirect line is not a hallucination — logging
    faithfulness=0.0 would be misleading. We log a distinct 'redirected'
    line instead and skip the metric computation.
    """
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        llm, "chat_text", lambda **_: temple_qa.REDIRECT_REPLY,
    )
    caplog.set_level("INFO", logger="app.services.temple_qa")
    temple_qa.answer("cricket world cup?")
    metric_lines = [
        r for r in caplog.records
        if "relevancy=" in r.message or "faithfulness=" in r.message
    ]
    redirected_lines = [
        r for r in caplog.records if "redirected off-topic" in r.message
    ]
    assert not metric_lines, "REDIRECT_REPLY must not trigger metric logging"
    assert redirected_lines, "expected a 'redirected off-topic' log line"


def test_answer_short_circuits_metrics_for_honest_dont_know(
    monkeypatch, caplog,
):
    """The 'I don't have a confident answer' fallback also skips metrics —
    it's an intentional short reply, not a substantive claim to evaluate.
    """
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        llm, "chat_text",
        lambda **_: (
            "I don't have a confident answer for that — please ask a temple guide."
        ),
    )
    caplog.set_level("INFO", logger="app.services.temple_qa")
    temple_qa.answer("what year did the mandapam get repaired?")
    metric_lines = [
        r for r in caplog.records
        if "relevancy=" in r.message or "faithfulness=" in r.message
    ]
    honest_lines = [
        r for r in caplog.records if "no confident answer" in r.message
    ]
    assert not metric_lines
    assert honest_lines


def test_answer_forwards_history_to_llm(monkeypatch):
    """Follow-up questions rely on the QA service passing prior turns through."""
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return "The main deity is Lord Shiva."

    monkeypatch.setattr(llm, "chat_text", _capture)
    history = [
        {"role": "user", "content": "who is the main god?"},
        {"role": "assistant", "content": "Lord Shiva as Annamalaiyar."},
    ]
    temple_qa.answer("tell me more", history=history)
    assert captured["history"] == history
