"""Keyword-scored retrieval over `temple_kb.KB`.

Deterministic, fast, embedding-free. Scores each KB entry by the number of
question tokens that overlap its `keywords` list. Ties are broken by KB
order (stable). The KB is small enough (~15 entries) that a linear pass is
fine — swap in embeddings later if the KB grows past a few hundred entries.

The retriever's quality is measured by `qa_eval.run_eval` (context recall).
"""

import re
from typing import Optional

from app.services.temple_kb import KB, KBEntry

_TOKEN_RE = re.compile(r"[a-z]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase ASCII-letter tokens. Drops digits/punctuation/non-Latin.

    That's a deliberate simplification: the KB keywords are English-only, and
    romanized user queries ("kartigai deepam evena") still tokenise cleanly.
    """
    return set(_TOKEN_RE.findall(text.lower()))


def _score(question_tokens: set[str], entry: KBEntry) -> int:
    """Number of question tokens that appear in the entry's keyword set."""
    kw = set(entry["keywords"])
    return len(question_tokens & kw)


def retrieve_top_k(
    question: str, *, k: int = 4, min_score: int = 1
) -> list[KBEntry]:
    """Return up to `k` KB entries most relevant to `question`.

    Only entries with score >= `min_score` are returned — so an off-topic
    question produces an empty list rather than a spray of low-signal facts.
    """
    tokens = _tokenize(question)
    if not tokens:
        return []
    scored: list[tuple[int, int, KBEntry]] = []
    for idx, entry in enumerate(KB):
        s = _score(tokens, entry)
        if s >= min_score:
            scored.append((s, idx, entry))
    # Higher score first; stable KB order for ties.
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [entry for _, _, entry in scored[:k]]


def retrieve_ids(question: str, *, k: int = 4) -> list[str]:
    """Convenience: just the ids of the top-K retrieved entries."""
    return [entry["id"] for entry in retrieve_top_k(question, k=k)]


def format_for_prompt(entries: list[KBEntry]) -> Optional[str]:
    """Format entries as a bulleted context block for injection into a prompt.

    Returns None when there is nothing to inject so callers can branch cleanly.
    """
    if not entries:
        return None
    lines = [f"- {e['text']}" for e in entries]
    return "\n".join(lines)
