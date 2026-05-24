# Feature 12 — Missing Person Alert — Karthigai Deepam
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities
# LAUNCH DEADLINE: 4 weeks before Karthigai Deepam

---

## WHAT THIS FEATURE DOES

Family group registers before entering Karthigai festival crowd.
If anyone separated — ONE message alerts entire family simultaneously.
Meeting points guide reunion. Rs.49 per family. Free for SOS.

---

## USER STORIES

```
US-01: Family registers before entering crowd. Rs.49 paid.
US-02: Child goes missing → entire family alerted in <5 seconds.
US-03: Elderly person missing → urgent protocol with medical info.
US-04: Person is found → all family get reunion message.
US-05: Police partnership → they announce our number at entry points.
```

---

## SOP

```
4 WEEKS BEFORE KARTHIGAI:
  Set up all 6 meeting points (verify locations)
  Visit police station — present system
  Put posters at bus stand, temple gates

ON REGISTRATION DAY:
  Families register via WhatsApp
  Bot assigns nearest meeting point
  Confirmation sent to all members

ON MISSING ALERT:
  MISSING [name] received
  ALL family members alerted in <5 seconds
  Meeting point sent to everyone
  Police and medical numbers sent

POLICE MEETING POINTS (verify before launch):
  MP1: East Gopuram — Big flagpole at main gate
  MP2: Ramana Ashram main entrance
  MP3: Old Bus Stand (Mofussil)
  MP4: Government Hospital entrance
  MP5: Big Bazaar Street junction
  MP6: Girivalam route km 0 starting point
```

---

## FILE TO CREATE

```
src/features/missing_person.py
```

---

## COMPLETE CODE

