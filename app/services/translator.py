"""Translate outgoing replies into the devotee's chosen language.

Pass-through (English in, English out) when:
- `target_language` is `english` or missing
- the LLM is disabled
- the LLM call fails for any reason

Numbers, dates, currency tokens (Rs.50, Rs.200), and proper nouns
(Arunachaleswarar, Tiruvannamalai, the gate names) are preserved verbatim —
they're already meaningful to a devotee in any language.
"""

import logging
from typing import Optional

from app.services import llm

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "tamil": "Tamil",
    "telugu": "Telugu",
    "kannada": "Kannada",
    "hindi": "Hindi",
    "english": "English",
}


def _system_prompt(language_name: str) -> str:
    return (
        f"You are the localization layer for ArunachalamGPT. Render the given "
        f"English text in {language_name}, keeping a respectful, devotee-friendly "
        "tone suited to temple-going families. Preserve numbers, dates, currency "
        "tokens (Rs.50, Rs.200), times (5:30 AM), and proper nouns "
        "(Arunachaleswarar, Tiruvannamalai, East Gopuram). Use the chosen "
        f"language's native script; do not romanize. Output only the translated "
        "text — no quotes, no markdown, no commentary."
    )


def translate(text: str, target_language: Optional[str]) -> str:
    if not text:
        return text
    if not target_language or target_language == "english":
        return text
    if target_language not in LANGUAGE_NAMES:
        return text
    if not llm.is_enabled():
        return text
    try:
        return llm.chat_text(
            system=_system_prompt(LANGUAGE_NAMES[target_language]),
            user=text,
        )
    except llm.LLMUnavailableError as exc:
        logger.info("Translation skipped — LLM unavailable: %s", exc)
        return text
