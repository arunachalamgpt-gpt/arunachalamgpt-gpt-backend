"""LLM intent classifier for the WhatsApp webhook.

Replaces the keyword-only path with a GPT-4o classifier that understands:
- Romanized Indic text ("crowd enna", "ticket eppadi vaanguradhu")
- Misspellings and code-mix
- Free-form questions ("what's the best time to come tomorrow")
- Numeric language picks ("1", "2", …)

Returns a typed `IntentResult`. On any failure (LLM disabled, network error,
unparseable JSON, schema mismatch) returns `intent="unknown"` so the caller
falls back to keyword matching — the bot never crashes because GPT-4o is
unreachable.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.services import llm

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "select_language",
    "register_visit",
    "ask_crowd",
    "ask_plan",
    "change_language",
    "general_question",
    "ask_smalltalk",
    "unknown",
}

VALID_LANGUAGES = {"tamil", "telugu", "kannada", "hindi", "english"}


@dataclass
class IntentResult:
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)


SYSTEM_PROMPT = """You are the intent classifier for ArunachalamGPT, a WhatsApp \
assistant for devotees visiting Arunachaleswarar Temple in Tiruvannamalai, \
India. Users write in Tamil, Telugu, Kannada, Hindi, English, or romanized \
mixes ("crowd enna", "ticket epdi"). Be tolerant of misspellings and code-mix.

Classify the user's most recent message and extract structured slots. Reply \
with ONLY a JSON object of the form:

  {"intent": "<intent>", "slots": { ... }}

Valid intents and slots:

- "select_language" — user picks from a numbered menu (1=Tamil, 2=Telugu, \
3=Kannada, 4=Hindi, 5=English). slots: {"language_code": "1"|"2"|"3"|"4"|"5"}.

- "register_visit" — user shares a visit date. slots: {"visit_date": \
"YYYY-MM-DD", "has_elderly": bool, "has_children": bool}. Infer elderly/\
children from words like "mother", "father", "parent", "amma", "appa", "kid", \
"child", "baby", "kuzhandhai". If the date is ambiguous, omit visit_date.

- "ask_crowd" — user asks about current crowd/queue/wait/line. slots: {}.

- "ask_plan" — user asks for advice on when to go, best time, what to bring. \
slots: {}.

- "change_language" — user asks to switch language. slots: {"target_language": \
"tamil"|"telugu"|"kannada"|"hindi"|"english"}.

- "general_question" — user asks a factual question about Arunachaleswarar \
Temple, Lord Shiva (Annamalaiyar), the goddess Unnamulai, the Arunachala \
hill, Girivalam, temple festivals (Karthigai Deepam, Pournami), temple \
history, location, opening times, how to reach. Also use for non-temple \
small questions the user wants help with — let the QA layer decline. \
slots: {"question": "<the user's question, cleaned up to standard English>"}.

- "ask_smalltalk" — greetings, thanks, well-being check, off-topic chit-chat, \
e.g. "how are you", "thanks", "good morning", "hello", "kya kar rahe ho", \
"nandri", "nice", "ok", "bye". slots: {}.

- "unknown" — none of the above. slots: {}.

# Follow-ups (IMPORTANT — use the conversation history)
Prior turns are provided as chat context. When the user's current message is a
short follow-up that only makes sense given the previous exchange, INHERIT the
last intent and update its slots. Do not reset to "unknown" or "ask_smalltalk"
just because the current message is short.

Follow-up rules:
- Affirmations ("yes", "yeah", "sari", "haan", "ok done") after the assistant
  asked a yes/no question: keep the previous intent; set the matching slot to
  true (e.g. has_elderly, has_children) if it clearly answers that question.
- Add-on info ("with kids", "just me", "and parents") after a planning turn:
  intent = "ask_plan"; set has_elderly / has_children accordingly.
- Refinements ("what about tomorrow?", "and in the evening?", "how about
  weekend?") after a crowd/plan turn: keep that intent (ask_crowd or ask_plan).
- Follow-up questions ("tell me more", "why?", "and the goddess?", "when is
  it?") after a general_question turn: intent = "general_question"; set
  `question` to the FULL question the user is asking now, resolving the
  pronoun/topic from the prior turn — e.g. previous topic "Karthigai Deepam"
  + user "when is it?" → question = "When is Karthigai Deepam?".
- If the previous intent was something else and the follow-up doesn't fit
  above, fall back to normal classification.

Output JSON only. No prose, no markdown."""


def classify(
    text: str, *, history: Optional[list[dict]] = None
) -> IntentResult:
    """Classify the user's message into one of `VALID_INTENTS`.

    Optional `history` is a list of prior OpenAI-format chat messages for this
    user; when provided, the LLM can resolve follow-ups like "yes" or "what
    about tomorrow" that only make sense in context of a previous turn.
    """
    if not llm.is_enabled():
        return IntentResult(intent="unknown")
    try:
        data = llm.chat_json(system=SYSTEM_PROMPT, user=text, history=history)
    except llm.LLMUnavailableError:
        return IntentResult(intent="unknown")

    intent = data.get("intent")
    if intent not in VALID_INTENTS:
        logger.info("LLM returned unknown intent %r, defaulting to 'unknown'", intent)
        return IntentResult(intent="unknown")

    raw_slots = data.get("slots") or {}
    if not isinstance(raw_slots, dict):
        raw_slots = {}

    clean_slots: dict[str, Any] = {}
    if intent == "select_language":
        code = str(raw_slots.get("language_code", "")).strip()
        if code in {"1", "2", "3", "4", "5"}:
            clean_slots["language_code"] = code
        else:
            return IntentResult(intent="unknown")
    elif intent == "register_visit":
        date_str = raw_slots.get("visit_date")
        if isinstance(date_str, str):
            try:
                date.fromisoformat(date_str)
                clean_slots["visit_date"] = date_str
            except ValueError:
                pass
        clean_slots["has_elderly"] = bool(raw_slots.get("has_elderly"))
        clean_slots["has_children"] = bool(raw_slots.get("has_children"))
    elif intent == "change_language":
        target = str(raw_slots.get("target_language", "")).strip().lower()
        if target in VALID_LANGUAGES:
            clean_slots["target_language"] = target
        else:
            return IntentResult(intent="unknown")
    elif intent == "general_question":
        question = raw_slots.get("question")
        if isinstance(question, str) and question.strip():
            clean_slots["question"] = question.strip()
        else:
            # No question slot → fall back: still treat as general question with
            # the raw text so downstream can ask the QA layer.
            clean_slots["question"] = text.strip()
    elif intent == "ask_plan":
        # Follow-ups like "with kids" / "just parents" — capture the family
        # composition so the planning service can factor it in.
        if raw_slots.get("has_elderly") is not None:
            clean_slots["has_elderly"] = bool(raw_slots.get("has_elderly"))
        if raw_slots.get("has_children") is not None:
            clean_slots["has_children"] = bool(raw_slots.get("has_children"))

    return IntentResult(intent=intent, slots=clean_slots)
