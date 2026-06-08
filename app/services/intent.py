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
from typing import Any

from app.services import llm

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "select_language",
    "register_visit",
    "ask_crowd",
    "ask_plan",
    "change_language",
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

- "unknown" — none of the above. slots: {}.

Output JSON only. No prose, no markdown."""


def classify(text: str) -> IntentResult:
    if not llm.is_enabled():
        return IntentResult(intent="unknown")
    try:
        data = llm.chat_json(system=SYSTEM_PROMPT, user=text)
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

    return IntentResult(intent=intent, slots=clean_slots)
