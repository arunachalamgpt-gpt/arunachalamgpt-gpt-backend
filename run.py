"""Process entrypoint.

Reads host/port/reload from `app.config` (driven by `.env`) and launches
uvicorn against `app.main:app`. Run with `python run.py`.

Render / Heroku / Fly inject `$PORT` at runtime — honour that override so we
don't need a platform-specific code path.
"""

import os

import uvicorn

from app.config import APP_HOST, APP_PORT, APP_RELOAD

if __name__ == "__main__":
    port = int(os.environ.get("PORT", APP_PORT))
    uvicorn.run(
        "app.main:app",
        host=APP_HOST,
        port=port,
        reload=APP_RELOAD,
    )
