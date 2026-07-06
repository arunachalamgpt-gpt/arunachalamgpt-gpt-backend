"""Offline evaluation for the KB retriever.

Context recall = |retrieved ∩ needed| / |needed|

We compare the retriever's top-K output against a hand-curated ground-truth
set: for each eval question, which KB fact IDs would a correct answer *need*
to see. A run reports per-question recall + a mean across the set. The
regression test in `tests/test_services_qa_eval.py` fails the CI build if
mean recall drops below the baseline — so a bad edit to the KB, retriever,
or an added fact without matching keywords is caught immediately.

This module has no LLM dependency. It measures retrieval quality only.
"""

import re
from dataclasses import dataclass
from typing import Optional, TypedDict

from app.services import retriever
from app.services.temple_kb import KBEntry


class EvalCase(TypedDict, total=False):
    question: str
    needed: list[str]  # KB ids that the answer requires
    # Optional reference answer. When present, utilization is computed against
    # it during `run_eval`. Real production traffic can compute utilization
    # against live LLM answers via `compute_context_utilization` directly.
    expected_answer: str


# Hand-curated. Each `needed` set is the minimum fact(s) the answer must
# lean on. Add cases when the KB grows or when you spot a real production
# question the retriever missed.
EVAL_SET: list[EvalCase] = [
    {
        "question": "which god is at the temple?",
        "needed": ["annamalaiyar_deity"],
        "expected_answer": (
            "The primary deity is Lord Shiva, worshipped here as Annamalaiyar "
            "(also called Arunachaleswarar)."
        ),
    },
    {"question": "who is the main deity?", "needed": ["annamalaiyar_deity"]},
    {
        "question": "tell me about the goddess",
        "needed": ["unnamulai_goddess"],
        "expected_answer": (
            "The consort goddess is Unnamulai Amman, a form of Parvati."
        ),
    },
    {
        "question": "when is Karthigai Deepam?",
        "needed": ["karthigai_deepam"],
        "expected_answer": (
            "Karthigai Deepam is held in November or December. A great flame "
            "is lit atop Arunachala hill."
        ),
    },
    {"question": "what festival happens in December?", "needed": ["karthigai_deepam"]},
    {"question": "how big is the Raja gopuram?", "needed": ["gopurams"]},
    {"question": "how many gopurams are there?", "needed": ["gopurams"]},
    {
        "question": "what is Girivalam?",
        "needed": ["girivalam_pournami"],
        "expected_answer": (
            "Girivalam is a 14 km barefoot circumambulation of Arunachala "
            "hill done on Pournami days."
        ),
    },
    {"question": "when does the temple open?", "needed": ["opening_time"]},
    {
        "question": "how far is Chennai from the temple?",
        "needed": ["location"],
        "expected_answer": (
            "Tiruvannamalai is about 185 km from Chennai."
        ),
    },
    {"question": "where is Tiruvannamalai?", "needed": ["location"]},
    {"question": "how old is the temple?", "needed": ["history_chola"]},
    {"question": "who built it?", "needed": ["history_chola"]},
    {
        "question": "who is Ramana Maharshi?",
        "needed": ["ramana_maharshi"],
        "expected_answer": (
            "Ramana Maharshi was a saint who lived on Arunachala hill. "
            "Sri Ramanasramam ashram is nearby."
        ),
    },
    {"question": "where is the bus stand?", "needed": ["bus_stand"]},
    {"question": "tell me about the hill", "needed": ["arunachala_hill"]},
    {
        "question": "who is the god and who is the goddess?",
        "needed": ["annamalaiyar_deity", "unnamulai_goddess"],
        "expected_answer": (
            "The deity is Lord Shiva as Annamalaiyar. The goddess is "
            "Unnamulai Amman, a form of Parvati."
        ),
    },
]


@dataclass
class CaseResult:
    question: str
    needed: list[str]
    retrieved: list[str]
    # Recall = |retrieved ∩ needed| / |needed|
    recall: float
    # Precision@k = |retrieved ∩ needed| / k  — strict; penalises padding.
    precision_at_k: float
    # R-Precision = |top-|needed| ∩ needed| / |needed| — rewards ranking
    # the required facts into the very top positions.
    r_precision: float
    # Reciprocal rank of the FIRST needed hit — 1.0 = top slot, 0 if never.
    reciprocal_rank: float
    # None when the case has no `expected_answer` fixture.
    utilization: Optional[float]
    answer_relevancy: Optional[float]
    faithfulness: Optional[float]


