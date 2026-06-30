"""The 10-step devotee user journey as a state machine.

Drives `POST /webhook/whatsapp`. The bridge (Twilio / 360dialog) hands us the
incoming text and the sender's phone; we read/upsert the profile, decide
which step we're in, return a structured `BotReply`, and persist any state
transitions.

State machine:

    new ──language pick──▶ language_selected ──registers visit──▶ registered
                                  │
                                  └──onboarding answers──▶ profile_complete

Dispatch order on every turn (post-language-select):

1. GPT-4o intent classifier (`app.services.intent`) — understands romanized
   text, code-mix, free-form questions.
2. Keyword matcher — runs only when the LLM is disabled or returns `unknown`.
3. Outgoing text is passed through `app.services.translator` so the devotee
   sees it in their saved language (English is pass-through).

Reminders (D-2 / D-1 / D-0) are scheduler-owned and outside this module.
"""

import hashlib
import logging
import re
from datetime import date as date_t
from datetime import datetime, timedelta, timezone
from typing import Optional

import dateparser
from dateparser.search import search_dates

from sqlalchemy.orm import Session

from app.models.devotee import DevoteeProfile
from app.schemas.devotee import BotReply, IncomingWhatsAppMessage
from app.services import crowd as crowd_svc
from app.services import intent as intent_svc
from app.services import lunar_calendar
from app.services import planning as planning_svc
from app.services import temple_qa as qa_svc
from app.services import translator as translator_svc
from app.services import whatsapp as whatsapp_svc

logger = logging.getLogger(__name__)

LANGUAGE_MENU = (
    "Welcome to ArunachalamGPT! Reply with a number to choose your language:\n"
    "1 — Tamil\n2 — Telugu\n3 — Kannada\n4 — Hindi\n5 — English"
)
LANGUAGE_BY_INDEX = {
    "1": "tamil",
    "2": "telugu",
    "3": "kannada",
    "4": "hindi",
    "5": "english",
}
LANGUAGE_NAMES = {v: v.title() for v in LANGUAGE_BY_INDEX.values()}

_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),  # 2026-06-15
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),  # 15/06/2026
]

# Only invoke dateparser when text contains an explicit English date trigger.
# Without this gate, dateparser hallucinates dates out of innocuous tokens
# ("now", weekday-like words in other languages), breaking the keyword
# fallback for crowd/language/smalltalk queries.
_DATE_TRIGGER_RE = re.compile(
    r"\b(today|tomorrow|tmrw|tonight|yesterday|next|this|coming|after|"
    r"mon(day)?|tue(s|sday)?|wed(nesday)?|thu(r|rs|rsday)?|fri(day)?|"
    r"sat(urday)?|sun(day)?|"
    r"jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|"
    r"aug(ust)?|sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?|"
    r"weekend|in\s+\d+\s+(day|days|week|weeks|month|months))\b",
    re.IGNORECASE,
)

# Keyword shortcuts that bypass the LLM — typed across most languages.
RESET_KEYWORDS = {"/reset", "reset", "restart", "start over", "/start"}
MENU_KEYWORDS = {"/menu", "menu", "/help", "help", "options"}
HELP_BODY = (
    "I can help with:\n"
    "• 'crowd' — live East-gate queue\n"
    "• 'plan' — best arrival time + checklist\n"
    "• send a date YYYY-MM-DD to register a visit\n"
    "• 'change to <language>' — Tamil/Telugu/Kannada/Hindi/English\n"
    "• ask anything about the temple\n"
    "• '/reset' — start over"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_profile(db: Session, phone: str) -> DevoteeProfile:
    profile = db.get(DevoteeProfile, phone)
    if profile is None:
        profile = DevoteeProfile(phone=phone, onboarding_state="new")
        db.add(profile)
        db.flush()
    return profile


def _parse_date(text: str) -> Optional[date_t]:
    # Fast path — explicit YYYY-MM-DD or DD/MM/YYYY anywhere in the text.
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups[0]) == 4:
                y, mth, d = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                d, mth, y = int(groups[0]), int(groups[1]), int(groups[2])
            return date_t(y, mth, d)
        except ValueError:
            continue
    # Natural-language fallback — "next Friday", "tomorrow", "in 2 weeks",
    # "15th June", etc. Only fire when the text contains an explicit English
    # date-trigger word; otherwise dateparser hallucinates dates out of words
    # like "now", "ippo", or stray weekday tokens. Only accept FUTURE dates.
    if not _DATE_TRIGGER_RE.search(text):
        return None
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    parsed = None
    try:
        matches = search_dates(text, settings=settings)
    except Exception:
        matches = None
    if matches:
        parsed = matches[0][1]
    else:
        try:
            parsed = dateparser.parse(text, settings=settings)
        except Exception:
            return None
    if parsed is None:
        return None
    candidate = parsed.date()
    if candidate < date_t.today():
        return None
    return candidate


