"""FastAPI application entrypoint.

Composes the running service:

- installs structured logging
- adds the request-context middleware (X-Request-ID, access logs)
- registers global exception handlers (uniform JSON error envelope)
- mounts the `lodges` and `bookings` routers
- runs DB connectivity verification + `create_all` at startup via lifespan
- exposes `/`, `/health`, `/db-check` for system probing
- serves Swagger UI at `/docs` and ReDoc at `/redoc`
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import exception_handlers
from app.config import CORS_ORIGINS, MAX_REQUEST_BODY_BYTES
from app.database import engine, get_db, verify_connection
from app.errors import DatabaseError
from app.logging_config import setup_logging
from app.middleware import MaxBodySizeMiddleware, RequestContextMiddleware
from app.routers import bookings as bookings_router
from app.routers import crowd as crowd_router
from app.routers import devotees as devotees_router
from app.routers import lodges as lodges_router
from app.routers import temple_config as temple_config_router
from app.routers import webhook as webhook_router

setup_logging()
logger = logging.getLogger(__name__)


API_DESCRIPTION = """
Backend for **ArunachalamGPT — Feature 6: Verified Lodge Booking**.

Devotees book personally-verified lodges near Arunachaleswarar Temple
(Tiruvannamalai). The flow:

1. **Search** verified lodges with availability for a given date.
2. **Create** a booking — generates `TVM-LODGE-XXXX` reference and holds a room.
3. **Confirm payment** of Rs.49 booking fee (room rent paid at lodge on arrival).
4. **Cancel** if needed — 24-hour refund rule applies automatically.

All errors return a uniform JSON envelope:
```json
{ "error": { "code": "lodge_not_found", "message": "...", "request_id": "..." } }
```
"""

TAGS_METADATA = [
    {"name": "crowd", "description": "Volunteer reports, live status, predictions, post-darshan history."},
    {"name": "devotees", "description": "Devotee profile + planning recommendation."},
    {"name": "webhook", "description": "WhatsApp bridge — drives the 10-step user journey."},
    {"name": "admin", "description": "temple_config CRUD and `ADMIN ...` command dispatch."},
    {"name": "lodges", "description": "Lodge directory, verified listings, daily availability."},
    {"name": "bookings", "description": "Devotee bookings: create, confirm payment, cancel."},
    {"name": "system", "description": "Health, DB diagnostics, root."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ArunachalamGPT Backend")
    try:
        verify_connection()
    except SQLAlchemyError:
        logger.exception("Startup aborted — database unreachable")
        raise
    yield
    logger.info("Shutting down — disposing DB engine")
    engine.dispose()


app = FastAPI(
    title="ArunachalamGPT Backend",
    description=API_DESCRIPTION,
    version="0.1.0",
    contact={"name": "ArunachalamGPT", "email": "support@arunachalagpt.local"},
    license_info={"name": "Proprietary"},
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(MaxBodySizeMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)
exception_handlers.register(app)

app.include_router(crowd_router.router)
app.include_router(devotees_router.router)
app.include_router(webhook_router.router)
app.include_router(temple_config_router.router)
app.include_router(lodges_router.router)
app.include_router(bookings_router.router)


@app.get("/", tags=["system"], summary="Service banner")
def root():
    return {"message": "ArunachalamGPT Backend is running", "docs": "/docs"}


@app.get("/health", tags=["system"], summary="Liveness probe")
def health():
    return {"status": "ok"}


@app.get(
    "/db-check",
    tags=["system"],
    summary="DB connectivity + pool stats",
    description="Runs `SELECT 1` and returns live SQLAlchemy pool counters.",
)
def db_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise DatabaseError(str(exc))

    pool = engine.pool

    def _stat(name: str):
        fn = getattr(pool, name, None)
        return fn() if callable(fn) else None

    return {
        "database": "connected",
        "pool": {
            "type": pool.__class__.__name__,
            "size": _stat("size"),
            "checked_in": _stat("checkedin"),
            "checked_out": _stat("checkedout"),
            "overflow": _stat("overflow"),
        },
    }
