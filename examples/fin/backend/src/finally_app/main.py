"""Application factory and process lifespan.

Route registration order is load-bearing and asserted by a test
(``tests/test_static_mount.py``). Three groups, in this order: the API routers,
a JSON 404 for anything else under ``/api``, then the exported frontend as a
catch-all. Registering the export first makes it absorb ``/api/health`` itself;
omitting the middle one leaves unknown API paths answering with the export's
``404.html``, i.e. HTML where the frontend expects JSON.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import chat, portfolio, stream, system, watchlist
from .api.ratelimit import CHAT_BURST, CHAT_REFILL_SECONDS, TokenBucket
from .config import Settings, load_settings
from .db.init import ensure_initialized
from .market.cache import PriceCache
from .market.factory import create_source
from .market.producer import run_producer
from .services.snapshots import SNAPSHOT_INTERVAL_SECONDS, run_snapshotter

logger = logging.getLogger(__name__)

# Where the built frontend lands. `frontend/npm run build` writes `frontend/out/`;
# the Dockerfile's second stage and check C1 both copy that directory's contents
# here. It is a build artifact and is gitignored — an API-only checkout simply
# has no such directory, which is why the mount is conditional rather than
# assumed.
STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging() -> None:
    """Give this package's loggers a handler of their own.

    uvicorn's dictConfig configures only the ``uvicorn.*`` loggers and leaves
    the root logger at WARNING, so anything this package logs at INFO is
    silently discarded under the documented run command. Without this, the
    startup lines below never appear — and they are the observable half of the
    "am I about to spend money on LLM calls?" guard.
    """
    package_logger = logging.getLogger("finally_app")
    if package_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO)
    package_logger.propagate = False


def _log_startup_configuration(settings: Settings) -> None:
    """State which external paths are live, once, at startup.

    This is the fastest way to answer "was it using the simulator or real data?"
    and "did that chat turn cost money?" after the fact.
    """
    source = "massive (real market data)" if settings.use_massive else "simulator (GBM)"
    if settings.llm_mock:
        llm = "mock (no network calls, no cost)"
    elif settings.llm_configured:
        llm = f"live via OpenRouter, model={settings.openrouter_model}"
    else:
        llm = "unconfigured (chat will return 503)"
    logger.info("market source: %s", source)
    logger.info("llm: %s", llm)
    # The third startup disclosure, beside the other two the README tells people
    # to read. `*` disables the check entirely, which should never be quiet.
    if "*" in settings.allowed_hosts:
        logger.warning("allowed hosts: ANY — the DNS-rebinding guard is disabled")
    else:
        logger.info("allowed hosts: %s", ", ".join(settings.allowed_hosts))


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the background work that outlives a single request."""
    settings: Settings = fastapi_app.state.settings
    _log_startup_configuration(settings)

    # Order is load-bearing: the schema and seed must exist before the price
    # producer starts, because the producer reads the watchlist to learn which
    # tickers to price. `to_thread` because sqlite3 is blocking and this is the
    # event loop (D21).
    await asyncio.to_thread(ensure_initialized, settings.db_path)

    cache = getattr(fastapi_app.state, "cache", None) or PriceCache()
    fastapi_app.state.cache = cache
    source = create_source(settings)
    fastapi_app.state.source = source

    producer = asyncio.create_task(run_producer(settings.db_path, source, cache))
    logger.info("price producer started (interval %.2fs)", source.interval_seconds)

    # After the producer, per the design's startup order: the first snapshot
    # values whatever the cache holds, and starting it second gives the producer
    # a chance to have filled it.
    # Interval passed explicitly, read from this module's namespace at call
    # time, so the wiring test can shorten it without patching the task —
    # patching the task is the thing that test exists to catch.
    snapshotter = asyncio.create_task(run_snapshotter(settings.db_path, cache, SNAPSHOT_INTERVAL_SECONDS))
    logger.info("snapshot task started (interval %.0fs)", SNAPSHOT_INTERVAL_SECONDS)

    try:
        yield
    finally:
        # Cancel *and await*: without the await, uvicorn exits before the tasks
        # unwind and the shutdown looks like a hang followed by a timeout.
        for task in (producer, snapshotter):
            task.cancel()
        for task in (producer, snapshotter):
            try:
                await task
            except asyncio.CancelledError:
                pass
        # After the tasks, never before: the producer holds the only reference
        # to the source that is actively polling, and closing a connection pool
        # out from under an in-flight request turns an orderly shutdown into a
        # traceback. The simulator's implementation is a no-op.
        await source.aclose()