def _detect_elderly_children(text: str) -> tuple[bool, bool]:
    lower = text.lower()
    has_elderly = any(
        w in lower for w in ("elderly", "old", "senior", "parent", "mother", "father")
    )
    has_children = any(
        w in lower for w in ("child", "children", "kid", "kids", "baby")
    )
    return has_elderly, has_children


def _crowd_summary_line(snapshot) -> str:
    """Build the `Free 100 min | Rs.50 SOLD | Rs.200 5 min` summary."""
    if snapshot.freshness == "closed" or snapshot.free_wait_min is None:
        return ""
    parts = [f"Free {snapshot.free_wait_min} min"]
    if snapshot.rs50_sold_out:
        parts.append("Rs.50 SOLD")
    elif snapshot.rs50_wait_min is not None:
        parts.append(f"Rs.50 {snapshot.rs50_wait_min} min")
    if snapshot.rs200_sold_out:
        parts.append("Rs.200 SOLD")
    elif snapshot.rs200_wait_min is not None:
        parts.append(f"Rs.200 {snapshot.rs200_wait_min} min")
    return " | ".join(parts)


# ---------- LLM intent path ----------


def _dispatch_intent(
    db: Session, profile: DevoteeProfile, phone: str, result: intent_svc.IntentResult
) -> Optional[BotReply]:
    """Handle a recognised LLM intent; return None if we can't act on it."""
    if result.intent == "register_visit":
        date_str = result.slots.get("visit_date")
        if not date_str:
            return None
        try:
            visit_date = date_t.fromisoformat(date_str)
        except ValueError:
            return None
        profile.planned_visit_date = visit_date
        profile.onboarding_state = "registered"
        if result.slots.get("has_elderly"):
            profile.has_elderly = True
        if result.slots.get("has_children"):
            profile.has_children = True
        profile.updated_at = _now()
        return BotReply(
            phone=phone,
            text=(
                f"Saved {visit_date.isoformat()}. Reminders will be sent D-2 (7am), "
                "D-1 (7pm) and visit-day 6am. Send 'plan' anytime to get advice."
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"planned_visit_date": visit_date.isoformat()},
        )

    if result.intent == "ask_crowd":
        snapshot = crowd_svc.current_status(db)
        summary = _crowd_summary_line(snapshot)
        text = f"{snapshot.message} — {summary}" if summary else snapshot.message
        return BotReply(
            phone=phone,
            text=text,
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"freshness": snapshot.freshness},
        )

    if result.intent == "ask_plan":
        target = profile.planned_visit_date or date_t.today()
        rec = planning_svc.recommend(
            visit_date=target,
            has_elderly=profile.has_elderly,
            has_children=profile.has_children,
            is_pournami=lunar_calendar.is_pournami(target),
            is_festival=lunar_calendar.is_karthigai_deepam(target),
        )
        return BotReply(
            phone=phone,
            text=(
                f"Recommended arrival: {rec.recommended_arrival}\n"
                f"Line: {rec.recommended_line}\n{rec.rationale}"
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"checklist": rec.packing_checklist},
        )

    if result.intent == "change_language":
        target = result.slots.get("target_language")
        if target:
            profile.language = target
            profile.updated_at = _now()
            return BotReply(
                phone=phone,
                text=f"Language switched to {LANGUAGE_NAMES[target]}.",
                language=target,  # type: ignore[arg-type]
                state=profile.onboarding_state,  # type: ignore[arg-type]
            )

    if result.intent == "general_question":
        question = result.slots.get("question", "").strip()
        if not question:
            return None
        answer = qa_svc.answer(question)
        if answer is None:
            # LLM confidently classified this as a factual question, but the
            # QA service is unavailable. Don't fall through to date parsing —
            # that would silently turn "tell me history" into a visit-date.
            return BotReply(
                phone=phone,
                text=(
                    "I couldn't fetch an answer right now. Please try again "
                    "in a moment, or send 'menu' to see what I can help with."
                ),
                language=profile.language,  # type: ignore[arg-type]
                state=profile.onboarding_state,  # type: ignore[arg-type]
                metadata={"qa": False},
            )
        return BotReply(
            phone=phone,
            text=answer,
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"qa": True},
        )

    if result.intent == "ask_smalltalk":
        name = (profile.name or "").strip()
        greeting = f"🙏 Hello {name}!" if name else "🙏 Hello!"
        return BotReply(
            phone=phone,
            text=(
                f"{greeting} I'm ArunachalamGPT — I can help with the East-gate "
                "crowd ('crowd'), planning your visit ('plan'), registering a "
                "visit date (YYYY-MM-DD), or temple questions. What would you "
                "like to know?"
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"smalltalk": True},
        )

    return None


