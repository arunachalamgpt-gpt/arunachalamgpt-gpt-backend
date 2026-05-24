# Feature 7 — Ashram Satsang Calendar
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Daily 7am WhatsApp to all subscribers with today's complete
ashram program schedule, visiting teachers, and special events.
Rs.99/month subscription. First 7 days free trial.

---

## USER STORIES

```
US-01: Long-stay devotee subscribes for daily updates.
US-02: NRI devotee receives daily programs from Arunachala.
US-03: Devotee queries specific ashram schedule.
US-04: Admin adds visiting teacher announcement.
US-05: Day 7 trial expiry reminder sent automatically.
US-06: Subscriber cancels by sending STOP.
```

---

## SOP

```
WEEKLY (20 minutes every Sunday):
  WhatsApp each ashram contact:
  "Any special programs or visiting teachers this week?"
  Update special_events table with replies

DAILY AUTOMATIC (7am):
  Scheduler triggers send_daily_update()
  Query today's fixed programs + special events
  Send to all active subscribers

WHEN VISITING TEACHER ANNOUNCES:
  They pay Rs.500 to your UPI
  You add to special_events table
  Bot sends special broadcast immediately

TRIAL MANAGEMENT:
  Day 7: Bot sends payment reminder
  Day 10: If not paid, set active = False
```

---

## FILE TO CREATE

```
src/features/ashram_calendar.py
```

---

## COMPLETE CODE

```python
# src/features/ashram_calendar.py

"""
Feature 7: Ashram Satsang Calendar
Owner: [Name]
Status: in-progress
"""

from datetime import date, datetime
from src.database import get_db
from src.whatsapp import send_text, send_buttons
import logging

logger = logging.getLogger(__name__)

SUBSCRIPTION_FEE = 99
TRIAL_DAYS = 7


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for calendar queries."""
    text_upper = text.upper()

    if "STOP" in text_upper or "CANCEL" in text_upper:
        await handle_unsubscribe(phone)
        return

    if "PAID" in text_upper:
        await handle_payment(phone)
        return

    if "SUBSCRIBE" in text_upper or "DAILY" in text_upper:
        await handle_subscribe(phone, language)
        return

    # Query about specific ashram
    await handle_query(phone, text, language)


async def handle_subscribe(phone: str, language: str) -> None:
    """Start free trial subscription."""
    db = get_db()
    existing = db.table("calendar_subscribers")\
        .select("phone, active, is_trial")\
        .eq("phone", phone).execute()

    if existing.data and existing.data[0]["active"]:
        await send_text(phone,
            "You are already subscribed! 🙏\n"
            "Daily updates arrive at 7am every morning."
        )
        return

    db.table("calendar_subscribers").upsert({
        "phone": phone,
        "language": language,
        "trial_started": date.today().isoformat(),
        "active": True,
        "is_trial": True
    }).execute()

    await send_text(phone,
        "Ashram Daily Calendar — Subscribed! 🙏\n\n"
        "Every morning at 7am you will receive:\n"
        "  All ashram programs for today\n"
        "  Visiting teacher satsangs\n"
        "  Special events and festivals\n\n"
        f"First {TRIAL_DAYS} days FREE.\n"
        f"After that: Rs.{SUBSCRIPTION_FEE}/month\n\n"
        "To cancel anytime: Reply STOP"
    )


async def handle_payment(phone: str) -> None:
    """Confirm subscription payment."""
    db = get_db()
    from datetime import timedelta
    next_payment = (date.today() + timedelta(days=30)).isoformat()

    db.table("calendar_subscribers").update({
        "is_trial": False,
        "next_payment": next_payment,
        "active": True
    }).eq("phone", phone).execute()

    await send_text(phone,
        f"Payment confirmed! 🙏\n"
        f"Subscription active for 30 days.\n"
        f"Next payment: {next_payment}\n\n"
        f"Daily updates continue at 7am. 🙏"
    )


async def handle_unsubscribe(phone: str) -> None:
    """Cancel subscription."""
    db = get_db()
    db.table("calendar_subscribers").update({"active": False})\
        .eq("phone", phone).execute()
    await send_text(phone,
        "Subscription cancelled. 🙏\n"
        "You will no longer receive daily updates.\n"
        "To resubscribe anytime: Reply SUBSCRIBE"
    )


async def handle_query(phone: str, text: str, language: str) -> None:
    """Answer query about specific ashram or program."""
    programs = await get_todays_programs()
    events = await get_todays_events()

    msg = build_daily_message(programs, events)
    await send_buttons(phone, msg,
        ["Subscribe daily", "This week programs", "Main menu"]
    )


async def send_daily_update() -> int:
    """
    Send daily 7am update to all active subscribers.
    Called by scheduler. Returns count sent.
    """
    db = get_db()
    subscribers = db.table("calendar_subscribers")\
        .select("phone, language")\
        .eq("active", True)\
        .execute()

    programs = await get_todays_programs()
    events = await get_todays_events()
    message = build_daily_message(programs, events)

    count = 0
    for sub in (subscribers.data or []):
        try:
            await send_text(sub["phone"], message)
            count += 1
        except Exception as e:
            logger.error(f"Daily update failed for {sub['phone']}: {e}")

    logger.info(f"Daily update sent to {count} subscribers")
    return count


async def send_trial_reminders() -> None:
    """Send payment reminder on day 7 of trial."""
    db = get_db()
    from datetime import timedelta
    day7 = (date.today() - timedelta(days=TRIAL_DAYS)).isoformat()

    trials = db.table("calendar_subscribers")\
        .select("phone")\
        .eq("is_trial", True)\
        .eq("active", True)\
        .eq("trial_started", day7)\
        .execute()

    for sub in (trials.data or []):
        await send_text(sub["phone"],
            f"Your {TRIAL_DAYS}-day free trial ends tomorrow! 🙏\n\n"
            f"To continue daily Arunachala updates:\n"
            f"Rs.{SUBSCRIPTION_FEE}/month\n\n"
            f"Pay: UPI arunachala@ybl | Note: CALENDAR\n"
            f"Or: https://rzp.io/l/calendar\n\n"
            f"Reply PAID to continue | Reply STOP to cancel"
        )


async def get_todays_programs() -> list:
    """Get today's fixed ashram programs."""
    db = get_db()
    today = datetime.now().strftime("%A").lower()
    result = db.table("ashram_programs")\
        .select("*")\
        .eq("active", True)\
        .in_("day_type", ["daily", today])\
        .order("ashram_name")\
        .order("time_of_day")\
        .execute()
    return result.data or []


async def get_todays_events() -> list:
    """Get today's special events and visiting teachers."""
    db = get_db()
    today = date.today().isoformat()
    result = db.table("special_events")\
        .select("*")\
        .eq("event_date", today)\
        .eq("active", True)\
        .order("event_time")\
        .execute()
    return result.data or []


def build_daily_message(programs: list, events: list) -> str:
    """Build the daily 7am message from programs and events."""
    today_str = date.today().strftime("%A, %B %d")
    lines = [f"Arunachala — Today's Programs 🙏", f"{today_str}", ""]

    # Group by ashram
    ashrams = {}
    for p in programs:
        ashram = p.get("ashram_name", "Other")
        if ashram not in ashrams:
            ashrams[ashram] = []
        time_str = str(p.get("time_of_day", ""))[:5]
        ashrams[ashram].append(f"  {time_str}  {p.get('program_name', '')}")

    for ashram, program_list in ashrams.items():
        lines.append(f"{ashram.upper()}:")
        lines.extend(program_list)
        lines.append("")

    if events:
        lines.append("SPECIAL TODAY:")
        for e in events:
            time_str = str(e.get("event_time", ""))[:5]
            lines.append(f"  {time_str} — {e.get('event_name', '')}")
            if e.get("teacher_name"):
                lines.append(f"           Teacher: {e['teacher_name']}")
            if e.get("venue"):
                lines.append(f"           Venue: {e['venue']}")
            lines.append("")

    return "\n".join(lines)
```

