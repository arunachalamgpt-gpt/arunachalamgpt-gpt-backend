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

import logging
import re
from datetime import date as date_t
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.devotee import DevoteeProfile
from app.schemas.devotee import BotReply, IncomingWhatsAppMessage
from app.services import crowd as crowd_svc
from app.services import intent as intent_svc
from app.services import planning as planning_svc
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
    return None


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
        reply_text = (
            f"Got it — replies will be in {LANGUAGE_NAMES[picked]}. "
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

    db.flush()
    # Cap the English text first → cheaper LLM call, predictable max body.
    reply.text = whatsapp_svc.truncate_for_whatsapp(reply.text)
    reply.text = translator_svc.translate(reply.text, profile.language)
    return reply
