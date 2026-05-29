"""Process-wide logging setup.

- Single stdout `StreamHandler` with a `RequestIdFilter` so every log line
  carries the current request's id (`-` when outside a request context).
- Format: `TIMESTAMP | LEVEL | logger | rid=<id> | message`
- Tames noisy SQLAlchemy loggers; leaves uvicorn access logs visible.

Call `setup_logging()` once from the entrypoint. Repeat calls are no-ops.
"""

import logging
import sys

from app.middleware import RequestIdFilter


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | rid=%(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("sqlalchemy.pool").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
