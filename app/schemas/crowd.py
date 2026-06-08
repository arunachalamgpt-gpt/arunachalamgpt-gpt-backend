"""Pydantic schemas for crowd reporting, current status, predictions, history."""

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lodge import PHONE_PATTERN

CrowdSource = Literal["volunteer", "admin", "post_visit", "rollup", "prediction"]


class VolunteerRawMessage(BaseModel):
    """Raw text from the WhatsApp bridge — server parses `F:180 T50:40 T200:15`."""

    reporter_phone: str = Field(pattern=PHONE_PATTERN, examples=["9444444444"])
    text: str = Field(min_length=1, examples=["F:180 T50:40 T200:15"])
    notes: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Normal hourly report",
                    "value": {
                        "reporter_phone": "9444444444",
                        "text": "F:180 T50:40 T200:15",
                    },
                },
                {
                    "summary": "Rs.50 sold out",
                    "value": {
                        "reporter_phone": "9444444444",
                        "text": "F:200 T50:SOLD T200:15",
                        "notes": "Pournami day — counter ran out of Rs.50",
                    },
                },
            ]
        }
    )


class CrowdReportIn(BaseModel):
    """Structured submission used by tests and the admin manual path."""

    reporter_phone: str = Field(pattern=PHONE_PATTERN)
    free_wait_min: Optional[int] = Field(default=None, ge=0)
    rs50_wait_min: Optional[int] = Field(default=None, ge=0)
    rs200_wait_min: Optional[int] = Field(default=None, ge=0)
    rs50_sold_out: bool = False
    rs200_sold_out: bool = False
    notes: Optional[str] = None
    source: CrowdSource = "volunteer"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reporter_phone": "9444444444",
                "free_wait_min": 60,
                "rs50_wait_min": 15,
                "rs200_wait_min": 5,
                "rs50_sold_out": False,
                "rs200_sold_out": False,
                "source": "volunteer",
            }
        }
    )


class CrowdStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reported_at: datetime
    reported_by: str
    free_wait_min: Optional[int]
    rs50_wait_min: Optional[int]
    rs200_wait_min: Optional[int]
    rs50_sold_out: bool
    rs200_sold_out: bool
    notes: Optional[str]
    source: str


CrowdFreshness = Literal["live", "stale", "prediction_only", "closed"]


class CrowdCurrentResponse(BaseModel):
    """Live answer for `/crowd/current`, shaped by the fallback rules."""

    freshness: CrowdFreshness
    source: CrowdSource
    reported_at: Optional[datetime]
    age_minutes: Optional[int]
    free_wait_min: Optional[int]
    rs50_wait_min: Optional[int]
    rs200_wait_min: Optional[int]
    rs50_sold_out: bool
    rs200_sold_out: bool
    message: str


class CrowdPredictionResponse(BaseModel):
    """Average wait times from `crowd_history`, broken down by line."""

    visit_date: date
    hour_of_day: int
    is_pournami: bool
    is_festival: bool
    sample_size: int
    free_wait_min: Optional[int]
    rs50_wait_min: Optional[int]
    rs200_wait_min: Optional[int]


class CrowdHistoryIn(BaseModel):
    """Post-darshan crowdsourced observation (Step 10)."""

    visit_date: date
    hour_of_day: int = Field(ge=0, le=23)
    is_pournami: bool = False
    is_festival: bool = False
    free_wait_min: Optional[int] = Field(default=None, ge=0)
    rs50_wait_min: Optional[int] = Field(default=None, ge=0)
    rs200_wait_min: Optional[int] = Field(default=None, ge=0)
    source: CrowdSource = "post_visit"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "visit_date": "2026-06-15",
                "hour_of_day": 9,
                "is_pournami": False,
                "is_festival": False,
                "free_wait_min": 75,
                "rs50_wait_min": 15,
                "rs200_wait_min": 5,
                "source": "post_visit",
            }
        }
    )


class CrowdHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_date: date
    hour_of_day: int
    is_pournami: bool
    is_festival: bool
    free_wait_min: Optional[int]
    rs50_wait_min: Optional[int]
    rs200_wait_min: Optional[int]
    source: str
    created_at: datetime
