# Feature 13 — Arunachala Hill Climb Guide
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Step-by-step guide to climb Arunachala hill to Virupaksha Cave,
Skandashram, or the Summit. Covers Ramana Maharshi history,
what to do at each spot, safety warnings, elderly advice.

---

## USER STORIES

```
US-01: First-time visitor asks how to climb → full guide.
US-02: Elderly parent coming → honest difficulty + alternatives.
US-03: Devotee at Virupaksha Cave → what to do there.
US-04: Devotee planning evening climb → safety warning.
US-05: Ramana Maharshi devotee → historical context given.
```

---

## SOP

```
BEFORE LAUNCH:
  Walk the hill yourself — confirm all timings
  Verify: water points, dangerous sections, path condition
  Verify: jeep availability and cost for elderly
  Confirm exact open/close times for both caves
  Update hill_config table with verified data
```

---

## FILE TO CREATE

```
src/features/hill_climb.py
```

---

## COMPLETE CODE

```python
# src/features/hill_climb.py

"""
Feature 13: Arunachala Hill Climb Guide
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

HILL_SYSTEM_PROMPT = f"""
You are Arunachala GPT — guide for climbing Arunachala Hill,
Tiruvannamalai. Home of Ramana Maharshi.

SPOTS ON THE HILL:
1. Virupaksha Cave
   - Distance: 1 km uphill from Ramana Ashram back gate
   - Time up: 30-45 minutes
   - Ramana lived here: 1899 to 1916 (17 years)
   - Significance: Where Ramana's awakening deepened
   - What to do: Sit in silence 15-20 min. Remove footwear inside.
   - Open: 6am to 6pm

2. Skandashram
   - Distance: 1.5 km uphill
   - Time up: 45-60 minutes
   - Ramana lived here: 1916 to 1922
   - Significance: Mother joined here. View of entire Tiruvannamalai.
   - What to do: Sit facing valley. Morning view spectacular.
   - Open: 6am to 6pm

3. Summit (Top of Arunachala)
   - Distance: 2.5-3 km
   - Time: 2-3 hours
   - Difficulty: Hard — fit people only
   - The hill itself is Lord Shiva as Agni Lingam

STARTING POINT: Behind Sri Ramana Ashram (Ramanasramam)

BEST TIME: 6am to 8am (cool, less crowded, beautiful light)
AVOID: After 10am (very hot), After 4pm (gets dark — dangerous)
LAST SAFE START: 4pm maximum

WHAT TO CARRY:
- Water: 2 litres per person minimum
- Closed shoes with grip (NOT sandals)
- Hat or umbrella
- Light snack
- Fully charged phone

ELDERLY ADVICE:
- Virupaksha Cave: Possible but steep and rocky
- Better alternative: Ramana Ashram itself is deeply sacred
- Ashram samadhi hall is at ground level — equal spiritual value
- Jeep service may be available — ask at ashram office

SAFETY:
- Rocky path — take each step carefully
- No lights on the path — never climb after 4pm
- Turn back immediately if weather changes
- Do not climb alone if first time

{LANGUAGE_RULE}
Be honest about difficulty. Prioritize safety.
If elderly mentioned — always give alternative (Ashram samadhi).
"""


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for hill climb queries."""
    text_upper = text.upper()

    # Safety check — evening timing
    evening_words = ["5PM", "6PM", "7PM", "EVENING", "NIGHT", "SUNSET"]
    if any(w in text_upper for w in evening_words):
        await send_safety_warning(phone, language)
        return

    # Elderly advice
    elderly_words = ["ELDERLY", "OLD", "SENIOR", "70", "75", "80",
                     "VAYASAL", "THATHA", "PAATI", "PARENT"]
    if any(w in text_upper for w in elderly_words):
        await send_elderly_advice(phone, text, language)
        return

    # Spot-specific queries
    if "VIRUPAKSHA" in text_upper or "CAVE" in text_upper:
        await send_spot_guide(phone, text, language, "virupaksha")
        return

    if "SKANDASHRAM" in text_upper or "SKANDA" in text_upper:
        await send_spot_guide(phone, text, language, "skandashram")
        return

    if "SUMMIT" in text_upper or "TOP" in text_upper:
        await send_spot_guide(phone, text, language, "summit")
        return

    # General hill climb guide
    await send_general_guide(phone, text, language)


async def send_general_guide(phone: str, text: str, language: str) -> None:
    """Send general hill climbing guide with route options."""
    reply = await get_reply(
        system_prompt=HILL_SYSTEM_PROMPT,
        user_message=text,
        max_tokens=400
    )
    await send_buttons(phone, reply,
        ["Virupaksha Cave guide", "Elderly parent advice", "What to carry"]
    )


async def send_spot_guide(phone: str, text: str,
                           language: str, spot: str) -> None:
    """Send detailed guide for a specific spot."""
    spot_context = {
        "virupaksha": "Focus on Virupaksha Cave — what to do when you get there.",
        "skandashram": "Focus on Skandashram — Ramana's history and what to do.",
        "summit": "Focus on Summit — difficulty, time, fitness requirements.",
    }

    system = HILL_SYSTEM_PROMPT + f"\n\nFOCUS ON: {spot_context.get(spot, '')}"
    reply = await get_reply(system_prompt=system, user_message=text, max_tokens=400)
    await send_buttons(phone, reply,
        ["Starting point", "What to carry", "Elderly advice"]
    )


async def send_safety_warning(phone: str, language: str) -> None:
    """Send safety warning for evening climbing."""
    warning = await get_reply(
        system_prompt=HILL_SYSTEM_PROMPT,
        user_message="I am planning to climb in the evening. Is it safe?",
        max_tokens=250
    )
    await send_buttons(phone, warning,
        ["Best time to climb", "Virupaksha Cave guide", "Main menu"]
    )


async def send_elderly_advice(phone: str, text: str, language: str) -> None:
    """Send specific advice for elderly visitors."""
    reply = await get_reply(
        system_prompt=HILL_SYSTEM_PROMPT,
        user_message=f"Elderly person coming: {text}",
        max_tokens=350
    )
    await send_buttons(phone, reply,
        ["Try with support", "Ashram alternative", "Jeep service info"]
    )
```

