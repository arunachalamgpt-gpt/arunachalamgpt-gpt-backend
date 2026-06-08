# ArunachalamGPT Backend

FastAPI service powering the ArunachalamGPT WhatsApp assistant for devotees
travelling to Tiruvannamalai.

- **Feature 1 — Crowd Alert and Visit Planning.** Live East-gate crowd
  status from hourly volunteer reports, historical-prediction fallback,
  multi-language devotee profiles, the 10-step user journey driven by the
  WhatsApp webhook, planning advice for families with elderly or children,
  admin commands for sold-out tickets and config tweaks.
- **Feature 6 — Verified Lodge Booking.** Devotees book personally-verified
  lodges near Arunachaleswarar Temple, pay a Rs.49 booking fee, and pay the
  room rent at the lodge on arrival.

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
├── requirements.txt             # runtime deps (pinned)
├── requirements-dev.txt         # pytest, pytest-cov, httpx, pip-audit
├── pytest.ini                   # --cov-fail-under=100
├── .coveragerc                  # coverage scope = app/
├── Dockerfile                   # python:3.12-slim, non-root, /health probe
├── .env / .env.example
├── .gitignore / .dockerignore
├── alembic.ini                  # Alembic config; URL pulled from app.config
├── alembic/
│   ├── env.py                   # bridges Alembic to SQLModel.metadata
│   ├── script.py.mako           # revision template (auto-imports sqlmodel + StringArray)
│   └── versions/                # generated migration files
├── scripts/
│   └── reset_db.py              # dev-only: drop everything + alembic upgrade head
├── postman/
│   ├── Feature1-Crowd-Alert.postman_collection.json
│   └── ArunachalamGPT-Backend.postman_collection.json
├── tests/                       # 100% coverage suite (184 tests)
└── app/
    ├── main.py                  # FastAPI composition, lifespan, routers, /docs
    ├── config.py                # env-driven settings
    ├── database.py              # engine + pool + session + table init
    ├── errors.py                # domain exception hierarchy
    ├── exception_handlers.py    # global handlers, uniform JSON envelope
    ├── middleware.py            # X-Request-ID + access logging + body size cap
    ├── logging_config.py        # stdout logger with request-id context
    ├── models/                  # SQLModel ORM tables
    │   ├── types.py             # StringArray — ARRAY(Text) on Postgres, JSON on SQLite
    │   ├── crowd.py             # Feature 1: CrowdStatus, CrowdHistory
    │   ├── devotee.py           # Feature 1: DevoteeProfile
    │   ├── temple_config.py     # Feature 1: TempleConfig key/value store
    │   └── lodge.py             # Feature 6: Lodge, LodgeBooking, LodgeAvailability
    ├── schemas/                 # Pydantic request/response schemas
    │   ├── crowd.py
    │   ├── devotee.py
    │   ├── temple_config.py
    │   └── lodge.py
    ├── services/                # Business logic
    │   ├── crowd.py             # Feature 1: volunteer parser + fallback rules
    │   ├── prediction.py        # Feature 1: avg waits from crowd_history
    │   ├── planning.py          # Feature 1: Step 3 advice (elderly/children)
    │   ├── admin_commands.py    # Feature 1: ADMIN config|crowd|broadcast parser
    │   ├── devotee_flow.py      # Feature 1: 10-step state machine (LLM-first, keyword fallback)
    │   ├── temple_config.py     # Feature 1: key/value CRUD + seed defaults
    │   ├── llm.py               # Feature 1: OpenAI GPT-4o client wrapper
    │   ├── intent.py            # Feature 1: LLM intent classifier (romanized text aware)
    │   ├── translator.py        # Feature 1: reply translator into devotee's language
    │   ├── whatsapp.py          # Feature 1: Twilio bridge (signature verify + send_text)
    │   ├── booking.py           # Feature 6: create / confirm / cancel + refund rule
    │   ├── availability.py      # Feature 6: daily updates + auto increment/decrement
    │   └── pricing.py           # Feature 6: normal/Pournami/Karthigai price selection
    └── routers/                 # HTTP endpoints
        ├── crowd.py             # Feature 1
        ├── devotees.py          # Feature 1
        ├── webhook.py           # Feature 1: POST /webhook/whatsapp
        ├── temple_config.py     # Feature 1: /admin/config + /admin/commands
        ├── lodges.py            # Feature 6
        └── bookings.py          # Feature 6
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

## Postman collections

Three ready-to-import collections live under `postman/`:

### All APIs (recommended)
[postman/ArunachalamGPT-All-APIs.postman_collection.json](postman/ArunachalamGPT-All-APIs.postman_collection.json)

