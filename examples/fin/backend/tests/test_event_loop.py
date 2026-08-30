"""The chat turn must not stop the event loop (D21, check GD6).

The only kind of check that can catch this. Every other test in this suite
asserts an **outcome**, and the outcome was always right: the trade filled, the
transcript persisted, the status code was 200. What was wrong was that the whole
process stopped while it happened.

Measured at review time, before the fix: a chat turn with a one-second stall
fired **0** event-loop beats where ~208 were due, while the same work through
the ``def`` trade handler fired 162 of ~203. Every SSE stream, the price
producer and the snapshot task were frozen for the duration, and
``BEGIN IMMEDIATE``'s five-second busy timeout meant contention with a manual
trade could freeze the process for five seconds.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI

from finally_app.config import Settings
from finally_app.db.init import ensure_initialized
from finally_app.services import portfolio

BEAT_INTERVAL = 0.005
STALL_SECONDS = 0.4
# A loop that never yields fires zero. A loop that yields normally fires roughly
# STALL_SECONDS / BEAT_INTERVAL (80 here). Half of that is a wide margin against
# a slow machine while still being unreachable if the loop is blocked.
MINIMUM_BEATS = int((STALL_SECONDS / BEAT_INTERVAL) * 0.5)


async def _beats_during(app: FastAPI, request: object) -> tuple[int, int]:
    """Run one request while counting event-loop wakeups."""
    beats = 0

    async def heartbeat() -> None:
        nonlocal beats
        while True:
            await asyncio.sleep(BEAT_INTERVAL)
            beats += 1

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ticker = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.05)
        beats = 0
        method, path, payload = request  # type: ignore[misc]
        response = await client.request(method, path, json=payload)
        ticker.cancel()
    return beats, response.status_code


@pytest.fixture
def ready(app: FastAPI, settings: Settings) -> FastAPI:
    """A seeded database and a priced cache, without running the lifespan.

    The lifespan would start the producer and the snapshotter, and both of those
    are exactly the tasks this file is measuring the starvation of — they would
    fire beats of their own and flatter the result.
    """
    ensure_initialized(settings.db_path)
    app.state.cache.apply({"AAPL": 190.0})
    return app


@pytest.fixture
def stalled_trade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make one trade take `STALL_SECONDS`, standing in for lock contention.

    Not artificial: `execute_trade` takes `BEGIN IMMEDIATE` behind a five-second
    `busy_timeout`, so a real second writer produces exactly this shape of
    blocking wait — check B2 demonstrates that contention is reachable.
    """
    real = portfolio.execute_trade

    def slow(*args: object, **kwargs: object) -> object:
        time.sleep(STALL_SECONDS)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(portfolio, "execute_trade", slow)


@pytest.mark.asyncio
async def test_a_chat_turn_does_not_stop_the_event_loop(ready: FastAPI, stalled_trade: None) -> None:
    """The regression. `async def` + blocking sqlite = a frozen process."""
    beats, status = await _beats_during(ready, ("POST", "/api/chat", {"message": "buy 1 AAPL"}))

    assert status == 200
    assert beats >= MINIMUM_BEATS, f"the loop fired {beats} times during a chat turn — it was blocked"


@pytest.mark.asyncio
async def test_a_manual_trade_does_not_stop_the_event_loop(ready: FastAPI, stalled_trade: None) -> None:
    """The control.

    This path was always fine — Starlette runs `def` handlers on its threadpool —
    and it is here so the chat assertion above is a comparison rather than a
    guess about what "enough beats" means.
    """
    beats, status = await _beats_during(
        ready, ("POST", "/api/portfolio/trade", {"ticker": "AAPL", "side": "buy", "quantity": 1})
    )

    assert status == 200
    assert beats >= MINIMUM_BEATS


@pytest.mark.asyncio
async def test_reading_the_transcript_does_not_stop_the_event_loop(ready: FastAPI) -> None:
    """`GET /api/chat/messages` is a `def` handler; this pins that it stays one."""
    beats, status = await _beats_during(ready, ("GET", "/api/chat/messages", None))

    assert status == 200
    assert beats >= 1
