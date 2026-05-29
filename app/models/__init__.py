"""SQLModel ORM tables.

Importing this package registers all `table=True` classes with
`SQLModel.metadata`, which `init_tables()` in `app.database` uses to create
schema at startup.
"""

from app.models.lodge import Lodge, LodgeAvailability, LodgeBooking

__all__ = ["Lodge", "LodgeAvailability", "LodgeBooking"]
