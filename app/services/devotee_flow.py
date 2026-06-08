"""The 10-step devotee user journey as a state machine.

Drives `POST /webhook/whatsapp`. The bridge (Twilio / 360dialog) hands us the
incoming text and the sender's phone; we read/upsert the profile, decide
which step we're in, return a structured `BotReply`, and persist any state
transitions.

State machine:

    new ──language pick──▶ language_selected ──registers visit──▶ registered
                                  │
                                  └──onboarding answers──▶ profile_complete

`visited` is set by the post-darshan helper once the user submits crowd
history. Reminders (D-2 / D-1 / D-0) are sent by the scheduler — outside
this module's scope.
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
from app.services import planning as planning_svc

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
    has_elderly = any(w in lower for w in ("elderly", "old", "senior", "parent", "mother", "father"))
    has_children = any(w in lower for w in ("child", "children", "kid", "kids", "baby"))
    return has_elderly, has_children


def _crowd_one_liner(db: Session) -> str:
    snapshot = crowd_svc.current_status(db)
    if snapshot.freshness == "closed":
        return snapshot.message
    if snapshot.free_wait_min is None:
        return snapshot.message
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


def handle_incoming(db: Session, msg: IncomingWhatsAppMessage) -> BotReply:
    profile = _get_or_create_profile(db, msg.phone)
    text = msg.text.strip()

    # Step 2: Language selection (every new contact lands here first).
    if profile.language is None:
        picked = LANGUAGE_BY_INDEX.get(text)
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
        return BotReply(
            phone=msg.phone,
            text=(
                f"Got it — replies will be in {LANGUAGE_NAMES[picked]}. "
                "Ask me about crowd, tickets or timings any time. "
                "When you're ready, share your visit date (YYYY-MM-DD)."
            ),
            language=picked,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
        )

    # Step 4: Visit registration if the message contains a date.
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
        db.flush()
        return BotReply(
            phone=msg.phone,
            text=(
                f"Saved {visit_date.isoformat()}. Reminders will be sent D-2 (7am), "
                "D-1 (7pm) and visit-day 6am. Send 'plan' anytime to get advice."
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"planned_visit_date": visit_date.isoformat()},
        )

    lower = text.lower()

    # Step 8 / 9: Live crowd query.
    if any(k in lower for k in ("crowd", "queue", "line", "wait", "now")):
        snapshot = crowd_svc.current_status(db)
        return BotReply(
            phone=msg.phone,
            text=snapshot.message + " — " + _crowd_one_liner(db),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"freshness": snapshot.freshness},
        )

    # Step 3: Planning query.
    if any(k in lower for k in ("plan", "advice", "when", "best time")):
        target = profile.planned_visit_date or date_t.today()
        rec = planning_svc.recommend(
            visit_date=target,
            has_elderly=profile.has_elderly,
            has_children=profile.has_children,
        )
        return BotReply(
            phone=msg.phone,
            text=(
                f"Recommended arrival: {rec.recommended_arrival}\n"
                f"Line: {rec.recommended_line}\n{rec.rationale}"
            ),
            language=profile.language,  # type: ignore[arg-type]
            state=profile.onboarding_state,  # type: ignore[arg-type]
            metadata={"checklist": rec.packing_checklist},
        )

    # Language change.
    if "change to" in lower or "switch to" in lower:
        for code in LANGUAGE_BY_INDEX.values():
            if code in lower:
                profile.language = code
                profile.updated_at = _now()
                db.flush()
                return BotReply(
                    phone=msg.phone,
                    text=f"Language switched to {LANGUAGE_NAMES[code]}.",
                    language=code,  # type: ignore[arg-type]
                    state=profile.onboarding_state,  # type: ignore[arg-type]
                )

    return BotReply(
        phone=msg.phone,
        text=(
            "I can help with crowd status ('crowd'), planning ('plan'), or visit "
            "registration (send a date like YYYY-MM-DD). 'Change to <language>' to "
            "switch language."
        ),
        language=profile.language,  # type: ignore[arg-type]
        state=profile.onboarding_state,  # type: ignore[arg-type]
    )
