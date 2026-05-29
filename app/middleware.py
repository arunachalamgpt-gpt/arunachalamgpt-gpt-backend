"""HTTP middleware and per-request context.

- `request_id_var` — ContextVar holding the current request's id, accessible
  anywhere in the call stack (services, logs, error handlers).
- `RequestContextMiddleware` — assigns/propagates `X-Request-ID`, emits an
  access log line with method, path, status, and elapsed ms.
- `RequestIdFilter` — logging filter that injects `request_id` into every
  `LogRecord` so the formatter can render `rid=<id>`.
"""

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id")
        rid = incoming or uuid.uuid4().hex
        token = request_id_var.set(rid)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            request_id_var.reset(token)

        response.headers["x-request-id"] = rid
        logger.info(
            "%s %s -> %s in %.1fms [rid=%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            rid,
        )
        return response


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds `max_bytes`."""

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "payload_too_large",
                                "message": f"Request body exceeds {self.max_bytes} bytes",
                                "request_id": request_id_var.get(),
                            }
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)
