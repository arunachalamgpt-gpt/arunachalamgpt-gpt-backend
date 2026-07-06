"""Tests for the QA context-recall evaluation harness.

The final `test_regression_mean_recall` is a load-bearing check: if someone
edits the KB or the retriever and drops recall below the baseline, CI fails
here. The threshold sits below the current baseline (1.00) to leave room
for small regressions on individual questions without allowing quality
death by a thousand cuts.
"""

from app.services import qa_eval, retriever
from app.services.temple_kb import KB


# ---------- compute_context_recall ----------


def test_recall_empty_needed_is_one():
    assert qa_eval.compute_context_recall([], []) == 1.0
    assert qa_eval.compute_context_recall(["x"], []) == 1.0


def test_recall_perfect_hit():
    assert qa_eval.compute_context_recall(
        ["annamalaiyar_deity", "history_chola"],
        ["annamalaiyar_deity"],
    ) == 1.0


def test_recall_partial_hit():
    r = qa_eval.compute_context_recall(
        ["annamalaiyar_deity"],
        ["annamalaiyar_deity", "unnamulai_goddess"],
    )
    assert r == 0.5


def test_recall_zero_when_missed():
    assert qa_eval.compute_context_recall(
        ["history_chola"], ["annamalaiyar_deity"]
    ) == 0.0


def test_recall_ignores_extra_retrievals():
    """Extra retrieved chunks don't hurt recall (they hurt precision)."""
    r = qa_eval.compute_context_recall(
        ["annamalaiyar_deity", "history_chola", "opening_time"],
        ["annamalaiyar_deity"],
    )
    assert r == 1.0


# ---------- compute_context_precision (precision@k) ----------


def test_precision_at_k_perfect_hit():
    """1 needed, 1 in top-k of size 4 → 1/4 precision."""
    assert qa_eval.compute_context_precision(
        ["annamalaiyar_deity", "x", "y", "z"],
        ["annamalaiyar_deity"],
        k=4,
    ) == 0.25


def test_precision_at_k_zero_when_none_relevant():
    assert qa_eval.compute_context_precision(
        ["x", "y"], ["annamalaiyar_deity"], k=4,
    ) == 0.0


def test_precision_at_k_ignores_below_k_positions():
    """Only the top-k are counted — position 5 doesn't help."""
    assert qa_eval.compute_context_precision(
        ["x", "y", "z", "w", "annamalaiyar_deity"],
        ["annamalaiyar_deity"],
        k=4,
    ) == 0.0


def test_precision_at_k_empty_needed_is_one():
    assert qa_eval.compute_context_precision(["x"], [], k=4) == 1.0


def test_precision_at_k_defensive_on_zero_k():
    assert qa_eval.compute_context_precision(["x"], ["y"], k=0) == 0.0


# ---------- compute_r_precision ----------


def test_r_precision_hit_at_top_1():
    assert qa_eval.compute_r_precision(
        ["annamalaiyar_deity", "x"], ["annamalaiyar_deity"]
    ) == 1.0


def test_r_precision_miss_at_top_1():
    """Needed=1 but not in top-1 — R-Precision is zero even if it's at #2."""
    assert qa_eval.compute_r_precision(
        ["x", "annamalaiyar_deity"], ["annamalaiyar_deity"]
    ) == 0.0


def test_r_precision_multi_needed_partial():
    """Needed=2, top-2 has 1 → 1/2."""
    r = qa_eval.compute_r_precision(
        ["annamalaiyar_deity", "history_chola"],
        ["annamalaiyar_deity", "unnamulai_goddess"],
    )
    assert r == 0.5


def test_r_precision_empty_needed_is_one():
    assert qa_eval.compute_r_precision(["x"], []) == 1.0


# ---------- compute_reciprocal_rank ----------


def test_mrr_first_position():
    assert qa_eval.compute_reciprocal_rank(
        ["annamalaiyar_deity", "x"], ["annamalaiyar_deity"]
    ) == 1.0


