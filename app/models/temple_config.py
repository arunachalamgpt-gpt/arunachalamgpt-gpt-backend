"""Key/value config table mutable from admin WhatsApp commands.

Values are stored as strings — callers coerce. This lets a single table back
booleans (`rs50_sold_out`), prices (`rs50_ticket_price`), and times
(`ticket_sale_start_time`) without per-field migrations.

Default rows are seeded by `app.services.temple_config.ensure_defaults()`.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TempleConfig(SQLModel, table=True):
    __tablename__ = "temple_config"

    key: str = Field(primary_key=True, max_length=80)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=_utcnow)
    updated_by: Optional[str] = Field(default=None, max_length=20)
