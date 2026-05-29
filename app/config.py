"""Environment-driven application configuration.

Reads `.env` at import time and exposes typed module-level constants used
across the app:

- `DB_CONNECTION_STRING` — full Postgres URL (URL-encode special chars in pwd)
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE` —
  SQLAlchemy QueuePool tuning
- `DB_ECHO` — when true, log every SQL statement
- `APP_HOST` / `APP_PORT` / `APP_RELOAD` — uvicorn launch settings (see run.py)

Fails fast at import if `DB_CONNECTION_STRING` is missing.
"""

import os
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

if not DB_CONNECTION_STRING:
    raise RuntimeError("DB_CONNECTION_STRING is not set in environment")

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
APP_RELOAD = os.getenv("APP_RELOAD", "true").lower() == "true"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1 * 1024 * 1024)))

LOCAL_TZ_OFFSET_MINUTES = int(os.getenv("LOCAL_TZ_OFFSET_MINUTES", "330"))