def test_mrr_second_position():
    assert qa_eval.compute_reciprocal_rank(
        ["x", "annamalaiyar_deity"], ["annamalaiyar_deity"]
    ) == 0.5


def test_mrr_zero_when_not_found():
    assert qa_eval.compute_reciprocal_rank(
        ["x", "y"], ["annamalaiyar_deity"]
    ) == 0.0


def test_mrr_takes_earliest_needed_hit():
    """When multiple needed present, MRR keys on the FIRST one encountered."""
    r = qa_eval.compute_reciprocal_rank(
        ["x", "unnamulai_goddess", "annamalaiyar_deity"],
        ["annamalaiyar_deity", "unnamulai_goddess"],
    )
    assert r == 0.5  # first needed at rank 2


def test_mrr_empty_needed_is_one():
    assert qa_eval.compute_reciprocal_rank(["x"], []) == 1.0


# ---------- context utilization ----------


def _kb(fact_id):
    from app.services import temple_kb
    return temple_kb.get(fact_id)


def test_stopwords_source_has_no_duplicates():
    """Read the qa_eval.py source and verify the _STOPWORDS literal has no
    duplicate entries — silently harmless (set dedups) but a code hygiene
    smell that hid twice."""
    import ast
    import inspect
    from collections import Counter
    from app.services import qa_eval as _qa

    source = inspect.getsource(_qa)
    tree = ast.parse(source)
    stopword_literals: list[str] = []
    for node in ast.walk(tree):
        # Find the `_STOPWORDS: frozenset[str] = frozenset({...})` assignment.
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_STOPWORDS"
            and isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Set)
        ):
            for elt in node.value.args[0].elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    stopword_literals.append(elt.value)
            break
    assert stopword_literals, "could not locate _STOPWORDS literal"
    dupes = [w for w, c in Counter(stopword_literals).items() if c > 1]
    assert not dupes, f"duplicate stopwords in source: {dupes}"


def test_content_tokens_drops_stopwords_and_short_words():
    tokens = qa_eval._content_tokens("The hill is on the east side of a big temple.")
    assert "the" not in tokens
    assert "on" not in tokens  # short + stopword-adjacent
    assert "hill" in tokens
    assert "temple" in tokens
    assert "east" in tokens


def test_utilization_empty_retrieved_is_one():
    assert qa_eval.compute_context_utilization("any answer", []) == 1.0


def test_utilization_full_when_answer_echoes_chunk():
    chunk = _kb("annamalaiyar_deity")
    answer = "The main deity here is Lord Shiva, worshipped as Annamalaiyar."
    assert qa_eval.compute_context_utilization(answer, [chunk]) == 1.0


def test_utilization_zero_when_answer_ignores_chunk():
    chunk = _kb("karthigai_deepam")
    answer = "I don't have a confident answer for that."
    assert qa_eval.compute_context_utilization(answer, [chunk]) == 0.0


def test_utilization_partial_across_multi_chunk_retrieval():
    """Two chunks retrieved, answer echoes only one → 0.5."""
    used_chunk = _kb("annamalaiyar_deity")
    unused_chunk = _kb("bus_stand")
    answer = "The deity is Shiva as Annamalaiyar in fire form."
    r = qa_eval.compute_context_utilization(answer, [used_chunk, unused_chunk])
    assert r == 0.5


def test_utilization_min_tokens_gate_is_configurable():
    chunk = _kb("annamalaiyar_deity")
    answer = "annamalaiyar"  # only 1 distinctive content token
    # Default min_tokens=2 → not counted as used
    assert qa_eval.compute_context_utilization(answer, [chunk]) == 0.0
    # Relaxed to 1 → counted
    assert qa_eval.compute_context_utilization(
        answer, [chunk], min_tokens=1,
    ) == 1.0


