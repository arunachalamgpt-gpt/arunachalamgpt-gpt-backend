"""Pydantic schemas for the temple_config key/value store and admin commands."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lodge import PHONE_PATTERN


class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    description: Optional[str]
    updated_at: datetime
    updated_by: Optional[str]


class ConfigUpsertIn(BaseModel):
    value: str = Field(min_length=1)
    description: Optional[str] = None
    updated_by: Optional[str] = Field(default=None, pattern=PHONE_PATTERN)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "value": "08:30",
                "description": "Counter delayed by 30 minutes today.",
                "updated_by": "9444444444",
            }
        }
    )


AdminAction = Literal["config_set", "crowd_report", "broadcast", "unknown"]


class AdminCommandIn(BaseModel):
    """Raw `ADMIN ...` text sent from the admin's WhatsApp number."""

    sender_phone: str = Field(pattern=PHONE_PATTERN)
    text: str = Field(min_length=1, examples=["ADMIN config rs50_sold_out true"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Mark Rs.50 sold out",
                    "value": {
                        "sender_phone": "9444444444",
                        "text": "ADMIN config rs50_sold_out true",
                    },
                },
                {
                    "summary": "Push manual crowd report",
                    "value": {
                        "sender_phone": "9444444444",
                        "text": "ADMIN crowd F:60 T50:15 T200:5",
                    },
                },
                {
                    "summary": "Broadcast to Tamil users",
                    "value": {
                        "sender_phone": "9444444444",
                        "text": "ADMIN broadcast Tamil Crowd is low now!",
                    },
                },
            ]
        }
    )


class AdminCommandResult(BaseModel):
    action: AdminAction
    detail: str
    payload: dict = Field(default_factory=dict)
