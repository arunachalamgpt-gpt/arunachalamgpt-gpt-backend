"""Tests for the keyword-scored KB retriever."""

from app.services import retriever
from app.services.temple_kb import KB


def test_tokenize_lowercases_and_drops_punctuation():
    assert retriever._tokenize("Which GOD, and Which festival?!") == {
        "which", "god", "and", "festival",
    }


def test_tokenize_drops_digits_and_non_ascii():
    """Only lowercase ASCII letter runs are kept — deliberate simplification."""
    assert retriever._tokenize("14 km walk கோயில்") == {"km", "walk"}


def test_retrieve_top_k_returns_score_ordered_matches():
    hits = retriever.retrieve_top_k("who is the main god?", k=3)
    ids = [h["id"] for h in hits]
    assert ids[0] == "annamalaiyar_deity"


def test_retrieve_top_k_returns_empty_for_off_topic_query():
    """No KB keywords matched → empty list (better than low-signal spray)."""
    assert retriever.retrieve_top_k("cricket world cup score") == []


def test_retrieve_top_k_empty_string_returns_empty():
    assert retriever.retrieve_top_k("") == []


def test_retrieve_top_k_honours_k():
    hits = retriever.retrieve_top_k(
        "god goddess hill festival gopuram", k=2
    )
    assert len(hits) == 2


def test_retrieve_top_k_stable_order_for_ties():
    """Ties break by KB order so runs are deterministic across processes."""
    q = "temple"  # matches many entries with score=1
    first = retriever.retrieve_top_k(q, k=5)
    second = retriever.retrieve_top_k(q, k=5)
    assert [h["id"] for h in first] == [h["id"] for h in second]


def test_retrieve_ids_shortcut():
    ids = retriever.retrieve_ids("what is Girivalam?", k=2)
    assert ids[0] == "girivalam_pournami"


def test_format_for_prompt_none_on_empty():
    assert retriever.format_for_prompt([]) is None


def test_format_for_prompt_bullets_the_facts():
    entries = [KB[0], KB[1]]
    formatted = retriever.format_for_prompt(entries)
    assert formatted is not None
    assert formatted.count("\n- ") == 1  # 2 bullets → 1 internal newline
    assert formatted.startswith("- ")


def test_min_score_gate_filters_weak_matches():
    """Setting min_score high forces empty output on marginal overlap."""
    # "temple" matches many entries with score 1; require score 2+
    hits = retriever.retrieve_top_k("temple", k=5, min_score=2)
    assert hits == []