@dataclass
class EvalReport:
    k: int
    n: int
    mean_recall: float
    mean_precision_at_k: float
    mean_r_precision: float
    mean_reciprocal_rank: float
    # All three means below are computed only over cases that supplied an
    # `expected_answer`. None when no such case exists in `EVAL_SET`.
    mean_utilization: Optional[float]
    mean_answer_relevancy: Optional[float]
    mean_faithfulness: Optional[float]
    utilization_n: int
    cases: list[CaseResult]


def compute_context_recall(
    retrieved_ids: list[str], needed_ids: list[str]
) -> float:
    """Fraction of `needed_ids` that appear in `retrieved_ids`.

    Convention: if nothing was needed, recall is 1.0 (nothing to miss).
    """
    if not needed_ids:
        return 1.0
    retrieved_set = set(retrieved_ids)
    hits = sum(1 for nid in needed_ids if nid in retrieved_set)
    return hits / len(needed_ids)


def compute_context_precision(
    retrieved_ids: list[str], needed_ids: list[str], *, k: int
) -> float:
    """Fraction of the top-`k` retrievals that are relevant (in `needed_ids`).

    Uses `k` (not `len(retrieved_ids)`) as the denominator so under-filled
    top-K is punished the same as top-K padded with irrelevant chunks. An
    empty needed set yields 1.0 by convention (nothing to be wrong about).
    """
    if not needed_ids:
        return 1.0
    if k <= 0:
        return 0.0
    needed_set = set(needed_ids)
    top = retrieved_ids[:k]
    hits = sum(1 for rid in top if rid in needed_set)
    return hits / k


def compute_r_precision(
    retrieved_ids: list[str], needed_ids: list[str]
) -> float:
    """Precision on the top-|needed| retrievals.

    R-Precision (Buckley & Voorhees) rewards rankers that surface the
    required facts into the very top positions, independent of `k`.
    """
    if not needed_ids:
        return 1.0
    r = len(needed_ids)
    needed_set = set(needed_ids)
    top = retrieved_ids[:r]
    hits = sum(1 for rid in top if rid in needed_set)
    return hits / r


def compute_reciprocal_rank(
    retrieved_ids: list[str], needed_ids: list[str]
) -> float:
    """1 / rank of the first needed chunk in `retrieved_ids`. Zero if none.

    Standard MRR component. Averaged across the eval set this is the classic
    Mean Reciprocal Rank metric.
    """
    if not needed_ids:
        return 1.0
    needed_set = set(needed_ids)
    for idx, rid in enumerate(retrieved_ids, start=1):
        if rid in needed_set:
            return 1.0 / idx
    return 0.0


# ---------- context utilization ----------

# Common English stopwords + boilerplate tokens that always appear in KB
# entries. Excluded from utilization overlap so we measure content, not glue.
_STOPWORDS: frozenset[str] = frozenset({
    # Articles, conjunctions, common auxiliaries.
    "the", "and", "for", "with", "from", "into", "onto", "than", "then",
    "that", "this", "these", "those", "them", "there", "here", "also",
    "have", "has", "had", "was", "were", "are", "been", "being", "will",
    "would", "should", "could", "can", "may", "might", "shall", "must",
    "not", "but",
    # Question words — questions like "which god" should not have "which"
    # inflate topic overlap.
    "which", "when", "where", "who", "whom", "whose", "how", "why", "what",
    # Determiners + quantifiers.
    "some", "any", "all", "each", "every", "one", "two", "three", "four",
    "five",
    # Personal pronouns.
    "his", "her", "our", "their", "its", "your", "you",
})

_TOKEN_RE = re.compile(r"[a-z]+")


def _content_tokens(text: str, *, min_len: int = 3) -> set[str]:
    """Lowercase ASCII words, dropping stopwords and very short tokens.

    Same regex as `retriever._tokenize` but with additional filters (length
    and stopwords) so glue words don't inflate overlap metrics.
    """
    return {
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) >= min_len and t not in _STOPWORDS
    }


@dataclass
class ChunkUsage:
    """Per-chunk breakdown of how much the answer echoed the chunk's content."""
    id: str
    overlap_tokens: int
    chunk_content_tokens: int
    used: bool


