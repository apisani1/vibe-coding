"""Check A12, client half — Massive response parsing and failure handling.

The live path cannot be verified here: MASSIVE_API_KEY is empty and the account
used previously returned 403 on /v2/snapshot. What follows is everything that
IS checkable without a working key — parsing against recorded fixtures, and the
failure behaviour D13 depends on.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from finally_app.config import DEFAULT_MASSIVE_POLL_SECONDS
from finally_app.market import massive
from finally_app.market.massive import (
    BACKOFF_CEILING_SECONDS,
    MINIMUM_POLL_SECONDS,
    MassiveClient,
    parse_snapshot,
    valid_poll_seconds,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


def _client_returning(status: int, body: object = None) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_parses_a_well_formed_snapshot() -> None:
    prices = parse_snapshot(_fixture("massive_snapshot_ok.json"))

    assert prices == {"AAPL": 190.25, "MSFT": 415.60, "JPM": 200.40}


def test_last_trade_wins_over_day_close() -> None:
    """Outside market hours there is no last trade, so the fallbacks matter."""
    prices = parse_snapshot(_fixture("massive_snapshot_ok.json"))

    assert prices["AAPL"] == 190.25  # lastTrade.p, not day.c 189.90
    assert prices["JPM"] == 200.40  # no lastTrade -> day.c


def test_one_malformed_entry_does_not_discard_the_whole_poll() -> None:
    """Nine good tickers and one broken one must price nine, not zero."""
    prices = parse_snapshot(_fixture("massive_snapshot_partial.json"))

    assert prices == {"AAPL": 190.25, "NVDA": 880.10}


@pytest.mark.parametrize(
    "payload",
    [{}, {"tickers": None}, {"tickers": []}, {"tickers": "nope"}, {"status": "ERROR"}],
)
def test_degenerate_payloads_yield_no_prices_rather_than_raising(payload: dict[str, object]) -> None:
    assert parse_snapshot(payload) == {}


def test_a_zero_or_negative_price_is_rejected() -> None:
    """A price of 0 would be folded into the cache and shown as a real quote."""
    assert parse_snapshot({"tickers": [{"ticker": "X", "lastTrade": {"p": 0}}]}) == {}
    assert parse_snapshot({"tickers": [{"ticker": "X", "lastTrade": {"p": -5}}]}) == {}


def test_tickers_are_normalised_to_uppercase() -> None:
    assert parse_snapshot({"tickers": [{"ticker": "aapl", "lastTrade": {"p": 1.0}}]}) == {"AAPL": 1.0}


# --- failure handling -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_poll_returns_prices() -> None:
    client = _client_returning(200, _fixture("massive_snapshot_ok.json"))
    source = MassiveClient("k", 15.0, client=client)

    assert await source.fetch(["AAPL"]) == {"AAPL": 190.25, "MSFT": 415.60, "JPM": 200.40}
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
async def test_failures_return_empty_rather_than_raising(status: int) -> None:
    """The producer folds an empty result in as 'nothing changed'.

    Raising would restart the producer loop and log a traceback for an ordinary
    rate limit, and clearing the cache would blank every price on one bad HTTP
    response.
    """
    client = _client_returning(status)
    source = MassiveClient("k", 15.0, client=client)

    assert await source.fetch(["AAPL"]) == {}
    await client.aclose()


@pytest.mark.asyncio
async def test_backoff_grows_then_resets_on_success() -> None:
    fail = _client_returning(429)
    source = MassiveClient("k", 15.0, client=fail)

    assert source.interval_seconds == 15.0
    for _ in range(8):
        await source.fetch(["AAPL"])
    assert source.interval_seconds > 15.0, "repeated 429s must extend the poll interval"
    # Pin the ceiling's VALUE, not just that one exists: eight failures saturate
    # whatever the ceiling happens to be, so `<= 60.0` alone stays green if the
    # constant is lowered to 16.
    assert source.interval_seconds == BACKOFF_CEILING_SECONDS == 60.0
    await fail.aclose()

    ok = _client_returning(200, _fixture("massive_snapshot_ok.json"))
    source._client = ok  # pylint: disable=protected-access
    await source.fetch(["AAPL"])
    assert source.interval_seconds == 15.0, "a success must clear the backoff"
    await ok.aclose()


@pytest.mark.asyncio
async def test_an_auth_failure_is_logged_at_error_and_names_the_no_fallback_rule(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D13 requires this to be loud. A quiet 403 looks exactly like a quiet market."""
    client = _client_returning(403)
    source = MassiveClient("k", 15.0, client=client)

    with caplog.at_level("ERROR", logger="finally_app.market.massive"):
        await source.fetch(["AAPL"])

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "403" in messages
    assert "NOT fall back" in messages
    await client.aclose()