def test_utilization_detail_reports_per_chunk_overlap():
    entries = [_kb("annamalaiyar_deity"), _kb("bus_stand")]
    answer = "Shiva worshipped as Annamalaiyar."
    detail = qa_eval.context_utilization_detail(answer, entries)
    assert len(detail) == 2
    deity, bus = detail
    assert deity.id == "annamalaiyar_deity"
    assert deity.used is True
    assert deity.overlap_tokens >= 2
    assert bus.id == "bus_stand"
    assert bus.used is False


# ---------- utilization in the eval report ----------


def test_eval_case_carries_utilization_when_fixture_provided():
    report = qa_eval.run_eval(k=4)
    with_util = [c for c in report.cases if c.utilization is not None]
    assert len(with_util) == report.utilization_n
    assert report.utilization_n > 0, "expected some EVAL_SET cases to have expected_answer"
    for c in with_util:
        assert 0.0 <= c.utilization <= 1.0


def test_eval_case_utilization_is_none_when_no_fixture():
    """Cases without an `expected_answer` must have utilization=None."""
    report = qa_eval.run_eval(k=4)
    no_fixture_qs = {
        e["question"] for e in qa_eval.EVAL_SET if "expected_answer" not in e
    }
    for c in report.cases:
        if c.question in no_fixture_qs:
            assert c.utilization is None


UTILIZATION_FLOOR = 0.70


def test_regression_mean_utilization_above_floor():
    report = qa_eval.run_eval(k=4)
    assert report.mean_utilization is not None
    assert report.mean_utilization >= UTILIZATION_FLOOR, (
        f"Context utilization regressed: mean={report.mean_utilization:.3f} "
        f"< floor={UTILIZATION_FLOOR}. Per-case: "
        + ", ".join(
            f"{c.question!r}→{c.utilization:.2f}"
            for c in report.cases
            if c.utilization is not None and c.utilization < 1.0
        )
    )


# ---------- answer relevancy ----------


def test_answer_relevancy_empty_answer_is_zero():
    assert qa_eval.compute_answer_relevancy("which god?", "") == 0.0
    assert qa_eval.compute_answer_relevancy("which god?", "   ") == 0.0


def test_answer_relevancy_answer_only_stopwords_is_zero():
    """Answer with no content tokens (only stopwords) counts as unanswered."""
    r = qa_eval.compute_answer_relevancy("which god?", "the a is on")
    assert r == 0.0


def test_answer_relevancy_direct_topic_overlap_scores_above_zero():
    """Without retrieval, only the direct Q↔A overlap counts. Paraphrased
    detail ("eleven", "storeys") isn't in the question, so relevancy stays
    modest — but at least some of the answer must be on-topic to score."""
    r = qa_eval.compute_answer_relevancy(
        "how big is the Raja gopuram?",
        "The Raja gopuram is eleven storeys tall.",
    )
    assert r > 0.0


def test_answer_relevancy_off_topic_answer_scores_low():
    """Answer talks about something unrelated to the question."""
    r = qa_eval.compute_answer_relevancy(
        "which god is at the temple?",
        "The weather in Delhi is sunny today.",
    )
    assert r == 0.0


def test_answer_relevancy_retrieval_bridges_synonyms():
    """The answer uses "Shiva" / "Annamalaiyar" which aren't in the question,
    but the retrieved KB chunk brings those terms into the topic set."""
    from app.services import retriever
    chunks = retriever.retrieve_top_k("which god is at the temple?", k=2)
    r_with_retrieval = qa_eval.compute_answer_relevancy(
        "which god is at the temple?",
        "Lord Shiva as Annamalaiyar.",
        retrieved=chunks,
    )
    r_without = qa_eval.compute_answer_relevancy(
        "which god is at the temple?",
        "Lord Shiva as Annamalaiyar.",
    )
    assert r_with_retrieval > r_without
    assert r_with_retrieval >= 0.9


