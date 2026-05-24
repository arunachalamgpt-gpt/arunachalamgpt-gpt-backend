# Feature 8 — Auto and Shop Fair Price Guide
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities + temple_config table

---

## WHAT THIS FEATURE DOES

Tells devotees exact fair prices for autos, prasadam items,
and shops near the temple BEFORE they get overcharged.
Free feature. Shops pay Rs.300/month to be listed as verified.

---

## USER STORIES

```
US-01: Devotee asks auto rate from bus stand → exact price.
US-02: Devotee asks Rudraksha price → fair price range.
US-03: Devotee asks about all puja item prices → full list.
US-04: Admin updates price when market rates change.
```

---

## FILE TO CREATE

```
src/features/fair_price.py
```

---

## COMPLETE CODE

```python
# src/features/fair_price.py

"""
Feature 8: Auto and Shop Fair Price Guide
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

PRICE_DATA = {
    "auto": {
        "bus_stand_to_temple": {"price": "Rs.80", "note": "Fixed rate"},
        "railway_station_to_temple": {"price": "Rs.100", "note": "Fixed rate"},
        "girivalam_drop_halfway": {"price": "Rs.120", "note": "Approximate"},
        "full_day_hire": {"price": "Rs.1,500 to Rs.2,000", "note": "Negotiate"},
        "walking_time_bus_stand": {"price": "15 minutes", "note": "On foot"},
    },
    "puja_items": {
        "rudraksha_mala_5_mukhi": {"price": "Rs.150 to Rs.300", "note": "Per mala"},
        "rudraksha_single_bead": {"price": "Rs.20 to Rs.50", "note": "Per bead"},
        "vibhuti_100gm": {"price": "Rs.30 to Rs.50", "note": "Packet"},
        "kumkum_packet": {"price": "Rs.10 to Rs.20", "note": "Small packet"},
        "camphor_karpuram": {"price": "Rs.20 to Rs.30", "note": "Packet"},
        "flower_garland_marigold": {"price": "Rs.30 to Rs.60", "note": "Per garland"},
        "coconut_for_offering": {"price": "Rs.30 to Rs.50", "note": "Per coconut"},
        "mineral_water_bottle": {"price": "Rs.20", "note": "MRP — do not pay more"},
    },
    "food": {
        "basic_meals_near_temple": {"price": "Rs.60 to Rs.100", "note": "Veg thali"},
        "coffee_or_tea": {"price": "Rs.10 to Rs.15", "note": "Per cup"},
        "snacks": {"price": "Rs.20 to Rs.50", "note": "Depends on item"},
    }
}

PRICE_SYSTEM_PROMPT = f"""
You are Arunachala GPT — fair price guide for Tiruvannamalai.

FAIR PRICES (verified on ground):
AUTO RATES:
  Bus stand to East Gate: Rs.80 fixed
  Railway station to temple: Rs.100
  Half Girivalam drop: Rs.120
  Full day hire: Rs.1,500 to Rs.2,000

PUJA ITEMS:
  Rudraksha mala (5 mukhi): Rs.150 to Rs.300
  Rudraksha single bead: Rs.20 to Rs.50
  Vibhuti (100gm): Rs.30 to Rs.50
  Kumkum packet: Rs.10 to Rs.20
  Camphor (karpuram): Rs.20 to Rs.30
  Flower garland (marigold): Rs.30 to Rs.60
  Coconut for offering: Rs.30 to Rs.50
  Water bottle: Rs.20 (MRP)

FOOD:
  Veg thali near temple: Rs.60 to Rs.100
  Tea/coffee: Rs.10 to Rs.15

If driver or shop charges more than these:
  Politely say: "I know the standard rate"
  Most will agree to fair price

{LANGUAGE_RULE}
Be practical. Give exact prices. Help them not get overcharged.
"""


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for price queries."""
    text_upper = text.upper()

    # Detect specific category
    if any(w in text_upper for w in ["AUTO", "RATE", "FARE", "TAXI"]):
        await send_auto_prices(phone)
        return

    if any(w in text_upper for w in ["RUDRAKSHA", "VIBHUTI", "KUMKUM",
                                      "CAMPHOR", "FLOWER", "COCONUT"]):
        await send_puja_prices(phone)
        return

    if any(w in text_upper for w in ["FOOD", "EAT", "MEAL", "RESTAURANT"]):
        await send_food_prices(phone)
        return

    # General price query — use Claude
    reply = await get_reply(
        system_prompt=PRICE_SYSTEM_PROMPT,
        user_message=text,
        max_tokens=300
    )
    await send_buttons(phone, reply,
        ["Auto rates", "Puja item prices", "Food prices"]
    )


async def send_auto_prices(phone: str) -> None:
    """Send auto fare information."""
    msg = (
        "Auto Fair Rates — Tiruvannamalai 🙏\n\n"
        "Bus stand → East Gate:     Rs.80 (fixed)\n"
        "Railway station → Temple:  Rs.100\n"
        "Girivalam halfway drop:    Rs.120\n"
        "Full day hire:             Rs.1,500 to Rs.2,000\n"
        "Walking (bus stand):       15 minutes\n\n"
        "If driver asks more:\n"
        "Say: 'Standard rate is Rs.80'\n"
        "Most drivers will agree. 🙏"
    )
    await send_buttons(phone, msg, ["Puja item prices", "Food prices", "Main menu"])


async def send_puja_prices(phone: str) -> None:
    """Send puja item fair prices."""
    msg = (
        "Puja Item Fair Prices 🙏\n\n"
        "Rudraksha mala (5 mukhi): Rs.150 to Rs.300\n"
        "Rudraksha bead (single):  Rs.20 to Rs.50\n"
        "Vibhuti (100gm):          Rs.30 to Rs.50\n"
        "Kumkum packet:            Rs.10 to Rs.20\n"
        "Camphor packet:           Rs.20 to Rs.30\n"
        "Marigold garland:         Rs.30 to Rs.60\n"
        "Coconut (offering):       Rs.30 to Rs.50\n"
        "Water bottle:             Rs.20 (MRP)\n\n"
        "If shop charges much more:\n"
        "Try next shop — many shops near temple\n"
        "have fair prices. 🙏"
    )
    await send_buttons(phone, msg, ["Auto rates", "Food prices", "Main menu"])


async def send_food_prices(phone: str) -> None:
    """Send food price information."""
    msg = (
        "Food Prices Near Temple 🙏\n\n"
        "Veg thali:    Rs.60 to Rs.100\n"
        "Tea / Coffee: Rs.10 to Rs.15\n"
        "Snacks:       Rs.20 to Rs.50\n\n"
        "Free Annadhanam (community meals):\n"
        "Available at Ramana Ashram:\n"
        "  Breakfast: 8am | Lunch: 11am\n"
        "Open to all devotees — no charge. 🙏"
    )
    await send_buttons(phone, msg, ["Auto rates", "Puja items", "Main menu"])
```

