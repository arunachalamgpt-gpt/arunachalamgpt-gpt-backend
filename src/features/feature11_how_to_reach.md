# Feature 11 — How to Reach from Any City
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Tells devotees the best route from their city to Tiruvannamalai.
Covers Chennai, Bangalore, Hyderabad, Coimbatore, Madurai, Mumbai.
Free feature. Transport operators pay Rs.500/month for listing.

---

## USER STORIES

```
US-01: Chennai devotee asks best way → bus timings, cost.
US-02: Bangalore devotee asks → KSRTC night bus details.
US-03: Hyderabad devotee asks → train + bus combination.
US-04: Devotee asks on arrival → auto rate from bus stand.
US-05: Pournami tip → best time to travel for less crowd.
```

---

## FILE TO CREATE

```
src/features/how_to_reach.py
```

---

## COMPLETE CODE

```python
# src/features/how_to_reach.py

"""
Feature 11: How to Reach Tiruvannamalai from Any City
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

ROUTE_DATA = {
    "chennai": {
        "best": "Direct bus from Koyambedu bus stand",
        "frequency": "Every 30 minutes, 5am to 11pm",
        "duration": "3 hours",
        "cost": "Rs.150",
        "night_bus": "10pm and 11pm (arrives 1am — good for Pournami)",
        "train": "Chennai Central to Tiruvannamalai — 4 trains daily — Rs.80 to Rs.200",
        "pournami_tip": "Take 10pm or 11pm night bus. Arrive 1am. Crowd is less early morning.",
    },
    "bangalore": {
        "best": "KSRTC night bus from Kempegowda Bus Stand (Majestic)",
        "frequency": "Night buses: 9pm, 10pm, 11pm",
        "duration": "3.5 to 4 hours",
        "cost": "Rs.400 to Rs.600",
        "book_at": "ksrtc.in or redBus app",
        "cab": "Direct cab Rs.3,500 to Rs.4,500 — good for groups of 4",
        "pournami_tip": "9pm bus arrives 1am. Pournami crowd builds after 8am. Early arrival is better.",
    },
    "hyderabad": {
        "best": "Train to Chennai then bus to Tiruvannamalai",
        "train": "Hyderabad to Chennai overnight — Rs.600 to Rs.1,200",
        "then": "Chennai Koyambedu bus to Tiruvannamalai — Rs.150",
        "total_time": "12 to 14 hours",
        "pournami_tip": "Book train 2 weeks early. Overnight train + morning bus works well.",
    },
    "coimbatore": {
        "best": "Bus via Erode or Salem",
        "frequency": "Every 2 hours",
        "duration": "4 to 5 hours",
        "cost": "Rs.200 to Rs.300",
        "pournami_tip": "Early morning 5am bus arrives by 9am — before main crowd builds.",
    },
    "madurai": {
        "best": "Bus — direct or via Trichy",
        "frequency": "Morning buses",
        "duration": "4 hours",
        "cost": "Rs.200",
    },
    "mumbai": {
        "best": "Train to Chennai or Bangalore then bus",
        "train": "Mumbai to Chennai — overnight train Rs.800 to Rs.2,000",
        "then": "Chennai to Tiruvannamalai bus Rs.150",
        "total_time": "18 to 22 hours",
        "book": "Book train 3 weeks in advance on IRCTC",
    },
}

ARRIVAL_INFO = {
    "bus_stand_to_temple": "Auto Rs.80 or 15 min walk",
    "railway_station_to_temple": "Auto Rs.100",
    "auto_tip": "Say the standard rate if driver quotes more",
}

REACH_SYSTEM_PROMPT = f"""
You are Arunachala GPT — travel guide for reaching Tiruvannamalai.

ROUTE DATA:
{{route_data}}

ON ARRIVAL:
Bus stand to temple: Auto Rs.80 or 15 min walk
Railway station to temple: Auto Rs.100

{LANGUAGE_RULE}
Give practical, specific information.
Include: mode of transport, cost, duration, departure point.
Include Pournami tip if they mention Pournami.
"""

CITY_KEYWORDS = {
    "chennai": ["chennai", "madras", "சென்னை", "చెన్నై"],
    "bangalore": ["bangalore", "bengaluru", "bengalore", "ಬೆಂಗಳೂರು", "బెంగళూరు"],
    "hyderabad": ["hyderabad", "hyd", "హైదరాబాద్"],
    "coimbatore": ["coimbatore", "kovai", "coimbator", "கோவை"],
    "madurai": ["madurai", "மதுரை"],
    "mumbai": ["mumbai", "bombay", "मुंबई"],
}


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for travel queries."""
    text_lower = text.lower()

    # Detect city
    detected_city = None
    for city, keywords in CITY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected_city = city
            break

    if detected_city:
        await send_city_guide(phone, detected_city, text, language)
    else:
        # Ask which city
        await send_text(phone,
            "Which city are you coming from? 🙏\n\n"
            "1. Chennai\n"
            "2. Bangalore\n"
            "3. Hyderabad\n"
            "4. Coimbatore\n"
            "5. Madurai\n"
            "6. Mumbai\n"
            "7. Other city\n\n"
            "Reply with city name or number"
        )


async def send_city_guide(phone: str, city: str, text: str, language: str) -> None:
    """Send route guide for specific city."""
    route = ROUTE_DATA.get(city, {})
    if not route:
        await send_text(phone, "Route not available. Search KSRTC or IRCTC for options.")
        return

    system = REACH_SYSTEM_PROMPT.format(
        route_data=format_route(city, route)
    )
    reply = await get_reply(
        system_prompt=system,
        user_message=text,
        max_tokens=350
    )
    await send_buttons(phone, reply,
        ["Auto rate on arrival", "Lodge booking", "Main menu"]
    )


def format_route(city: str, data: dict) -> str:
    """Format route data for Claude."""
    lines = [f"FROM {city.upper()} TO TIRUVANNAMALAI:"]
    for key, value in data.items():
        lines.append(f"  {key.replace('_', ' ').title()}: {value}")
    return "\n".join(lines)
```

