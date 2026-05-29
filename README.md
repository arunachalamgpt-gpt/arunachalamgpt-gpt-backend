# ArunachalamGPT Backend

FastAPI service powering **Feature 6 — Verified Lodge Booking** for the
ArunachalamGPT WhatsApp assistant. Devotees travelling to Tiruvannamalai
book personally-verified lodges near Arunachaleswarar Temple, pay a Rs.49
booking fee, and pay the room rent at the lodge on arrival.

## Stack

| Layer | Choice |
| --- | --- |
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| ORM | SQLModel (Pydantic + SQLAlchemy 2.0) |
| Driver | psycopg2-binary |
| Database | Supabase Postgres (pooler) |
| Env loader | python-dotenv |

## Project layout

```
arunachalamgpt-gpt-backend/
├── run.py                       # uvicorn launcher, reads APP_PORT from env
├── requirements.txt
├── .env / .env.example
├── .gitignore
├── alembic.ini                  # Alembic config; URL pulled from app.config
├── alembic/
│   ├── env.py                   # bridges Alembic to SQLModel.metadata
│   ├── script.py.mako           # revision template
│   └── versions/                # generated migration files
├── scripts/
│   └── reset_db.py              # dev-only: drop everything + alembic upgrade head
└── app/
    ├── main.py                  # FastAPI composition, lifespan, routers, /docs
    ├── config.py                # env-driven settings
    ├── database.py              # engine + pool + session + table init
    ├── errors.py                # domain exception hierarchy
    ├── exception_handlers.py    # global handlers, uniform JSON envelope
    ├── middleware.py            # X-Request-ID + access logging
    ├── logging_config.py        # stdout logger with request-id context
    ├── models/                  # SQLModel ORM tables
    │   └── lodge.py
    ├── schemas/                 # Pydantic request/response schemas
    │   └── lodge.py
    ├── services/                # Business logic
    │   ├── booking.py           # create / confirm / cancel + refund rule
    │   └── availability.py      # daily updates + auto increment/decrement
    └── routers/                 # HTTP endpoints
        ├── lodges.py
        └── bookings.py
```

## Database migrations

Schema changes go through **Alembic**. The lifespan no longer auto-creates
tables — apply migrations explicitly before starting the app.

### Day-one bootstrap

You're already past day one with stale columns on Supabase. Drop and rebuild:

```bash
python scripts/reset_db.py --yes      # drops every app table + alembic_version, runs `alembic upgrade head`
python run.py
```

### Normal day-to-day flow

```bash
alembic upgrade head                  # apply pending migrations
python run.py
```

### Schema change → new migration

1. Edit `app/models/lodge.py` (or add a new model under `app/models/`).
2. Generate the migration:
   ```bash
   alembic revision --autogenerate -m "describe_the_change"
   ```
3. Open the new file under `alembic/versions/`, **review the diff** (autogen
   misses things like Postgres enum changes), commit it.
4. Apply it:
   ```bash
   alembic upgrade head
   ```

### Rolling back

```bash
alembic downgrade -1                  # one step back
alembic downgrade <revision_id>       # to a specific revision
alembic history                       # see what's available
```

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

The server listens on `APP_PORT` (default **8080**). Override in `.env`:

```
APP_HOST=0.0.0.0
APP_PORT=9090
APP_RELOAD=true
```

### URLs

- Swagger UI → http://localhost:8080/docs
- ReDoc → http://localhost:8080/redoc
- OpenAPI JSON → http://localhost:8080/openapi.json
- Liveness → http://localhost:8080/health
- DB + pool stats → http://localhost:8080/db-check

## Postman collection

A ready-to-import collection lives at
[postman/ArunachalamGPT-Backend.postman_collection.json](postman/ArunachalamGPT-Backend.postman_collection.json).

It includes every endpoint with sample payloads, a `{{baseUrl}}` variable
(defaults to `http://localhost:8080`), and test scripts that chain requests
end-to-end:

1. **Create lodge** stores the new `id` as `{{lodge_id}}`.
2. **Update lodge — mark verified** flips `verified=true`.
3. **Set daily availability** seeds rooms for `{{checkin_date}}` (default
   `2026-06-15`; edit the variable to test other days).