# ---------- keyword fallback path (unchanged from the pre-LLM build) ----------


def _dispatch_keywords(
    db: Session, profile: DevoteeProfile, phone: str, text: str
) -> BotReply:
    visit_date = _parse_date(text)
    if visit_date is not None:
        profile.planned_visit_date = visit_date
        profile.onboarding_state = "registered"
        has_elderly, has_children = _detect_elderly_children(text)
        if has_elderly:
            profile.has_elderly = True
        if has_children:
            profile.has_children = True
        profile.updated_at = _now()
        return BotReply(
            phone=phone,
            text=(
                f"Saved {visit_date.isoformat()}. Reminders will be sent D-2 (7am), "
                "D-1 (7pm) and visit-day 6am. Send 'plan' anytime to get advice."
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"planned_visit_date": visit_date.isoformat()},
        )

    lower = text.lower()

    if any(k in lower for k in ("crowd", "queue", "line", "wait", "now")):
        snapshot = crowd_svc.current_status(db)
        summary = _crowd_summary_line(snapshot)
        text_out = f"{snapshot.message} — {summary}" if summary else snapshot.message
        return BotReply(
            phone=phone,
            text=text_out,
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"freshness": snapshot.freshness},
        )

    if any(k in lower for k in ("plan", "advice", "when", "best time")):
        target = profile.planned_visit_date or date_t.today()
        rec = planning_svc.recommend(
            visit_date=target,
            has_elderly=profile.has_elderly,
            has_children=profile.has_children,
            is_pournami=lunar_calendar.is_pournami(target),
            is_festival=lunar_calendar.is_karthigai_deepam(target),
        )
        return BotReply(
            phone=phone,
            text=(
                f"Recommended arrival: {rec.recommended_arrival}\n"
                f"Line: {rec.recommended_line}\n{rec.rationale}"
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"checklist": rec.packing_checklist},
        )

    if "change to" in lower or "switch to" in lower:
        for code in LANGUAGE_BY_INDEX.values():
            if code in lower:
                profile.language = code
                profile.updated_at = _now()
                return BotReply(
                    phone=phone,
                    text=f"Language switched to {LANGUAGE_NAMES[code]}.",
                    language=code,  # type: ignore[arg-type]
                    state=profile.onboarding_state,  # type: ignore[arg-type]
                )

    return BotReply(
        phone=phone,
        text=(
            "I can help with crowd status ('crowd'), planning ('plan'), or visit "
            "registration (send a date like YYYY-MM-DD). 'Change to <language>' to "
            "switch language."
        ),
        language=profile.language,  # type: ignore[arg-type]
        state=profile.onboarding_state,  # type: ignore[arg-type]
    )


# ---------- entry point ----------