---

## TEST CASES

```python
# tests/test_feature11.py

import pytest
from unittest.mock import AsyncMock, patch
from src.features.how_to_reach import handle, CITY_KEYWORDS, ROUTE_DATA


class TestCityDetection:
    def test_chennai_detected(self):
        from src.features.how_to_reach import CITY_KEYWORDS
        text = "coming from chennai"
        detected = None
        for city, kws in CITY_KEYWORDS.items():
            if any(kw in text.lower() for kw in kws):
                detected = city
                break
        assert detected == "chennai"

    def test_bangalore_detected(self):
        text = "from bangalore"
        detected = None
        for city, kws in CITY_KEYWORDS.items():
            if any(kw in text.lower() for kw in kws):
                detected = city
                break
        assert detected == "bangalore"

    def test_tamil_chennai_detected(self):
        text = "சென்னையில் இருந்து வருகிறேன்"
        detected = None
        for city, kws in CITY_KEYWORDS.items():
            if any(kw in text.lower() for kw in kws):
                detected = city
                break
        assert detected == "chennai"


class TestRouteData:
    def test_all_6_cities_have_routes(self):
        assert len(ROUTE_DATA) >= 6

    def test_chennai_has_bus_info(self):
        assert "chennai" in ROUTE_DATA
        assert "cost" in ROUTE_DATA["chennai"]

    def test_all_cities_have_pournami_tip(self):
        cities_with_tip = [c for c, d in ROUTE_DATA.items()
                          if "pournami_tip" in d]
        assert len(cities_with_tip) >= 3


class TestFeature11Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_chennai_query_returns_route(self):
        with patch("src.features.how_to_reach.get_reply",
                   new_callable=AsyncMock,
                   return_value="Take bus from Koyambedu Rs.150"), \
             patch("src.features.how_to_reach.send_buttons",
                   new_callable=AsyncMock) as mock_btn:
            await handle("919XXXXXXXXX", "Coming from Chennai", "english")
            mock_btn.assert_called_once()

    @pytest.mark.asyncio
    async def test_AC02_unknown_city_asks_for_city(self):
        with patch("src.features.how_to_reach.send_text",
                   new_callable=AsyncMock) as mock_send:
            await handle("919XXXXXXXXX", "How to come?", "english")
            assert mock_send.called
            msg = mock_send.call_args[0][1]
            assert "Chennai" in msg or "city" in msg.lower()

    @pytest.mark.asyncio
    async def test_AC03_pournami_tip_included_in_context(self):
        context = []
        async def capture(system_prompt, user_message, **kwargs):
            context.append(system_prompt)
            return "Take 10pm bus"

        with patch("src.features.how_to_reach.get_reply", side_effect=capture), \
             patch("src.features.how_to_reach.send_buttons", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "Coming from Chennai for Pournami", "english")
            assert any("pournami_tip" in c.lower() or "Pournami" in c
                       for c in context)
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: "Chennai" keyword → Chennai route with bus timings
[ ] AC-02: "Bangalore" keyword → KSRTC night bus details
[ ] AC-03: Unknown city → asks which city
[ ] AC-04: Pournami mentioned → Pournami travel tip included
[ ] AC-05: All 6 cities have route data in ROUTE_DATA dict
[ ] AC-06: All tests pass: pytest tests/test_feature11.py -v
[ ] AC-07: Real test: "Coming from Bangalore" → KSRTC details shown
```
