"""OpenAI GPT-4o client wrapper.

Lazy-instantiates a single `OpenAI` client. `is_enabled()` is the gate every
caller checks first — when false (default in dev/tests), the helpers raise
`LLMUnavailableError` instead of making a network call. Higher-level services
catch that and fall back to keyword logic or English text, so the bot still
works without an API key.

Costs are kept low by:
- defaulting to `gpt-4o-mini` (the cheaper SKU; override via `OPENAI_MODEL`)
- `temperature=0` for deterministic JSON output
- short timeout (`OPENAI_TIMEOUT_SECONDS`, default 8s) so a stalled call can't
  block a WhatsApp reply
"""

import json
import logging
from typing import Optional

from openai import OpenAI

from app.config import (
    OPENAI_API_KEY,
    OPENAI_ENABLED,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM is disabled, mis-configured, or call failed."""


_client: Optional[OpenAI] = None


def is_enabled() -> bool:
    """LLM is usable only when explicitly enabled AND key is present."""
    return OPENAI_ENABLED and bool(OPENAI_API_KEY)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)
    return _client


def reset_client_for_tests() -> None:
    """Test hook — drop the cached client so monkeypatched config takes effect."""
    global _client
    _client = None


def chat_json(*, system: str, user: str) -> dict:
    """Run a chat completion expecting a JSON object back. Returns parsed dict."""
    if not is_enabled():
        raise LLMUnavailableError("OpenAI is disabled or missing API key")
    try:
        response = _get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("OpenAI returned non-JSON: %s", exc)
        raise LLMUnavailableError(f"non-JSON response: {exc}") from exc
    except Exception as exc:  # network / auth / rate-limit / API errors
        logger.warning("OpenAI chat_json failed: %s", exc)
        raise LLMUnavailableError(str(exc)) from exc


def chat_text(*, system: str, user: str, temperature: float = 0.2) -> str:
    """Run a chat completion expecting plain text back.

    `temperature` defaults to 0.2 (light variety for translation), but
    factual callers (Q&A) should pass 0.0 to minimise hallucination.
    """
    if not is_enabled():
        raise LLMUnavailableError("OpenAI is disabled or missing API key")
    try:
        response = _get_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("OpenAI chat_text failed: %s", exc)
        raise LLMUnavailableError(str(exc)) from exc