4. **Create booking** generates a fresh `Idempotency-Key` per click and stores
   `booking_ref` as `{{booking_ref}}` — used by the confirm-payment and
   cancel requests.

Import via *File → Import → Upload* in Postman, pick the JSON, then click
through the requests in folder order for a working smoke test.

## Security audit

Direct dependencies are pinned to known-good versions in `requirements.txt`
and `requirements-dev.txt`. Run a CVE scan against the PyPI Advisory Database
any time:

```bash
pip install pip-audit
pip-audit
```

A clean run reports `No known vulnerabilities found`. Run this in CI on every
PR and at least weekly on `main` to catch newly-disclosed CVEs against pinned
versions.

## Tests

Install dev deps and run the suite with coverage:

```bash
pip install -r requirements-dev.txt
pytest
```

The run enforces **100% line coverage** of `app/` (`--cov-fail-under=100`) and
prints a missing-lines report; an HTML report is written to `htmlcov/`. Tests
use an in-memory SQLite — production `psql` is never touched. The model layer
stays Postgres-compatible because the `StringArray` type-decorator in
[app/models/types.py](app/models/types.py) transparently switches to JSON on
SQLite.

## Docker

Build:
```bash
docker build -t arunachalamgpt-backend .
```

Run (pass secrets via `--env-file`; never bake them into the image):
```bash
docker run --rm -p 8080:8080 --env-file .env arunachalamgpt-backend
```

Override the port without rebuilding:
```bash
docker run --rm -p 9090:9090 -e APP_PORT=9090 --env-file .env arunachalamgpt-backend
```

The image uses `python:3.12-slim`, runs as a non-root `app` user, installs
`libpq5` for `psycopg2`, exposes `8080`, and ships a `HEALTHCHECK` against
`/health`. Layers are ordered so application-code edits don't bust the
`pip install` cache.

## Configuration

