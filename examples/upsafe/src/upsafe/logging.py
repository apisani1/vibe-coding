"""Redacting request logging — owner of acceptance criterion 10 (no secret leakage).

``log_request`` accepts *only* an explicit allow-list of fields (method, route template,
status, size, duration). It is redacting **by construction**: there is no parameter
through which the API key, download token, original filename, or file bytes could be
logged.

Crucially the caller passes the *route template* (``/downloads/{token}``), never the
concrete path — so the capability token never reaches the log even though it lives in the
download URL.
"""

from __future__ import annotations

import logging  # stdlib (absolute import; not this module)

LOGGER_NAME = "upsafe"


_HANDLER_NAME = "upsafe-request-handler"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Return the upsafe logger, attaching a single stream handler once (idempotent)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if not any(h.get_name() == _HANDLER_NAME for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


def log_request(  # pylint: disable=too-many-arguments
    logger: logging.Logger,
    *,
    method: str,
    route: str,
    status: int,
    size_bytes: int,
    duration_ms: float,
) -> None:
    """Emit one structured request line from the field allow-list only.

    ``route`` must be a static template (e.g. ``/downloads/{token}``), never the concrete
    path, so the token is never logged.
    """
    logger.info(
        "method=%s route=%s status=%d size=%d duration_ms=%.1f",
        method,
        route,
        status,
        size_bytes,
        duration_ms,
    )