def context_utilization_detail(
    answer: str,
    retrieved: list[KBEntry],
    *,
    min_tokens: int = 2,
) -> list[ChunkUsage]:
    """Per-chunk usage detail for observability / debugging.

    A chunk counts as "used" when its text shares at least `min_tokens`
    content tokens with the answer. Two is a deliberate low bar — a concise
    answer that mentions the deity name plus one adjective still qualifies.
    """
    answer_tokens = _content_tokens(answer)
    detail: list[ChunkUsage] = []
    for entry in retrieved:
        chunk_tokens = _content_tokens(entry["text"])
        overlap = len(answer_tokens & chunk_tokens)
        detail.append(
            ChunkUsage(
                id=entry["id"],
                overlap_tokens=overlap,
                chunk_content_tokens=len(chunk_tokens),
                used=(overlap >= min_tokens),
            )
        )
    return detail


def compute_context_utilization(
    answer: str,
    retrieved: list[KBEntry],
    *,
    min_tokens: int = 2,
) -> float:
    """Fraction of retrieved chunks whose content shows up in the answer.

    High = the model leveraged what we gave it. Low = the model either
    already knew the answer or ignored the retrieved context — in either
    case retrieval was wasted effort (worth flagging).

    Empty `retrieved` returns 1.0 by convention (nothing to under-utilize).
    """
    if not retrieved:
        return 1.0
    detail = context_utilization_detail(
        answer, retrieved, min_tokens=min_tokens
    )
    used = sum(1 for d in detail if d.used)
    return used / len(retrieved)


# ---------- answer relevancy ----------


def compute_answer_relevancy(
    question: str,
    answer: str,
    retrieved: Optional[list[KBEntry]] = None,
) -> float:
    """How well `answer` addresses `question`.

    Definition (retrieval-aware lexical focus):

    - Build a *topic set* from question content tokens plus, when provided,
      the content tokens of every retrieved KB chunk. Retrieved chunks bring
      in synonyms — so an answer of "Lord Shiva as Annamalaiyar" for the
      question "which god?" still scores highly because the retrieved deity
      chunk contributes "shiva", "annamalaiyar" to the topic set.
    - Score = fraction of the answer's content tokens that lie in the topic
      set. High = focused response. Low = the answer wandered off-topic.

    Guards:
    - Empty answer → 0.0 (nothing was said).
    - Vacuous question and vacuous retrieval (no topic tokens) → 1.0.
    - Non-committal answer (redirect / "I don't know" / echo) is not
      special-cased here — those are filtered upstream by
      `temple_qa._looks_like_valid_answer`. If one slips through this metric
      correctly scores it low.
    """
    if not answer.strip():
        return 0.0
    answer_tokens = _content_tokens(answer)
    if not answer_tokens:
        return 0.0

    topic = _content_tokens(question)
    if retrieved:
        for chunk in retrieved:
            topic |= _content_tokens(chunk["text"])

    if not topic:
        return 1.0

    on_topic = sum(1 for t in answer_tokens if t in topic)
    return on_topic / len(answer_tokens)


# ---------- faithfulness ----------

# Split on end-of-sentence punctuation. Good enough for the short 1-4 sentence
# WhatsApp answers our QA layer produces; a document-scale system would want
# a proper sentence splitter.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+\s*")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


@dataclass
class SentenceGrounding:
    """Per-sentence support detail — matches the shape of `ChunkUsage`."""
    text: str
    content_tokens: int
    supported_tokens: int
    grounded: bool


def _build_support_pool(
    retrieved: Optional[list[KBEntry]], question: Optional[str],
) -> set[str]:
    """Union of KB-chunk content and question content — the "known good"
    token pool that a faithful answer sentence should draw from."""
    pool: set[str] = set()
    if retrieved:
        for chunk in retrieved:
            pool |= _content_tokens(chunk["text"])
    if question:
        pool |= _content_tokens(question)
    return pool


def faithfulness_detail(
    answer: str,
    retrieved: Optional[list[KBEntry]],
    *,
    question: Optional[str] = None,
    support_threshold: float = 0.5,
) -> list[SentenceGrounding]:
    """Per-sentence grounding breakdown for debugging unfaithful answers."""
    support_pool = _build_support_pool(retrieved, question)
    detail: list[SentenceGrounding] = []
    for sentence in _split_sentences(answer):
        s_tokens = _content_tokens(sentence)
        if not s_tokens:
            # Stopwords-only sentence — no measurable claim, skip in scoring.
            continue
        supported = len(s_tokens & support_pool)
        ratio = supported / len(s_tokens) if s_tokens else 0.0
        detail.append(
            SentenceGrounding(
                text=sentence,
                content_tokens=len(s_tokens),
                supported_tokens=supported,
                grounded=(ratio >= support_threshold),
            )
        )
    return detail


