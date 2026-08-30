"""Check A14 — the chat rate limit, the only spend limit in the application.

Every `POST /api/chat` is one billed completion. Nothing else here costs money,
which is why this is one bucket on one route rather than general throttling.

The clock is injected throughout. A limiter tested by sleeping can only be
watched *refuse*: proving that it forgives would cost a real minute per
assertion, so in practice nobody writes that half and the refill arithmetic
ships unproven. Both halves are below, and both run instantly.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finally_app.api.ratelimit import CHAT_BURST, CHAT_REFILL_SECONDS, TokenBucket
from finally_app.config import Settings
from finally_app.db.init import ensure_initialized


class FakeClock:
    """A clock that only moves when a test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_the_burst_is_allowed_and_the_next_call_is_not() -> None:
    clock = FakeClock()
    bucket = TokenBucket(3, 6.0, clock)

    assert [bucket.take() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert bucket.take() > 0


def test_the_refusal_names_a_wait_that_is_actually_long_enough() -> None:
    """The returned number becomes a `Retry-After`, so it has to be true.

    A limiter that refuses and then says "1s" when the real wait is six sends
    the client back to be refused again — which is worse than no header, because
    it converts one refusal into a polling loop.
    """
    clock = FakeClock()
    bucket = TokenBucket(1, 6.0, clock)
    bucket.take()

    wait = bucket.take()
    assert wait == pytest.approx(6.0)

    # One tick short of the advertised wait: still refused.
    clock.advance(wait - 0.01)
    assert bucket.take() > 0

    # And at the advertised wait, allowed. Both directions, or the number is
    # decoration.
    clock.advance(0.01)
    assert bucket.take() == 0.0


def test_tokens_come_back_one_at_a_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(5, 6.0, clock)
    for _ in range(5):
        bucket.take()

    clock.advance(12.0)

    assert bucket.take() == 0.0
    assert bucket.take() == 0.0
    assert bucket.take() > 0


def test_the_bucket_never_fills_past_its_capacity() -> None:
    """Otherwise an idle hour banks 600 completions and the limit means nothing."""
    clock = FakeClock()
    bucket = TokenBucket(3, 6.0, clock)

    clock.advance(3600.0)

    assert [bucket.take() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert bucket.take() > 0


def test_a_clock_that_goes_backwards_does_not_mint_tokens() -> None:
    """`monotonic` cannot, but the clock is injected and this class is generic.

    **This test's first version could not fail** — the overseer deleted the
    `max(0.0, ...)` clamp it is named for and got eight passes. Asserting only
    `take() > 0` after a rewind proves nothing: without the clamp the rewind
    drives the balance to *minus six hundred* tokens, which is still refused, so
    the assertion held while the bug it exists to catch was fully present. The
    ninth check in this run that could not fail, and mine.

    What discriminates is the state left **behind** the rewind. An unclamped
    bucket is buried so deep that a full refill interval cannot bring it back;
    a clamped one ignores the rewind entirely and returns exactly one token.
    """
    clock = FakeClock()
    bucket = TokenBucket(1, 6.0, clock)
    bucket.take()

    clock.advance(-3600.0)
    assert bucket.take() > 0

    # One refill interval forward from where the rewind left us. Clamped: the
    # rewind was ignored, so this is simply one interval since the last take,
    # and one token is due. Unclamped: the balance is around -600, and 6 seconds
    # buys back exactly 1.0 of it.
    clock.advance(6.0)
    assert bucket.take() == 0.0, "a rewound clock left the bucket in debt it cannot climb out of"


@pytest.fixture
def ready(app: FastAPI, settings: Settings) -> FastAPI:
    """A seeded database and a priced cache; the mock LLM answers every turn."""
    ensure_initialized(settings.db_path)
    app.state.cache.apply({"AAPL": 190.0})
    return app


async def _post_chat(app: FastAPI, message: str = "hello") -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/chat", json={"message": message})


@pytest.mark.asyncio
async def test_the_endpoint_refuses_the_call_after_the_burst(ready: FastAPI) -> None:
    """End to end: the wiring, not just the bucket."""
    for index in range(CHAT_BURST):
        response = await _post_chat(ready)
        assert response.status_code == 200, f"call {index + 1} of the burst was refused"

    refused = await _post_chat(ready)

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == str(round(CHAT_REFILL_SECONDS))
    assert "wait" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_refused_turn_is_not_persisted(ready: FastAPI, settings: Settings) -> None:
    """The reason the check runs before `handle_message` rather than inside it.

    A 429 raised after the user's message was written would leave the transcript
    holding a turn the assistant was never asked about — the same orphan the 503
    path had, arriving by a different door.
    """
    for _ in range(CHAT_BURST):
        await _post_chat(ready, "counted")
    await _post_chat(ready, "refused-turn")

    transport = httpx.ASGITransport(app=ready)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        stored = (await client.get("/api/chat/messages")).json()

    assert not [row for row in stored if row["content"] == "refused-turn"]


@pytest.mark.asyncio
async def test_every_app_gets_its_own_bucket(settings: Settings, tmp_path: Path) -> None:
    """A module-level bucket would make the first exhausting test fail the rest.

    And it would fail them as a 429 from an endpoint that looks broken, in a file
    that never mentions rate limiting — which is the kind of shared state that
    costs an afternoon.
    """
    from finally_app import main  # pylint: disable=import-outside-toplevel

    first = main.create_app(settings)
    second = main.create_app(settings)

    for _ in range(CHAT_BURST):
        first.state.chat_limiter.take()

    assert first.state.chat_limiter.take() > 0
    assert second.state.chat_limiter.take() == 0.0
