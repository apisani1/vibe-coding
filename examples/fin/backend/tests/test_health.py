"""The skeleton is wired: the app builds, routes resolve, and /api/health answers."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finally_app.config import DEFAULT_ALLOWED_HOSTS, load_settings


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_health_reports_ok(app: FastAPI) -> None:
    response = await _get(app, "/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_health_does_not_touch_the_database(app: FastAPI, settings: object) -> None:
    """A health check that depends on SQLite turns a degraded dependency into a restart loop."""
    await _get(app, "/api/health")

    db_path = app.state.settings.db_path
    assert not db_path.exists()


@pytest.mark.asyncio
async def test_unknown_api_path_is_a_json_404(app: FastAPI) -> None:
    """Guard for R3 **on the no-export arrangement only**.

    This docstring used to claim the assertion "cannot regress once the export
    is mounted". Since CP10 pinned ``STATIC_DIR`` in the shared ``app`` fixture,
    this test never sees a mounted export, so the claim is false — and it was
    only ever true on a machine that happened to have run ``npm run build``. The
    mounted arrangement is covered deterministically by
    ``tests/test_static_mount.py``, which builds its own app around a fixture
    export; what remains here is that an unknown ``/api`` path is a JSON 404 on
    a checkout with no frontend at all. Both arrangements must agree.

    Behavioural rather than structural on purpose: an earlier version of this
    test inspected ``app.routes`` and broke immediately, because this FastAPI
    version keeps included routers in an ``_IncludedRouter`` wrapper instead of
    flattening them. What matters is the response, not the route table's shape.
    """
    response = await _get(app, "/api/definitely-not-a-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "<!DOCTYPE" not in response.text.upper()


def test_startup_configuration_is_actually_logged(caplog: pytest.LogCaptureFixture) -> None:
    """The startup lines must reach a handler, not just be issued.

    uvicorn configures only the uvicorn.* loggers and leaves root at WARNING,
    so a plain module logger emits nothing under the documented run command.
    The README tells the reader to check this output before assuming the chat
    is mocked, which makes its absence a documentation lie, not a cosmetic gap.
    """
    from finally_app.config import Settings
    from finally_app.main import _log_startup_configuration

    offline = Settings(
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=True,
        db_path=Path("unused.db"),
    )
    with caplog.at_level("INFO", logger="finally_app.main"):
        _log_startup_configuration(offline)

    messages = " ".join(record.message for record in caplog.records)
    assert "simulator" in messages
    assert "mock" in messages


@pytest.mark.asyncio
async def test_a_foreign_host_header_is_refused(app: FastAPI) -> None:
    """DNS rebinding is the attack that survives "it is localhost, there is no login".

    An attacker page re-resolves its own domain to 127.0.0.1 and becomes
    **same-origin**, so the (correct) absence of CORS never gets consulted. It
    could then read the portfolio and the whole chat transcript, trade, and drive
    /api/chat in a loop at real cost. `Host: evil.example.com` returned 200 until
    this middleware existed — measured, not assumed.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health", headers={"Host": "evil.example.com"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_the_hosts_we_are_actually_served_under_are_allowed(app: FastAPI) -> None:
    """The other half: the guard must not break the documented ways in."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for host in ("localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8000"):
            response = await client.get("/api/health", headers={"Host": host})
            assert response.status_code == 200, f"{host} was refused"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", DEFAULT_ALLOWED_HOSTS),
        ("   ", DEFAULT_ALLOWED_HOSTS),
        ("workstation", ("workstation",)),
        ("a, b ,c", ("a", "b", "c")),
        ("a,,b,", ("a", "b")),
    ],
)
def test_allowed_hosts_parsing(monkeypatch: pytest.MonkeyPatch, raw: str, expected: tuple[str, ...]) -> None:
    """The env var's parser, which was proved only by the E2E stack before.

    It **replaces** the defaults rather than extending them, so a wrong value
    fails loudly — every request 400s — instead of silently widening the
    allow-list. That is the behaviour worth pinning: the failure mode of a
    security control should be refusal, not permission.
    """
    monkeypatch.setenv("ALLOWED_HOSTS", raw)

    assert load_settings().allowed_hosts == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
async def test_the_interactive_docs_are_not_served(app: FastAPI, path: str) -> None:
    """`/docs` fetched Swagger UI from a CDN — floating tag, no SRI — into an
    origin that requires no authentication and holds a portfolio.

    All three go together because FastAPI derives both UIs from the schema URL,
    so `openapi_url=None` removes the lot. Parametrized rather than asserted on
    `/docs` alone: dropping only the UI while leaving `/openapi.json` would pass
    a one-path check and still publish the surface.

    What is lost is route discovery, which is why `README.md` now carries an
    endpoint table. Check GD7 holds the two together.
    """
    response = await _get(app, path)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_the_api_still_answers(app: FastAPI) -> None:
    """The half that stops the fix above from being "break the application".

    `openapi_url=None` disables schema *generation*, not routing. If it ever did
    more than that, this is what would say so.
    """
    response = await _get(app, "/api/health")

    assert response.status_code == 200