```python
# src/features/missing_person.py

"""
Feature 12: Missing Person Alert — Karthigai Deepam
Owner: [Name]
Status: in-progress
CRITICAL: Missing alerts must deliver in under 5 seconds.
"""

from src.database import get_db
from src.whatsapp import send_text
import logging
import uuid
from datetime import date

logger = logging.getLogger(__name__)

EMERGENCY_NUMBERS = (
    "Child helpline: 1098 (FREE)\n"
    "Police: 04175-252222\n"
    "Medical: 04175-252422"
)

MEETING_POINT_DEFAULT = "MP1 — East Gopuram — Big flagpole at main gate"


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for missing person / family registration."""
    text_upper = text.upper()

    if text_upper.startswith("MISSING"):
        await handle_missing_alert(phone, text)
        return

    if text_upper.startswith("FOUND"):
        await handle_found(phone, text)
        return

    if "FAMILY" in text_upper and "REGISTER" in text_upper:
        await start_family_registration(phone, language)
        return

    if "PAID" in text_upper:
        await handle_payment(phone)
        return

    # Check conversation state for ongoing registration
    db = get_db()
    state = db.table("conversation_state")\
        .select("step, data")\
        .eq("phone", phone)\
        .eq("current_feature", "family_register")\
        .execute()

    if state.data:
        await handle_registration_step(phone, text,
                                        state.data[0]["step"],
                                        state.data[0].get("data", {}))
        return

    # Default — show info
    await send_text(phone,
        "Karthigai Family Safety 🙏\n\n"
        "Register your family so everyone stays connected.\n"
        "If anyone separated — entire family alerted instantly.\n\n"
        "To register: Reply FAMILY REGISTER\n"
        "Cost: Rs.49 per family group"
    )


async def handle_missing_alert(phone: str, text: str) -> None:
    """
    CRITICAL: Handle MISSING alert.
    Must complete in under 5 seconds.
    """
    try:
        # Parse missing person details
        parts = text.strip().split(maxsplit=1)
        missing_info = parts[1] if len(parts) > 1 else "Family member"

        # Determine person type
        is_child = any(w in text.upper() for w in
                       ["BOY", "GIRL", "CHILD", "KID", "BABY", "SON", "DAUGHTER"])
        is_elderly = any(w in text.upper() for w in
                         ["ELDERLY", "OLD", "SENIOR", "VAYASAL"])

        # Get family members
        family_members = await get_family_members(phone)
        meeting_point = await get_meeting_point(phone)

        # Build alert message
        urgency = "URGENT — ELDERLY PERSON MISSING! 🚨" if is_elderly else \
                  "URGENT — MISSING PERSON! 🚨"
        alert_type = " (CHILD — ACT IMMEDIATELY)" if is_child else ""

        alert_msg = (
            f"{urgency}{alert_type}\n\n"
            f"{missing_info} reported missing\n"
            f"Time: now\n\n"
            f"GO TO MEETING POINT:\n"
            f"{meeting_point}\n"
            f"STAY THERE — DO NOT SEARCH ALONE\n\n"
            f"{EMERGENCY_NUMBERS}\n\n"
            f"Share with people around you:\n"
            f"'{missing_info} — If found call: {phone}'"
        )

        # Send to reporter first
        await send_text(phone, f"Alert sent to family! 🚨\n\n{alert_msg}")

        # Alert all family members
        notified = 0
        for member in family_members:
            if member["phone"] != phone:
                try:
                    member_msg = (
                        f"{urgency}\n\n"
                        f"{missing_info} reported by your family member.\n\n"
                        f"GO TO: {meeting_point}\n\n"
                        f"{EMERGENCY_NUMBERS}\n\n"
                        f"Call reporter: {phone}"
                    )
                    await send_text(member["phone"], member_msg)
                    notified += 1
                except Exception as e:
                    logger.error(f"Alert failed to {member['phone']}: {e}")

        # Log alert
        db = get_db()
        group_id = await get_group_id(phone)
        db.table("missing_alerts").insert({
            "group_id": group_id,
            "reported_by": phone,
            "missing_person": missing_info,
            "person_type": "child" if is_child else "elderly" if is_elderly else "adult",
            "family_notified": True
        }).execute()

        logger.warning(f"Missing alert: {missing_info} by {phone}. {notified} family notified.")

    except Exception as e:
        logger.error(f"Missing alert CRITICAL ERROR for {phone}: {e}")
        # Ensure reporter always gets emergency numbers
        await send_text(phone,
            f"Emergency numbers:\n{EMERGENCY_NUMBERS}"
        )


async def handle_found(phone: str, text: str) -> None:
    """Handle FOUND notification."""
    parts = text.strip().split(maxsplit=1)
    found_info = parts[1] if len(parts) > 1 else "Family member"

    family_members = await get_family_members(phone)
    meeting_point = await get_meeting_point(phone)

    found_msg = (
        f"{found_info} HAS BEEN FOUND! 🙏\n\n"
        f"Go to: {meeting_point}\n\n"
        f"Call this number: {phone}"
    )

    for member in family_members:
        try:
            await send_text(member["phone"], found_msg)
        except Exception as e:
            logger.error(f"Found notification failed to {member['phone']}: {e}")

    # Update alert as resolved
    db = get_db()
    db.table("missing_alerts").update({"found": True})\
        .eq("reported_by", phone)\
        .eq("found", False)\
        .execute()

    await send_text(phone, f"Great! Family notified that {found_info} is found. 🙏")


async def start_family_registration(phone: str, language: str) -> None:
    """Begin family registration process."""
    db = get_db()
    db.table("conversation_state").upsert({
        "phone": phone,
        "current_feature": "family_register",
        "step": "collect_members",
        "data": {"members": [{"name": "You", "phone": phone}]}
    }).execute()

    await send_text(phone,
        "Karthigai Family Safety Registration 🙏\n\n"
        "Add family member WhatsApp numbers.\n"
        "Send: MEMBER [name] [phone]\n\n"
        "Example: MEMBER Priya 94XXXXXXXXXX\n\n"
        "Add all members then send: DONE"
    )


async def handle_registration_step(phone: str, text: str,
                                    step: str, data: dict) -> None:
    """Handle each step of family registration."""
    db = get_db()
    text_upper = text.upper()

    if text_upper == "DONE":
        members = data.get("members", [])
        if len(members) < 2:
            await send_text(phone, "Add at least one more family member before DONE.")
            return

        # Assign meeting point
        meeting_point = await assign_meeting_point()

        # Save registration
        group_id = f"KTG-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        db.table("conversation_state").update({
            "step": "await_payment",
            "data": {**data, "group_id": group_id, "meeting_point": meeting_point}
        }).eq("phone", phone).execute()

        member_list = "\n".join([f"  {m['name']}: {m['phone']}"
                                  for m in members])
        await send_text(phone,
            f"Registration summary:\n\n"
            f"Members:\n{member_list}\n\n"
            f"Meeting point if separated:\n"
            f"{meeting_point}\n\n"
            f"Pay Rs.49 to confirm:\n"
            f"UPI: arunachala@ybl\n"
            f"Note: {group_id}\n\n"
            f"Reply PAID to activate"
        )

    elif text_upper.startswith("MEMBER"):
        parts = text.strip().split()
        if len(parts) >= 3:
            name = parts[1]
            member_phone = parts[2].replace("-", "").replace(" ", "")
            members = data.get("members", [])
            members.append({"name": name, "phone": member_phone})
            data["members"] = members
            db.table("conversation_state").update({"data": data})\
                .eq("phone", phone).execute()
            await send_text(phone,
                f"Added {name}. {len(members)} members total.\n"
                f"Add more or send DONE"
            )
        else:
            await send_text(phone, "Format: MEMBER [name] [phone]\nExample: MEMBER Priya 94XXXXXXXXXX")


async def handle_payment(phone: str) -> None:
    """Activate registration after payment."""
    db = get_db()
    state = db.table("conversation_state")\
        .select("data")\
        .eq("phone", phone)\
        .eq("current_feature", "family_register")\
        .execute()

    if not state.data:
        await send_text(phone, "No pending registration. Send FAMILY REGISTER to start.")
        return

    data = state.data[0]["data"]
    group_id = data.get("group_id")
    members = data.get("members", [])
    meeting_point = data.get("meeting_point", MEETING_POINT_DEFAULT)

    # Save family group
    db.table("family_groups").insert({
        "group_id": group_id,
        "festival_date": date.today().isoformat(),
        "registered_by": phone,
        "meeting_point": meeting_point,
        "member_count": len(members),
        "payment_done": True,
        "active": True
    }).execute()

    # Save all members
    for member in members:
        db.table("family_members").insert({
            "group_id": group_id,
            "name": member["name"],
            "phone": member["phone"],
            "is_emergency": member.get("is_emergency", False)
        }).execute()

    db.table("conversation_state").delete().eq("phone", phone).execute()

    # Notify all family members
    for member in members:
        await send_text(member["phone"],
            f"Family safety registered! 🙏\n\n"
            f"Group: {group_id}\n"
            f"If separated — send MISSING [name]\n\n"
            f"Your meeting point:\n{meeting_point}\n\n"
            f"Stay safe at Karthigai! 🙏"
        )

    await send_text(phone,
        f"Registration ACTIVE! 🙏\n\n"
        f"Group: {group_id}\n"
        f"Members: {len(members)}\n"
        f"Meeting point: {meeting_point}\n\n"
        f"If anyone separated: Send MISSING [name]\n"
        f"If found: Send FOUND [name]\n\n"
        f"Have a blessed Karthigai! 🙏"
    )


async def get_family_members(phone: str) -> list:
    """Get all family members for a registered phone."""
    db = get_db()
    group = db.table("family_groups")\
        .select("group_id")\
        .eq("registered_by", phone)\
        .eq("active", True)\
        .execute()

    if not group.data:
        # Also check if phone is a member (not registrant)
        member_check = db.table("family_members")\
            .select("group_id")\
            .eq("phone", phone)\
            .execute()
        if not member_check.data:
            return []
        group_id = member_check.data[0]["group_id"]
    else:
        group_id = group.data[0]["group_id"]

    members = db.table("family_members")\
        .select("name, phone")\
        .eq("group_id", group_id)\
        .execute()
    return members.data or []


async def get_group_id(phone: str) -> str | None:
    """Get group ID for a phone number."""
    db = get_db()
    result = db.table("family_groups")\
        .select("group_id")\
        .eq("registered_by", phone)\
        .execute()
    if result.data:
        return result.data[0]["group_id"]
    return None


async def get_meeting_point(phone: str) -> str:
    """Get assigned meeting point for family group."""
    db = get_db()
    result = db.table("family_groups")\
        .select("meeting_point")\
        .eq("registered_by", phone)\
        .execute()
    if result.data:
        return result.data[0].get("meeting_point", MEETING_POINT_DEFAULT)
    return MEETING_POINT_DEFAULT


async def assign_meeting_point() -> str:
    """Assign a meeting point (simple round-robin for now)."""
    db = get_db()
    points = db.table("meeting_points")\
        .select("code, name")\
        .eq("active", True)\
        .execute()
    if points.data:
        return f"{points.data[0]['code']} — {points.data[0]['name']}"
    return MEETING_POINT_DEFAULT
```

