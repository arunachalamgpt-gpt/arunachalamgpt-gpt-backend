# Feature 2B — Annadhanam Sponsorship
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Allows devotees and NRI to sponsor feeding of pilgrims
(Annadhanam) at Tiruvannamalai on a specific date.
Platform collects payment, arranges feeding, sends proof.

---

## USER STORIES

```
US-01: Sponsor feeding on parent's anniversary.
US-02: NRI sponsors from abroad via card/PayPal.
US-03: Receive photo, video, digital certificate as proof.
US-04: Family name announced to all subscribers.
```

---

## SOP

```
ON BOOKING:
  Collect: date, people count, occasion, sponsor name
  Show price breakdown
  Collect payment

ON FEEDING DAY:
  Your partner arranges and executes feeding
  Take photos and short video
  Send to sponsor via WhatsApp

AFTER FEEDING:
  Generate digital certificate
  Update booking status to completed
  Announce to calendar subscribers
```

---

## FILE TO CREATE

```
src/features/annadhanam.py
```

---

## COMPLETE CODE

```python
# src/features/annadhanam.py

"""
Feature 2B: Annadhanam Sponsorship
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

PRICING = {
    25:  {"food": 750,  "fee": 150},
    50:  {"food": 1500, "fee": 200},
    100: {"food": 3000, "fee": 350},
    200: {"food": 6000, "fee": 500},
    500: {"food": 15000,"fee": 800},
}

def get_price(count: int) -> dict:
    """Get pricing for given people count."""
    for limit in sorted(PRICING.keys()):
        if count <= limit:
            return PRICING[limit]
    return PRICING[500]


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for annadhanam queries."""
    text_upper = text.upper()

    if "PAID" in text_upper:
        await handle_payment_confirmation(phone, text)
        return

    db = get_db()
    state = db.table("conversation_state")\
        .select("step, data")\
        .eq("phone", phone)\
        .eq("current_feature", "annadhanam")\
        .execute()

    if state.data:
        step = state.data[0]["step"]
        data = state.data[0].get("data", {})
        await handle_booking_step(phone, text, step, data)
    else:
        await start_booking(phone, language)


async def start_booking(phone: str, language: str) -> None:
    """Start Annadhanam booking conversation."""
    db = get_db()
    db.table("conversation_state").upsert({
        "phone": phone,
        "current_feature": "annadhanam",
        "step": "ask_date",
        "data": {}
    }).execute()

    await send_text(phone,
        "Annadhanam Sponsorship 🙏\n\n"
        "Feed pilgrims at Tiruvannamalai in your family's name.\n"
        "You receive: Photo + Video + Digital Certificate\n\n"
        "Which date? (Example: JUNE 15)"
    )


async def handle_booking_step(phone: str, text: str, step: str, data: dict) -> None:
    """Handle each step of the booking conversation."""
    db = get_db()

    if step == "ask_date":
        data["date"] = text.strip()
        db.table("conversation_state").update(
            {"step": "ask_count", "data": data}
        ).eq("phone", phone).execute()
        await send_text(phone, "How many people to feed?\n(25 / 50 / 100 / 200 / 500)")

    elif step == "ask_count":
        try:
            count = int(text.strip().replace(" ", ""))
            pricing = get_price(count)
            data["count"] = count
            data["food_cost"] = pricing["food"]
            data["platform_fee"] = pricing["fee"]
            data["total"] = pricing["food"] + pricing["fee"]

            db.table("conversation_state").update(
                {"step": "ask_occasion", "data": data}
            ).eq("phone", phone).execute()

            await send_text(phone,
                f"Price for {count} people:\n\n"
                f"  Food cost:     Rs.{pricing['food']}\n"
                f"  Platform fee:  Rs.{pricing['fee']}\n"
                f"  ─────────────────────\n"
                f"  TOTAL:         Rs.{data['total']}\n\n"
                f"What is the occasion?\n"
                f"(Example: Appa birthday / Amma anniversary)"
            )
        except ValueError:
            await send_text(phone, "Please enter a number. (25 / 50 / 100 / 200 / 500)")

    elif step == "ask_occasion":
        data["occasion"] = text.strip()
        db.table("conversation_state").update(
            {"step": "ask_name", "data": data}
        ).eq("phone", phone).execute()
        await send_text(phone,
            "Sponsor name for announcement?\n"
            "(Example: Rajan Family, Chennai)"
        )

    elif step == "ask_name":
        data["sponsor_name"] = text.strip()
        ref = f"ANN-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        data["booking_ref"] = ref

        db.table("conversation_state").update(
            {"step": "await_payment", "data": data}
        ).eq("phone", phone).execute()

        await send_text(phone,
            f"Booking Summary:\n\n"
            f"  Date: {data['date']}\n"
            f"  People: {data['count']}\n"
            f"  Occasion: {data['occasion']}\n"
            f"  Sponsored by: {data['sponsor_name']}\n"
            f"  Total: Rs.{data['total']}\n\n"
            f"Pay to confirm:\n"
            f"  UPI: arunachala@ybl\n"
            f"  Amount: Rs.{data['total']}\n"
            f"  Note: {ref}\n\n"
            f"Reply PAID after payment"
        )


async def handle_payment_confirmation(phone: str, text: str) -> None:
    """Handle PAID confirmation and save booking."""
    try:
        db = get_db()
        state = db.table("conversation_state")\
            .select("data")\
            .eq("phone", phone)\
            .eq("current_feature", "annadhanam")\
            .execute()

        if not state.data:
            await send_text(phone, "No pending booking found. Start with 'annadhanam'.")
            return

        data = state.data[0]["data"]

        db.table("annadhanam_bookings").insert({
            "booking_ref": data["booking_ref"],
            "sponsor_phone": phone,
            "sponsor_name": data["sponsor_name"],
            "occasion": data["occasion"],
            "feeding_date": data["date"],
            "people_count": data["count"],
            "total_amount": data["total"],
            "platform_fee": data["platform_fee"],
            "status": "confirmed"
        }).execute()

        db.table("conversation_state")\
            .delete().eq("phone", phone).execute()

        await send_text(phone,
            f"Booking Confirmed! 🙏\n\n"
            f"Reference: {data['booking_ref']}\n"
            f"Date: {data['date']}\n"
            f"People: {data['count']}\n"
            f"Sponsored by: {data['sponsor_name']}\n\n"
            f"On {data['date']} we will announce:\n"
            f"'Today's Annadhanam by {data['sponsor_name']}'\n\n"
            f"Photo, video and certificate will be sent same day. 🙏"
        )
    except Exception as e:
        logger.error(f"Payment confirmation error {phone}: {e}")
        await send_text(phone, "Error saving booking. Please contact support.")
```

