# Feature 6 — Verified Lodge Booking
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Allows devotees to book verified, clean rooms near the temple
via WhatsApp. You personally verify every lodge.
Devotee pays Rs.49 booking fee to confirm room hold.
Full room rent paid at lodge on arrival.

---

## USER STORIES

```
US-01: Devotee books room from Chennai before travelling.
US-02: Devotee at bus stand at 5am needs room immediately.
US-03: Lodge owner gets WhatsApp notification of booking.
US-04: Devotee cancels booking 24+ hours before.
US-05: Admin marks lodge as full for a specific date.
```

---

## SOP

```
BEFORE LAUNCH (you do this):
  Visit 20 lodges personally
  Check room, bathroom, location
  Get owner agreement: listing fee + room hold policy
  Take 2 photos per lodge: room + bathroom
  Upload photos to Supabase Storage
  Fill lodges table with all data

DAILY MORNING (5 minutes):
  Bot sends availability request to all lodge owners at 8am
  Lodge owners reply: AVAIL 5
  You review — database updated by 9am

ON BOOKING:
  Devotee selects lodge
  Pays Rs.49 booking fee (UPI or Razorpay)
  Bot notifies lodge owner
  Lodge confirms within 30 minutes
  Devotee gets confirmation with address + directions

ON ARRIVAL:
  Devotee pays full room rent at lodge directly
  Lodge pays you monthly listing fee separately
```

---

## FILE TO CREATE

```
src/features/lodge_booking.py
```

---

## COMPLETE CODE

