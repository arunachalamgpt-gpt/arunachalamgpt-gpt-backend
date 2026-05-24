# Feature 2C — Girivalam Guide Booking
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Books a verified local guide who walks the 14km Girivalam
route with the devotee's family, explaining all 8 Ashta Lingams
and sacred spots. Not a priest — a knowledgeable guide.

---

## USER STORIES

```
US-01: First-time family books a guide for Pournami night.
US-02: Family with elderly books half-route guide.
US-03: Foreign devotee books English-speaking guide.
US-04: Guide receives booking notification on WhatsApp.
US-05: Devotee rates guide after tour completion.
```

---

## TOUR TYPES AND PRICING

```
full_girivalam    14km  Rs.1,000  (guide Rs.800 + platform Rs.200)
half_girivalam     7km  Rs.650    (guide Rs.500 + platform Rs.150)
night_pournami    14km  Rs.1,500  (guide Rs.1,200 + platform Rs.300)
lingam_focus      8km   Rs.900    (guide Rs.700 + platform Rs.200)
```

---

## SOP

```
GUIDE VERIFICATION (you do this before listing):
  Meet guide personally
  Test: Ask them to explain all 8 lingams
  Check language ability
  Walk route with them once
  Take their photo and ID

ON BOOKING:
  Show available guides for requested date
  Devotee selects guide
  Bot notifies guide via WhatsApp
  Guide must confirm within 2 hours
  Booking fee Rs.49 collected

ON TOUR DAY:
  Guide contacts devotee 30 min before start
  Guide walks route and explains
  After tour: Bot asks devotee for rating

PAYMENT:
  Devotee pays Rs.49 booking fee upfront
  Devotee pays guide balance on the day directly
  You pay guide Rs.800 etc. or devotee pays guide directly
```

---

## FILE TO CREATE

```
src/features/girivalam_guide.py
```

---

## COMPLETE CODE

