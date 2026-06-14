"""Lightweight `X-API-Key` guard for the open POST endpoints.

Applied via `Depends(require_api_key)` on the routes that aren't already
authenticated by Twilio's HMAC signature. When `API_KEY` is unset (default
in dev/tests), the dependency is a no-op so local development and the test
suite continue to work without credentials.

The comparison uses `hmac.compare_digest` to avoid timing attacks.
"""

import hmac

from fastapi import Header, HTTPException, status

from app import config


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = config.API_KEY
    if not expected:
        # Auth disabled — allow.
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
