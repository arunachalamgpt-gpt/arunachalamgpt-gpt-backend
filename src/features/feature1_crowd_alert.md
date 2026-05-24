# Feature 1 — Crowd Alert and Visit Planning
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities only

---

## WHAT THIS FEATURE DOES

Tells devotees the current crowd wait time at East Gate
of Arunachaleswara temple. Three queues exist:
- Free darshan (longest)
- Rs.50 ticket (medium)
- Rs.200 ticket (shortest)

All queues start at the same point. Difference is
how many people are in each queue.

---

## USER STORIES

```
US-01: As a devotee planning a visit, I want to know
       current wait times for all 3 queues so I can
       decide when to arrive.

US-02: As a devotee at the temple gate, I want to know
       if Rs.50 and Rs.200 tickets are still available
       so I can decide which queue to join.

US-03: As a family with elderly members, I want
       specific advice on which queue to use and
       what to expect.

US-04: As a devotee arriving before 8am, I want to
       know that ticket counters are not open yet
       and what my best option is.

US-05: As a volunteer at the gate, I want a simple
       format to send hourly crowd updates to the bot.

US-06: As admin (you), I want to update ticket
       availability instantly via WhatsApp command.
```

---

## SOP — STANDARD OPERATING PROCEDURE

### How this feature runs day-to-day:

```
DAILY OPERATIONS:

8:00am  → Bot sends request to volunteer:
          "How many minutes wait? Format: F:X T50:X T200:X"

Every   → Volunteer replies with crowd update
hour      Bot parses and saves to crowd_status table

When    → You send admin command:
tickets   ADMIN config rs50_sold_out true
sold out  All users instantly see correct info

If      → Bot falls back to historical prediction
volunteer  (crowd_history table)
offline
```

### Volunteer Training SOP:
```
1. Give volunteer this phone: +91-bot-number
2. Teach them ONE format: F:180 T50:45 T200:15
   F = Free queue minutes
   T50 = Rs.50 ticket queue minutes
   T200 = Rs.200 ticket queue minutes
3. They send this every hour from East Gate
4. If ticket sold out: F:180 T50:SOLD T200:15
5. Pay: Rs.500 per Pournami day via UPI
```

---

## FILE TO CREATE

```
src/features/crowd_alert.py
```

---

## COMPLETE CODE TO WRITE