Every endpoint in one collection — 39 requests across 7 folders:
**System · Crowd · Devotees · Webhook (WhatsApp) · Admin · Lodges · Bookings**.
End-to-end smoke test: `Health → Crowd report → Current → Webhook (Hi → 1 →
register date → plan) → Admin sold-out → Lodge create → Lodge verify → Set
availability → Booking create → Confirm payment → Cancel`.

### Feature 1 — Crowd Alert (subset)
[postman/Feature1-Crowd-Alert.postman_collection.json](postman/Feature1-Crowd-Alert.postman_collection.json)

Folders: **Crowd · Devotees · Webhook (WhatsApp) · Admin**. End-to-end flow:
1. *Crowd / Submit raw volunteer message* — `F:180 T50:40 T200:15`
2. *Crowd / Get current* — should return `freshness: live`
3. *Webhook / First contact (Hi)* — language menu
4. *Webhook / Pick language (1=Tamil)* — saved on profile
5. *Webhook / Register visit date + elderly* — saves planned date and flags
6. *Webhook / Ask for plan* — returns Step 3 recommendation
7. *Admin / Run command — ADMIN config rs50_sold_out true* — flips sold-out flag
8. *Crowd / Get current* — confirms `rs50_sold_out: true` propagates

### Feature 6 — Verified Lodge Booking (subset)
[postman/ArunachalamGPT-Backend.postman_collection.json](postman/ArunachalamGPT-Backend.postman_collection.json)

Folders: **System · Lodges · Bookings**. End-to-end flow:
1. *Lodges / Create lodge* — captures `{{lodge_id}}`
2. *Lodges / Update lodge — mark verified* — flips `verified=true`
3. *Lodges / Set daily availability* — seeds rooms for `{{checkin_date}}`
4. *Bookings / Create booking* — generates a fresh `Idempotency-Key` per click,
   captures `{{booking_ref}}`
5. *Bookings / Confirm payment* — moves status to `confirmed`
6. *Bookings / Cancel booking* — applies the 24h refund rule

Both collections use a `{{baseUrl}}` variable (default `http://localhost:8080`)
and chain captured IDs via test scripts. Import via *File → Import → Upload*
in Postman, then click through the requests in folder order.

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

The run enforces **100% line coverage** of `app/` (`--cov-fail-under=100`) — at
last count **241 tests** covering models, schemas, services (parsers,
fallback, state machine, refund rule, LLM wrapper, intent classifier,
translator, Twilio signature verify + send), routers, middleware, handlers,
the lifespan, and reflection of the OpenAPI schema. An HTML coverage report is
written to `htmlcov/`. Tests use an in-memory SQLite — production `psql` is
never touched. The model layer stays Postgres-compatible because the
`StringArray` type-decorator in [app/models/types.py](app/models/types.py)
transparently switches to JSON on SQLite.

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
| `OPENAI_ENABLED` | `false` | Master switch for the GPT-4o intent classifier + reply translator. Off in dev/tests. |
| `OPENAI_API_KEY` | *(unset)* | OpenAI API key. Required when `OPENAI_ENABLED=true`. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name. `gpt-4o-mini` is cheaper; switch to `gpt-4o` for higher-quality translations. |
| `OPENAI_TIMEOUT_SECONDS` | `8` | Per-request timeout. Short so a stalled call can't block a WhatsApp reply. |
| `TWILIO_ENABLED` | `false` | Master switch for the Twilio WhatsApp bridge. Off in dev/tests. |
| `TWILIO_ACCOUNT_SID` | *(unset)* | Twilio account SID (`AC…`). Required when enabled. |
| `TWILIO_AUTH_TOKEN` | *(unset)* | Twilio auth token. Used for HTTP Basic auth on outbound + HMAC verification on inbound. |
| `TWILIO_FROM_NUMBER` | *(unset)* | Sender phone in E.164 (`+14155238886` for the sandbox). |
| `TWILIO_WEBHOOK_URL` | *(unset)* | The exact public URL Twilio is configured to call. Must match what's set in Twilio Console for signature verification to succeed. |
| `TWILIO_TIMEOUT_SECONDS` | `8` | Per-request timeout for outbound Twilio API calls. |

## API map

### Crowd (`/crowd`) — Feature 1
- `POST /crowd/reports` — volunteer raw WhatsApp text `F:180 T50:40 T200:15`
- `POST /crowd/reports/structured` — same payload, pre-parsed
- `GET /crowd/current` — live status with fallback (`live` / `stale` / `prediction_only` / `closed`)
- `GET /crowd/predict?visit_date=...&hour_of_day=...&is_pournami=...&is_festival=...`
- `POST /crowd/history` — post-darshan crowdsourced observation (Step 10)
- `GET /crowd/history` — paginated history

### Devotees (`/devotees`) — Feature 1
- `POST /devotees` — upsert by phone (language, family details, planned date)
- `GET /devotees/{phone}` — profile
- `PATCH /devotees/{phone}` — partial update
- `GET /devotees/{phone}/plan` — Step 3 recommendation (arrival time + line + packing checklist)

