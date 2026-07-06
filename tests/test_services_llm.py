"""Tests for the OpenAI client wrapper.

The real client is never called — we monkeypatch `_get_client` and the env
flags to drive every branch (enabled/disabled, JSON success, JSON parse error,
generic API error, plain-text success, plain-text error).
"""

import json

import pytest

from app.services import llm


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, *, content=None, raise_with=None):
        self._content = content
        self._raise_with = raise_with
        self.chat = type("C", (), {"completions": self})

    def create(self, **kwargs):
        if self._raise_with is not None:
            raise self._raise_with
        return _FakeResponse(self._content)


def _force_enabled(monkeypatch):
    import app.services.llm as mod

    monkeypatch.setattr(mod, "OPENAI_ENABLED", True)
    monkeypatch.setattr(mod, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod, "OPENAI_MODEL", "gpt-4o-mini")
    mod.reset_client_for_tests()


def test_is_enabled_default_false():
    assert llm.is_enabled() is False


def test_chat_json_raises_when_disabled():
    with pytest.raises(llm.LLMUnavailableError):
        llm.chat_json(system="s", user="u")


def test_chat_text_raises_when_disabled():
    with pytest.raises(llm.LLMUnavailableError):
        llm.chat_text(system="s", user="u")


def test_chat_json_happy_path(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(content=json.dumps({"intent": "ask_crowd", "slots": {}}))
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    out = llm.chat_json(system="s", user="u")
    assert out["intent"] == "ask_crowd"


def test_chat_json_returns_empty_when_content_missing(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(content=None)
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    out = llm.chat_json(system="s", user="u")
    assert out == {}


def test_chat_json_invalid_json_raises_llm_unavailable(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(content="not json")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    with pytest.raises(llm.LLMUnavailableError):
        llm.chat_json(system="s", user="u")


def test_chat_json_propagates_api_error_as_llm_unavailable(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(raise_with=RuntimeError("boom"))
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    with pytest.raises(llm.LLMUnavailableError):
        llm.chat_json(system="s", user="u")


def test_chat_text_happy_path(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(content="  hello there  ")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    assert llm.chat_text(system="s", user="u") == "hello there"


def test_chat_text_empty_content(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(content=None)
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    assert llm.chat_text(system="s", user="u") == ""


def test_chat_text_api_error_raises_llm_unavailable(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _FakeClient(raise_with=RuntimeError("timeout"))
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    with pytest.raises(llm.LLMUnavailableError):
        llm.chat_text(system="s", user="u")


def test_get_client_caches_after_first_call(monkeypatch):
    _force_enabled(monkeypatch)
    first = llm._get_client()
    second = llm._get_client()
    assert first is second
    llm.reset_client_for_tests()
    third = llm._get_client()
    assert third is not first
    llm.reset_client_for_tests()


# ---------- history splice ----------


class _CapturingClient:
    """Records the `messages` list sent to OpenAI so tests can assert order."""
    def __init__(self, content):
        self._content = content
        self.chat = type("C", (), {"completions": self})
        self.calls: list[list[dict]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs["messages"])
        return _FakeResponse(self._content)


def test_chat_json_threads_history_between_system_and_user(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _CapturingClient(content=json.dumps({"intent": "unknown", "slots": {}}))
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    history = [
        {"role": "user", "content": "old q"},
        {"role": "assistant", "content": "old a"},
    ]
    llm.chat_json(system="SYS", user="now", history=history)
    msgs = fake.calls[0]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1:3] == history
    assert msgs[-1] == {"role": "user", "content": "now"}


def test_chat_text_history_optional(monkeypatch):
    """Omitting `history` should keep the old two-message shape (system+user)."""
    _force_enabled(monkeypatch)
    fake = _CapturingClient(content="ok")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    llm.chat_text(system="S", user="U")
    assert fake.calls[0] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]


def test_chat_text_threads_history(monkeypatch):
    _force_enabled(monkeypatch)
    fake = _CapturingClient(content="ok")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    history = [{"role": "user", "content": "prev"}]
    llm.chat_text(system="S", user="U", history=history)
    assert fake.calls[0] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "prev"},
        {"role": "user", "content": "U"},
    ]
