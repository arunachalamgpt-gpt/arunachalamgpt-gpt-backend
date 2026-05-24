# Feature 2A — Abhishekam Booking Guidance + Cancellation Alert
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Guides devotees through the official temple Abhishekam
booking process on tnhrce.gov.in. Current wait is 6+ months.
Sends instant WhatsApp alert when a cancellation slot opens.

We do NOT run a separate booking system.
We guide devotees through the OFFICIAL system.

---

## USER STORIES

```
US-01: As a devotee, I want step-by-step guidance
       to book Abhishekam on the official website.

US-02: As a devotee who cannot wait 6 months,
       I want to be notified the moment a
       cancellation slot appears.

US-03: As an NRI devotee, I want help completing
       the booking from abroad in English.

US-04: As admin, I want to manually trigger
       a cancellation alert to all subscribers.
```

---

## SOP

```
WEEKLY:
  Monday 9am → Check tnhrce.gov.in for available slots
  If slot found → Send alert to all subscribers immediately
  Log check in abhishekam_alerts table

WHEN SUBSCRIBER REGISTERS:
  Save phone number
  Note which Abhishekam type they want
  Note flexible vs specific dates

ADMIN OVERRIDE:
  ADMIN abhishekam alert → Send alert to all subscribers
  ADMIN abhishekam check → Trigger manual slot check
```

---

## FILE TO CREATE

```
src/features/abhishekam.py
```

---

## COMPLETE CODE

```python
# src/features/abhishekam.py

"""
Feature 2A: Abhishekam Booking Guidance + Cancellation Alert
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

BOOKING_SYSTEM_PROMPT = f"""
You are Arunachala GPT — guide for Abhishekam booking
at Arunachaleswara Temple, Tiruvannamalai.

FACTS:
- Official booking: tnhrce.gov.in
- Current wait: approximately 6 months
- Cannot book inside the temple directly
- Cancellation slots appear randomly — we alert immediately

BOOKING STEPS:
1. Go to tnhrce.gov.in
2. Select Arunachaleswara Temple
3. Select Abhishekam type
4. Choose date (6+ months from now)
5. Fill name, phone, address, Aadhaar
6. Pay online

DOCUMENTS NEEDED: Name, phone, address, Aadhaar number

{LANGUAGE_RULE}
Be concise. Guide one step at a time.
"""

ABHISHEKAM_TYPES = [
    "Thiruvannamalai Abhishekam",
    "Panchamirtha Abhishekam",
    "Rudrabhishekam",
    "Special Abhishekam"
]


async def handle(phone: str, text: str, language: str) -> None:
    """Main entry point for abhishekam queries."""
    text_upper = text.upper()

    if "ALERT" in text_upper or "NOTIFY" in text_upper or "CANCEL" in text_upper:
        await handle_alert_subscription(phone, language)
        return

    if "STEP" in text_upper or "HOW" in text_upper or "BOOK" in text_upper:
        await handle_booking_guidance(phone, text, language)
        return

    # General abhishekam query
    await handle_booking_guidance(phone, text, language)


async def handle_booking_guidance(phone: str, text: str, language: str) -> None:
    """Guide devotee through booking process."""
    reply = await get_reply(
        system_prompt=BOOKING_SYSTEM_PROMPT,
        user_message=text,
        max_tokens=400
    )
    await send_buttons(
        phone=phone,
        body=reply,
        buttons=["Alert me for cancellation", "Booking steps", "Main menu"]
    )


async def handle_alert_subscription(phone: str, language: str) -> None:
    """Subscribe devotee to cancellation alerts."""
    try:
        db = get_db()
        existing = db.table("abhishekam_alerts")\
            .select("id")\
            .eq("phone", phone)\
            .eq("active", True)\
            .execute()

        if existing.data:
            await send_text(
                phone,
                "You are already subscribed! "
                "We will alert you when a slot opens. 🙏"
            )
            return

        db.table("abhishekam_alerts").insert({
            "phone": phone,
            "active": True
        }).execute()

        await send_text(
            phone,
            "Alert registered! 🙏\n\n"
            "We check tnhrce.gov.in every week.\n"
            "The moment a cancellation slot appears —\n"
            "we will WhatsApp you immediately.\n\n"
            "Slots go fast — be ready to book instantly."
        )
    except Exception as e:
        logger.error(f"Alert subscription error {phone}: {e}")
        await send_text(phone, "Registration failed. Please try again.")


async def send_cancellation_alert(slot_info: str) -> int:
    """
    Send cancellation alert to all subscribers.
    Returns count of messages sent.
    Called by admin or automated checker.
    """
    db = get_db()
    subscribers = db.table("abhishekam_alerts")\
        .select("phone")\
        .eq("active", True)\
        .execute()

    count = 0
    message = (
        f"SLOT AVAILABLE! 🙏\n\n"
        f"Abhishekam cancellation slot found:\n"
        f"{slot_info}\n\n"
        f"Book NOW at: tnhrce.gov.in\n"
        f"Go to: Arunachaleswara → Abhishekam\n\n"
        f"Slots disappear in minutes!"
    )

    for sub in subscribers.data:
        try:
            await send_text(sub["phone"], message)
            count += 1
        except Exception as e:
            logger.error(f"Alert send failed to {sub['phone']}: {e}")

    logger.info(f"Cancellation alert sent to {count} subscribers")
    return count
```

