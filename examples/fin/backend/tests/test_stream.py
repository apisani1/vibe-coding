"""Check A13 — the SSE contract.

Every assertion here is paired with a mutation that breaks it, listed in the
docstring, because five checks across CP4 and CP4b passed against broken code
before anyone tried to falsify them.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI

from finally_app.api.stream import format_event, price_events
from finally_app.market.cache import PriceCache

QUOTE_KEYS = {"ticker", "price", "previous_price", "session_open", "timestamp", "direction"}


async def _collect(generator: Any, count: int, timeout: float = 2.0) -> list[str]:
    """Pull up to `count` frames, giving up rather than hanging."""
    frames: list[str] = []

    async def pump() -> None:
        async for frame in generator:
            frames.append(frame)
            if len(frames) >= count:
                return

    try:
        await asyncio.wait_for(pump(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return frames


def _payloads(frames: list[str]) -> list[dict[str, Any]]:
    return [json.loads(f[len("data: ") :]) for f in frames if f.startswith("data: ")]


@pytest.mark.asyncio
async def test_first_frame_is_a_full_snapshot() -> None:
    """Breaks if the generator starts in change-only mode.

    A client joining a quiet market would render blank prices until something
    moved — which, with a 15s Massive poll, is up to fifteen seconds of an empty
    watchlist on a working system.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0, "MSFT": 415.0, "JPM": 200.0})

    frames = await _collect(price_events(cache, emit_interval=0.01), count=3)
    payloads = _payloads(frames)

    assert {p["ticker"] for p in payloads} == {"AAPL", "MSFT", "JPM"}


@pytest.mark.asyncio
async def test_every_frame_carries_all_six_quote_keys() -> None:
    """The frontend needs session_open for change % and previous_price for the flash."""
    cache = PriceCache()
    cache.apply({"AAPL": 190.0})

    payloads = _payloads(await _collect(price_events(cache, emit_interval=0.01), count=1))

    assert payloads
    assert set(payloads[0]) == QUOTE_KEYS


@pytest.mark.asyncio
async def test_a_frozen_cache_yields_nothing_but_heartbeats() -> None:
    """The load-bearing D4 assertion. Breaks if the generator emits every tick.

    Under the Massive source (15s poll, 500ms emit) an emit-everything loop
    pushes ~30 identical frames per real quote, each firing a price-flash
    animation on a price that did not move.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0, "MSFT": 415.0})

    generator = price_events(cache, emit_interval=0.01, heartbeat_interval=0.05)
    frames = await _collect(generator, count=12, timeout=1.0)

    after_snapshot = frames[2:]
    assert after_snapshot, "the generator stopped producing anything at all"
    assert all(
        f == ": keepalive\n\n" for f in after_snapshot
    ), f"a frozen cache emitted data frames: {[f for f in after_snapshot if f.startswith('data')][:3]}"


@pytest.mark.asyncio
async def test_only_the_changed_ticker_is_resent() -> None:
    """Breaks if change detection compares nothing, or compares the wrong field."""
    cache = PriceCache()
    cache.apply({"AAPL": 190.0, "MSFT": 415.0})

    generator = price_events(cache, emit_interval=0.01, heartbeat_interval=99.0)
    await _collect(generator, count=2)  # drain the snapshot

    cache.apply({"AAPL": 191.0})  # MSFT unchanged
    later = _payloads(await _collect(generator, count=1, timeout=1.0))

    assert [p["ticker"] for p in later] == ["AAPL"]


@pytest.mark.asyncio
async def test_an_unchanged_price_does_not_produce_a_frame() -> None:
    """The CP4b condition: cache.apply must not restamp an unchanged price.

    If it restamps, the timestamp advances, change detection sees a change, and
    a frame goes out for a price that did not move — the exact noise D4 exists
    to prevent, arriving through the cache rather than the generator.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0})

    generator = price_events(cache, emit_interval=0.01, heartbeat_interval=99.0)
    await _collect(generator, count=1)

    for _ in range(5):
        cache.apply({"AAPL": 190.0})  # same price, five times

    later = await _collect(generator, count=1, timeout=0.3)
    assert not _payloads(later), "an unchanged price produced an SSE frame"


@pytest.mark.asyncio
async def test_a_new_ticker_appears_without_a_reconnect() -> None:
    """Adding to the watchlist must show up on the existing stream."""
    cache = PriceCache()
    cache.apply({"AAPL": 190.0})

    generator = price_events(cache, emit_interval=0.01, heartbeat_interval=99.0)
    await _collect(generator, count=1)

    cache.apply({"PYPL": 60.0})
    later = _payloads(await _collect(generator, count=1, timeout=1.0))

    assert [p["ticker"] for p in later] == ["PYPL"]


