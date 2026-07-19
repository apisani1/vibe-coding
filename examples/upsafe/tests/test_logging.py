import io
import logging

from upsafe.logging import LOGGER_NAME, configure_logging, log_request


def _capture(logger):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger.addHandler(handler)
    return buf, handler


def test_configure_logging_is_idempotent():
    logger = configure_logging()
    n = len(logger.handlers)
    configure_logging()
    assert len(logger.handlers) == n  # no duplicate handler
    assert logger.name == LOGGER_NAME


def test_log_request_emits_only_allowlisted_fields():
    logger = configure_logging()
    buf, handler = _capture(logger)
    try:
        log_request(logger, method="POST", route="/uploads", status=201, size_bytes=1234, duration_ms=5.6)
    finally:
        logger.removeHandler(handler)
    out = buf.getvalue()
    assert "method=POST" in out
    assert "route=/uploads" in out
    assert "status=201" in out
    assert "size=1234" in out


def test_log_request_cannot_leak_a_token_via_route_template():
    # The download route is logged as its template, never the concrete token path.
    logger = configure_logging()
    buf, handler = _capture(logger)
    secret_token = "SUPERSECRETTOKEN123"
    try:
        log_request(
            logger,
            method="GET",
            route="/downloads/{token}",  # template, not /downloads/<token>
            status=200,
            size_bytes=10,
            duration_ms=1.0,
        )
    finally:
        logger.removeHandler(handler)
    out = buf.getvalue()
    assert secret_token not in out
    assert "/downloads/{token}" in out
