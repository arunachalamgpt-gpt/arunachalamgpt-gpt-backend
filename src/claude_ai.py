import anthropic
from src.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

async def get_reply(
    system_prompt: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    max_tokens: int = 500
) -> str:
    """Call Claude API and return reply text."""
    messages = conversation_history or []
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages
    )
    return response.content[0].text

LANGUAGE_RULE = """
CRITICAL LANGUAGE RULE:
Detect the language of the user message and reply in EXACTLY that language.
Tamil script or romanized Tamil → reply in Tamil
Telugu → reply in Telugu
Kannada → reply in Kannada
Hindi → reply in Hindi
English → reply in English
Keep responses warm, brief, and practical.
"""