All settings come from environment variables (loaded from `.env`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_CONNECTION_STRING` | *(required)* | Full Postgres URL; URL-encode special chars in the password (e.g. `@` → `%40`). |
| `DB_POOL_SIZE` | `5` | Persistent connections in the pool. |
| `DB_MAX_OVERFLOW` | `10` | Extra connections allowed beyond `pool_size`. |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a free connection. |
| `DB_POOL_RECYCLE` | `1800` | Recycle connections older than this many seconds (avoids stale Supabase connections). |
| `DB_ECHO` | `false` | When `true`, logs every SQL statement. |
| `APP_HOST` | `0.0.0.0` | Bind host. |
| `APP_PORT` | `8080` | Listen port. |
| `APP_RELOAD` | `true` | Uvicorn auto-reload (dev only). |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins for CORS. |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Reject requests with a Content-Length above this (1 MiB default). |
| `LOCAL_TZ_OFFSET_MINUTES` | `330` | Minutes offset from UTC for "today" and the 24-hour refund window (IST = 330). |

## API map

### Lodges (`/lodges`)
- `GET /lodges` — directory list with `verified_only`, `max_walk_minutes`, `max_price` filters
- `GET /lodges/search?checkin_date=...` — verified lodges with availability for a date, plus **backup** lodges when primary is full (Method 3 of the design)
- `GET /lodges/{id}` — single lodge details
- `POST /lodges` — admin: create a lodge
- `PATCH /lodges/{id}` — admin: toggle `verified`, change pricing, etc.
- `GET /lodges/{id}/availability?date=...` — read the room count
- `POST /lodges/{id}/availability` — lodge owner's daily update (wired to the `AVAIL N` WhatsApp message in production)

### Bookings (`/bookings`)
- `POST /bookings` — create a `pending` booking, generates `TVM-LODGE-XXXX` reference, decrements availability
- `GET /bookings?phone=...&status=...` — devotee's bookings, newest first
- `GET /bookings/{ref}` — single booking
- `POST /bookings/{ref}/confirm-payment` — verify Rs.49 fee, status → `confirmed`
- `POST /bookings/{ref}/cancel?cancelled_by_lodge=true|false` — apply 24-hour refund rule, restore availability

### System
- `GET /` — banner
- `GET /health` — liveness
- `GET /db-check` — DB round-trip + live pool counters

## Robustness guarantees

- **Anti-oversell.** `decrement`/`set_availability` take a `SELECT ... FOR UPDATE`
  lock on the `lodge_availability` row, serializing concurrent bookings for the
  same lodge/date. A DB-level `CHECK (rooms_available >= 0)` is a second line of
  defence.
- **Unique booking references.** Refs are random 6-char Crockford-style strings
  (alphabet excludes `0`, `O`, `1`, `I`, `L`). The `booking_ref` column is
  uniquely indexed; insertion retries up to 5 times on conflict before raising
  a 409.
- **Idempotent booking creation.** Clients pass an `Idempotency-Key` header.
  Replays return the original booking — no double-hold.
- **Past-date rejection.** `BookingCreate.checkin_date` and
  `AvailabilityUpdate.date` reject any value before "today in IST".
- **Phone format check.** Both `Lodge.phone` and `BookingCreate.devotee_phone`
  validate against an E.164-style pattern.
- **Body size cap.** `MAX_REQUEST_BODY_BYTES` middleware rejects oversized
  requests with a 413 envelope before any handler runs.
- **CORS** is configurable via `CORS_ORIGINS` (defaults to `*` for dev).
- **Session safety.** `get_db()` rolls back on any exception before closing,
  so a failed request never leaks a dirty transaction back to the pool.

## Business rules

**Booking lifecycle**

```
pending ── confirm_payment ──► confirmed ──► checked_in ──► completed
   │                                    │
   └─────────── cancel ────────► cancelled (with refund_amount computed)
                                                                  no_show (terminal)
```

**24-hour refund rule** (`app/services/booking.py::cancel_booking`)

| Who cancels | When | Refund |
| --- | --- | --- |
| Devotee | 24h+ before check-in | Full Rs.49 refund |
| Devotee | <24h before check-in | No refund (lodge held the room) |
| Devotee | No-show | No refund |
| Lodge | Any time | Full refund + backup arranged |

**Availability accounting** (`app/services/availability.py`)

- `set_availability` — owner's daily `AVAIL N` update
- `decrement` — auto on new booking
- `increment` — auto on cancellation

## Error envelope

Every error response is shaped like:

```json
{
  "error": {
    "code": "lodge_not_verified",
    "message": "Lodge is not verified — booking blocked",
    "request_id": "a3f1c2...",
    "details": { "lodge_id": "..." }
  }
}
```

`request_id` matches the `X-Request-ID` response header and the `rid=...`
log field, so a single request can be traced across services. `code` is
stable; clients should switch on it rather than the human-readable
`message`.

### Error code reference

| Code | HTTP | Source |
| --- | --- | --- |
| `lodge_not_found` | 404 | Lodge id does not exist |
| `booking_not_found` | 404 | `TVM-LODGE-XXXX` reference unknown |
| `availability_not_found` | 404 | No availability record for that lodge/date |
| `lodge_not_verified` | 400 | Attempt to book an unverified lodge |
| `no_rooms_available` | 409 | Availability count is zero |
| `invalid_booking_state` | 409 | e.g. confirming a cancelled booking |
| `integrity_violation` | 409 | DB unique/FK constraint violated |
| `validation_failed` | 422 | Pydantic request validation failed |
| `database_error` | 503 | DB unreachable / query failed |
| `internal_error` | 500 | Unhandled exception (logged with stack trace) |

## Things deliberately left for later

- WhatsApp bot bridge (parsing `AVAIL`, `PAID`, `CANCEL` messages → these endpoints)
- Razorpay webhook handler for auto-payment-verification (Phase 2/3 of design)
- Authentication (anyone can hit endpoints today — needs API key or JWT before launch)
- Pournami / Karthigai date detection — `POURNAMI_DAYS_OF_MONTH` is empty; wire to a lunar-calendar lookup so `price_pournami` actually triggers
- Photo upload to Supabase Storage — `photo_urls` is a plain text array right now
- Alembic migrations — currently using `create_all` for dev convenience
