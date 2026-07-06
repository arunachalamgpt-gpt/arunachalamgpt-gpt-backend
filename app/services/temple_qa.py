"""GPT-4o-backed Q&A about Arunachaleswarar Temple and Tiruvannamalai.

Used by `intent.general_question` dispatch. Pass-through fallback when LLM is
disabled or fails — same safety pattern as `translator.py`.

Faithfulness rules (so the bot doesn't invent dates, miracles, or relics):
- The system prompt lists the *only* facts the model may rely on.
- Temperature is forced to 0 for maximum determinism.
- Off-domain or out-of-scope questions get a fixed redirect, not a guess.
"""

import logging
from typing import Optional

from app.services import llm, retriever
from app.services import qa_eval as qa_eval_svc

logger = logging.getLogger(__name__)

# The model has rich parametric knowledge of Tiruvannamalai; we still enumerate
# the grounded facts here so the prompt is the source of truth and the
# behavioural rules forbid invention. If asked something not covered, the model
# must say so explicitly rather than fabricate.
REDIRECT_REPLY = (
    "I can only help with the temple, crowd status, ticket queues, and your "
    "visit planning. Ask me about those!"
)

SYSTEM_PROMPT = f"""You are ArunachalamGPT, a WhatsApp assistant for devotees \
visiting Arunachaleswarar Temple in Tiruvannamalai, Tamil Nadu, India.

# Grounded facts (your ONLY knowledge base)
Deity (primary): Lord Shiva, worshipped here as Annamalaiyar / Arunachaleswarar.
The temple is the fire-element (Agni) manifestation among the Pancha Bhoota Stalas.
Goddess: Unnamulai Amman (Apita Kuchambal) — a form of Parvati.
Sacred hill: Arunachala, said to be a manifestation of Shiva himself.
Gopurams: four — Raja Gopuram (east, 11 storeys, ~66 m), plus north, west, south.
Festivals: Karthigai Deepam (Nov/Dec — the giant hilltop flame); Pournami \
Girivalam (the 14 km hill circumambulation done every full moon).
History: Chola-period core (9th century), expanded by Vijayanagara and Hoysala dynasties.
Location: Tiruvannamalai town; ~185 km from Chennai; ~210 km from Bengaluru.
Practical: temple opens 5:30 AM. Bus stand is ~2 km from the east gate.
Famous saints associated with the place: Ramana Maharshi (who lived on the hill), \
Seshadri Swamigal.

# Faithfulness rules (read carefully — these are mandatory)
1. Only state facts present in the "Grounded facts" section above or that are \
common, undisputed public knowledge about this specific temple. If unsure, \
say so honestly — never invent dates, names, miracles, or rituals.
2. If the question is about a non-temple topic (sports, politics, your health, \
ChatGPT itself, the weather, code, other temples in detail, etc.), reply with \
EXACTLY this line and nothing else:
   "{REDIRECT_REPLY}"
3. If the question is temple-related but the answer isn't in your grounded \
facts and isn't basic common knowledge, reply: "I don't have a confident \
answer for that — please ask a temple guide or the office on site."
4. Never recommend a specific date for a festival in a future year — direct \
the user to the temple office or a panchang instead.

# Style
- Plain text only. No markdown, no asterisks, no headers, no bullet symbols.
- Under 4 sentences. WhatsApp users prefer short.
- Respectful, devotional tone. Preserve Sanskrit/Tamil terms in common spelling.
"""


_MIN_ANSWER_CHARS = 20  # anything shorter can't substantively answer.


