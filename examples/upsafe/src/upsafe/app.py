"""Application factory.

``create_app`` builds a fully-wired FastAPI app from a ``Settings`` (loaded from the
environment when not supplied). It creates the data root, initializes the SQLite schema
once, configures the redacting logger, and mounts the router. Taking ``settings`` as an
argument keeps construction separate from use — tests build an app against a ``tmp_path``
data root and a known API key.
"""

from __future__ import annotations

from typing import Optional

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from .config import (
    Settings,
    load_settings,
)
from .logging import (
    configure_logging,
    log_request,
)
from .metadata import (
    connect,
    init_db,
)
from .middleware import (
    MULTIPART_OVERHEAD_ALLOWANCE,
    BodySizeLimitMiddleware,
)
from .routes import create_router


def _route_label(request: Request) -> str:
    """The matched route TEMPLATE (e.g. /downloads/{token}), never the concrete path,
    so a logged rejection can never carry the download token."""
    route = request.scope.get("route")
    return getattr(route, "path_format", None) or "<unmatched>"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = load_settings() if settings is None else settings
    settings.quarantine_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(settings.db_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    logger = configure_logging()
    # Docs/OpenAPI are disabled unless explicitly enabled (UPSAFE_ENABLE_DOCS) so a
    # production deployment exposes no unauthenticated schema/UI surface.
    enabled = settings.enable_docs
    app = FastAPI(
        title="upsafe",
        version="0.1.0",
        docs_url="/docs" if enabled else None,
        redoc_url="/redoc" if enabled else None,
        openapi_url="/openapi.json" if enabled else None,
    )
    app.state.settings = settings

    # Log every rejected request through the redacting logger (route template only) so
    # abuse — API-key brute-force, oversize/disallowed uploads — stays observable even
    # with uvicorn access logging disabled. Success paths log themselves in routes.py.
    async def _log_and_handle_http_exception(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, StarletteHTTPException)
        log_request(
            logger,
            method=request.method,
            route=_route_label(request),
            status=exc.status_code,
            size_bytes=0,
            duration_ms=0.0,
        )
        return await http_exception_handler(request, exc)

    app.add_exception_handler(StarletteHTTPException, _log_and_handle_http_exception)

    # Cap the request body at the transport layer: Starlette's multipart parser does not
    # bound file parts, so without this a large upload is spooled in full before the route
    # can reject it (temp-disk exhaustion). The allowance covers single-part framing.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_ALLOWANCE,
    )
    app.include_router(create_router(settings, logger))
    return app