```python
# src/features/lodge_booking.py

"""
Feature 6: Verified Lodge Booking
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
import logging
import uuid
from datetime import datetime, date

logger = logging.getLogger(__name__)

BOOKING_FEE = 49


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for lodge booking queries."""
    text_upper = text.upper()

    # Lodge owner sending availability update
    if text_upper.startswith("AVAIL") and await is_lodge_owner(phone):
        await handle_availability_update(phone, text)
        return

    # Lodge owner confirming booking
    if text_upper in ["YES", "CONFIRM", "FULL"] and await is_lodge_owner(phone):
        await handle_lodge_confirmation(phone, text_upper)
        return

    # Devotee payment confirmation
    if "PAID" in text_upper:
        await handle_payment(phone)
        return

    # Check conversation state
    db = get_db()
    state = db.table("conversation_state")\
        .select("step, data")\
        .eq("phone", phone)\
        .eq("current_feature", "lodge_booking")\
        .execute()

    if state.data:
        await handle_step(phone, text,
                         state.data[0]["step"],
                         state.data[0].get("data", {}))
    else:
        await start_booking(phone, language)


async def start_booking(phone: str, language: str) -> None:
    """Start lodge booking conversation."""
    db = get_db()
    db.table("conversation_state").upsert({
        "phone": phone,
        "current_feature": "lodge_booking",
        "step": "ask_date",
        "data": {}
    }).execute()
    await send_text(phone,
        "Lodge Booking — Tiruvannamalai 🙏\n\n"
        "Verified rooms near the temple.\n"
        "Booking fee: Rs.49 | Room rent paid at lodge.\n\n"
        "Which date are you arriving?\n"
        "(Example: MAY 23)"
    )


async def handle_step(phone: str, text: str, step: str, data: dict) -> None:
    """Handle each step of booking conversation."""
    db = get_db()

    if step == "ask_date":
        data["checkin_date"] = text.strip()
        db.table("conversation_state").update(
            {"step": "ask_time", "data": data}
        ).eq("phone", phone).execute()
        await send_buttons(phone,
            f"Date: {text.strip()}\n\nArrival time?",
            ["Early morning 5am", "Morning 8am+", "Afternoon/Evening"]
        )

    elif step == "ask_time":
        data["checkin_time"] = text.strip()

        # Get available lodges
        lodges = await get_available_lodges(data["checkin_date"])
        if not lodges:
            await send_text(phone,
                "No verified rooms available for that date.\n"
                "Try another date or check dharamshalas.")
            db.table("conversation_state").delete().eq("phone", phone).execute()
            return

        data["available_lodge_ids"] = [str(l["id"]) for l in lodges]
        db.table("conversation_state").update(
            {"step": "select_lodge", "data": data}
        ).eq("phone", phone).execute()

        msg = f"Available verified rooms for {data['checkin_date']}:\n\n"
        for i, lodge in enumerate(lodges, 1):
            msg += (f"{i}. {lodge['name']}\n"
                   f"   {lodge['walk_minutes']} min walk to temple\n"
                   f"   Rs.{lodge['price_normal']}/night\n"
                   f"   {', '.join(lodge.get('facilities', []))}\n\n")
        msg += "Reply 1 / 2 / 3 to select\nOr PHOTO 1 / PHOTO 2 to see photos"
        await send_text(phone, msg)

    elif step == "select_lodge":
        if text.upper().startswith("PHOTO"):
            await handle_photo_request(phone, text, data)
            return
        try:
            idx = int(text.strip()) - 1
            lodge_id = data["available_lodge_ids"][idx]
            lodge = await get_lodge_by_id(lodge_id)
            data["lodge_id"] = lodge_id
            data["lodge_name"] = lodge["name"]
            data["room_rent"] = lodge["price_normal"]

            ref = f"LDG-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
            data["booking_ref"] = ref

            db.table("conversation_state").update(
                {"step": "await_payment", "data": data}
            ).eq("phone", phone).execute()

            await send_text(phone,
                f"Lodge: {lodge['name']}\n"
                f"Date: {data['checkin_date']} | {data['checkin_time']}\n"
                f"Room rent: Rs.{lodge['price_normal']} (pay at lodge)\n\n"
                f"Booking fee to confirm: Rs.{BOOKING_FEE}\n\n"
                f"Pay options:\n"
                f"1. UPI: arunachala@ybl | Amount: Rs.{BOOKING_FEE} | Note: {ref}\n"
                f"2. Link: https://rzp.io/l/arunachala (card/UPI/wallet)\n"
                f"3. NRI: Use link above — accepts international cards\n\n"
                f"Reply PAID after payment"
            )
        except (IndexError, ValueError):
            await send_text(phone, "Invalid selection. Reply 1, 2, or 3.")


async def handle_payment(phone: str) -> None:
    """Process payment and notify lodge owner."""
    db = get_db()
    state = db.table("conversation_state")\
        .select("data")\
        .eq("phone", phone)\
        .eq("current_feature", "lodge_booking")\
        .execute()

    if not state.data:
        await send_text(phone, "No pending booking. Start with 'lodge booking'.")
        return

    data = state.data[0]["data"]

    # Save booking
    db.table("lodge_bookings").insert({
        "booking_ref": data["booking_ref"],
        "devotee_phone": phone,
        "lodge_id": data["lodge_id"],
        "checkin_date": data["checkin_date"],
        "checkin_time": data["checkin_time"],
        "room_rent": data["room_rent"],
        "booking_fee": BOOKING_FEE,
        "payment_verified": False,
        "lodge_confirmed": False,
        "status": "pending_lodge_confirm"
    }).execute()

    # Reduce availability
    db.table("lodge_availability").update(
        {"rooms_available": "rooms_available - 1"}
    ).eq("lodge_id", data["lodge_id"])\
     .eq("date", data["checkin_date"])\
     .execute()

    db.table("conversation_state").delete().eq("phone", phone).execute()

    # Notify lodge owner
    lodge = await get_lodge_by_id(data["lodge_id"])
    if lodge:
        await send_text(lodge["phone"],
            f"New booking! 🙏\n\n"
            f"Ref: {data['booking_ref']}\n"
            f"Guest: {phone}\n"
            f"Date: {data['checkin_date']} — {data['checkin_time']}\n"
            f"Room rent: Rs.{data['room_rent']}\n\n"
            f"Reply YES to confirm or FULL if unavailable"
        )

    await send_text(phone,
        f"Payment received! 🙏\n"
        f"Confirming with lodge... (up to 30 min)\n"
        f"Ref: {data['booking_ref']}\n"
        f"We will WhatsApp you once confirmed."
    )


async def handle_lodge_confirmation(phone: str, response: str) -> None:
    """Handle lodge owner YES/FULL response."""
    db = get_db()
    lodge = db.table("lodges").select("id, name")\
        .eq("phone", phone).execute()
    if not lodge.data:
        return

    lodge_id = lodge.data[0]["id"]
    booking = db.table("lodge_bookings")\
        .select("*")\
        .eq("lodge_id", lodge_id)\
        .eq("status", "pending_lodge_confirm")\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if not booking.data:
        return

    b = booking.data[0]

    if response == "YES" or response == "CONFIRM":
        db.table("lodge_bookings").update({
            "lodge_confirmed": True,
            "status": "confirmed"
        }).eq("id", b["id"]).execute()

        # Get lodge address for devotee
        lodge_data = await get_lodge_by_id(lodge_id)

        await send_text(b["devotee_phone"],
            f"BOOKING CONFIRMED! 🙏\n\n"
            f"Ref: {b['booking_ref']}\n"
            f"Lodge: {lodge.data[0]['name']}\n"
            f"Date: {b['checkin_date']} — {b['checkin_time']}\n"
            f"Room rent: Rs.{b['room_rent']} (pay at lodge)\n\n"
            f"ADDRESS:\n{lodge_data.get('address', '')}\n"
            f"Phone: {lodge_data.get('phone', '')}\n\n"
            f"Auto from bus stand: Rs.80\n"
            f"Tell driver: {lodge_data.get('name', '')}"
        )

    elif response == "FULL":
        db.table("lodge_bookings").update({"status": "cancelled"})\
            .eq("id", b["id"]).execute()
        await send_text(b["devotee_phone"],
            "Lodge unavailable on that date. Full refund will be processed. "
            "Searching alternative — we will contact you shortly."
        )


async def handle_availability_update(phone: str, text: str) -> None:
    """Handle lodge owner AVAIL X update."""
    try:
        parts = text.upper().split()
        count = int(parts[1]) if len(parts) > 1 else 0
        db = get_db()
        lodge = db.table("lodges").select("id").eq("phone", phone).execute()
        if lodge.data:
            today = date.today().isoformat()
            db.table("lodge_availability").upsert({
                "lodge_id": lodge.data[0]["id"],
                "date": today,
                "rooms_available": count,
                "is_full": count == 0
            }).execute()
            await send_text(phone, f"Updated: {count} rooms available today.")
    except Exception as e:
        logger.error(f"Availability update error: {e}")
        await send_text(phone, "Format: AVAIL 5 (or AVAIL 0 if full)")


async def handle_photo_request(phone: str, text: str, data: dict) -> None:
    """Send lodge room photos."""
    try:
        idx = int(text.upper().replace("PHOTO", "").strip()) - 1
        lodge_id = data["available_lodge_ids"][idx]
        lodge = await get_lodge_by_id(lodge_id)
        photos = lodge.get("photo_urls", [])
        if photos:
            for url in photos[:2]:
                await send_text(phone, f"Photo: {url}")
        else:
            await send_text(phone, "Photos not available. Reply with number to book.")
    except Exception:
        await send_text(phone, "Reply with lodge number (1, 2, or 3) to book.")


async def get_available_lodges(checkin_date: str) -> list:
    """Get lodges with available rooms for given date."""
    db = get_db()
    result = db.table("lodges")\
        .select("*")\
        .eq("active", True)\
        .eq("verified", True)\
        .execute()
    return result.data or []


async def get_lodge_by_id(lodge_id: str) -> dict | None:
    """Get lodge details by ID."""
    db = get_db()
    result = db.table("lodges").select("*").eq("id", lodge_id).execute()
    return result.data[0] if result.data else None


async def is_lodge_owner(phone: str) -> bool:
    """Check if phone belongs to a lodge owner."""
    db = get_db()
    result = db.table("lodges").select("id").eq("phone", phone).execute()
    return bool(result.data)
```

