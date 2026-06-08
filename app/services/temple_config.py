"""CRUD + seeding for the temple_config key/value store."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.temple_config import TempleConfig

DEFAULTS: dict[str, tuple[str, str]] = {
    "ticket_sale_start_time": ("08:00", "When the East-gate ticket counter opens."),
    "rs50_ticket_price": ("50", "Price (INR) of the first-tier line ticket."),
    "rs200_ticket_price": ("200", "Price (INR) of the second-tier line ticket."),
    "rs50_sold_out": ("false", "true when Rs.50 tickets are sold out for the day."),
    "rs200_sold_out": ("false", "true when Rs.200 tickets are sold out for the day."),
    "temple_open_time": ("05:30", "Temple opening time."),
    "temple_close_time": ("21:00", "Temple closing time."),
    "volunteer_phone": ("", "Active volunteer's WhatsApp number."),
}


def get(db: Session, key: str) -> Optional[TempleConfig]:
    return db.execute(
        select(TempleConfig).where(TempleConfig.key == key)
    ).scalar_one_or_none()


def list_all(db: Session) -> list[TempleConfig]:
    return list(db.execute(select(TempleConfig).order_by(TempleConfig.key)).scalars())


def upsert(
    db: Session,
    key: str,
    value: str,
    *,
    description: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> TempleConfig:
    row = get(db, key)
    now = datetime.now(timezone.utc)
    if row is None:
        row = TempleConfig(
            key=key,
            value=value,
            description=description,
            updated_at=now,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.value = value
        if description is not None:
            row.description = description
        row.updated_at = now
        row.updated_by = updated_by
    db.flush()
    return row


def ensure_defaults(db: Session) -> int:
    """Insert any missing default keys. Returns the count of new rows."""
    inserted = 0
    for key, (value, description) in DEFAULTS.items():
        if get(db, key) is None:
            upsert(db, key, value, description=description)
            inserted += 1
    return inserted


def is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}
