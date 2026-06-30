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

from app.services import llm

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


def answer(question: str) -> Optional[str]:
    """Return a temple-flavoured answer to the user's question.

    Returns `None` when the LLM is unavailable so the caller can fall back to
    generic help text. Never raises.
    """
    if not llm.is_enabled():
        return None
    try:
        text = llm.chat_text(system=SYSTEM_PROMPT, user=question, temperature=0.0)
    except llm.LLMUnavailableError as exc:
        logger.info("Temple Q&A skipped — LLM unavailable: %s", exc)
        return None
    return text or None