def handle_incoming(db: Session, msg: IncomingWhatsAppMessage) -> BotReply:
    profile = _get_or_create_profile(db, msg.phone)
    text = msg.text.strip()
    lower = text.lower()

    # Keyword shortcuts that always run first — no LLM cost.
    if lower in RESET_KEYWORDS:
        profile.language = None
        profile.onboarding_state = "new"
        # Clear loop-detection state too — the user explicitly asked to start
        # over, so previous repeats are no longer relevant.
        profile.last_reply_hash = None
        profile.last_reply_at = None
        profile.repeat_count = 0
        profile.updated_at = _now()
        db.flush()
        return BotReply(
            phone=msg.phone,
            text=LANGUAGE_MENU,
            state=profile.onboarding_state,
        )

    if lower in MENU_KEYWORDS:
        # Translate so non-English users get a help message they can read.
        help_text = whatsapp_svc.truncate_for_whatsapp(HELP_BODY)
        if profile.language:
            help_text = translator_svc.translate(help_text, profile.language)
        return BotReply(
            phone=msg.phone,
            text=help_text,
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,
        )

    # Step 2: Language selection.
    # Fast path: direct numeric match — no LLM call needed for "1".."5".
    # LLM only fires when the user typed something else (e.g. "Tamil please").
    if profile.language is None:
        picked: Optional[str] = LANGUAGE_BY_INDEX.get(text)
        if picked is None:
            result = intent_svc.classify(text)
            if result.intent == "select_language":
                picked = LANGUAGE_BY_INDEX.get(
                    result.slots.get("language_code", "")
                )
        if picked is None:
            return BotReply(
                phone=msg.phone,
                text=LANGUAGE_MENU,
                state=profile.onboarding_state,
            )
        profile.language = picked
        profile.onboarding_state = "language_selected"
        profile.updated_at = _now()
        db.flush()
        name = (profile.name or "").strip()
        intro = f"Got it{', ' + name if name else ''} — "
        reply_text = (
            f"{intro}replies will be in {LANGUAGE_NAMES[picked]}. "
            "Ask me about crowd, tickets or timings any time. "
            "When you're ready, share your visit date (YYYY-MM-DD)."
        )
        # Truncate BEFORE translation so we don't pay LLM cost on chars we'd cut.
        reply_text = whatsapp_svc.truncate_for_whatsapp(reply_text)
        return BotReply(
            phone=msg.phone,
            text=translator_svc.translate(reply_text, picked),
            language=picked,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
        )

    # LLM intent first; keyword fallback if it doesn't fire or returns unknown.
    intent_result = intent_svc.classify(text)
    reply = _dispatch_intent(db, profile, msg.phone, intent_result)
    if reply is None:
        reply = _dispatch_keywords(db, profile, msg.phone, text)

    # Loop-break: if this English reply matches the previous one we sent
    # within a few minutes, the user is repeating themselves and we'd
    # otherwise mechanically repeat ourselves. Vary the response.
    reply.text = _maybe_break_repeat_loop(profile, reply.text)

    db.flush()
    # Cap the English text first → cheaper LLM call, predictable max body.
    reply.text = whatsapp_svc.truncate_for_whatsapp(reply.text)
    reply.text = translator_svc.translate(reply.text, profile.language)
    return reply


# ---------- repeat-loop detection ----------

_REPEAT_WINDOW = timedelta(minutes=10)


def _hash_reply(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()


def _maybe_break_repeat_loop(profile: DevoteeProfile, reply_text: str) -> str:
    """If the reply we're about to send matches the previous one, vary it.

    Updates `last_reply_hash`, `last_reply_at`, `repeat_count` on the profile.
    The new prefixes acknowledge the loop AND nudge the user toward `/menu`
    so they don't feel stuck.
    """
    now = _now()
    new_hash = _hash_reply(reply_text)
    last_at = profile.last_reply_at
    if last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)

    within_window = last_at is not None and (now - last_at) <= _REPEAT_WINDOW
    if profile.last_reply_hash == new_hash and within_window:
        profile.repeat_count = (profile.repeat_count or 0) + 1
    else:
        profile.repeat_count = 0
    profile.last_reply_hash = new_hash
    profile.last_reply_at = now

    if profile.repeat_count == 0:
        return reply_text
    prefix, suffix = (
        ("Got the same question again — here's what I have:\n\n",
         "\n\nSend 'menu' for other things I can help with.")
        if profile.repeat_count == 1
        else (
            "Looks like we're going in circles. I'm a bot, so I can only give "
            "the same answer until something changes:\n\n",
            "\n\nTry 'menu' to see options, or 'reset' to start fresh.",
        )
    )
    # Keep the inner reply short enough that prefix + body + suffix still
    # fits inside the WhatsApp body limit, so the helpful hint never gets
    # truncated off the end.
    budget = whatsapp_svc.MAX_OUTBOUND_BODY - len(prefix) - len(suffix)
    inner = reply_text if len(reply_text) <= budget else reply_text[: budget - 1] + "…"
    return f"{prefix}{inner}{suffix}"