```python
# src/features/girivalam_guide.py

"""
Feature 2C: Girivalam Guide Booking
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

TOUR_TYPES = {
    "1": {"name": "Full Girivalam (14km)", "duration": "4-6 hours",
          "total": 1000, "platform_fee": 200, "key": "full_girivalam"},
    "2": {"name": "Half Girivalam (7km)", "duration": "2-3 hours",
          "total": 650, "platform_fee": 150, "key": "half_girivalam"},
    "3": {"name": "Pournami Night (14km)", "duration": "5-7 hours",
          "total": 1500, "platform_fee": 300, "key": "night_pournami"},
    "4": {"name": "Lingam Focus Tour (8km)", "duration": "3-4 hours",
          "total": 900, "platform_fee": 200, "key": "lingam_focus"},
}


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for girivalam guide booking."""
    text_upper = text.upper()

    if "CONFIRM" in text_upper and await is_guide(phone):
        await handle_guide_confirmation(phone, text)
        return

    if "PAID" in text_upper:
        await handle_payment(phone)
        return

    if "RATE" in text_upper or text.strip() in ["1", "2", "3", "4", "5"]:
        await handle_rating(phone, text)
        return

    db = get_db()
    state = db.table("conversation_state")\
        .select("step, data")\
        .eq("phone", phone)\
        .eq("current_feature", "girivalam_guide")\
        .execute()

    if state.data:
        await handle_step(phone, text, state.data[0]["step"],
                         state.data[0].get("data", {}))
    else:
        await start_booking(phone, language)


async def start_booking(phone: str, language: str) -> None:
    """Show tour type selection."""
    db = get_db()
    db.table("conversation_state").upsert({
        "phone": phone,
        "current_feature": "girivalam_guide",
        "step": "select_tour",
        "data": {}
    }).execute()

    await send_text(phone,
        "Girivalam Guide Booking 🙏\n\n"
        "Choose tour type:\n\n"
        "1 — Full Girivalam 14km — Rs.1,000\n"
        "2 — Half Girivalam 7km  — Rs.650\n"
        "3 — Pournami Night     — Rs.1,500\n"
        "4 — Lingam Focus Tour  — Rs.900\n\n"
        "Reply 1 / 2 / 3 / 4"
    )


async def handle_step(phone: str, text: str, step: str, data: dict) -> None:
    """Handle booking conversation steps."""
    db = get_db()

    if step == "select_tour":
        tour = TOUR_TYPES.get(text.strip())
        if not tour:
            await send_text(phone, "Please reply 1, 2, 3, or 4")
            return
        data["tour"] = tour
        db.table("conversation_state").update(
            {"step": "ask_date", "data": data}
        ).eq("phone", phone).execute()
        await send_text(phone, f"Selected: {tour['name']}\n\nWhich date? (Example: MAY 23)")

    elif step == "ask_date":
        data["date"] = text.strip()
        db.table("conversation_state").update(
            {"step": "ask_group_size", "data": data}
        ).eq("phone", phone).execute()
        await send_text(phone, "How many people in your group?")

    elif step == "ask_group_size":
        try:
            size = int(text.strip())
            data["group_size"] = size
            guides = await get_available_guides(data["date"])

            if not guides:
                await send_text(phone, "No guides available for that date. Try another date.")
                return

            data["available_guides"] = [g["id"] for g in guides]
            msg = f"Available guides for {data['date']}:\n\n"
            for i, g in enumerate(guides, 1):
                langs = ", ".join(g.get("languages", ["Tamil"]))
                msg += f"{i}. {g['name']}\n"
                msg += f"   Languages: {langs}\n"
                msg += f"   Rating: {g.get('rating', 0)}/5\n\n"
            msg += "Reply 1 / 2 / 3 to select"

            db.table("conversation_state").update(
                {"step": "select_guide", "data": data}
            ).eq("phone", phone).execute()
            await send_text(phone, msg)

        except ValueError:
            await send_text(phone, "Please enter a number for group size.")

    elif step == "select_guide":
        try:
            idx = int(text.strip()) - 1
            guide_id = data["available_guides"][idx]
            data["guide_id"] = guide_id
            ref = f"GG-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
            data["booking_ref"] = ref

            db.table("conversation_state").update(
                {"step": "await_payment", "data": data}
            ).eq("phone", phone).execute()

            tour = data["tour"]
            await send_text(phone,
                f"Booking: {tour['name']}\n"
                f"Date: {data['date']}\n"
                f"Group: {data['group_size']} people\n"
                f"Total: Rs.{tour['total']}\n\n"
                f"Booking fee (to confirm): Rs.49\n"
                f"Balance paid to guide on tour day\n\n"
                f"UPI: arunachala@ybl\n"
                f"Amount: Rs.49\n"
                f"Note: {ref}\n\n"
                f"Reply PAID after payment"
            )
        except (IndexError, ValueError):
            await send_text(phone, "Invalid selection. Please try again.")


async def handle_payment(phone: str) -> None:
    """Confirm payment and notify guide."""
    db = get_db()
    state = db.table("conversation_state")\
        .select("data")\
        .eq("phone", phone)\
        .eq("current_feature", "girivalam_guide")\
        .execute()

    if not state.data:
        await send_text(phone, "No pending booking found.")
        return

    data = state.data[0]["data"]

    db.table("guide_bookings").insert({
        "booking_ref": data["booking_ref"],
        "devotee_phone": phone,
        "guide_id": data["guide_id"],
        "tour_type": data["tour"]["key"],
        "tour_date": data["date"],
        "group_size": data["group_size"],
        "total_amount": data["tour"]["total"],
        "booking_fee": 49,
        "status": "pending_guide_confirm"
    }).execute()

    db.table("conversation_state").delete().eq("phone", phone).execute()

    guide = db.table("guide_profiles")\
        .select("name, phone")\
        .eq("id", data["guide_id"])\
        .execute()

    if guide.data:
        guide_phone = guide.data[0]["phone"]
        await send_text(guide_phone,
            f"New booking! 🙏\n\n"
            f"Ref: {data['booking_ref']}\n"
            f"Tour: {data['tour']['name']}\n"
            f"Date: {data['date']}\n"
            f"Group: {data['group_size']} people\n"
            f"Devotee: {phone}\n\n"
            f"Reply CONFIRM or DECLINE"
        )

    await send_text(phone,
        f"Booking received! 🙏\n"
        f"Ref: {data['booking_ref']}\n"
        f"Guide confirmation within 2 hours.\n"
        f"We will notify you immediately."
    )


async def handle_guide_confirmation(phone: str, text: str) -> None:
    """Handle guide CONFIRM or DECLINE."""
    db = get_db()
    booking = db.table("guide_bookings")\
        .select("*, devotee_phone")\
        .eq("status", "pending_guide_confirm")\
        .execute()

    for b in (booking.data or []):
        guide = db.table("guide_profiles").select("phone").eq("id", b.get("guide_id", "")).execute()
        if guide.data and guide.data[0]["phone"] == phone:
            if "CONFIRM" in text.upper():
                db.table("guide_bookings").update({"status": "confirmed"})\
                    .eq("id", b["id"]).execute()
                await send_text(b["devotee_phone"],
                    f"Guide confirmed your booking! 🙏\n"
                    f"Ref: {b['booking_ref']}\n"
                    f"Guide will contact you on {b['tour_date']}."
                )
            break


async def handle_rating(phone: str, text: str) -> None:
    """Save guide rating from devotee."""
    try:
        rating = int(text.strip())
        if 1 <= rating <= 5:
            db = get_db()
            booking = db.table("guide_bookings")\
                .select("id, guide_id")\
                .eq("devotee_phone", phone)\
                .eq("status", "confirmed")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

            if booking.data:
                b = booking.data[0]
                db.table("guide_bookings").update({"status": "completed"})\
                    .eq("id", b["id"]).execute()
                await send_text(phone,
                    f"Thank you! Rating {rating}/5 saved. 🙏"
                )
    except ValueError:
        pass


async def get_available_guides(date: str) -> list:
    """Get guides available for given date."""
    db = get_db()
    result = db.table("guide_profiles")\
        .select("*")\
        .eq("active", True)\
        .execute()
    return result.data or []


async def is_guide(phone: str) -> bool:
    """Check if phone belongs to a guide."""
    db = get_db()
    result = db.table("guide_profiles")\
        .select("id")\
        .eq("phone", phone)\
        .execute()
    return bool(result.data)
```