def _looks_like_valid_answer(text: str, *, question: str) -> bool:
    """Reject partial/degenerate LLM outputs that would confuse the user.

    Accepts the fixed off-topic redirect and the honest "don't have a confident
    answer" line — both are intentional short replies. Rejects: empty, too
    short, the model asking a clarifying question back, or the model simply
    echoing the user's question.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # The intentional short replies from the prompt are always valid.
    if stripped == REDIRECT_REPLY:
        return True
    if "don't have a confident answer" in stripped.lower():
        return True
    if len(stripped) < _MIN_ANSWER_CHARS:
        return False
    # Model asking a clarifying question back instead of answering.
    # A single trailing "?" on a long, informative answer is fine
    # ("Would you like directions?"); rejection targets short question-heavy
    # replies.
    q_marks = stripped.count("?")
    if q_marks >= 2 and len(stripped) < 200:
        return False
    if stripped.endswith("?") and len(stripped) < 80:
        return False
    # Model just echoed the user's question back (near-verbatim).
    if question and stripped.lower().rstrip("?.! ") == question.lower().rstrip("?.! "):
        return False
    return True


RETRIEVAL_TOP_K = 4


def _build_user_message(question: str, retrieved) -> str:
    """Prepend retrieved KB facts to the user's question when we found any.

    The LLM sees the facts as vetted "extra context", then the raw question.
    Retrieval failure is safe — the SYSTEM_PROMPT still enumerates the
    baseline grounded facts, and the faithfulness rules kick in.
    """
    ctx = retriever.format_for_prompt(retrieved)
    if not ctx:
        return question
    return (
        "Extra grounded context for this question (already vetted — prefer "
        "these facts over parametric knowledge if they overlap):\n"
        f"{ctx}\n\n"
        f"Question: {question}"
    )


def answer(
    question: str, *, history: Optional[list[dict]] = None
) -> Optional[str]:
    """Return a temple-flavoured answer to the user's question.

    Retrieval: top-K KB facts are pulled by `retriever.retrieve_top_k` and
    injected into the user message so the LLM has explicit grounding for the
    current question. Retrieved IDs are logged for observability — pair with
    `qa_eval.run_eval` to measure context recall offline.

    Optional `history` threads prior turns into the LLM context so follow-ups
    like "tell me more about that" or "when is it?" resolve to the topic just
    discussed. Returns `None` when the LLM is unavailable OR when the response
    fails partial-answer validation, so the caller can fall back to a helpful
    generic reply. Never raises.
    """
    if not llm.is_enabled():
        return None
    retrieved = retriever.retrieve_top_k(question, k=RETRIEVAL_TOP_K)
    if retrieved:
        logger.info(
            "Temple QA retrieved %d chunks for %r: %s",
            len(retrieved), question[:80],
            [entry["id"] for entry in retrieved],
        )
    try:
        text = llm.chat_text(
            system=SYSTEM_PROMPT,
            user=_build_user_message(question, retrieved),
            temperature=0.0,
            history=history,
        )
    except llm.LLMUnavailableError as exc:
        logger.info("Temple Q&A skipped — LLM unavailable: %s", exc)
        return None
    if not text:
        return None
    if not _looks_like_valid_answer(text, question=question):
        logger.info(
            "Temple QA rejected partial answer for %r: %r",
            question[:80], text[:120],
        )
        return None
    # Observability: log utilization + relevancy + faithfulness so we can
    # spot when the model ignored what we retrieved, wandered off-topic, or
    # invented facts. Two intentional short replies are exempted from the
    # metrics — they'd otherwise show faithfulness=0 / relevancy=0 by design
    # and drown out real signal.
    if text.strip() == REDIRECT_REPLY:
        logger.info("Temple QA redirected off-topic query %r", question[:80])
        return text
    if "don't have a confident answer" in text.lower():
        logger.info(
            "Temple QA emitted honest 'no confident answer' for %r",
            question[:80],
        )
        return text
    relevancy = qa_eval_svc.compute_answer_relevancy(
        question, text, retrieved or None
    )
    faithfulness = qa_eval_svc.compute_faithfulness(
        text, retrieved or None, question=question,
    )
    if retrieved:
        util = qa_eval_svc.compute_context_utilization(text, retrieved)
        logger.info(
            "Temple QA utilization=%.2f relevancy=%.2f faithfulness=%.2f "
            "for %r (retrieved=%s)",
            util, relevancy, faithfulness, question[:80],
            [entry["id"] for entry in retrieved],
        )
    else:
        logger.info(
            "Temple QA relevancy=%.2f faithfulness=%.2f for %r (no retrieval)",
            relevancy, faithfulness, question[:80],
        )
    return text
