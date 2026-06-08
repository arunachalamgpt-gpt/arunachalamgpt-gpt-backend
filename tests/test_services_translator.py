from app.services import llm
from app.services import translator


def test_translate_empty_pass_through():
    assert translator.translate("", "tamil") == ""


def test_translate_english_is_pass_through():
    assert translator.translate("hello", "english") == "hello"


def test_translate_none_language_is_pass_through():
    assert translator.translate("hello", None) == "hello"


def test_translate_unknown_language_is_pass_through():
    assert translator.translate("hello", "klingon") == "hello"


def test_translate_skipped_when_llm_disabled():
    assert translator.translate("hello", "tamil") == "hello"


def test_translate_falls_back_when_llm_raises(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)

    def _raise(**_):
        raise llm.LLMUnavailableError("network down")

    monkeypatch.setattr(llm, "chat_text", _raise)
    assert translator.translate("hello", "tamil") == "hello"


def test_translate_happy_path(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        llm,
        "chat_text",
        lambda **_: "வணக்கம்",
    )
    assert translator.translate("Welcome", "tamil") == "வணக்கம்"