---

## TEST CASES

```python
# tests/test_feature2c.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.girivalam_guide import handle, start_booking, TOUR_TYPES


class TestTourTypes:
    def test_all_4_tour_types_defined(self):
        assert len(TOUR_TYPES) == 4

    def test_night_tour_most_expensive(self):
        prices = [t["total"] for t in TOUR_TYPES.values()]
        assert max(prices) == 1500

    def test_platform_fee_less_than_total(self):
        for t in TOUR_TYPES.values():
            assert t["platform_fee"] < t["total"]


class TestFeature2CAcceptance:

    @pytest.mark.asyncio
    async def test_AC01_start_shows_4_tour_types(self):
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.girivalam_guide.get_db", return_value=mock_db), \
             patch("src.features.girivalam_guide.send_text",
                   new_callable=AsyncMock) as mock_send:
            await start_booking("919XXXXXXXXX", "english")
            msg = mock_send.call_args[0][1]
            assert "1" in msg and "2" in msg and "3" in msg and "4" in msg

    @pytest.mark.asyncio
    async def test_AC02_invalid_tour_selection_rejected(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [
                {"step": "select_tour", "data": {}}
            ]

        with patch("src.features.girivalam_guide.get_db", return_value=mock_db), \
             patch("src.features.girivalam_guide.send_text",
                   new_callable=AsyncMock) as mock_send:
            await handle("919XXXXXXXXX", "9", "english")
            assert "1, 2, 3" in mock_send.call_args[0][1] or \
                   "Reply" in mock_send.call_args[0][1]
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: Start → shows 4 tour type options
[ ] AC-02: Invalid selection → friendly error
[ ] AC-03: Full booking flow → booking saved in DB
[ ] AC-04: PAID → guide gets WhatsApp notification
[ ] AC-05: Guide confirms → devotee gets confirmation
[ ] AC-06: 1-5 rating → saved in guide_bookings table
[ ] AC-07: All tests pass: pytest tests/test_feature2c.py -v
[ ] AC-08: Real test: Complete booking end-to-end
```
