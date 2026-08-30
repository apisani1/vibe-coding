"""System endpoints: health, used by Docker and by the start scripts."""

from __future__ import annotations

from typing import Literal, TypedDict

from fastapi import APIRouter

from finally_app import __version__

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(TypedDict):
    """Shape of the health payload."""

    status: Literal["ok"]
    version: str


@router.get("/health")
def health() -> HealthResponse:
    """Report that the process is up and serving.

    Deliberately shallow: it must not touch the database or the market source,
    because a health check that fails when a dependency is degraded turns a
    partial outage into a container restart loop.
    """
    return {"status": "ok", "version": __version__}