@pytest.mark.asyncio
async def test_cancelling_the_generator_unwinds_it() -> None:
    """Breaks if the generator swallows CancelledError.

    FastAPI cancels it when the client disconnects; a swallowed cancellation is
    a task leaked per closed tab.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0})
    generator = price_events(cache, emit_interval=0.01)

    task = asyncio.create_task(_collect(generator, count=1000, timeout=30))
    await asyncio.sleep(0.05)
    before = len(asyncio.all_tasks())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)

    assert len(asyncio.all_tasks()) < before


@pytest.mark.asyncio
async def test_the_stream_route_is_registered_and_reads_the_app_cache(app: FastAPI) -> None:
    """The route exists and is wired to `app.state.cache`.

    The endpoint's *wire* behaviour is verified by A13's raw `curl -N` smoke
    against a real uvicorn server, not here: `httpx.ASGITransport` does not
    return response headers until the response completes, so it cannot test a
    stream that never ends by design. An earlier version of this test hung the
    whole suite for exactly that reason.
    """
    from finally_app.api.stream import router, stream_prices

    assert any(getattr(r, "path", "") == "/api/stream/prices" for r in router.routes)

    app.state.cache.apply({"AAPL": 190.0})

    class _Req:
        pass

    request = _Req()
    request.app = app  # type: ignore[attr-defined]
    response = await stream_prices(request)  # type: ignore[arg-type]

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    first = await response.body_iterator.__anext__()  # type: ignore[attr-defined]
    assert "AAPL" in (first if isinstance(first, str) else first.decode())
    await response.body_iterator.aclose()  # type: ignore[attr-defined]


def test_frames_are_shaped_as_server_sent_events() -> None:
    """`data: ` prefix and a blank-line terminator, or EventSource ignores it."""
    frame = format_event(
        {
            "ticker": "AAPL",
            "price": 1.0,
            "previous_price": 1.0,
            "session_open": 1.0,
            "timestamp": "t",
            "direction": "flat",
        }
    )

    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame[len("data: ") :])["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_the_stream_never_writes_to_the_cache() -> None:
    """D2: the SSE endpoint is a pure reader.

    Structural intent, asserted behaviourally: running the generator must leave
    the cache identical.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0, "MSFT": 415.0})
    before = dict(cache.snapshot())

    await _collect(price_events(cache, emit_interval=0.01, heartbeat_interval=0.02), count=8, timeout=0.5)

    assert cache.snapshot() == before


def test_no_router_reassigns_the_shared_source_or_cache() -> None:
    """The second CP5 condition from the CP4b review.

    `app.state.source` and `app.state.cache` are writable by any router, and a
    router that swapped either would defeat every provenance guard at once —
    the write guard, the fetch-return guard and the import ban all constrain
    `market/`, not `api/`. Lifespan owns those two attributes; the HTTP layer
    reads them.
    """
    import ast
    import importlib
    import inspect
    import pkgutil

    import finally_app.api as api_package

    offending: list[str] = []
    for module_info in pkgutil.iter_modules(api_package.__path__):
        module = importlib.import_module(f"finally_app.api.{module_info.name}")
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AugAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in ("source", "cache"):
                    offending.append(f"{module_info.name}: {ast.unparse(target)}")

    assert not offending, f"a router reassigns shared state {offending} — lifespan owns it, api/ reads it"


@pytest.mark.asyncio
async def test_the_heartbeat_fires_at_its_configured_cadence() -> None:
    """Closes the one real hole the overseer found in A13.

    Two mutants survived the original battery: `since_heartbeat += emit_interval
    * 10` and replacing the interval comparison with `if True`. Either would ship
    a keepalive every tick -- two per second per client -- undetected. The
    shipped cadence is right; nothing proved it.

    Counts keepalives against elapsed emits rather than wall clock, so it stays
    fast and does not depend on real time.
    """
    cache = PriceCache()
    cache.apply({"AAPL": 190.0})

    emit, heartbeat = 0.01, 0.1  # one keepalive per 10 emits
    generator = price_events(cache, emit_interval=emit, heartbeat_interval=heartbeat)
    await _collect(generator, count=1)  # drain the snapshot

    # Collect for a fixed DURATION, not a fixed frame count: capping the count
    # makes the assertion circular -- ask for 4 frames and you can never see
    # more than 4, whatever the cadence.
    window = 0.3  # ~30 emits at 0.01s
    frames = await _collect(generator, count=10_000, timeout=window)
    keepalives = [f for f in frames if f == ": keepalive\n\n"]

    assert keepalives, "no heartbeat at all on a frozen cache"
    # ~30 emits at one keepalive per 10 emits is ~3. A per-tick heartbeat would
    # deliver ~30. The bound excludes that by an order of magnitude while
    # leaving generous slack for scheduling jitter.
    assert len(keepalives) <= 8, f"{len(keepalives)} keepalives in ~30 emits; the configured cadence is one per 10"