def test_answer_relevancy_vacuous_question_and_no_retrieval_is_one():
    """When there's no topic to be off-topic about, any real answer wins."""
    # Question with only stopwords / punctuation → no content tokens.
    assert qa_eval.compute_answer_relevancy("? .", "Some answer here") == 1.0


def test_answer_relevancy_partial_wandering_answer():
    """Half the answer is on-topic, half is unrelated."""
    r = qa_eval.compute_answer_relevancy(
        "when is Karthigai Deepam?",
        "Karthigai Deepam is in November. Also I like cricket.",
    )
    assert 0.3 < r < 0.9


# ---------- answer relevancy in run_eval ----------


def test_eval_case_carries_answer_relevancy_when_fixture_provided():
    report = qa_eval.run_eval(k=4)
    with_rel = [c for c in report.cases if c.answer_relevancy is not None]
    assert with_rel  # some fixtures exist
    assert report.mean_answer_relevancy is not None
    for c in with_rel:
        assert 0.0 <= c.answer_relevancy <= 1.0


def test_eval_case_answer_relevancy_is_none_when_no_fixture():
    report = qa_eval.run_eval(k=4)
    no_fixture_qs = {
        e["question"] for e in qa_eval.EVAL_SET if "expected_answer" not in e
    }
    for c in report.cases:
        if c.question in no_fixture_qs:
            assert c.answer_relevancy is None


ANSWER_RELEVANCY_FLOOR = 0.75


def test_regression_mean_answer_relevancy_above_floor():
    report = qa_eval.run_eval(k=4)
    assert report.mean_answer_relevancy is not None
    assert report.mean_answer_relevancy >= ANSWER_RELEVANCY_FLOOR, (
        f"Answer relevancy regressed: mean={report.mean_answer_relevancy:.3f} "
        f"< floor={ANSWER_RELEVANCY_FLOOR}. Per-case: "
        + ", ".join(
            f"{c.question!r}→{c.answer_relevancy:.2f}"
            for c in report.cases
            if c.answer_relevancy is not None and c.answer_relevancy < 1.0
        )
    )


# ---------- faithfulness ----------


def test_split_sentences_handles_common_punctuation():
    assert qa_eval._split_sentences("Hello. World! Right?") == [
        "Hello", "World", "Right",
    ]


def test_split_sentences_ignores_empty_fragments():
    assert qa_eval._split_sentences("...one!!!two??") == ["one", "two"]


def test_faithfulness_perfect_when_answer_only_uses_context():
    chunk = _kb("annamalaiyar_deity")
    answer = "The primary deity is Lord Shiva, worshipped as Annamalaiyar."
    assert qa_eval.compute_faithfulness(answer, [chunk]) == 1.0


def test_faithfulness_zero_when_answer_pure_hallucination():
    """Answer introduces content entirely absent from context and question."""
    chunk = _kb("annamalaiyar_deity")
    answer = "Cricket world cup happens every four years in different cities."
    assert qa_eval.compute_faithfulness(
        answer, [chunk], question="which god?",
    ) == 0.0


def test_faithfulness_partial_when_some_sentences_hallucinated():
    """One grounded + one invented sentence → 0.5."""
    chunk = _kb("karthigai_deepam")
    answer = (
        "Karthigai Deepam is held in November or December. "
        "It celebrates Lord Vishnu visiting Kailash on a chariot."
    )
    r = qa_eval.compute_faithfulness(
        answer, [chunk], question="when is Karthigai Deepam?",
    )
    assert r == 0.5


def test_faithfulness_empty_answer_is_one():
    assert qa_eval.compute_faithfulness("", [_kb("annamalaiyar_deity")]) == 1.0
    assert qa_eval.compute_faithfulness("   ", [_kb("annamalaiyar_deity")]) == 1.0


def test_faithfulness_no_support_pool_is_one():
    """With no retrieval and no question, we can't check anything → 1.0."""
    assert qa_eval.compute_faithfulness("anything at all", None) == 1.0