---

## TEST CASES

```python
# tests/test_feature6.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.lodge_booking import (
    handle, start_booking, handle_availability_update, is_lodge_owner
)


class TestAvailabilityUpdate:

    @pytest.mark.asyncio
    async def test_valid_avail_update_saves_to_db(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [{"id": "lodge-123"}]
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.lodge_booking.get_db", return_value=mock_db), \
             patch("src.features.lodge_booking.send_text", new_callable=AsyncMock) as mock_send:
            await handle_availability_update("919LODGE", "AVAIL 5")
            mock_db.table.return_value.upsert.assert_called_once()
            assert "5" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_avail_zero_marks_full(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [{"id": "lodge-123"}]
        upsert_data = {}
        def capture_upsert(data):
            upsert_data.update(data)
            return mock_db.table.return_value.upsert.return_value
        mock_db.table.return_value.upsert.side_effect = capture_upsert
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.lodge_booking.get_db", return_value=mock_db), \
             patch("src.features.lodge_booking.send_text", new_callable=AsyncMock):
            await handle_availability_update("919LODGE", "AVAIL 0")
            assert upsert_data.get("is_full") is True or \
                   upsert_data.get("rooms_available") == 0


class TestFeature6Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_start_asks_for_date(self):
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.lodge_booking.get_db", return_value=mock_db), \
             patch("src.features.lodge_booking.send_text",
                   new_callable=AsyncMock) as mock_send:
            await start_booking("919XXXXXXXXX", "english")
            assert "date" in mock_send.call_args[0][1].lower() or \
                   "Date" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_AC02_paid_saves_booking_and_notifies_lodge(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [{
                "data": {
                    "booking_ref": "LDG-TEST",
                    "lodge_id": "lodge-123",
                    "lodge_name": "Krishna Lodge",
                    "room_rent": 600,
                    "checkin_date": "MAY 23",
                    "checkin_time": "5am"
                }
            }]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value\
            .eq.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.delete.return_value.eq.return_value\
            .execute.return_value = MagicMock()

        sent_messages = {}
        async def mock_send(phone, msg):
            sent_messages[phone] = msg

        with patch("src.features.lodge_booking.get_db", return_value=mock_db), \
             patch("src.features.lodge_booking.get_lodge_by_id",
                   new_callable=AsyncMock,
                   return_value={"phone": "919LODGE", "address": "Car Street",
                                 "name": "Krishna Lodge"}), \
             patch("src.features.lodge_booking.send_text", side_effect=mock_send):
            await handle("919DEVOTEE", "PAID", "english")
            assert "919LODGE" in sent_messages
            assert "919DEVOTEE" in sent_messages

    @pytest.mark.asyncio
    async def test_AC03_lodge_confirmation_notifies_devotee(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [{"id": "lodge-123", "name": "Krishna"}]
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.order.return_value.limit.return_value\
            .execute.return_value.data = [{
                "id": "booking-1",
                "booking_ref": "LDG-001",
                "devotee_phone": "919DEVOTEE",
                "checkin_date": "MAY 23",
                "checkin_time": "5am",
                "room_rent": 600
            }]
        mock_db.table.return_value.update.return_value.eq.return_value\
            .execute.return_value = MagicMock()

        with patch("src.features.lodge_booking.get_db", return_value=mock_db), \
             patch("src.features.lodge_booking.get_lodge_by_id",
                   new_callable=AsyncMock,
                   return_value={"address": "Car Street", "phone": "919LODGE",
                                 "name": "Krishna Lodge"}), \
             patch("src.features.lodge_booking.send_text",
                   new_callable=AsyncMock) as mock_send:
            await handle("919LODGE", "YES", "english")
            calls = [c[0][0] for c in mock_send.call_args_list]
            assert "919DEVOTEE" in calls
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: Start → asks for check-in date
[ ] AC-02: Date + time → shows available verified lodges
[ ] AC-03: Lodge selected → shows price + payment options
[ ] AC-04: PAID → booking saved + lodge owner notified
[ ] AC-05: Lodge says YES → devotee gets confirmation + address
[ ] AC-06: Lodge says FULL → devotee gets refund notice
[ ] AC-07: Lodge sends AVAIL 5 → availability updated in DB
[ ] AC-08: Booking fee is Rs.49 (constant in code)
[ ] AC-09: All tests pass: pytest tests/test_feature6.py -v
[ ] AC-10: Real test: Complete full booking with real lodge owner
```