---

## TEST CASES

```python
# tests/test_feature7.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.ashram_calendar import (
    handle_subscribe, handle_unsubscribe, build_daily_message,
    send_daily_update, handle_payment
)


class TestDailyMessage:
    def test_message_contains_date(self):
        msg = build_daily_message([], [])
        from datetime import date
        assert date.today().strftime("%A") in msg

    def test_message_shows_programs_by_ashram(self):
        programs = [
            {"ashram_name": "Ramana Ashram", "time_of_day": "05:30:00",
             "program_name": "Veda Parayana", "day_type": "daily"}
        ]
        msg = build_daily_message(programs, [])
        assert "RAMANA ASHRAM" in msg
        assert "Veda Parayana" in msg
        assert "05:30" in msg

    def test_message_shows_special_events(self):
        events = [
            {"event_name": "Visiting Satsang", "event_time": "19:00:00",
             "teacher_name": "Robert Adams Foundation", "venue": "Old Hall"}
        ]
        msg = build_daily_message([], events)
        assert "SPECIAL TODAY" in msg
        assert "Visiting Satsang" in msg

    def test_empty_programs_gracefully_handled(self):
        msg = build_daily_message([], [])
        assert "Arunachala" in msg
        assert msg is not None


class TestSubscription:

    @pytest.mark.asyncio
    async def test_new_subscriber_saved(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = []
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.ashram_calendar.get_db", return_value=mock_db), \
             patch("src.features.ashram_calendar.send_text", new_callable=AsyncMock):
            await handle_subscribe("919XXXXXXXXX", "english")
            mock_db.table.return_value.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_sets_inactive(self):
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value\
            .execute.return_value = MagicMock()

        with patch("src.features.ashram_calendar.get_db", return_value=mock_db), \
             patch("src.features.ashram_calendar.send_text", new_callable=AsyncMock):
            await handle_unsubscribe("919XXXXXXXXX")
            mock_db.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_update_sent_to_all_subscribers(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [
                {"phone": "919A", "language": "tamil"},
                {"phone": "919B", "language": "english"},
                {"phone": "919C", "language": "telugu"},
            ]
        mock_db.table.return_value.select.return_value.eq.return_value\
            .in_.return_value.order.return_value.order.return_value\
            .execute.return_value.data = []
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.order.return_value.execute.return_value.data = []

        with patch("src.features.ashram_calendar.get_db", return_value=mock_db), \
             patch("src.features.ashram_calendar.get_todays_programs",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.features.ashram_calendar.get_todays_events",
                   new_callable=AsyncMock, return_value=[]), \
             patch("src.features.ashram_calendar.send_text",
                   new_callable=AsyncMock) as mock_send:
            count = await send_daily_update()
            assert count == 3
            assert mock_send.call_count == 3
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: SUBSCRIBE → saved in DB + confirmation sent
[ ] AC-02: STOP → active set to False
[ ] AC-03: PAID → is_trial = False, next_payment set
[ ] AC-04: send_daily_update() → all active subscribers receive message
[ ] AC-05: build_daily_message() → contains date, programs, events
[ ] AC-06: Day 7 trial reminder sent automatically
[ ] AC-07: All tests pass: pytest tests/test_feature7.py -v
[ ] AC-08: Scheduler configured to run send_daily_update() at 7am daily
[ ] AC-09: Real test: Subscribe → receive 7am message next morning
```
