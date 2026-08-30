"""The exported frontend is served without shadowing the API (R3, check C1).

The mount is a catch-all at ``/``. Two distinct failures live here, and the
plan anticipated only the first:

1. **The export registered before the routers** absorbs ``/api/health`` itself.
2. **The export registered after them, with nothing in between**, still absorbs
   every *unknown* ``/api`` path — no router matched, so the mount is the only
   thing left — and answers it with the export's ``404.html``. HTML, where the
   frontend's ``fetch`` wrapper expects JSON.

Both were measured against this fixture rather than reasoned about; the plan's
predicted symptom (an HTML shell with a **200**) turned out not to be what
Starlette does at all. ``main._add_api_not_found`` is what closes the second.

These tests run against a fixture export rather than a real ``npm run build``,
so the guarantee is covered by ``pytest`` on a machine with no Node.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finally_app import main
from finally_app.config import Settings

SHELL = "<!DOCTYPE html><html><body><div id='root'>FinAlly</div></body></html>"
NOT_FOUND_PAGE = "<!DOCTYPE html><html><body>404</body></html>"


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """A stand-in for ``frontend/out``: shell, one asset, and a ``404.html``.

    The ``404.html`` is not decoration. ``next build`` with ``output: 'export'``
    emits one (verified against this project's own ``out/``), and Starlette's
    ``StaticFiles(html=True)`` serves it — as **HTML** — for any path it cannot
    resolve. That is the whole shadowing symptom: a fixture without it makes
    unhandled paths raise a plain ``HTTPException``, which FastAPI renders as a
    *JSON* 404, and the test below then passes under a wrongly-ordered mount.
    Measured, not assumed: with the 404 page absent, mounting ahead of the
    routers left that test green.
    """
    export = tmp_path / "static"
    (export / "assets").mkdir(parents=True)
    (export / "index.html").write_text(SHELL, encoding="utf-8")
    (export / "404.html").write_text(NOT_FOUND_PAGE, encoding="utf-8")
    (export / "assets" / "app.js").write_text("console.log('finally');", encoding="utf-8")
    return export


@pytest.fixture
def mounted_app(settings: Settings, export_dir: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """An app built with the export in place, exactly as the container runs it."""
    monkeypatch.setattr(main, "STATIC_DIR", export_dir)
    return main.create_app(settings)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_root_serves_the_shell(mounted_app: FastAPI) -> None:
    response = await _get(mounted_app, "/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE" in response.text.upper()


@pytest.mark.asyncio
async def test_static_assets_are_served(mounted_app: FastAPI) -> None:
    """Not only the catch-all: real files under the export resolve too.

    Without this, a mount that served ``index.html`` for every path — including
    ``/assets/app.js`` — would pass the shell test while the page loaded no
    JavaScript at all.
    """
    response = await _get(mounted_app, "/assets/app.js")

    assert response.status_code == 200
    assert "console.log('finally')" in response.text


@pytest.mark.asyncio
async def test_api_still_answers_with_the_export_mounted(mounted_app: FastAPI) -> None:
    response = await _get(mounted_app, "/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_unknown_api_path_is_a_json_404_even_with_the_export_mounted(mounted_app: FastAPI) -> None:
    """**The check.** It fails under both ways of getting this wrong.

    Deleting ``_add_api_not_found`` leaves this returning ``text/html`` with the
    export's 404 page — the failure the plan missed. Moving the mount ahead of
    the routers fails it too. The status code alone would catch neither, since
    both wrong arrangements also answer 404: the content type is the assertion
    that discriminates.
    """
    response = await _get(mounted_app, "/api/definitely-not-a-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "<!DOCTYPE" not in response.text.upper()
    assert response.json()["detail"] == "No API route matches /api/definitely-not-a-route"


@pytest.mark.asyncio
async def test_the_bare_api_prefix_is_json_too(mounted_app: FastAPI) -> None:
    """``/api`` itself, which ``/api/{path:path}`` does not match.

    The overseer found this one: the pattern requires the separator, so the bare
    prefix reached the mount and came back as the export's ``404.html`` — while
    three docstrings claimed everything under ``/api`` was JSON, and while the
    same request had answered JSON *before* this checkpoint. A checkpoint that
    closes a class of bug and simultaneously reintroduces one instance of it is
    the reason this file tests the prefix and the paths separately.
    """
    response = await _get(mounted_app, "/api")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "No API route matches /api"


@pytest.mark.asyncio
async def test_a_real_route_with_a_trailing_slash_is_json(mounted_app: FastAPI) -> None:
    """Pins an accepted regression rather than wishing it away.

    ``/api/portfolio/`` used to answer 307 to the canonical path; the catch-all
    now matches it first, so it is a JSON 404. Nothing in this repo calls the
    trailing-slash form, and under a mounted export it returned the export's
    404 page anyway — but the change is real, so it is written down and pinned
    here instead of being discovered later as a mystery.
    """
    response = await _get(mounted_app, "/api/portfolio/")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_unknown_api_path_is_json_without_an_export_too(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same contract on a checkout that has never run ``npm``.

    Both arrangements must agree, or the frontend's error handling is tested
    against one shape and shipped against another.

    It builds its own app rather than taking the shared fixture — and when it
    did take the shared fixture, on this machine it was testing the mounted
    arrangement twice, because ``backend/src/finally_app/static/`` exists here
    after check C1 ran. The fixture now pins the same thing; this test states
    the requirement locally so it cannot regress if the fixture changes.
    """
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path / "never-built")
    app = main.create_app(settings)

    for path in ("/api", "/api/definitely-not-a-route"):
        response = await _get(app, path)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_app_builds_and_serves_the_api_without_an_export(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkout that has never run ``npm`` must still start.

    The backend is developed and tested without Node, so a missing export is a
    normal state. If this raised, every test in the suite would fail at import
    on a machine without a build.
    """
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path / "never-built")
    app = main.create_app(settings)

    assert (await _get(app, "/api/health")).status_code == 200
    assert (await _get(app, "/")).status_code == 404
