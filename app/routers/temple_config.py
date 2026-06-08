"""Key/value config CRUD + admin command endpoints."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import NotFoundError
from app.schemas.temple_config import (
    AdminCommandIn,
    AdminCommandResult,
    ConfigOut,
    ConfigUpsertIn,
)
from app.services import admin_commands
from app.services import temple_config as temple_config_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class ConfigKeyNotFoundError(NotFoundError):
    code = "config_not_found"
    message = "Config key not found"


@router.get(
    "/config",
    response_model=list[ConfigOut],
    summary="List every temple_config key",
)
def list_config(db: Session = Depends(get_db)):
    return temple_config_svc.list_all(db)


@router.get(
    "/config/{key}",
    response_model=ConfigOut,
    summary="Read a single config value",
    responses={404: {"description": "Config key not found"}},
)
def get_one(key: str, db: Session = Depends(get_db)):
    row = temple_config_svc.get(db, key)
    if row is None:
        raise ConfigKeyNotFoundError(details={"key": key})
    return row


@router.put(
    "/config/{key}",
    response_model=ConfigOut,
    summary="Upsert a config value",
    description=(
        "Creates the row if missing; updates it otherwise. Values are stored "
        "as strings — callers parse. Use this for the seedable knobs: "
        "`ticket_sale_start_time`, `rs50_ticket_price`, `rs200_ticket_price`, "
        "`rs50_sold_out`, `rs200_sold_out`, `temple_open_time`, "
        "`temple_close_time`, `volunteer_phone`."
    ),
)
def upsert_one(key: str, payload: ConfigUpsertIn, db: Session = Depends(get_db)):
    row = temple_config_svc.upsert(
        db,
        key,
        payload.value,
        description=payload.description,
        updated_by=payload.updated_by,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/commands",
    response_model=AdminCommandResult,
    status_code=status.HTTP_200_OK,
    summary="Run a raw `ADMIN ...` command",
    description=(
        "Accepts the verbatim WhatsApp text from the admin number and dispatches "
        "it. Always returns 200 — an unknown command surfaces as "
        "`action: \"unknown\"` so the bot can reply with a help message.\n\n"
        "**Forms:**\n"
        "- `ADMIN config <key> <value>` — upsert `temple_config`\n"
        "- `ADMIN crowd F:60 T50:15 T200:5` — record a manual crowd snapshot "
        "with `source=admin`\n"
        "- `ADMIN broadcast <language> <message>` — returns the parsed payload "
        "for the bridge to send (no send happens here)"
    ),
)
def run_command(payload: AdminCommandIn, db: Session = Depends(get_db)):
    result = admin_commands.dispatch(
        db, sender_phone=payload.sender_phone, text=payload.text
    )
    db.commit()
    return result