---

## TEST CASES

```python
# tests/test_feature8.py

import pytest
from unittest.mock import AsyncMock, patch
from src.features.fair_price import handle, send_auto_prices, send_puja_prices


class TestPriceDetection:

    @pytest.mark.asyncio
    async def test_auto_keyword_triggers_auto_prices(self):
        with patch("src.features.fair_price.send_auto_prices",
                   new_callable=AsyncMock) as mock_auto:
            await handle("919XXXXXXXXX", "Auto rate from bus stand?", "english")
            mock_auto.assert_called_once()

    @pytest.mark.asyncio
    async def test_rudraksha_keyword_triggers_puja_prices(self):
        with patch("src.features.fair_price.send_puja_prices",
                   new_callable=AsyncMock) as mock_puja:
            await handle("919XXXXXXXXX", "Rudraksha mala price?", "english")
            mock_puja.assert_called_once()


class TestPriceContent:

    @pytest.mark.asyncio
    async def test_auto_prices_contain_80_rupees(self):
        messages = []
        async def mock_btn(phone, body, buttons):
            messages.append(body)

        with patch("src.features.fair_price.send_buttons", side_effect=mock_btn):
            await send_auto_prices("919XXXXXXXXX")
            assert "80" in messages[0]
            assert "Bus stand" in messages[0] or "bus stand" in messages[0].lower()

    @pytest.mark.asyncio
    async def test_puja_prices_contain_rudraksha(self):
        messages = []
        async def mock_btn(phone, body, buttons):
            messages.append(body)

        with patch("src.features.fair_price.send_buttons", side_effect=mock_btn):
            await send_puja_prices("919XXXXXXXXX")
            assert "Rudraksha" in messages[0]
            assert "150" in messages[0]


class TestFeature8Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_auto_query_returns_rs80_rate(self):
        messages = []
        async def mock_btn(phone, body, buttons):
            messages.append(body)

        with patch("src.features.fair_price.send_buttons", side_effect=mock_btn):
            await handle("919XXXXXXXXX", "auto rate", "english")
            assert any("80" in m for m in messages)

    @pytest.mark.asyncio
    async def test_AC02_all_major_items_in_puja_price(self):
        messages = []
        async def mock_btn(phone, body, buttons):
            messages.append(body)

        with patch("src.features.fair_price.send_buttons", side_effect=mock_btn):
            await send_puja_prices("919XXXXXXXXX")
            combined = " ".join(messages)
            assert "Rudraksha" in combined
            assert "Vibhuti" in combined
            assert "Kumkum" in combined
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: "auto rate" → Rs.80 rate clearly shown
[ ] AC-02: "rudraksha price" → fair price range shown
[ ] AC-03: "food" keyword → food prices + free Annadhanam info
[ ] AC-04: General price query → Claude answers with full list
[ ] AC-05: All tests pass: pytest tests/test_feature8.py -v
[ ] AC-06: Real test: "auto bus stand to temple" → Rs.80 in reply
```