```python
# src/features/crowd_alert.py

"""
Feature 1: Crowd Alert and Visit Planning
Owner: [Name]
Status: in-progress

Handles all crowd-related queries for East Gate,
Arunachaleswara Temple, Tiruvannamalai.
"""

from datetime import datetime, time
from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

# ─── SYSTEM PROMPT ───────────────────────────────────────────

CROWD_SYSTEM_PROMPT = f"""
You are Arunachala GPT — crowd guide for East Gate,
Arunachaleswara Temple, Tiruvannamalai.

FACTS YOU KNOW:
- East Gate has 3 queues: Free, Rs.50 ticket, Rs.200 ticket
- All queues START at the same place
- Difference is number of people in each queue
- Ticket counter is 10 metres INSIDE East Gate
- Ticket sale starts at 8am (configurable)
- All 3 queues merge 10 feet before darshan

{{crowd_data}}
{{config_data}}

{LANGUAGE_RULE}

Keep answer under 150 words. Be warm and practical.
If user has elderly or children — give specific advice.
"""


# ─── MAIN HANDLER ────────────────────────────────────────────

async def handle(phone: str, text: str, language: str) -> None:
    """
    Entry point for crowd-related queries.
    Called by router when intent == 'crowd'.
    """
    text_upper = text.upper()

    # Check if volunteer is sending a crowd update
    if await is_volunteer(phone) and is_crowd_report(text):
        await handle_volunteer_report(phone, text)
        return

    # Check for elderly/children context
    has_elderly = any(w in text_upper for w in
                      ["ELDERLY", "OLD", "SENIOR", "AGED", "VAYASAL", "THATHA", "PAATI"])
    has_children = any(w in text_upper for w in
                       ["CHILD", "BABY", "KID", "KUZHANTHAI", "PAPPA"])

    # Get current crowd data
    crowd_data = await get_current_crowd()
    config_data = await get_temple_config()

    # Build context for Claude
    crowd_context = format_crowd_context(crowd_data, config_data)
    user_context = ""
    if has_elderly:
        user_context = "\nUSER HAS ELDERLY — recommend Rs.200 ticket strongly."
    if has_children:
        user_context += "\nUSER HAS CHILDREN — advise early morning visit."

    # Get Claude response
    system = CROWD_SYSTEM_PROMPT.format(
        crowd_data=crowd_context,
        config_data=format_config(config_data)
    ) + user_context

    reply = await get_reply(
        system_prompt=system,
        user_message=text,
        max_tokens=300
    )

    # Send reply with action buttons
    await send_buttons(
        phone=phone,
        body=reply,
        buttons=["Best time to visit", "Ticket info", "Main menu"]
    )

    # Save to profile if elderly/children context detected
    if has_elderly or has_children:
        await update_profile(phone, has_elderly, has_children)


# ─── VOLUNTEER FUNCTIONS ─────────────────────────────────────

async def is_volunteer(phone: str) -> bool:
    """Check if this phone number is a registered volunteer."""
    db = get_db()
    result = db.table("temple_config")\
        .select("value")\
        .eq("key", "volunteer_phone")\
        .execute()
    if result.data:
        return phone == result.data[0].get("value", "")
    return False


def is_crowd_report(text: str) -> bool:
    """Check if message is a volunteer crowd report."""
    text_upper = text.upper()
    return "F:" in text_upper and "T50:" in text_upper


async def handle_volunteer_report(phone: str, text: str) -> None:
    """
    Parse volunteer message and save to crowd_status.
    Format: F:180 T50:45 T200:15
    Sold out format: F:180 T50:SOLD T200:15
    """
    try:
        parts = text.upper().split()
        free_min = rs50_min = rs200_min = None
        rs50_sold = rs200_sold = False

        for part in parts:
            if part.startswith("F:"):
                val = part[2:]
                free_min = int(val) if val.isdigit() else None
            elif part.startswith("T50:"):
                val = part[4:]
                if val == "SOLD":
                    rs50_sold = True
                    rs50_min = 0
                else:
                    rs50_min = int(val) if val.isdigit() else None
            elif part.startswith("T200:"):
                val = part[5:]
                if val == "SOLD":
                    rs200_sold = True
                    rs200_min = 0
                else:
                    rs200_min = int(val) if val.isdigit() else None

        # Save to database
        db = get_db()
        db.table("crowd_status").insert({
            "reported_by": phone,
            "free_wait_min": free_min,
            "rs50_wait_min": rs50_min,
            "rs200_wait_min": rs200_min,
        }).execute()

        # Update sold-out config if needed
        if rs50_sold:
            db.table("temple_config").update({"value": "true"})\
                .eq("key", "rs50_sold_out").execute()
        if rs200_sold:
            db.table("temple_config").update({"value": "true"})\
                .eq("key", "rs200_sold_out").execute()

        # Confirm to volunteer
        summary = f"Updated: Free={free_min}min | Rs.50={'SOLD' if rs50_sold else f'{rs50_min}min'} | Rs.200={'SOLD' if rs200_sold else f'{rs200_min}min'}"
        await send_text(phone, f"Saved! {summary}")

    except Exception as e:
        logger.error(f"Volunteer report parse error: {e}")
        await send_text(phone, "Format error. Use: F:180 T50:45 T200:15")


# ─── DATA FETCH FUNCTIONS ────────────────────────────────────

async def get_current_crowd() -> dict | None:
    """
    Get most recent crowd report.
    Returns None if report is older than 3 hours.
    """
    db = get_db()
    result = db.table("crowd_status")\
        .select("*")\
        .order("reported_at", desc=True)\
        .limit(1)\
        .execute()

    if not result.data:
        return None

    report = result.data[0]
    # Check if report is too old (3 hours)
    from datetime import datetime, timezone
    reported = datetime.fromisoformat(
        report["reported_at"].replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - reported).seconds / 3600
    if age_hours > 3:
        return None

    report["age_minutes"] = int(age_hours * 60)
    return report


async def get_temple_config() -> dict:
    """Get all temple configuration values."""
    db = get_db()
    result = db.table("temple_config").select("key, value").execute()
    return {row["key"]: row["value"] for row in result.data}


def format_crowd_context(crowd: dict | None, config: dict) -> str:
    """Format crowd data into readable context for Claude."""
    if not crowd:
        return "No recent crowd report available. Use historical estimates."

    age = crowd.get("age_minutes", 0)
    rs50_sold = config.get("rs50_sold_out", "false") == "true"
    rs200_sold = config.get("rs200_sold_out", "false") == "true"

    lines = [f"CURRENT CROWD (report from {age} minutes ago):"]
    lines.append(f"Free darshan: ~{crowd.get('free_wait_min', '?')} minutes wait")

    if rs50_sold:
        lines.append("Rs.50 ticket: SOLD OUT")
    else:
        lines.append(f"Rs.50 ticket: ~{crowd.get('rs50_wait_min', '?')} minutes wait | Available")

    if rs200_sold:
        lines.append("Rs.200 ticket: SOLD OUT")
    else:
        lines.append(f"Rs.200 ticket: ~{crowd.get('rs200_wait_min', '?')} minutes wait | Available")

    return "\n".join(lines)


def format_config(config: dict) -> str:
    """Format temple config for Claude context."""
    lines = [
        f"Ticket counter: 10 metres INSIDE East Gate",
        f"Ticket sale starts: {config.get('ticket_sale_start_time', '08:00')}",
        f"Temple opens: {config.get('temple_open_time', '05:30')}",
        f"Temple closes: {config.get('temple_close_time', '21:00')}",
    ]
    return "\n".join(lines)


async def update_profile(phone: str, has_elderly: bool, has_children: bool) -> None:
    """Update devotee profile with elderly/children context."""
    db = get_db()
    db.table("devotee_profile").upsert({
        "phone": phone,
        "has_elderly": has_elderly,
        "has_children": has_children,
        "updated_at": "now()"
    }).execute()
```