def test_faithfulness_question_alone_provides_support():
    """Restating the question is trivially faithful even without retrieval."""
    r = qa_eval.compute_faithfulness(
        "The gopuram is a gopuram.",
        None,
        question="how big is the gopuram?",
    )
    assert r == 1.0


def test_faithfulness_answer_has_only_stopword_sentences(monkeypatch):
    """Detail comes back empty when every sentence has zero content tokens
    (the sentences are all stopwords). We return 1.0 by convention — there
    were no measurable claims to score."""
    chunk = _kb("annamalaiyar_deity")
    # Every "sentence" is only stopwords → filtered out in detail
    answer = "The is. And a."
    r = qa_eval.compute_faithfulness(answer, [chunk])
    assert r == 1.0


def test_faithfulness_stopword_only_sentences_are_skipped():
    """A sentence with no content tokens shouldn't count as either grounded
    or hallucinated — it has no claim to score."""
    chunk = _kb("annamalaiyar_deity")
    # First sentence is stopwords-only, second is grounded → 1/1 = 1.0
    answer = "And it is. Shiva is the primary deity here as Annamalaiyar."
    r = qa_eval.compute_faithfulness(answer, [chunk])
    assert r == 1.0


def test_faithfulness_detail_flags_offending_sentence():
    chunk = _kb("karthigai_deepam")
    answer = (
        "Karthigai Deepam is in November. "
        "It commemorates the marriage of Vishnu and Lakshmi."
    )
    detail = qa_eval.faithfulness_detail(
        answer, [chunk], question="when?",
    )
    assert len(detail) == 2
    assert detail[0].grounded is True
    assert detail[1].grounded is False
    # The unfaithful sentence introduced tokens not in the pool.
    assert detail[1].supported_tokens < detail[1].content_tokens


def test_faithfulness_threshold_is_configurable():
    """A stricter threshold catches partial-support sentences we'd otherwise
    let through."""
    chunk = _kb("karthigai_deepam")
    # Half the content tokens overlap the chunk.
    answer = "Karthigai Deepam is a cricket match played in September."
    lenient = qa_eval.compute_faithfulness(
        answer, [chunk], support_threshold=0.3,
    )
    strict = qa_eval.compute_faithfulness(
        answer, [chunk], support_threshold=0.9,
    )
    assert lenient > strict


# ---------- faithfulness in run_eval ----------


def test_eval_case_carries_faithfulness_when_fixture_provided():
    report = qa_eval.run_eval(k=4)
    with_f = [c for c in report.cases if c.faithfulness is not None]
    assert with_f
    assert report.mean_faithfulness is not None
    for c in with_f:
        assert 0.0 <= c.faithfulness <= 1.0


def test_eval_case_faithfulness_is_none_when_no_fixture():
    report = qa_eval.run_eval(k=4)
    no_fixture_qs = {
        e["question"] for e in qa_eval.EVAL_SET if "expected_answer" not in e
    }
    for c in report.cases:
        if c.question in no_fixture_qs:
            assert c.faithfulness is None


# Expected answers are hand-written from KB text, so they should always be
# fully grounded. Any drop is a genuine unfaithfulness bug.
FAITHFULNESS_FLOOR = 0.90


def test_regression_mean_faithfulness_above_floor():
    report = qa_eval.run_eval(k=4)
    assert report.mean_faithfulness is not None
    assert report.mean_faithfulness >= FAITHFULNESS_FLOOR, (
        f"Faithfulness regressed: mean={report.mean_faithfulness:.3f} "
        f"< floor={FAITHFULNESS_FLOOR}. Per-case: "
        + ", ".join(
            f"{c.question!r}→{c.faithfulness:.2f}"
            for c in report.cases
            if c.faithfulness is not None and c.faithfulness < 1.0
        )
    )


# ---------- run_eval ----------


