"""Global FastAPI exception handlers.

Translates domain and framework exceptions into the uniform JSON envelope:

```json
{
  "error": {
    "code": "...",
    "message": "...",
    "request_id": "...",
    "details": {...}
  }
}
```

Handlers (most-specific first):

- `AppError` — domain errors → `status_code` and `code` from the class
- `StarletteHTTPException` — bare `raise HTTPException(...)`
- `RequestValidationError` — Pydantic body/query validation → 422 with per-field details
- `IntegrityError` — DB constraint violation (unique, FK) → 409
- `SQLAlchemyError` — other DB errors → 503 (with full stack trace logged)
- `Exception` — catch-all → 500 (also logged with stack trace)

Call `register(app)` from `main.py` to bind them.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError, ConflictError, DatabaseError
from app.middleware import request_id_var

logger = logging.getLogger(__name__)


def _error_body(
    *, code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(),
        }
    }
    if details:
        body["error"]["details"] = details
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.info(
        "AppError on %s %s: code=%s message=%s",
        request.method,
        request.url.path,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code=exc.code, message=exc.message, details=exc.details),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            code=f"http_{exc.status_code}",
            message=str(exc.detail) if exc.detail else "HTTP error",
        ),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "loc": ".".join(str(p) for p in err["loc"]),
            "msg": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    logger.info(
        "ValidationError on %s %s: %s",
        request.method,
        request.url.path,
        errors,
    )
    return JSONResponse(
        status_code=422,
        content=_error_body(
            code="validation_failed",
            message="Request body or query failed validation",
            details={"errors": errors},
        ),
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    logger.warning(
        "IntegrityError on %s %s: %s",
        request.method,
        request.url.path,
        getattr(exc.orig, "args", exc),
    )
    return JSONResponse(
        status_code=ConflictError.status_code,
        content=_error_body(
            code="integrity_violation",
            message="Operation violates a database constraint",
        ),
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.exception(
        "SQLAlchemyError on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=DatabaseError.status_code,
        content=_error_body(
            code=DatabaseError.code,
            message=DatabaseError.message,
        ),
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(
            code="internal_error",
            message="An unexpected error occurred",
        ),
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
