"""Process entrypoint.

Reads host/port/reload from `app.config` (driven by `.env`) and launches
uvicorn against `app.main:app`. Run with `python run.py`.
"""

import uvicorn

from app.config import APP_HOST, APP_PORT, APP_RELOAD

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_RELOAD,
    )
