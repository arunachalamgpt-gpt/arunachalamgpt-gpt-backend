from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.crowd import CrowdHistoryIn, CrowdReportIn, VolunteerRawMessage
from app.schemas.devotee import DevoteeProfileIn, DevoteeProfileUpdate
from app.schemas.temple_config import (
    AdminCommandIn,
    AdminCommandResult,
    ConfigOut,
    ConfigUpsertIn,
)


def test_volunteer_raw_requires_phone_pattern():
    with pytest.raises(ValidationError):
        VolunteerRawMessage(reporter_phone="abc", text="F:1")


def test_crowd_report_in_defaults():
    r = CrowdReportIn(reporter_phone="9876543210")
    assert r.source == "volunteer"


def test_crowd_history_in_hour_range():
    with pytest.raises(ValidationError):
        CrowdHistoryIn(visit_date=date.today(), hour_of_day=24)


def test_devotee_profile_in_past_date_rejected():
    with pytest.raises(ValidationError):
        DevoteeProfileIn(
            phone="9876543210", planned_visit_date=date.today() - timedelta(days=1)
        )


def test_devotee_profile_in_today_ok():
    DevoteeProfileIn(
        phone="9876543210", planned_visit_date=date.today() + timedelta(days=1)
    )


def test_devotee_profile_update_partial_excludes_unset():
    upd = DevoteeProfileUpdate(language="tamil")
    assert upd.model_dump(exclude_unset=True) == {"language": "tamil"}


def test_admin_command_in_requires_text():
    with pytest.raises(ValidationError):
        AdminCommandIn(sender_phone="9444444444", text="")


def test_admin_command_result_default_payload():
    res = AdminCommandResult(action="unknown", detail="x")
    assert res.payload == {}


def test_config_upsert_in_value_required():
    with pytest.raises(ValidationError):
        ConfigUpsertIn(value="")


def test_config_out_round_trip():
    from datetime import datetime, timezone

    class _Row:
        key = "k"
        value = "v"
        description = None
        updated_at = datetime.now(timezone.utc)
        updated_by = None

    out = ConfigOut.model_validate(_Row(), from_attributes=True)
    assert out.key == "k"
