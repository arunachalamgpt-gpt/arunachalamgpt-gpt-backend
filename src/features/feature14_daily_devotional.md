# Feature 14 — Daily Devotional Message
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md + Feature 7 (calendar_subscribers table)

---

## WHAT THIS FEATURE DOES

Daily morning WhatsApp subscription with a short spiritual message
about Arunachala, Ramana Maharshi, or Tamil festival significance.
Rs.99/month. Sent at 6am every morning before the ashram calendar.

---

## USER STORIES

```
US-01: Devotee subscribes for daily morning inspiration.
US-02: NRI devotee in Singapore receives daily at local morning time.
US-03: Day 7 trial expiry — payment reminder sent.
US-04: Subscriber cancels by replying STOP.
US-05: Admin sends special message on festival days.
```

---

## MESSAGE TYPES

```
Monday:    Verse from Arunachala Stuti (Ramana's hymn to Arunachala)
Tuesday:   Significance of Girivalam for that month
Wednesday: Story or teaching related to Arunachala
Thursday:  Navagraha significance + which lingam to visit
Friday:    Thiruvannamalai festival or Pradosham reminder
Saturday:  Sani (Saturn) + Varuna Lingam significance
Sunday:    Ramana Maharshi teaching or quote (paraphrased)
Pournami:  Special Pournami significance message
Festival:  Special message about that festival
```

---

## SOP

```
DAILY (automated at 6am):
  Check what day it is
  Check if any festival today
  Generate appropriate message via Claude
  Send to all active subscribers

WEEKLY PREP (you do Sunday, 15 min):
  Check upcoming festival dates
  Add any special context to festival_context table

TRIAL MANAGEMENT:
  Shares same subscriber table as Feature 7 (calendar_subscribers)
  Or create separate devotional_subscribers table
```

---

## FILE TO CREATE

```
src/features/daily_devotional.py
```

---

## COMPLETE CODE