def compute_faithfulness(
    answer: str,
    retrieved: Optional[list[KBEntry]],
    *,
    question: Optional[str] = None,
    support_threshold: float = 0.5,
) -> float:
    """Fraction of answer sentences whose content tokens are grounded in
    the retrieved KB chunks (plus the question).

    Ragas-style faithfulness in a rule-based form. A sentence is "grounded"
    when at least `support_threshold` of its content tokens are found in
    the support pool. A sentence that introduces new named entities /
    numbers not present in the context is a hallucination candidate — it
    fails the threshold and drops the score.

    Empty answer → 1.0 by convention (there is nothing to hallucinate).
    No support pool → 1.0 (nothing to check against). Both cases show up
    as edge conditions in the eval report and are worth noticing.
    """
    if not answer.strip():
        return 1.0
    support_pool = _build_support_pool(retrieved, question)
    if not support_pool:
        return 1.0
    detail = faithfulness_detail(
        answer, retrieved,
        question=question,
        support_threshold=support_threshold,
    )
    if not detail:
        return 1.0
    grounded = sum(1 for d in detail if d.grounded)
    return grounded / len(detail)


def run_eval(*, k: int = 4) -> EvalReport:
    """Run the full eval set through the current retriever.

    `k` matches the top-K used at answer time — passing a different value
    lets you sweep the size vs. cost trade-off. Utilization is computed
    per-case when the `EvalCase` supplies an `expected_answer`, and averaged
    only over those cases.
    """
    cases: list[CaseResult] = []
    for entry in EVAL_SET:
        retrieved_entries = retriever.retrieve_top_k(entry["question"], k=k)
        retrieved_ids = [e["id"] for e in retrieved_entries]
        needed = list(entry["needed"])
        expected = entry.get("expected_answer")
        if expected:
            utilization = compute_context_utilization(expected, retrieved_entries)
            answer_relevancy = compute_answer_relevancy(
                entry["question"], expected, retrieved_entries,
            )
            faithfulness = compute_faithfulness(
                expected, retrieved_entries, question=entry["question"],
            )
        else:
            utilization = None
            answer_relevancy = None
            faithfulness = None
        cases.append(
            CaseResult(
                question=entry["question"],
                needed=needed,
                retrieved=retrieved_ids,
                recall=compute_context_recall(retrieved_ids, needed),
                precision_at_k=compute_context_precision(
                    retrieved_ids, needed, k=k
                ),
                r_precision=compute_r_precision(retrieved_ids, needed),
                reciprocal_rank=compute_reciprocal_rank(retrieved_ids, needed),
                utilization=utilization,
                answer_relevancy=answer_relevancy,
                faithfulness=faithfulness,
            )
        )
    n = len(cases) or 1  # avoid /0; empty EVAL_SET is caught by hygiene test.
    util_cases = [c for c in cases if c.utilization is not None]
    rel_cases = [c for c in cases if c.answer_relevancy is not None]
    faith_cases = [c for c in cases if c.faithfulness is not None]
    mean_util = (
        sum(c.utilization for c in util_cases) / len(util_cases)
        if util_cases else None
    )
    mean_rel = (
        sum(c.answer_relevancy for c in rel_cases) / len(rel_cases)
        if rel_cases else None
    )
    mean_faith = (
        sum(c.faithfulness for c in faith_cases) / len(faith_cases)
        if faith_cases else None
    )
    return EvalReport(
        k=k,
        n=len(cases),
        mean_recall=sum(c.recall for c in cases) / n,
        mean_precision_at_k=sum(c.precision_at_k for c in cases) / n,
        mean_r_precision=sum(c.r_precision for c in cases) / n,
        mean_reciprocal_rank=sum(c.reciprocal_rank for c in cases) / n,
        mean_utilization=mean_util,
        mean_answer_relevancy=mean_rel,
        mean_faithfulness=mean_faith,
        utilization_n=len(util_cases),
        cases=cases,
    )
