"""ArunachalamGPT Backend — Feature 6: Verified Lodge Booking.

Package layout:

- `main` — FastAPI app composition and lifespan
- `config` — env-driven settings
- `database` — engine, pool, session, table bootstrap
- `errors` — domain exception hierarchy
- `exception_handlers` — global handlers (uniform JSON error envelope)
- `middleware` — X-Request-ID + access logging
- `logging_config` — stdout logger with request-id context
- `models` — SQLModel ORM tables
- `schemas` — Pydantic request/response models
- `services` — business logic (booking, availability)
- `routers` — HTTP endpoints (lodges, bookings)
"""
