"""SQLModel ORM tables.

Importing this package registers all `table=True` classes with
`SQLModel.metadata`, which `init_tables()` (test) or Alembic (prod) uses to
build the schema.
"""

from app.models.crowd import CrowdHistory, CrowdStatus
from app.models.devotee import DevoteeProfile
from app.models.lodge import Lodge, LodgeAvailability, LodgeBooking
from app.models.temple_config import TempleConfig

__all__ = [
    "CrowdHistory",
    "CrowdStatus",
    "DevoteeProfile",
    "Lodge",
    "LodgeAvailability",
    "LodgeBooking",
    "TempleConfig",
]
