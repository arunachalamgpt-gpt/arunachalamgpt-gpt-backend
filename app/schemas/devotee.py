"""Pydantic schemas for the devotee profile + WhatsApp webhook surface."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.lodge import PHONE_PATTERN, _local_today

Language = Literal["tamil", "telugu", "kannada", "hindi", "english"]
OnboardingState = Literal[
    "new", "language_selected", "profile_complete", "registered", "visited"
]


class DevoteeProfileIn(BaseModel):
    phone: str = Field(pattern=PHONE_PATTERN, examples=["9876543210"])
    name: Optional[str] = Field(default=None, max_length=120)
    language: Optional[Language] = None
    has_elderly: bool = False
    has_children: bool = False
    planned_visit_date: Optional[date] = None
    home_city: Optional[str] = Field(default=None, max_length=80)

    @field_validator("planned_visit_date")
    @classmethod
    def _not_in_past(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < _local_today():
            raise ValueError("planned_visit_date cannot be in the past")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "phone": "9876543210",
                "name": "Kavitha",
                "language": "tamil",
                "has_elderly": True,
                "has_children": True,
                "planned_visit_date": "2026-06-15",
                "home_city": "Chennai",
            }
        }
    )


class DevoteeProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    language: Optional[Language] = None
    has_elderly: Optional[bool] = None
    has_children: Optional[bool] = None
    planned_visit_date: Optional[date] = None
    home_city: Optional[str] = Field(default=None, max_length=80)
    onboarding_state: Optional[OnboardingState] = None


class DevoteeProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone: str
    name: Optional[str]
    language: Optional[str]
    has_elderly: bool
    has_children: bool
    planned_visit_date: Optional[date]
    home_city: Optional[str]
    onboarding_state: str
    created_at: datetime
    updated_at: datetime


class IncomingWhatsAppMessage(BaseModel):
    """Body the WhatsApp bridge (Twilio/360dialog adaptor) POSTs to the bot."""

    phone: str = Field(pattern=PHONE_PATTERN, examples=["9876543210"])
    # WhatsApp message bodies can be up to 4096 chars; clamp at 4000 to leave
    # margin for downstream processing and bound abuse via huge payloads.
    text: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Step 1 — first contact",
                    "value": {"phone": "9876543210", "text": "Hi"},
                },
                {
                    "summary": "Step 2 — pick language (1=Tamil … 5=English)",
                    "value": {"phone": "9876543210", "text": "1"},
                },
                {
                    "summary": "Step 3/4 — register a visit",
                    "value": {
                        "phone": "9876543210",
                        "text": "Visiting with elderly mother on 2026-06-15",
                    },
                },
                {
                    "summary": "Step 8/9 — live crowd query (English)",
                    "value": {"phone": "9876543210", "text": "crowd now?"},
                },
                {
                    "summary": "Romanized Tamil — crowd query (requires OPENAI_ENABLED=true)",
                    "value": {"phone": "9876543210", "text": "crowd enna ippo"},
                },
                {
                    "summary": "Romanized Tamil — planning query",
                    "value": {
                        "phone": "9876543210",
                        "text": "epdi varuvadhu best time?",
                    },
                },
                {
                    "summary": "Romanized Hindi — language switch",
                    "value": {"phone": "9876543210", "text": "hindi me bolo"},
                },
                {
                    "summary": "Code-mix — visit registration",
                    "value": {
                        "phone": "9876543210",
                        "text": "amma ku visit on 15/06/2026",
                    },
                },
            ]
        }
    )


class BotReply(BaseModel):
    """Reply the bridge should send back to the user."""

    phone: str
    text: str
    language: Optional[Language] = None
    state: OnboardingState
    metadata: dict = Field(default_factory=dict)


class PlanningRecommendationResponse(BaseModel):
    """Output of Step 3 — planning advice for a registered devotee."""

    visit_date: date
    has_elderly: bool
    has_children: bool
    recommended_arrival: str
    recommended_line: str
    rationale: str
    packing_checklist: list[str]
