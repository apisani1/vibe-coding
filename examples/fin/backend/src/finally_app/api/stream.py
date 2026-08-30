"""Server-Sent Events: the live price stream.

Reads the cache on a timer and pushes to every connected client. It is a pure
reader — it never writes anything, and it holds no lock, because the producer
rebinds the cache dict rather than mutating it (D2).

Three details here are the ones this kind of endpoint usually gets wrong, and
each is asserted by check A13:

* **The first frame is a full snapshot.** A client connecting to a quiet market
  would otherwise render blank prices until something moved.
* **Later frames carry only changed tickers.** Under the Massive source (15 s
  poll, 500 ms emit) an emit-everything loop pushes ~30 identical frames per
  real quote, each firing a price-flash animation on a price that did not move.
* **A heartbeat comment keeps the connection alive.** Without it, an idle
  market is indistinguishable from a dead backend to a proxy or a browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..market.cache import PriceCache
from ..market.source import Quote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])

EMIT_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 15.0


def format_event(quote: Quote) -> str:
    """One SSE frame. All six Quote keys travel — the frontend needs every one."""
    return f"data: {json.dumps(quote)}\n\n"


async def price_events(
    cache: PriceCache,
    emit_interval: float = EMIT_INTERVAL_SECONDS,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE frames until the client goes away.

    Change detection is by producer timestamp, not by price comparison: the
    producer already decided what changed, and re-deriving it here would let the
    two disagree.
    """
    last_sent: dict[str, str] = {}
    since_heartbeat = 0.0
    first = True

    try:
        while True:
            snapshot = cache.snapshot()

            if first:
                # Full snapshot, so a client joining a quiet market renders
                # immediately rather than waiting for the next tick.
                to_send = list(snapshot.values())
                first = False
            else:
                to_send = [q for t, q in snapshot.items() if last_sent.get(t) != q["timestamp"]]

            for quote in to_send:
                last_sent[quote["ticker"]] = quote["timestamp"]
                yield format_event(quote)

            if to_send:
                since_heartbeat = 0.0
            else:
                since_heartbeat += emit_interval
                if since_heartbeat >= heartbeat_interval:
                    since_heartbeat = 0.0
                    yield ": keepalive\n\n"

            await asyncio.sleep(emit_interval)
    except asyncio.CancelledError:
        # FastAPI cancels the generator when the client disconnects. Unwinding
        # here is what keeps a closed tab from leaking a task; there is no
        # client registry to clean up because there is no client registry.
        logger.debug("SSE client disconnected")
        raise


@router.get("/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    """Long-lived SSE connection. The client uses the native EventSource API."""
    cache: PriceCache = request.app.state.cache
    return StreamingResponse(
        price_events(cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Proxies that buffer will hold frames until the buffer fills, which
            # presents as a stream that works locally and stalls in deployment.
            "X-Accel-Buffering": "no",
        },
    )