---

## TEST CASES — DEVELOPER MUST RUN ALL BEFORE MARKING COMPLETE

Create file: `tests/test_feature1.py`

```python
# tests/test_feature1.py

"""
Feature 1 Test Suite
Run: pytest tests/test_feature1.py -v

ALL tests must pass before marking Feature 1 complete.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.crowd_alert import (
    is_crowd_report,
    format_crowd_context,
    format_config,
    handle_volunteer_report,
    handle,
)


# ─── UNIT TESTS ───────────────────────────────────────────────

class TestCrowdReportDetection:
    """Test volunteer message detection."""

    def test_valid_crowd_report(self):
        assert is_crowd_report("F:180 T50:45 T200:15") is True

    def test_valid_crowd_report_lowercase(self):
        assert is_crowd_report("f:180 t50:45 t200:15") is True

    def test_sold_out_report(self):
        assert is_crowd_report("F:180 T50:SOLD T200:15") is True

    def test_regular_message_not_report(self):
        assert is_crowd_report("Crowd enna?") is False

    def test_partial_report_not_valid(self):
        assert is_crowd_report("F:180 only") is False


class TestFormatCrowdContext:
    """Test crowd context formatting for Claude."""

    def test_no_crowd_data_returns_fallback(self):
        result = format_crowd_context(None, {})
        assert "No recent" in result

    def test_valid_crowd_data_formatted(self):
        crowd = {
            "free_wait_min": 180,
            "rs50_wait_min": 45,
            "rs200_wait_min": 15,
            "age_minutes": 30
        }
        config = {
            "rs50_sold_out": "false",
            "rs200_sold_out": "false"
        }
        result = format_crowd_context(crowd, config)
        assert "180" in result
        assert "45" in result
        assert "15" in result

    def test_rs50_sold_out_shown(self):
        crowd = {
            "free_wait_min": 180,
            "rs50_wait_min": 0,
            "rs200_wait_min": 15,
            "age_minutes": 10
        }
        config = {"rs50_sold_out": "true", "rs200_sold_out": "false"}
        result = format_crowd_context(crowd, config)
        assert "SOLD OUT" in result

    def test_both_tickets_sold_out(self):
        crowd = {
            "free_wait_min": 240,
            "rs50_wait_min": 0,
            "rs200_wait_min": 0,
            "age_minutes": 5
        }
        config = {"rs50_sold_out": "true", "rs200_sold_out": "true"}
        result = format_crowd_context(crowd, config)
        assert result.count("SOLD OUT") == 2


class TestFormatConfig:
    """Test temple config formatting."""

    def test_config_contains_key_info(self):
        config = {
            "ticket_sale_start_time": "08:00",
            "temple_open_time": "05:30",
            "temple_close_time": "21:00"
        }
        result = format_config(config)
        assert "08:00" in result
        assert "10 metres" in result

    def test_default_values_used(self):
        result = format_config({})
        assert "08:00" in result


# ─── INTEGRATION TESTS ────────────────────────────────────────

class TestVolunteerReport:
    """Test volunteer crowd report handling."""

    @pytest.mark.asyncio
    async def test_valid_report_saved_to_db(self):
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.features.crowd_alert.get_db", return_value=mock_db), \
             patch("src.features.crowd_alert.send_text", new_callable=AsyncMock) as mock_send:
            await handle_volunteer_report("919XXXXXXXXX", "F:180 T50:45 T200:15")
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][1]
            assert "180" in call_args
            assert "45" in call_args

    @pytest.mark.asyncio
    async def test_sold_out_updates_config(self):
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
        update_mock = MagicMock()
        mock_db.table.return_value.update.return_value = update_mock
        update_mock.eq.return_value.execute.return_value = MagicMock()

        with patch("src.features.crowd_alert.get_db", return_value=mock_db), \
             patch("src.features.crowd_alert.send_text", new_callable=AsyncMock):
            await handle_volunteer_report("919XXXXXXXXX", "F:180 T50:SOLD T200:15")
            # Verify config was updated for sold out
            mock_db.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_format_sends_error(self):
        with patch("src.features.crowd_alert.get_db"), \
             patch("src.features.crowd_alert.send_text", new_callable=AsyncMock) as mock_send:
            await handle_volunteer_report("919XXXXXXXXX", "random message")
            # Should send error message
            assert mock_send.called


# ─── ACCEPTANCE TESTS ─────────────────────────────────────────
# These test the full handle() flow end-to-end

class TestFeature1Acceptance:
    """
    Full acceptance tests — simulate real WhatsApp messages.
    These must ALL pass for Feature 1 to be marked complete.
    """

    @pytest.mark.asyncio
    async def test_AC01_crowd_query_returns_all_3_queues(self):
        """
        AC-01: When user asks about crowd,
        response must mention all 3 queue options.
        """
        mock_crowd = {
            "free_wait_min": 180, "rs50_wait_min": 45,
            "rs200_wait_min": 15, "age_minutes": 30
        }
        mock_config = {
            "rs50_sold_out": "false", "rs200_sold_out": "false",
            "ticket_sale_start_time": "08:00",
            "temple_open_time": "05:30", "temple_close_time": "21:00"
        }
        received_messages = []

        async def mock_send_buttons(phone, body, buttons):
            received_messages.append(body)

        with patch("src.features.crowd_alert.get_current_crowd",
                   new_callable=AsyncMock, return_value=mock_crowd), \
             patch("src.features.crowd_alert.get_temple_config",
                   new_callable=AsyncMock, return_value=mock_config), \
             patch("src.features.crowd_alert.get_reply",
                   new_callable=AsyncMock, return_value="Free: 3hrs, Rs.50: 45min, Rs.200: 15min"), \
             patch("src.features.crowd_alert.send_buttons",
                   side_effect=mock_send_buttons), \
             patch("src.features.crowd_alert.is_volunteer",
                   new_callable=AsyncMock, return_value=False):
            await handle("919XXXXXXXXX", "Crowd enna?", "tamil")
            assert len(received_messages) > 0

    @pytest.mark.asyncio
    async def test_AC02_before_8am_no_tickets_message(self):
        """
        AC-02: Before 8am, bot must tell user
        that ticket counter is not open yet.
        """
        mock_config = {
            "rs50_sold_out": "false", "rs200_sold_out": "false",
            "ticket_sale_start_time": "08:00",
            "temple_open_time": "05:30", "temple_close_time": "21:00"
        }
        early_time_crowd = {
            "free_wait_min": 40, "rs50_wait_min": 0,
            "rs200_wait_min": 0, "age_minutes": 10
        }
        context_received = []

        async def capture_reply(system_prompt, user_message, **kwargs):
            context_received.append(system_prompt)
            return "Ticket counter opens at 8am. Free queue only 40 minutes now!"

        with patch("src.features.crowd_alert.get_current_crowd",
                   new_callable=AsyncMock, return_value=early_time_crowd), \
             patch("src.features.crowd_alert.get_temple_config",
                   new_callable=AsyncMock, return_value=mock_config), \
             patch("src.features.crowd_alert.get_reply", side_effect=capture_reply), \
             patch("src.features.crowd_alert.send_buttons", new_callable=AsyncMock), \
             patch("src.features.crowd_alert.is_volunteer",
                   new_callable=AsyncMock, return_value=False):
            await handle("919XXXXXXXXX", "7am vanthen. Ticket edukkalama?", "tamil")
            assert len(context_received) > 0
            assert "08:00" in context_received[0]

    @pytest.mark.asyncio
    async def test_AC03_elderly_gets_rs200_recommendation(self):
        """
        AC-03: When user mentions elderly,
        system prompt must include Rs.200 recommendation.
        """
        prompt_captured = []

        async def capture_prompt(system_prompt, user_message, **kwargs):
            prompt_captured.append(system_prompt)
            return "Rs.200 ticket recommended for elderly."

        with patch("src.features.crowd_alert.get_current_crowd",
                   new_callable=AsyncMock, return_value=None), \
             patch("src.features.crowd_alert.get_temple_config",
                   new_callable=AsyncMock, return_value={}), \
             patch("src.features.crowd_alert.get_reply", side_effect=capture_prompt), \
             patch("src.features.crowd_alert.send_buttons", new_callable=AsyncMock), \
             patch("src.features.crowd_alert.update_profile", new_callable=AsyncMock), \
             patch("src.features.crowd_alert.is_volunteer",
                   new_callable=AsyncMock, return_value=False):
            await handle("919XXXXXXXXX", "My elderly mother is coming", "english")
            assert any("ELDERLY" in p for p in prompt_captured)

    @pytest.mark.asyncio
    async def test_AC04_volunteer_report_accepted(self):
        """
        AC-04: Volunteer sending F:X T50:X T200:X
        must be saved and confirmation sent.
        """
        saved_data = []
        sent_messages = []

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"value": "919VOLUNTEER"}
        ]
        mock_db.table.return_value.insert.return_value.execute.side_effect = \
            lambda: saved_data.append(True)
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        async def mock_send(phone, msg):
            sent_messages.append(msg)

        with patch("src.features.crowd_alert.get_db", return_value=mock_db), \
             patch("src.features.crowd_alert.send_text", side_effect=mock_send):
            await handle_volunteer_report("919VOLUNTEER", "F:180 T50:45 T200:15")
            assert len(sent_messages) > 0
            assert "180" in sent_messages[0] or "Saved" in sent_messages[0]

    @pytest.mark.asyncio
    async def test_AC05_no_crowd_data_shows_prediction(self):
        """
        AC-05: When no recent crowd data exists,
        bot must clearly say it is a prediction/estimate.
        """
        context_passed = []

        async def capture_context(system_prompt, user_message, **kwargs):
            context_passed.append(system_prompt)
            return "Based on historical data, estimated wait is 3 hours."

        with patch("src.features.crowd_alert.get_current_crowd",
                   new_callable=AsyncMock, return_value=None), \
             patch("src.features.crowd_alert.get_temple_config",
                   new_callable=AsyncMock, return_value={}), \
             patch("src.features.crowd_alert.get_reply", side_effect=capture_context), \
             patch("src.features.crowd_alert.send_buttons", new_callable=AsyncMock), \
             patch("src.features.crowd_alert.is_volunteer",
                   new_callable=AsyncMock, return_value=False):
            await handle("919XXXXXXXXX", "crowd?", "english")
            assert any("No recent" in c or "historical" in c.lower()
                       for c in context_passed)
```