```python
# src/features/daily_devotional.py

"""
Feature 14: Daily Devotional Message
Owner: [Name]
Status: in-progress
"""

from datetime import date, datetime
from src.database import get_db
from src.whatsapp import send_text
import logging

logger = logging.getLogger(__name__)

SUBSCRIPTION_FEE = 99
TRIAL_DAYS = 7

DEVOTIONAL_SYSTEM_PROMPT = """
You are Arunachala GPT — daily spiritual guide for devotees
of Arunachaleswara, Tiruvannamalai.

TODAY: {today_context}
DAY TYPE: {day_type}

Write a SHORT (60-80 words) daily devotional message that:
1. Greets the devotee warmly
2. Shares something meaningful about today's spiritual significance
3. Connects to Arunachala, Ramana Maharshi, or the day's theme
4. Ends with an inspiring thought or simple practice for today
5. Closes with "Arunachala blessings 🙏"

Write in {language}.
Keep it warm, brief, and uplifting.
NOT too formal — as if a spiritual friend is sharing a thought.
Do NOT write "Dear devotee" — just begin naturally.
"""

DAY_THEMES = {
    "Monday":    "Arunachala Stuti — Ramana Maharshi's hymns to the hill",
    "Tuesday":   "Girivalam significance — walking around Lord Shiva",
    "Wednesday": "Story or teaching about Arunachala's sacred power",
    "Thursday":  "Navagraha wisdom — which lingam to focus prayers",
    "Friday":    "Pradosham or weekly temple significance",
    "Saturday":  "Sani — Saturn — patience and Varuna Lingam",
    "Sunday":    "Ramana Maharshi's teaching on Self-Enquiry and silence",
}

FESTIVAL_CONTEXT = {
    "pournami": "Today is Pournami — Full Moon. Most auspicious day for Girivalam. "
                "The hill's energy is amplified many times today.",
    "karthigai": "Karthigai Deepam — Lord Shiva appears as a column of fire on the hill. "
                 "The most sacred day of the year at Tiruvannamalai.",
    "shivaratri": "Maha Shivaratri — Night of Lord Shiva. "
                   "Stay awake in prayer tonight if possible.",
    "pradosham": "Pradosham today — auspicious for worshipping Shiva. "
                 "Temple is especially powerful this evening.",
}


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for devotional subscription queries."""
    text_upper = text.upper()

    if "STOP" in text_upper:
        await handle_unsubscribe(phone)
        return

    if "PAID" in text_upper:
        await handle_payment(phone)
        return

    await handle_subscribe(phone, language)


async def handle_subscribe(phone: str, language: str) -> None:
    """Subscribe devotee to daily messages."""
    db = get_db()
    existing = db.table("devotional_subscribers")\
        .select("phone, active")\
        .eq("phone", phone)\
        .execute()

    if existing.data and existing.data[0]["active"]:
        await send_text(phone,
            "You are already subscribed! 🙏\n"
            "Daily message arrives at 6am every morning."
        )
        return

    db.table("devotional_subscribers").upsert({
        "phone": phone,
        "language": language,
        "subscribed_at": datetime.now().isoformat(),
        "active": True
    }).execute()

    await send_text(phone,
        "Daily Devotional — Subscribed! 🙏\n\n"
        "Every morning at 6am you will receive:\n"
        "  A short spiritual message about Arunachala\n"
        "  Ramana Maharshi teachings\n"
        "  Festival and Pournami reminders\n\n"
        f"First {TRIAL_DAYS} days FREE.\n"
        f"After that: Rs.{SUBSCRIPTION_FEE}/month\n\n"
        "Your first message arrives tomorrow morning at 6am. 🙏\n"
        "To cancel anytime: Reply STOP"
    )


async def handle_payment(phone: str) -> None:
    """Confirm payment and extend subscription."""
    from datetime import timedelta
    next_payment = (date.today() + timedelta(days=30)).isoformat()
    db = get_db()
    db.table("devotional_subscribers").update({
        "next_payment": next_payment,
        "active": True
    }).eq("phone", phone).execute()

    await send_text(phone,
        f"Payment confirmed! 🙏\n"
        f"Daily devotional active for 30 days.\n"
        f"Next payment: {next_payment}"
    )


async def handle_unsubscribe(phone: str) -> None:
    """Cancel subscription."""
    db = get_db()
    db.table("devotional_subscribers").update({"active": False})\
        .eq("phone", phone).execute()
    await send_text(phone,
        "Unsubscribed. 🙏\n"
        "Arunachala blessings always with you.\n"
        "Resubscribe anytime — reply SUBSCRIBE"
    )


async def send_daily_devotional() -> int:
    """
    Send daily 6am devotional to all subscribers.
    Called by scheduler. Returns count sent.
    """
    from src.claude_ai import get_reply

    db = get_db()
    subscribers = db.table("devotional_subscribers")\
        .select("phone, language")\
        .eq("active", True)\
        .execute()

    today = date.today()
    day_name = today.strftime("%A")
    day_theme = DAY_THEMES.get(day_name, "Arunachala spiritual wisdom")
    festival = detect_festival(today)

    count = 0
    for sub in (subscribers.data or []):
        try:
            lang = sub.get("language", "english")
            context = festival if festival else day_theme

            system = DEVOTIONAL_SYSTEM_PROMPT.format(
                today_context=context,
                day_type=day_name,
                language=lang.title()
            )

            message = await get_reply(
                system_prompt=system,
                user_message=f"Write today's {day_name} devotional message",
                max_tokens=200
            )

            await send_text(sub["phone"], message)
            count += 1

        except Exception as e:
            logger.error(f"Devotional send failed for {sub['phone']}: {e}")

    logger.info(f"Daily devotional sent to {count} subscribers")
    return count


def detect_festival(today: date) -> str | None:
    """
    Detect if today is a festival.
    Simple check — extend with proper Tamil calendar library.
    """
    # Pournami check (simplified — use proper moon phase library in production)
    day = today.day
    if day in [14, 15]:
        return FESTIVAL_CONTEXT["pournami"]

    # Pradosham check (13th day of lunar fortnight — simplified)
    if day in [13, 28]:
        return FESTIVAL_CONTEXT["pradosham"]

    return None


async def send_trial_reminders() -> None:
    """Send payment reminder on day 7 of trial."""
    from datetime import timedelta
    db = get_db()
    day7_date = (date.today() - timedelta(days=TRIAL_DAYS)).isoformat()

    trials = db.table("devotional_subscribers")\
        .select("phone")\
        .eq("active", True)\
        .execute()

    for sub in (trials.data or []):
        try:
            await send_text(sub["phone"],
                f"Your free trial of Daily Devotional ends soon! 🙏\n\n"
                f"To continue daily Arunachala messages:\n"
                f"Rs.{SUBSCRIPTION_FEE}/month\n\n"
                f"Pay: UPI arunachala@ybl | Note: DEVOTIONAL\n"
                f"Or: https://rzp.io/l/devotional\n\n"
                f"Reply PAID to continue | Reply STOP to cancel"
            )
        except Exception as e:
            logger.error(f"Trial reminder failed for {sub['phone']}: {e}")
```