### Webhook (`/webhook`) — Feature 1
- `POST /webhook/whatsapp` — bridge dispatch for the 10-step journey
  (language pick → visit registration → live crowd → planning advice → language change)

### Admin (`/admin`) — Feature 1
- `GET /admin/config` — list every `temple_config` key
- `GET /admin/config/{key}` — single value
- `PUT /admin/config/{key}` — upsert
- `POST /admin/commands` — run raw `ADMIN config|crowd|broadcast ...` text

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

## Feature 1 — user journey & fallback

**The 10-step journey driven by `POST /webhook/whatsapp`**

| # | Step | Trigger | Action |
| --- | --- | --- | --- |
| 1 | First contact | any text from unknown phone | Profile shell created, language menu returned |
| 2 | Language pick | reply with `1`–`5` | Saved on profile; state → `language_selected` |
| 3 | Planning query | keywords *plan / advice / when* | Returns arrival time + line + checklist (see `services/planning.py`) |
| 4 | Visit registration | `YYYY-MM-DD` or `DD/MM/YYYY` in text | Saves `planned_visit_date`; auto-detects elderly/children keywords |
| 5 | D-2 reminder | scheduler (out of scope) | Sends crowd prediction + ticket prices + packing |
| 6 | D-1 reminder | scheduler (out of scope) | Sends weather + checklist + medical-point info |
| 7 | Morning alert | scheduler (out of scope) | Sends live crowd from `/crowd/current` |
| 8 | At bus stand | keywords *crowd / queue / wait* | Returns `/crowd/current` summary in one line |
| 9 | At East gate | same | Same flow — devotee gets current line lengths |
| 10 | After darshan | `POST /crowd/history` from bot | Wait time stored for future predictions |

Steps 5–7 are scheduler jobs the WhatsApp bridge will own — the data they
need is exactly what `/crowd/current` and `/crowd/predict` return now.

**Volunteer message format** (`POST /crowd/reports`)

```
F:180 T50:40 T200:15        ← typical hourly report
F:200 T50:SOLD T200:15      ← Rs.50 sold out
F:180 T50:40 T200:SOLD      ← Rs.200 sold out
```

`F` = Free line, `T50` = Rs.50, `T200` = Rs.200. Each value is non-negative
integer minutes **or** the literal `SOLD`, which flips the corresponding
sold-out flag and stores NULL in the wait column. Tokens may appear in any
order; missing tokens are recorded as NULL.

**Fallback rules** (`GET /crowd/current`, mirrors design doc Section 9)

| Age of latest report | `freshness` |
| --- | --- |
| < 2 h | `live` |
| 2 – 6 h | `stale` |
| > 6 h | `prediction_only` |
| Before opening / after closing | `closed` |

Opening hours come from `temple_open_time` and `temple_close_time` in
`temple_config` and can be changed at runtime via `PUT /admin/config/{key}`.

**Admin commands** (`POST /admin/commands`)

```
ADMIN config rs50_sold_out true              ← upsert temple_config
ADMIN config ticket_sale_start_time 09:00
ADMIN crowd F:60 T50:15 T200:5               ← manual report (source=admin)
ADMIN broadcast Tamil Crowd is low now!      ← returns parsed payload
```

Unknown commands return `action: "unknown"` (HTTP 200) so the bridge can
reply with a help message rather than crash.

### GPT-4o intent classification + reply translation

The WhatsApp dispatch ([app/services/devotee_flow.py](app/services/devotee_flow.py))
runs an LLM **intent classifier first**, then falls back to keyword matching
if the LLM is disabled or returns `unknown`. Outgoing text is then passed
through a **translator** so the devotee sees the reply in their saved
language.

| Layer | File | Behaviour when `OPENAI_ENABLED=false` |
| --- | --- | --- |
| Client wrapper | [app/services/llm.py](app/services/llm.py) | `chat_json`/`chat_text` raise `LLMUnavailableError`; never makes a network call. |
| Intent classifier | [app/services/intent.py](app/services/intent.py) | Returns `IntentResult(intent="unknown")` so the keyword path runs. |
| Translator | [app/services/translator.py](app/services/translator.py) | Pass-through (English in, English out). |

This means dev + the test suite work without an API key, and prod can flip
`OPENAI_ENABLED=true` once the key is provisioned. Defaults:
- Model `gpt-4o-mini` (cheap; bump to `gpt-4o` for higher-quality translation)
- `temperature=0` for intent (deterministic JSON), `0.2` for translation
- 8-second per-request timeout
- Any LLM failure (network, auth, rate limit, non-JSON, timeout) is logged
  and silently falls back — the bot never crashes because OpenAI is down

