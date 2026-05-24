# Feature 5 — Girivalam SOS Emergency Service
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Walker registers family numbers once.
In emergency — sends SOS.
Bot alerts ALL family simultaneously + sends medical info.
Free service. Builds massive trust.

---

## USER STORIES

```
US-01: Walker registers family numbers before Girivalam.
US-02: Emergency — send SOS → all family alerted in <5 sec.
US-03: Walker sends SAFE → family gets reassurance.
US-04: Family member registers on behalf of elderly walker.
```

---

## SOP

```
BEFORE POURNAMI:
  Put posters showing: "Register for Girivalam safety"
  "Send REGISTER to +91-XXXXX"

ON REGISTRATION:
  Walker sends: REGISTER or SOS REGISTER
  Bot collects family numbers
  Confirmation sent to all family members

ON SOS:
  Walker sends SOS
  Bot looks up registered family numbers
  Sends medical point info to walker
  Sends emergency alert to all family
  Logs in sos_alerts table

MEDICAL POINTS (verify these before launch):
  Main: Temple medical point 04175-252422
  Ambulance: 108 (free)
  Police: 04175-252222
```

---

## FILE TO CREATE

```
src/features/sos.py
```

---

## COMPLETE CODE

```python
# src/features/sos.py

"""
Feature 5: Girivalam SOS Emergency Service
Owner: [Name]
Status: in-progress

THIS IS A SAFETY FEATURE. Test thoroughly.
SOS must deliver in under 5 seconds.
"""

from src.database import get_db
from src.whatsapp import send_text
import logging

logger = logging.getLogger(__name__)

MEDICAL_INFO = (
    "Temple medical point: 04175-252422\n"
    "Ambulance: 108 (FREE — always works)\n"
    "Police: 04175-252222"
)

WALKER_SOS_MESSAGE = (
    "Help is coming! Stay where you are. 🚨\n\n"
    "Nearest medical help:\n"
    f"{MEDICAL_INFO}\n\n"
    "Show this message to anyone nearby.\n"
    "Sit down. Do not move."
)


async def handle_sos(phone: str) -> None:
    """
    CRITICAL: Handle SOS message.
    Must complete in under 5 seconds.
    """
    try:
        # Send medical info to walker immediately
        await send_text(phone, WALKER_SOS_MESSAGE)

        # Get family numbers
        family_phones = await get_family_phones(phone)

        if not family_phones:
            await send_text(phone,
                "Note: No family numbers registered.\n"
                "Register family: Send REGISTER"
            )
            return

        # Alert all family members
        for family_phone in family_phones:
            family_msg = (
                f"URGENT — SOS from Girivalam! 🚨\n\n"
                f"Your family member needs help!\n"
                f"Time: now\n"
                f"Location: Tiruvannamalai Girivalam route\n\n"
                f"{MEDICAL_INFO}\n\n"
                f"Call them: {phone}"
            )
            await send_text(family_phone, family_msg)

        # Log the alert
        db = get_db()
        db.table("sos_alerts").insert({
            "walker_phone": phone,
            "family_count": len(family_phones),
            "family_notified": True
        }).execute()

        logger.warning(f"SOS triggered by {phone}. {len(family_phones)} family alerted.")

    except Exception as e:
        logger.error(f"SOS CRITICAL ERROR for {phone}: {e}")
        # Even if everything else fails — send this
        await send_text(phone,
            "EMERGENCY HELP:\n"
            "Ambulance: 108\n"
            "Police: 100\n"
            "Medical: 04175-252422"
        )


async def handle_registration(phone: str, text: str) -> None:
    """Register family phone numbers for SOS."""
    db = get_db()
    state = db.table("conversation_state")\
        .select("step, data")\
        .eq("phone", phone)\
        .eq("current_feature", "sos_register")\
        .execute()

    if not state.data:
        # Start registration
        db.table("conversation_state").upsert({
            "phone": phone,
            "current_feature": "sos_register",
            "step": "collecting_numbers",
            "data": {"numbers": []}
        }).execute()
        await send_text(phone,
            "Girivalam Safety Registration 🙏\n\n"
            "Send family WhatsApp numbers one by one.\n"
            "(Add up to 5 numbers)\n\n"
            "Send: DONE when finished\n\n"
            "First family number:"
        )
        return

    step = state.data[0]["step"]
    data = state.data[0].get("data", {"numbers": []})

    if "DONE" in text.upper():
        if not data["numbers"]:
            await send_text(phone, "Please add at least one family number first.")
            return

        db.table("sos_registrations").upsert({
            "walker_phone": phone,
            "family_phones": data["numbers"],
            "active": True
        }).execute()
        db.table("conversation_state").delete().eq("phone", phone).execute()

        # Notify all family
        for fphone in data["numbers"]:
            await send_text(fphone,
                f"Your family member {phone} has registered\n"
                f"for Girivalam safety tracking.\n\n"
                f"If they send SOS — you will be\n"
                f"alerted immediately. 🙏"
            )

        await send_text(phone,
            f"Registered! 🙏\n\n"
            f"{len(data['numbers'])} family members will be\n"
            f"alerted if you send SOS.\n\n"
            f"During Girivalam emergency:\n"
            f"Just send: SOS"
        )
    else:
        # Collect phone number
        number = text.strip().replace(" ", "").replace("-", "")
        if len(number) >= 10:
            data["numbers"].append(number)
            db.table("conversation_state").update({"data": data})\
                .eq("phone", phone).execute()
            await send_text(phone,
                f"Added! {len(data['numbers'])} number(s) saved.\n"
                f"Add more or send DONE to finish."
            )
        else:
            await send_text(phone, "Invalid number. Please enter full phone number.")


async def handle_safe(phone: str) -> None:
    """Walker confirms they are safe after SOS."""
    db = get_db()
    db.table("sos_alerts").update({"resolved": True})\
        .eq("walker_phone", phone)\
        .eq("resolved", False)\
        .execute()

    family_phones = await get_family_phones(phone)
    for fphone in family_phones:
        await send_text(fphone,
            f"UPDATE: Your family member is SAFE! 🙏\n"
            f"Time: now\n"
            f"They have confirmed they are okay."
        )

    await send_text(phone, "Thank goodness you are safe! 🙏\nFamily has been notified.")


async def get_family_phones(walker_phone: str) -> list:
    """Get registered family phones for a walker."""
    db = get_db()
    result = db.table("sos_registrations")\
        .select("family_phones")\
        .eq("walker_phone", walker_phone)\
        .eq("active", True)\
        .execute()
    if result.data:
        return result.data[0].get("family_phones", [])
    return []
```

