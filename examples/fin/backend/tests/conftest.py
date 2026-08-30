"""Shared fixtures.

Every test builds its own app from explicit settings, so nothing depends on the
developer's `.env` and no test can reach OpenRouter (check B7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from finally_app import main
from finally_app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Offline settings pointing at a throwaway database."""
    return Settings(
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=True,
        db_path=tmp_path / "finally.db",
        # httpx's ASGI default host is `test`; Starlette's is `testserver`.
        # Set here rather than shipped in the production default, so the app's
        # own allow-list carries no test scaffolding.
        allowed_hosts=("test", "testserver", "localhost", "127.0.0.1"),
    )


@pytest.fixture
def app(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """An application instance wired to the throwaway database, and no frontend.

    ``STATIC_DIR`` is pinned to a path that does not exist so the suite behaves
    identically on a checkout that has run ``npm run build`` and copied the
    export into the package, and on one that has never seen Node. Without this
    pin the default app inherits whatever is on disk: every test whose docstring
    says "no export mounted" quietly tested the *mounted* arrangement on a built
    checkout, which is how a test stops meaning what it claims. Tests that want
    the export mounted build their own app (``tests/test_static_mount.py``).
    """
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path / "no-frontend-export")
    return main.create_app(settings)