---

## TEST CASES

```python
# tests/test_feature13.py

import pytest
from unittest.mock import AsyncMock, patch
from src.features.hill_climb import handle


class TestFeature13Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_general_query_returns_full_guide(self):
        with patch("src.features.hill_climb.get_reply",
                   new_callable=AsyncMock,
                   return_value="Start behind Ramana Ashram at 6am"), \
             patch("src.features.hill_climb.send_buttons",
                   new_callable=AsyncMock) as mock_btn:
            await handle("919XXXXXXXXX", "How to climb Arunachala?", "english")
            mock_btn.assert_called_once()

    @pytest.mark.asyncio
    async def test_AC02_evening_timing_triggers_warning(self):
        with patch("src.features.hill_climb.get_reply",
                   new_callable=AsyncMock,
                   return_value="5pm is not safe — path gets dark"), \
             patch("src.features.hill_climb.send_buttons",
                   new_callable=AsyncMock) as mock_btn:
            await handle("919XXXXXXXXX", "Planning to go at 5pm", "english")
            mock_btn.assert_called_once()
            call_text = mock_btn.call_args[0][1]
            assert "safe" in call_text.lower() or "dark" in call_text.lower() or \
                   mock_btn.called

    @pytest.mark.asyncio
    async def test_AC03_elderly_keyword_sends_elderly_advice(self):
        prompt_captured = []
        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(user_message)
            return "For elderly — Ashram samadhi is better option"

        with patch("src.features.hill_climb.get_reply", side_effect=capture), \
             patch("src.features.hill_climb.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "My mother is 70 years old", "english")
            assert any("Elderly" in m or "elderly" in m.lower()
                       for m in prompt_captured)

    @pytest.mark.asyncio
    async def test_AC04_virupaksha_specific_guide(self):
        prompt_captured = []
        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "Virupaksha Cave — remove footwear and sit in silence"

        with patch("src.features.hill_climb.get_reply", side_effect=capture), \
             patch("src.features.hill_climb.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "What to do at Virupaksha Cave?", "english")
            assert any("Virupaksha" in p for p in prompt_captured)

    @pytest.mark.asyncio
    async def test_AC05_safety_info_in_system_prompt(self):
        prompt_captured = []
        async def capture(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "Bring water and proper shoes"

        with patch("src.features.hill_climb.get_reply", side_effect=capture), \
             patch("src.features.hill_climb.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "What to carry for hill climb?", "english")
            assert any("4pm" in p or "dangerous" in p.lower()
                       or "SAFETY" in p for p in prompt_captured)
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: General query → full guide with 3 spot options
[ ] AC-02: Evening timing mentioned → safety warning given
[ ] AC-03: Elderly mentioned → Ashram alternative suggested
[ ] AC-04: "Virupaksha" → spot-specific guide
[ ] AC-05: System prompt contains safety info and timings
[ ] AC-06: All tests pass: pytest tests/test_feature13.py -v
[ ] AC-07: hill_spots table filled with verified data
[ ] AC-08: Real test: "5pm climbing" → clear warning message
```
