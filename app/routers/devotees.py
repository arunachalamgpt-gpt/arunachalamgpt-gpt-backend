"""Devotee profile + planning endpoints."""

import logging
from datetime import date as date_t
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.errors import NotFoundError
from app.models.devotee import DevoteeProfile
from app.schemas.devotee import (
    DevoteeProfileIn,
    DevoteeProfileOut,
    DevoteeProfileUpdate,
    PlanningRecommendationResponse,
)
from app.services import planning as planning_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devotees", tags=["devotees"])


class DevoteeNotFoundError(NotFoundError):
    code = "devotee_not_found"
    message = "Devotee profile not found"


@router.post(
    "",
    response_model=DevoteeProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upsert devotee profile by phone",
    description=(
        "Idempotent — re-POSTing the same `phone` overwrites only the fields "
        "you include. Use this when the bot collects info up-front; the "
        "WhatsApp webhook path mutates the profile in-place as the user "
        "progresses through the journey.\n\n"
        "Requires `X-API-Key` when `API_KEY` is set in the environment."
    ),
    responses={
        401: {"description": "Missing or invalid X-API-Key (when API_KEY is set)"},
        422: {"description": "Phone format invalid or past date supplied"},
    },
    dependencies=[Depends(require_api_key)],
)
def upsert_profile(payload: DevoteeProfileIn, db: Session = Depends(get_db)):
    profile = db.get(DevoteeProfile, payload.phone)
    now = datetime.now(timezone.utc)
    if profile is None:
        profile = DevoteeProfile(**payload.model_dump(), updated_at=now)
        db.add(profile)
    else:
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(profile, key, value)
        profile.updated_at = now
    db.commit()
    db.refresh(profile)
    return profile


@router.get(
    "/{phone}",
    response_model=DevoteeProfileOut,
    summary="Get a devotee profile",
    responses={404: {"description": "Devotee not found"}},
)
def get_profile(phone: str, db: Session = Depends(get_db)):
    profile = db.get(DevoteeProfile, phone)
    if profile is None:
        raise DevoteeNotFoundError(details={"phone": phone})
    return profile


@router.patch(
    "/{phone}",
    response_model=DevoteeProfileOut,
    summary="Partial update of a devotee profile",
    responses={404: {"description": "Devotee not found"}},
)
def update_profile(
    phone: str, payload: DevoteeProfileUpdate, db: Session = Depends(get_db)
):
    profile = db.get(DevoteeProfile, phone)
    if profile is None:
        raise DevoteeNotFoundError(details={"phone": phone})
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


@router.get(
    "/{phone}/plan",
    response_model=PlanningRecommendationResponse,
    summary="Planning recommendation for a devotee",
    description=(
        "Uses `has_elderly`/`has_children`/`planned_visit_date` from the profile "
        "to compute Step 3 advice — arrival time, recommended line, rationale, "
        "and a packing checklist. Rule-based so it's deterministic and "
        "translatable; the WhatsApp layer can localise the strings."
    ),
    responses={404: {"description": "Devotee not found"}},
)
def get_plan(phone: str, db: Session = Depends(get_db)):
    profile = db.get(DevoteeProfile, phone)
    if profile is None:
        raise DevoteeNotFoundError(details={"phone": phone})
    target = profile.planned_visit_date or date_t.today()
    return planning_svc.recommend(
        visit_date=target,
        has_elderly=profile.has_elderly,
        has_children=profile.has_children,
    )