---

## TEST CASES

```python
# tests/test_feature5.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from src.features.sos import handle_sos, handle_safe, get_family_phones, WALKER_SOS_MESSAGE


class TestSOSCritical:
    """CRITICAL tests — SOS must ALWAYS work."""

    @pytest.mark.asyncio
    async def test_sos_always_sends_medical_info_to_walker(self):
        """Even if everything fails, walker gets medical info."""
        sent_messages = []

        async def mock_send(phone, msg):
            sent_messages.append((phone, msg))

        with patch("src.features.sos.get_family_phones",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.features.sos.get_db"), \
             patch("src.features.sos.send_text", side_effect=mock_send):
            await handle_sos("919WALKER")
            walker_msgs = [m for p, m in sent_messages if p == "919WALKER"]
            assert len(walker_msgs) > 0
            assert "108" in walker_msgs[0] or "medical" in walker_msgs[0].lower()

    @pytest.mark.asyncio
    async def test_sos_alerts_all_family_members(self):
        """SOS must alert EVERY registered family member."""
        sent_to = []

        async def mock_send(phone, msg):
            sent_to.append(phone)

        family = ["919FAM1", "919FAM2", "919FAM3"]

        with patch("src.features.sos.get_family_phones",
                   new_callable=AsyncMock, return_value=family), \
             patch("src.features.sos.get_db", return_value=MagicMock()), \
             patch("src.features.sos.send_text", side_effect=mock_send):
            await handle_sos("919WALKER")
            for fam in family:
                assert fam in sent_to, f"Family member {fam} was NOT alerted!"

    @pytest.mark.asyncio
    async def test_sos_logged_in_database(self):
        """SOS alert must be logged in sos_alerts table."""
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        with patch("src.features.sos.get_family_phones",
                   new_callable=AsyncMock, return_value=["919FAM1"]), \
             patch("src.features.sos.get_db", return_value=mock_db), \
             patch("src.features.sos.send_text", new_callable=AsyncMock):
            await handle_sos("919WALKER")
            mock_db.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_sos_still_sends_to_walker_if_db_fails(self):
        """Even if DB fails, walker must get medical info."""
        sent_messages = []

        async def mock_send(phone, msg):
            sent_messages.append((phone, msg))

        with patch("src.features.sos.get_family_phones",
                   new_callable=AsyncMock, side_effect=Exception("DB down")), \
             patch("src.features.sos.send_text", side_effect=mock_send):
            await handle_sos("919WALKER")
            walker_msgs = [m for p, m in sent_messages if p == "919WALKER"]
            assert len(walker_msgs) > 0

    @pytest.mark.asyncio
    async def test_safe_notifies_all_family(self):
        """SAFE message must notify all registered family."""
        sent_to = []

        async def mock_send(phone, msg):
            sent_to.append(phone)

        family = ["919FAM1", "919FAM2"]
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value\
            .eq.return_value.execute.return_value = MagicMock()

        with patch("src.features.sos.get_family_phones",
                   new_callable=AsyncMock, return_value=family), \
             patch("src.features.sos.get_db", return_value=mock_db), \
             patch("src.features.sos.send_text", side_effect=mock_send):
            await handle_safe("919WALKER")
            for fam in family:
                assert fam in sent_to
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: SOS → walker receives medical info within 2 seconds
[ ] AC-02: SOS → ALL family members receive alert
[ ] AC-03: SOS → logged in sos_alerts table
[ ] AC-04: SOS → works even if DB is down (sends to walker)
[ ] AC-05: SAFE → all family notified
[ ] AC-06: REGISTER → saves family numbers correctly
[ ] AC-07: All tests pass: pytest tests/test_feature5.py -v
[ ] AC-08: REAL TEST: Send SOS from your phone
           Family members must receive within 5 seconds
[ ] AC-09: PERFORMANCE: Response time under 3 seconds
           (Measure with: time curl -X POST /webhook -d '{"from":"SOS"}')
```

---

## COMMON MISTAKES — CRITICAL

```
❌ NEVER use async DB call before sending to walker
   Walker gets medical info FIRST — then DB operations
❌ NEVER let DB failure stop the SOS message to walker
❌ Always use try/except around each family notification
   One failed number must not stop others
❌ Log ALL SOS events — this is safety data
```