---

## TEST CASES

```python
# tests/test_feature2a.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.abhishekam import (
    handle, handle_alert_subscription, send_cancellation_alert
)


class TestAlertSubscription:

    @pytest.mark.asyncio
    async def test_new_subscriber_saved(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        with patch("src.features.abhishekam.get_db", return_value=mock_db), \
             patch("src.features.abhishekam.send_text", new_callable=AsyncMock) as mock_send:
            await handle_alert_subscription("919XXXXXXXXX", "tamil")
            mock_db.table.return_value.insert.assert_called_once()
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_subscription_rejected(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [{"id": "existing"}]

        with patch("src.features.abhishekam.get_db", return_value=mock_db), \
             patch("src.features.abhishekam.send_text", new_callable=AsyncMock) as mock_send:
            await handle_alert_subscription("919XXXXXXXXX", "english")
            mock_db.table.return_value.insert.assert_not_called()
            assert "already subscribed" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_cancellation_alert_sent_to_all(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [
                {"phone": "919AAA"},
                {"phone": "919BBB"},
                {"phone": "919CCC"}
            ]

        with patch("src.features.abhishekam.get_db", return_value=mock_db), \
             patch("src.features.abhishekam.send_text", new_callable=AsyncMock) as mock_send:
            count = await send_cancellation_alert("March 15 — 8am slot")
            assert count == 3
            assert mock_send.call_count == 3


class TestFeature2AAcceptance:

    @pytest.mark.asyncio
    async def test_AC01_booking_query_returns_guidance(self):
        with patch("src.features.abhishekam.get_reply",
                   new_callable=AsyncMock,
                   return_value="Go to tnhrce.gov.in to book"), \
             patch("src.features.abhishekam.send_buttons", new_callable=AsyncMock) as mock_btn:
            await handle("919XXXXXXXXX", "How to book abhishekam?", "english")
            mock_btn.assert_called_once()

    @pytest.mark.asyncio
    async def test_AC02_alert_keyword_triggers_subscription(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        with patch("src.features.abhishekam.get_db", return_value=mock_db), \
             patch("src.features.abhishekam.send_text", new_callable=AsyncMock):
            await handle("919XXXXXXXXX", "Alert me for cancellation", "english")
            mock_db.table.return_value.insert.assert_called_once()
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: Booking query → step-by-step guidance returned
[ ] AC-02: "Alert" keyword → subscription saved in DB
[ ] AC-03: Duplicate subscription → friendly message, no duplicate
[ ] AC-04: send_cancellation_alert() → all subscribers notified
[ ] AC-05: All tests pass: pytest tests/test_feature2a.py -v
[ ] AC-06: Real test: Send "abhishekam book kanum" → guidance received
[ ] AC-07: Real test: Send "alert me" → confirmation message received
```