def _add_api_not_found(application: FastAPI) -> None:
    """Answer every unmatched ``/api/*`` path with JSON, ahead of the static mount.

    Ordering alone is **not** enough, which is the correction this checkpoint
    had to make to its own plan. The reasoning in the plan was that a mount
    registered after the routers can no longer shadow them — true, but
    incomplete: an unknown ``/api`` path matches no router either, so it falls
    through to the mount anyway. ``next build --output export`` emits a
    ``404.html``, Starlette's ``StaticFiles(html=True)`` serves that file for
    anything it cannot resolve, and the client receives **HTML with a 404**.
    Measured, not reasoned: with the routers first and this route absent, an
    unknown ``/api`` path returned ``text/html; charset=utf-8``.

    HTML with a 404 is much better than the HTML-with-a-200 the plan predicted —
    a 404 at least fails — but it still breaks the contract the frontend is
    written against, that everything under ``/api`` is JSON. This route makes
    that contract true instead of nearly true.

    **Two routes, not one.** ``/api/{path:path}`` requires the separator, so the
    bare ``/api`` matches neither it nor any router and reached the mount — the
    overseer measured ``text/html`` there while all three docstrings claimed the
    opposite, and worse, that path answered JSON *before* this checkpoint. The
    pattern is not widened to ``/api{path:path}`` instead: that would also
    swallow a future page route such as ``/apidocs``.

    Registered after every real router, so these can only receive what the
    routers declined. Two consequences, both accepted deliberately and both
    measured rather than predicted:

    * a known path with the **wrong method** now answers 404 rather than 405,
      because a full match beats the router's partial match;
    * a **trailing slash** on a real route (``/api/portfolio/``) now answers 404
      rather than redirecting 307 to the canonical path, because the redirect is
      Starlette's fallback for *no* match and there is now a match.

    Under a mounted export both requests returned the export's ``404.html``
    anyway, so neither loses anything a deployed build had; what changes is that
    the reply is JSON and says which path failed. No caller in this repo uses
    either form, and ``tests/test_static_mount.py`` pins both.

    One consequence reaches forward to the container: ``HEAD`` on a real route
    is a JSON 404 here (FastAPI does not auto-add ``HEAD``, so it was a 405
    before — nothing that worked stopped working), which means **CP15's
    ``HEALTHCHECK`` must use ``GET /api/health``**.

    Finally, "everything under ``/api`` is JSON" means exactly what it says:
    paths that *are* ``/api`` or *begin with* ``/api/``. Sibling paths that
    merely start with those letters — ``/API``, ``/apidocs``, ``/api.``,
    ``//api/health`` — reach the export and get its 404 page, deliberately: not
    swallowing ``/apidocs`` is why the pattern was not widened to
    ``/api{path:path}``. Nothing constructs those forms; ``lib/api.ts`` builds
    every URL from the constant ``/api`` plus a path that starts with ``/``.
    """

    async def api_not_found(path: str) -> NoReturn:
        raise HTTPException(status_code=404, detail=f"No API route matches /api/{path}")

    async def api_root_not_found() -> NoReturn:
        raise HTTPException(status_code=404, detail="No API route matches /api")

    for route, endpoint in (("/api", api_root_not_found), ("/api/{path:path}", api_not_found)):
        application.add_api_route(
            route,
            endpoint,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
            include_in_schema=False,
            # These handlers only raise, and FastAPI cannot build a response
            # model from `NoReturn`. Saying so is more honest than annotating a
            # return type the function never produces.
            response_model=None,
        )


def _mount_static(application: FastAPI, static_dir: Path) -> None:
    """Serve the exported frontend under everything else, if it has been built.

    ``html=True`` makes the mount a catch-all: any path it cannot resolve to a
    file gets ``index.html`` for a directory and ``404.html`` for anything else.
    That is what a single-page app needs, and it is precisely why the call site
    is the **last** line of ``create_app`` — Starlette matches routes in
    registration order, so a mount registered first would absorb ``/api/health``
    itself and hand back the export's 404 page. What it cannot fix is an
    *unknown* API path; ``_add_api_not_found`` covers that.

    Missing directory is a normal state, not an error: the backend is developed
    and tested without ever running ``npm``, and raising here would make every
    test import fail on a machine with no Node.
    """
    if not static_dir.is_dir():
        logger.info("no frontend export at %s — serving the API only", static_dir)
        return
    application.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    logger.info("serving frontend export from %s", static_dir)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Settings are injected rather than read here so tests can construct an app
    against a temporary database without touching the process environment.
    """
    _configure_logging()
    application = FastAPI(
        title="FinAlly",
        description="AI trading workstation",
        version="0.1.0",
        lifespan=lifespan,
        # No `/openapi.json`, and therefore no `/docs` and no `/redoc`: FastAPI
        # derives both UIs from the schema URL, so this one argument removes all
        # three. `/docs` fetched Swagger UI from a CDN, on a floating tag, with
        # no subresource integrity, into an origin that requires no
        # authentication — a third party able to change what that tag resolves
        # to could run script against the portfolio.
        #
        # What is lost is route discovery, and that is why README.md now carries
        # an endpoint table. Deleting the interactive docs without replacing
        # what they were used for would just move the problem.
        openapi_url=None,
    )
    application.state.settings = settings if settings is not None else load_settings()
    # A cache exists from construction, not only from lifespan: a request can
    # reach /api/stream/prices before startup completes, and an AttributeError
    # there would surface as a 500 on a route that should simply have no data
    # yet.
    application.state.cache = PriceCache()
    # Per app, not per module: a module-level bucket is shared by every test in
    # the process, so the first file to exhaust it fails the rest — and the
    # failure looks like the endpoint being broken rather than the fixture
    # leaking.
    application.state.chat_limiter = TokenBucket(CHAT_BURST, CHAT_REFILL_SECONDS)

    # Answer only for the hosts we are actually served under. This is the one
    # protection against DNS rebinding, which is the attack that survives "it is
    # localhost and there is no login": rebinding makes the attacker's page
    # same-origin, so CORS never gets a say. Configurable because the E2E stack
    # reaches the app as `workstation`.
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(application.state.settings.allowed_hosts))

    application.include_router(system.router)
    application.include_router(stream.router)
    application.include_router(portfolio.router)
    application.include_router(watchlist.router)
    application.include_router(chat.router)

    # After every real router and before the export: what the routers declined
    # is a missing API route, not a page. Anything registered *after* this line
    # — including a later checkpoint reaching for `app.add_api_route` at module
    # scope — is unreachable under `/api`. Add routes to a router above instead.
    _add_api_not_found(application)

    # Last, and read from this module's namespace at call time so a test can
    # point it at a fixture export without patching the mount itself — patching
    # the mount is what would make the shadowing test vacuous.
    _mount_static(application, STATIC_DIR)

    return application


app = create_app()
