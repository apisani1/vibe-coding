"""ASGI middleware that caps the total request body size.

Starlette's multipart parser does **not** bound file parts — ``max_part_size`` guards only
in-memory (non-file) fields, so a file part streams into a ``SpooledTemporaryFile`` with no
size check (memory up to the ~1 MiB spool threshold, then disk). Without this middleware a
large upload is therefore written in full before ``store_stream`` can reject it, letting an
authenticated client exhaust the temp filesystem.

This middleware counts body bytes off the ASGI ``receive`` channel (with a ``Content-Length``
fast path) and returns 413 *before* the body is buffered, bounding both memory and disk
regardless of how the downstream app parses the body.
"""

from __future__ import annotations

import logging

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from .logging import (
    LOGGER_NAME,
    log_request,
)

_logger = logging.getLogger(LOGGER_NAME)

# Headroom above ``max_upload_bytes`` for multipart framing (boundary lines, part headers,
# CRLFs) of a single file part, so a legitimately max-sized file is not rejected here before
# ``store_stream`` applies the exact limit.
MULTIPART_OVERHEAD_ALLOWANCE = 8192

_TOO_LARGE_BODY = b'{"detail":"upload too large"}'


class _BodyTooLarge(Exception):
    """Raised from the wrapped receive once the cumulative body exceeds the limit."""


def _log_rejection(scope: Scope) -> None:
    # Fixed label, never the request path — the body-limit reject fires before routing and
    # the path could contain a download token.
    log_request(
        _logger,
        method=scope.get("method", "?"),
        route="<body-too-large>",
        status=413,
        size_bytes=0,
        duration_ms=0.0,
    )


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})


class BodySizeLimitMiddleware:  # pylint: disable=too-few-public-methods
    """Reject requests whose body exceeds ``max_body_bytes`` before it is buffered."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: reject on a declared Content-Length over the limit without reading a byte.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    break
                if declared > self.max_body_bytes:
                    _log_rejection(scope)
                    await _send_413(send)
                    return
                break

        total = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if response_started:
                raise  # response already in flight — cannot cleanly replace it
            _log_rejection(scope)
            await _send_413(send)