---

## TEST CASES

```python
# tests/test_feature14.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.daily_devotional import (
    handle_subscribe, handle_unsubscribe, send_daily_devotional,
    detect_festival, DAY_THEMES
)


class TestDayThemes:
    def test_all_7_days_have_themes(self):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"]
        for day in days:
            assert day in DAY_THEMES, f"{day} missing from DAY_THEMES"

    def test_themes_are_non_empty(self):
        for day, theme in DAY_THEMES.items():
            assert len(theme) > 10, f"{day} theme too short"


class TestSubscription:

    @pytest.mark.asyncio
    async def test_new_subscriber_saved(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = []
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with patch("src.features.daily_devotional.get_db", return_value=mock_db), \
             patch("src.features.daily_devotional.send_text",
                   new_callable=AsyncMock) as mock_send:
            await handle_subscribe("919XXXXXXXXX", "english")
            mock_db.table.return_value.upsert.assert_called_once()
            assert mock_send.called

    @pytest.mark.asyncio
    async def test_duplicate_gets_friendly_message(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [{"phone": "919X", "active": True}]

        with patch("src.features.daily_devotional.get_db", return_value=mock_db), \
             patch("src.features.daily_devotional.send_text",
                   new_callable=AsyncMock) as mock_send:
            await handle_subscribe("919XXXXXXXXX", "english")
            mock_db.table.return_value.upsert.assert_not_called()
            assert "already" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_unsubscribe_deactivates(self):
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value\
            .execute.return_value = MagicMock()

        with patch("src.features.daily_devotional.get_db", return_value=mock_db), \
             patch("src.features.daily_devotional.send_text",
                   new_callable=AsyncMock):
            await handle_unsubscribe("919XXXXXXXXX")
            mock_db.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_send_reaches_all_subscribers(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .execute.return_value.data = [
                {"phone": "919A", "language": "tamil"},
                {"phone": "919B", "language": "english"},
                {"phone": "919C", "language": "telugu"},
            ]

        with patch("src.features.daily_devotional.get_db", return_value=mock_db), \
             patch("src.features.daily_devotional.get_reply",
                   new_callable=AsyncMock,
                   return_value="Arunachala blesses you today 🙏"), \
             patch("src.features.daily_devotional.send_text",
                   new_callable=AsyncMock) as mock_send:
            count = await send_daily_devotional()
            assert count == 3
            assert mock_send.call_count == 3

    def test_festival_detection_returns_context(self):
        from datetime import date
        # Test with a date that would be near Pournami
        test_date = date(2026, 5, 15)
        result = detect_festival(test_date)
        assert result is None or isinstance(result, str)
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: SUBSCRIBE → saved + confirmation with trial info
[ ] AC-02: Duplicate subscribe → friendly "already subscribed"
[ ] AC-03: STOP → active set to False
[ ] AC-04: PAID → subscription extended 30 days
[ ] AC-05: All 7 days have different themes in DAY_THEMES
[ ] AC-06: send_daily_devotional() → all subscribers receive message
[ ] AC-07: Festival days → festival-specific message context
[ ] AC-08: All tests pass: pytest tests/test_feature14.py -v
[ ] AC-09: Scheduler runs at 6am daily (before Feature 7 at 7am)
[ ] AC-10: Real test: Subscribe → receive message next morning at 6am
[ ] AC-11: Real test: Messages in Tamil, Telugu, English are different
```

---

## SCHEDULER SETUP (in main.py)

```python
# Add to main.py after creating FastAPI app

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def start_scheduler():
    from src.features.daily_devotional import send_daily_devotional
    from src.features.ashram_calendar import send_daily_update, send_trial_reminders

    # 6am — Daily devotional message
    scheduler.add_job(send_daily_devotional, "cron", hour=6, minute=0)

    # 7am — Ashram calendar update
    scheduler.add_job(send_daily_update, "cron", hour=7, minute=0)

    # 8am — Trial reminders
    scheduler.add_job(send_trial_reminders, "cron", hour=8, minute=0)

    scheduler.start()
    print("Scheduler started")

@app.on_event("shutdown")
async def stop_scheduler():
    scheduler.shutdown()
```