def test_run_eval_returns_report():
    report = qa_eval.run_eval(k=4)
    assert report.n == len(qa_eval.EVAL_SET)
    assert 0.0 <= report.mean_recall <= 1.0
    assert 0.0 <= report.mean_precision_at_k <= 1.0
    assert 0.0 <= report.mean_r_precision <= 1.0
    assert 0.0 <= report.mean_reciprocal_rank <= 1.0
    assert len(report.cases) == report.n
    for case in report.cases:
        assert 0.0 <= case.recall <= 1.0
        assert 0.0 <= case.precision_at_k <= 1.0
        assert 0.0 <= case.r_precision <= 1.0
        assert 0.0 <= case.reciprocal_rank <= 1.0
        assert isinstance(case.retrieved, list)


def test_eval_set_references_only_real_kb_ids():
    """Every `needed` id in EVAL_SET must resolve to a live KB entry, else
    the recall metric measures nothing meaningful."""
    valid_ids = {entry["id"] for entry in KB}
    for case in qa_eval.EVAL_SET:
        for nid in case["needed"]:
            assert nid in valid_ids, (
                f"EVAL_SET references missing KB id {nid!r} for "
                f"question {case['question']!r}"
            )


# ---------- KB hygiene ----------


def test_kb_ids_are_unique():
    ids = [entry["id"] for entry in KB]
    assert len(ids) == len(set(ids)), f"Duplicate KB ids: {ids}"


def test_kb_entries_are_well_formed():
    for entry in KB:
        assert entry["id"] and isinstance(entry["id"], str)
        assert entry["text"] and len(entry["text"]) >= 20
        assert entry["keywords"] and all(
            isinstance(k, str) and k == k.lower() for k in entry["keywords"]
        )
        assert entry["topic"]


# ---------- regression guard ----------


# All floors sit below the current baseline (all 1.00 as of shipping) with
# room for the odd edit to regress one case. Systemic regressions fail CI
# here — see `run_eval` for the definitions.
RECALL_FLOOR = 0.80
R_PRECISION_FLOOR = 0.80
MRR_FLOOR = 0.85


def _fail_msg(metric: str, value: float, floor: float, cases) -> str:
    below = ", ".join(
        f"{c.question!r}→{getattr(c, metric):.2f}"
        for c in cases if getattr(c, metric) < 1.0
    ) or "(all cases perfect but mean below floor — check math)"
    return f"{metric} regressed: mean={value:.3f} < floor={floor}. Below-perfect: {below}"


def test_regression_mean_recall_above_floor():
    r = qa_eval.run_eval(k=4)
    assert r.mean_recall >= RECALL_FLOOR, _fail_msg(
        "recall", r.mean_recall, RECALL_FLOOR, r.cases,
    )


def test_regression_mean_r_precision_above_floor():
    """R-Precision floor — the required fact must land in the very top slots."""
    r = qa_eval.run_eval(k=4)
    assert r.mean_r_precision >= R_PRECISION_FLOOR, _fail_msg(
        "r_precision", r.mean_r_precision, R_PRECISION_FLOOR, r.cases,
    )


def test_regression_mean_reciprocal_rank_above_floor():
    """MRR floor — the FIRST relevant hit must be near rank 1 on average."""
    r = qa_eval.run_eval(k=4)
    assert r.mean_reciprocal_rank >= MRR_FLOOR, _fail_msg(
        "reciprocal_rank", r.mean_reciprocal_rank, MRR_FLOOR, r.cases,
    )


def test_temple_kb_get_and_all_ids():
    assert set(__import__("app.services.temple_kb", fromlist=["all_ids"]).all_ids()) == \
        {entry["id"] for entry in KB}
    entry = __import__("app.services.temple_kb", fromlist=["get"]).get(
        "annamalaiyar_deity"
    )
    assert entry["id"] == "annamalaiyar_deity"


def test_temple_kb_get_missing_raises():
    import pytest
    from app.services import temple_kb
    with pytest.raises(KeyError):
        temple_kb.get("no_such_fact")