**Intents recognised** (`select_language`, `register_visit`, `ask_crowd`,
`ask_plan`, `change_language`, `unknown`). The classifier understands
romanized text (*"crowd enna"*, *"ticket epdi"*, *"kuthukal enna ippo"*),
code-mix, and misspellings.

### Twilio WhatsApp bridge

Inbound + outbound wiring lives in [app/services/whatsapp.py](app/services/whatsapp.py)
and the route is `POST /webhook/whatsapp/twilio`.

**Inbound:**
1. Twilio POSTs form-encoded (`From=whatsapp:+919876543210`, `Body=…`,
   `MessageSid=…`, …) with an `X-Twilio-Signature` header.
2. We HMAC-SHA1 the configured `TWILIO_WEBHOOK_URL` + sorted form params with
   `TWILIO_AUTH_TOKEN`, base64-encode, and `hmac.compare_digest` against the
   header. Mismatch → 403.
3. Strip `whatsapp:+` from `From` → normalised phone.
4. Run the same `devotee_flow.handle_incoming` pipeline as the internal
   route (LLM → keyword → translator).
5. POST the reply back to Twilio's Messages API.

**Outbound:** `send_text(phone, body)` POSTs to
`https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json` with HTTP
Basic auth. Returns a `SendResult` with the provider message id or error —
never raises, so a failed send doesn't break the inbound flow.

**Disabled mode:** when `TWILIO_ENABLED=false` (default), the route returns
**503**, `send_text` returns `SendResult(sent=False, error="twilio_disabled")`,
and no network call is made.

#### Local testing with the Twilio sandbox

1. Sign up for Twilio and join the WhatsApp sandbox
   (`https://www.twilio.com/console/sms/whatsapp/sandbox`).
2. Expose your local server: `ngrok http 8080` — copy the HTTPS forwarding
   URL.
3. In the Twilio sandbox config, set **WHEN A MESSAGE COMES IN** to
   `https://<your-ngrok>.ngrok.app/webhook/whatsapp/twilio`.
4. Put the **same** URL in your `.env` as `TWILIO_WEBHOOK_URL` (signature
   verification compares against this exact string).
5. Set `TWILIO_ENABLED=true`, plus `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   and `TWILIO_FROM_NUMBER=+14155238886` (the sandbox number).
6. Restart, then text *"join &lt;keyword&gt;"* to the sandbox number from your
   own WhatsApp — Twilio relays it through `/webhook/whatsapp/twilio`.

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
| `lodge_not_found` | 404 | Lodge id does not exist (Feature 6) |
| `booking_not_found` | 404 | `TVM-LODGE-XXXXXX` reference unknown (Feature 6) |
| `availability_not_found` | 404 | No availability record for that lodge/date (Feature 6) |
| `devotee_not_found` | 404 | Devotee profile not found (Feature 1) |
| `config_not_found` | 404 | `temple_config` key not seeded (Feature 1) |
| `lodge_not_verified` | 400 | Attempt to book an unverified lodge (Feature 6) |
| `validation_failed` | 400 | Volunteer message parse error (Feature 1) or schema validation |
| `no_rooms_available` | 409 | Availability count is zero (Feature 6) |
| `invalid_booking_state` | 409 | e.g. confirming a cancelled booking (Feature 6) |
| `integrity_violation` | 409 | DB unique/FK constraint violated |
| `payload_too_large` | 413 | Request body exceeded `MAX_REQUEST_BODY_BYTES` |
| `validation_failed` | 422 | Pydantic request validation failed |
| `database_error` | 503 | DB unreachable / query failed |
| `internal_error` | 500 | Unhandled exception (logged with stack trace) |

## Things deliberately left for later

**Feature 1 — Crowd Alert:**
- APScheduler jobs for the D-2 (7 am), D-1 (7 pm), morning-of (6 am) push
  templates from Steps 5–7 of the design doc
- Broadcast send-out — `ADMIN broadcast` parses and returns a payload; need
  to wire it to `whatsapp.send_text` over every devotee in the target language
- Volunteer crowdsourcing rollup — periodic job aggregating `crowd_history`
  hourly to inflate prediction sample size beyond just post-darshan reports
- 360dialog provider (if Twilio's per-message price becomes a concern at scale)

**Feature 6 — Verified Lodge Booking:**
- Razorpay webhook handler for auto-payment-verification (Phase 2/3 of design)
- Pournami / Karthigai date detection — the sets in `services/pricing.py` are
  empty; wire to a lunar-calendar lookup so `price_pournami` / `price_karthigai`
  actually trigger
- Photo upload to Supabase Storage — `photo_urls` is a plain text array

**Cross-cutting:**
- Authentication — every endpoint is open today; needs an API key, JWT, or
  Cloudflare Access in front before going live
- Rate limiting (`slowapi`) once the WhatsApp bot is firing
- Structured JSON logs for a log aggregator — current format is human-readable