@pytest.mark.asyncio
async def test_an_empty_ticker_list_makes_no_request() -> None:
    """An idle universe must not burn a rate-limited call."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = MassiveClient("k", 15.0, client=client)

    assert await source.fetch([]) == {}
    assert calls == 0
    await client.aclose()


# --- the poll interval -----------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (15.0, 15.0),
        (2.0, MINIMUM_POLL_SECONDS),
        (5.5, 5.5),
        (0.0, MINIMUM_POLL_SECONDS),
        (-5.0, MINIMUM_POLL_SECONDS),
        (0.001, MINIMUM_POLL_SECONDS),
        (float("inf"), DEFAULT_MASSIVE_POLL_SECONDS),
        (float("-inf"), DEFAULT_MASSIVE_POLL_SECONDS),
        (float("nan"), DEFAULT_MASSIVE_POLL_SECONDS),
    ],
)
def test_the_poll_interval_is_clamped(requested: float, expected: float) -> None:
    """`MASSIVE_POLL_SECONDS` was checked as *a float* and nothing further.

    Each of these was measured rather than imagined: `0` and `-5` give a hot
    loop against a metered paid API, `inf` freezes prices forever because
    `asyncio.sleep(inf)` never returns, and `nan` drops the producer into its
    restart loop — every comparison against NaN is False, so `max()` carries it
    straight into the sleep.

    Non-finite falls back to the default, not to the floor: a NaN is an
    unreadable value, not a request for the fastest legal poll.
    """
    assert valid_poll_seconds(requested) == expected


def test_the_client_clamps_what_it_is_constructed_with() -> None:
    """The guard is on the consumer, not on the loader.

    That placement is the point, and it is CP9's lesson rather than a
    preference: a rule enforced in `config.load_settings` is invisible to
    anything that builds a `MassiveClient` directly, which is every test in this
    file and would be any future caller.
    """
    assert MassiveClient("key", 0.0).interval_seconds == MINIMUM_POLL_SECONDS
    assert MassiveClient("key", float("nan")).interval_seconds == DEFAULT_MASSIVE_POLL_SECONDS


# --- the connection pool ---------------------------------------------------


@pytest.mark.asyncio
async def test_one_client_serves_every_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh `AsyncClient` per poll is a fresh pool and a fresh TLS handshake.

    Every 15 seconds, against the same host, for the life of the process. It
    survived review because the injection seam below is only ever used by tests,
    and a test hands in an already-open client — so the production path was the
    one path nothing exercised.

    Counting constructions rather than inspecting a private attribute: the claim
    is "one client is built", and that is the thing to observe.
    """
    real_client = httpx.AsyncClient
    created: list[httpx.AsyncClient] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tickers": []})

    def counting(*_args: object, **_kwargs: object) -> httpx.AsyncClient:
        client = real_client(transport=httpx.MockTransport(handler))
        created.append(client)
        return client

    monkeypatch.setattr(massive.httpx, "AsyncClient", counting)

    source = MassiveClient("key", 15.0)
    await source.fetch(["AAPL"])
    await source.fetch(["AAPL"])

    assert len(created) == 1, f"built {len(created)} clients for two polls"
    await source.aclose()


@pytest.mark.asyncio
async def test_aclose_releases_a_client_it_owns() -> None:
    source = MassiveClient("key", 15.0)

    await source.aclose()

    assert source._client.is_closed  # pylint: disable=protected-access


@pytest.mark.asyncio
async def test_aclose_leaves_an_injected_client_alone() -> None:
    """Whoever passed it in owns it.

    Closing a caller's client from here is how a shared fixture starts failing
    the *next* test rather than this one — which is a morning gone.
    """
    injected = _client_returning(200, {"tickers": []})
    source = MassiveClient("key", 15.0, injected)

    await source.aclose()

    assert not injected.is_closed
    await injected.aclose()