---

## TEST CASES

```python
# tests/test_feature2b.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.annadhanam import handle, get_price, start_booking


class TestPricing:
    def test_25_people_pricing(self):
        p = get_price(25)
        assert p["food"] == 750
        assert p["fee"] == 150

    def test_100_people_pricing(self):
        p = get_price(100)
        assert p["food"] == 3000
        assert p["fee"] == 350

    def test_count_rounds_up_to_next_tier(self):
        p = get_price(30)
        assert p == get_price(50)

    def test_large_count_uses_500_tier(self):
        p = get_price(600)
        assert p == get_price(500)


class TestFeature2BAcceptance:

    @pytest.mark.asyncio
    async def test_AC01_start_booking_asks_for_date(self):
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.annadhanam.get_db", return_value=mock_db), \
             patch("src.features.annadhanam.send_text", new_callable=AsyncMock) as mock_send:
            await start_booking("919XXXXXXXXX", "english")
            assert mock_send.called
            assert "date" in mock_send.call_args[0][1].lower() or \
                   "Date" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_AC02_invalid_count_rejected(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [
                {"step": "ask_count", "data": {"date": "JUNE 15"}}
            ]

        with patch("src.features.annadhanam.get_db", return_value=mock_db), \
             patch("src.features.annadhanam.send_text", new_callable=AsyncMock) as mock_send:
            await handle("919XXXXXXXXX", "many people", "english")
            assert mock_send.called
            assert "number" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_AC03_paid_saves_booking(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [{
                "data": {
                    "booking_ref": "ANN-TEST",
                    "date": "JUNE 15",
                    "count": 100,
                    "occasion": "Birthday",
                    "sponsor_name": "Rajan Family",
                    "total": 3350,
                    "platform_fee": 350
                }
            }]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.features.annadhanam.get_db", return_value=mock_db), \
             patch("src.features.annadhanam.send_text", new_callable=AsyncMock) as mock_send:
            await handle("919XXXXXXXXX", "PAID", "english")
            mock_db.table.return_value.insert.assert_called_once()
            assert "Confirmed" in mock_send.call_args[0][1]
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: "annadhanam" message → asks for date
[ ] AC-02: Invalid count → friendly error message
[ ] AC-03: Full flow completes → booking saved in DB
[ ] AC-04: PAID message → confirmation with reference number
[ ] AC-05: get_price() returns correct tiers
[ ] AC-06: All tests pass: pytest tests/test_feature2b.py -v
[ ] AC-07: Real test: Complete full booking flow end-to-end
```
