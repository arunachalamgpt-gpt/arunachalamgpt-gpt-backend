# Feature 4 — Anti-Middlemen Darshan Guide
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md + Feature 1 (temple_config table)

---

## WHAT THIS FEATURE DOES

Tells devotees the truth about official darshan options
BEFORE they are approached by middlemen outside the temple.
Educates about Rs.50 and Rs.200 official tickets.

---

## USER STORIES

```
US-01: Devotee asks about darshan → gets complete guide.
US-02: Devotee says someone asked Rs.500 → gets warning.
US-03: Devotee already paid middleman → gets next steps.
US-04: Devotee asks how to complain → gets temple number.
```

---

## FILE TO CREATE

```
src/features/anti_middlemen.py
```

---

## COMPLETE CODE

```python
# src/features/anti_middlemen.py

"""
Feature 4: Anti-Middlemen Darshan Guide
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

ANTI_MIDDLEMEN_PROMPT = f"""
You are Arunachala GPT — darshan guide for
Arunachaleswara Temple, Tiruvannamalai.

OFFICIAL FACTS (always tell these clearly):
- East Gate has 3 OFFICIAL queues: Free, Rs.50, Rs.200
- ALL 3 queues start at the same place
- Ticket counter: 10 metres INSIDE East Gate
- Ticket sale starts: 8am daily
- Rs.50 ticket: shorter queue, official government counter
- Rs.200 ticket: even shorter, same official counter
- Nobody outside the gate has any official connection
- Anyone asking money outside the gate is a MIDDLEMAN

WHEN USER MENTIONS HIGH PRICE (Rs.500, Rs.1000):
Tell clearly: That is a middleman. Official max is Rs.200.
Give exact steps to get official ticket.

COMPLAINT NUMBER: 04175-252422 (temple trust office)

{LANGUAGE_RULE}
Be clear and direct. This protects devotees from fraud.
"""


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for darshan/middlemen queries."""
    text_upper = text.upper()
    config = await get_config()

    # Detect if already paid middleman
    already_paid = any(w in text_upper for w in
                       ["ALREADY PAID", "PAID OUTSIDE", "GAVE MONEY"])

    # Detect middleman amount mentioned
    high_amount = any(w in text_upper for w in
                      ["500", "1000", "800", "600"])

    extra_context = ""
    if already_paid:
        extra_context = "\nUSER ALREADY PAID MIDDLEMAN — be empathetic, give next steps."
    elif high_amount:
        extra_context = "\nUSER MENTIONED HIGH PRICE — clearly explain this is a middleman."

    system = ANTI_MIDDLEMEN_PROMPT + extra_context
    system += f"\n\nCURRENT PRICES: Rs.50 ticket, Rs.200 ticket, ticket counter opens {config.get('ticket_sale_start_time', '08:00')}"

    reply = await get_reply(
        system_prompt=system,
        user_message=text,
        max_tokens=300
    )

    buttons = ["Ticket counter location", "Complaint number", "Current crowd"]
    await send_buttons(phone=phone, body=reply, buttons=buttons)


async def get_config() -> dict:
    """Get temple config for current prices."""
    db = get_db()
    result = db.table("temple_config").select("key, value").execute()
    return {row["key"]: row["value"] for row in result.data}
```

---

## TEST CASES

```python
# tests/test_feature4.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.anti_middlemen import handle


class TestFeature4Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_darshan_query_returns_3_options(self):
        """User asking about darshan gets all 3 official options."""
        prompt_captured = []

        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "Free, Rs.50, Rs.200 are official options"

        with patch("src.features.anti_middlemen.get_config",
                   new_callable=AsyncMock, return_value={"ticket_sale_start_time": "08:00"}), \
             patch("src.features.anti_middlemen.get_reply", side_effect=capture), \
             patch("src.features.anti_middlemen.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "How to get darshan?", "english")
            assert "Rs.50" in prompt_captured[0] or "official" in prompt_captured[0].lower()

    @pytest.mark.asyncio
    async def test_AC02_high_price_triggers_middleman_warning(self):
        prompt_captured = []

        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "That is a middleman"

        with patch("src.features.anti_middlemen.get_config",
                   new_callable=AsyncMock, return_value={}), \
             patch("src.features.anti_middlemen.get_reply", side_effect=capture), \
             patch("src.features.anti_middlemen.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "Someone asked Rs.500 per person", "english")
            assert "MIDDLEMAN" in prompt_captured[0] or "middleman" in prompt_captured[0]

    @pytest.mark.asyncio
    async def test_AC03_already_paid_gets_empathetic_response(self):
        prompt_captured = []

        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "I understand. Go inside and complete darshan."

        with patch("src.features.anti_middlemen.get_config",
                   new_callable=AsyncMock, return_value={}), \
             patch("src.features.anti_middlemen.get_reply", side_effect=capture), \
             patch("src.features.anti_middlemen.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "I already paid Rs.1000 outside", "english")
            assert "ALREADY PAID" in prompt_captured[0] or "empathetic" in prompt_captured[0].lower()
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: Darshan query → 3 official options mentioned
[ ] AC-02: High price mentioned → middleman warning in prompt
[ ] AC-03: Already paid → empathetic + next steps
[ ] AC-04: Complaint number (04175-252422) in system prompt
[ ] AC-05: All tests pass: pytest tests/test_feature4.py -v
[ ] AC-06: Real test: "Someone asked Rs.500" → clear warning
```