---

## TEST CASES

```python
# tests/test_feature12.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.missing_person import (
    handle_missing_alert, handle_found, handle, EMERGENCY_NUMBERS
)


class TestMissingAlertCritical:
    """CRITICAL: Missing alerts must always deliver."""

    @pytest.mark.asyncio
    async def test_missing_alert_always_sends_to_reporter(self):
        """Reporter MUST always get emergency info."""
        sent = []
        async def mock_send(phone, msg):
            sent.append((phone, msg))

        with patch("src.features.missing_person.get_family_members",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.features.missing_person.get_meeting_point",
                   new_callable=AsyncMock, return_value="MP1 — East Gopuram"), \
             patch("src.features.missing_person.get_db", return_value=MagicMock()), \
             patch("src.features.missing_person.get_group_id",
                   new_callable=AsyncMock, return_value="KTG-001"), \
             patch("src.features.missing_person.send_text", side_effect=mock_send):
            await handle_missing_alert("919REPORTER", "MISSING Arjun boy 8")
            reporter_msgs = [m for p, m in sent if p == "919REPORTER"]
            assert len(reporter_msgs) > 0

    @pytest.mark.asyncio
    async def test_missing_alert_sends_to_all_family(self):
        """Every family member must receive alert."""
        sent_to = []
        async def mock_send(phone, msg):
            sent_to.append(phone)

        family = [
            {"phone": "919FAM1", "name": "Priya"},
            {"phone": "919FAM2", "name": "Rajan"},
        ]

        with patch("src.features.missing_person.get_family_members",
                   new_callable=AsyncMock, return_value=family), \
             patch("src.features.missing_person.get_meeting_point",
                   new_callable=AsyncMock, return_value="MP1"), \
             patch("src.features.missing_person.get_db", return_value=MagicMock()), \
             patch("src.features.missing_person.get_group_id",
                   new_callable=AsyncMock, return_value="KTG-001"), \
             patch("src.features.missing_person.send_text", side_effect=mock_send):
            await handle_missing_alert("919REPORTER", "MISSING Arjun")
            assert "919FAM1" in sent_to
            assert "919FAM2" in sent_to

    @pytest.mark.asyncio
    async def test_child_missing_adds_urgency(self):
        """Child missing alert must be marked as urgent."""
        sent = []
        async def mock_send(phone, msg):
            sent.append((phone, msg))

        with patch("src.features.missing_person.get_family_members",
                   new_callable=AsyncMock, return_value=[{"phone": "919FAM1", "name": "X"}]), \
             patch("src.features.missing_person.get_meeting_point",
                   new_callable=AsyncMock, return_value="MP1"), \
             patch("src.features.missing_person.get_db", return_value=MagicMock()), \
             patch("src.features.missing_person.get_group_id",
                   new_callable=AsyncMock, return_value="KTG-001"), \
             patch("src.features.missing_person.send_text", side_effect=mock_send):
            await handle_missing_alert("919REPORTER", "MISSING Arjun BOY 8")
            all_messages = " ".join([m for _, m in sent])
            assert "CHILD" in all_messages or "child" in all_messages.lower()

    @pytest.mark.asyncio
    async def test_found_notification_sent_to_all_family(self):
        """FOUND must notify all family members."""
        sent_to = []
        async def mock_send(phone, msg):
            sent_to.append(phone)

        family = [
            {"phone": "919FAM1", "name": "P"},
            {"phone": "919FAM2", "name": "R"},
        ]
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value\
            .eq.return_value.execute.return_value = MagicMock()

        with patch("src.features.missing_person.get_family_members",
                   new_callable=AsyncMock, return_value=family), \
             patch("src.features.missing_person.get_meeting_point",
                   new_callable=AsyncMock, return_value="MP1"), \
             patch("src.features.missing_person.get_db", return_value=mock_db), \
             patch("src.features.missing_person.send_text", side_effect=mock_send):
            await handle_found("919REPORTER", "FOUND Arjun")
            assert "919FAM1" in sent_to
            assert "919FAM2" in sent_to

    @pytest.mark.asyncio
    async def test_emergency_numbers_in_missing_alert(self):
        """Emergency numbers must be in every missing alert."""
        sent = []
        async def mock_send(phone, msg):
            sent.append(msg)

        with patch("src.features.missing_person.get_family_members",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.features.missing_person.get_meeting_point",
                   new_callable=AsyncMock, return_value="MP1"), \
             patch("src.features.missing_person.get_db", return_value=MagicMock()), \
             patch("src.features.missing_person.get_group_id",
                   new_callable=AsyncMock, return_value=None), \
             patch("src.features.missing_person.send_text", side_effect=mock_send):
            await handle_missing_alert("919REPORTER", "MISSING Arjun")
            all_text = " ".join(sent)
            assert "1098" in all_text or "252222" in all_text
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: MISSING [name] → reporter gets alert with meeting point
[ ] AC-02: MISSING [name] → ALL family members alerted
[ ] AC-03: Child missing → CHILD urgency added to message
[ ] AC-04: Elderly missing → medical point check suggested
[ ] AC-05: FOUND [name] → all family members notified
[ ] AC-06: Emergency numbers (1098, 252222) in every alert
[ ] AC-07: Alert reaches family in under 5 seconds
[ ] AC-08: Registration → group saved in DB
[ ] AC-09: All tests pass: pytest tests/test_feature12.py -v
[ ] AC-10: REAL TEST: Simulate missing alert with 3 test phones
            All 3 phones must receive in under 5 seconds
[ ] AC-11: Meeting points table filled before launch
```