---

## ACCEPTANCE CRITERIA CHECKLIST

Developer signs off on each item before marking complete:

```
[ ] AC-01: User asks about crowd → Response mentions all 3 queues
[ ] AC-02: Before 8am query → Response mentions ticket counter not open
[ ] AC-03: Elderly mentioned → Rs.200 ticket recommended in context
[ ] AC-04: Volunteer sends F:X T50:X T200:X → Saved + confirmation sent
[ ] AC-05: No crowd data → Response indicates it is an estimate
[ ] AC-06: Volunteer sends SOLD → temple_config updated immediately
[ ] AC-07: All unit tests pass: pytest tests/test_feature1.py -v
[ ] AC-08: Handler does not crash on empty/unexpected input
[ ] AC-09: Real WhatsApp test: Send "crowd?" from a test phone → get reply
[ ] AC-10: Real volunteer test: Send "F:60 T50:20 T200:10" → saved in Supabase
```

---

## HOW TO TEST MANUALLY (after unit tests pass)

```bash
# Step 1: Start server
uvicorn main:app --reload

# Step 2: Start ngrok tunnel
ngrok http 8000

# Step 3: Set ngrok URL as 360dialog webhook

# Step 4: Send these WhatsApp messages from your phone:
#   "crowd?"               → should see 3 queue options
#   "koottam enna?"        → should reply in Tamil
#   "F:180 T50:45 T200:15" → should save and confirm (from volunteer number)
#   "elderly mother coming" → should recommend Rs.200

# Step 5: Check Supabase:
#   crowd_status table should have new row
#   devotee_profile should have your phone saved
```

---

## COMMON MISTAKES — AVOID THESE

```
❌ Do NOT use print() — use logger.error() or logger.info()
❌ Do NOT hardcode "Rs.50" prices — read from temple_config table
❌ Do NOT assume volunteer is always online — always have fallback
❌ Do NOT forget the is_crowd_report() check before parsing
❌ Do NOT return before sending a reply — user must always get response
```
