"""API-key authentication for the upload endpoint.

A single static key, supplied in the ``X-API-Key`` header, compared in constant time
(``secrets.compare_digest``) against the configured key. The key is read from ``Settings``
(env-derived) and is never logged. ``require_api_key`` is a dependency *factory* so the
key is injected, not read from a global — keeping construction separate from use.
"""

from __future__ import annotations

import secrets
from typing import (
    Callable,
    Optional,
)

from fastapi import (
    Header,
    HTTPException,
    status,
)

from .config import Settings

API_KEY_HEADER = "X-API-Key"


def require_api_key(settings: Settings) -> Callable[[Optional[str]], None]:
    """Return a FastAPI dependency that rejects requests without the correct API key."""
    expected = settings.api_key.encode("utf-8")

    def dependency(x_api_key: Optional[str] = Header(default=None)) -> None:
        provided = (x_api_key or "").encode("utf-8")
        if not secrets.compare_digest(provided, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing API key",
            )

    return dependency
