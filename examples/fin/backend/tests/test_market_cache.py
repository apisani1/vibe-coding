"""Check A10 — session_open is stamped once; previous_price moves every tick."""

from __future__ import annotations

import random

from finally_app.market.cache import PriceCache
from finally_app.market.simulator import Simulator


def test_session_open_is_stamped_once_and_never_rewritten() -> None:
    """A10 / D19.

    This is the property the watchlist's change % rests on. If session_open
    tracked the latest price, change % would read 0.00% forever; if it tracked
    the previous tick, it would read +-0.01% and flip sign twice a second.
    """
    cache = PriceCache()
    simulator = Simulator(rng=random.Random(42))
    tickers = ["AAPL", "MSFT"]

    cache.apply(simulator.advance(tickers))
    first_opens = {t: cache.get(t)["session_open"] for t in tickers}  # type: ignore[index]

    previous_price_changes = {t: 0 for t in tickers}
    for _ in range(50):
        before = {t: cache.get(t)["previous_price"] for t in tickers}  # type: ignore[index]
        cache.apply(simulator.advance(tickers))
        for ticker in tickers:
            if cache.get(ticker)["previous_price"] != before[ticker]:  # type: ignore[index]
                previous_price_changes[ticker] += 1

    for ticker in tickers:
        assert cache.get(ticker)["session_open"] == first_opens[ticker]  # type: ignore[index]
        assert previous_price_changes[ticker] >= 40, "previous_price should move nearly every tick"


def test_a_ticker_added_mid_run_gets_its_own_session_open() -> None:
    """Its change % must read exactly 0.00% on the first tick, not inherit a baseline."""
    cache = PriceCache()
    simulator = Simulator(rng=random.Random(11))

    for _ in range(20):
        cache.apply(simulator.advance(["AAPL"]))

    cache.apply(simulator.advance(["AAPL", "PYPL"]))
    pypl = cache.get("PYPL")

    assert pypl is not None
    assert pypl["session_open"] == pypl["price"]
    assert pypl["previous_price"] == pypl["price"]
    assert pypl["direction"] == "flat"


def test_direction_is_derived_by_the_writer() -> None:
    """One direction per tick for every reader, rather than each SSE client deciding."""
    cache = PriceCache()
    cache.apply({"AAPL": 100.0})
    assert cache.get("AAPL")["direction"] == "flat"  # type: ignore[index]

    cache.apply({"AAPL": 101.0})
    assert cache.get("AAPL")["direction"] == "up"  # type: ignore[index]

    cache.apply({"AAPL": 99.0})
    assert cache.get("AAPL")["direction"] == "down"  # type: ignore[index]

    # An unchanged price is skipped entirely now (it must not restamp the
    # timestamp, or SSE would emit a frame for a price that did not move), so
    # the quote keeps the direction of its last real move rather than resetting
    # to "flat". That is also the more truthful reading: the last thing this
    # price did was go down.
    before = cache.get("AAPL")
    cache.apply({"AAPL": 99.0})
    assert cache.get("AAPL") == before


def test_omitted_tickers_keep_their_previous_quote() -> None:
    """A source that skipped a symbol must not blank the row.

    This is what turns a Massive rate-limit into "prices go stale" rather than
    "every price disappears".
    """
    cache = PriceCache()
    cache.apply({"AAPL": 100.0, "MSFT": 400.0})
    cache.apply({"AAPL": 101.0})

    assert cache.get("MSFT")["price"] == 400.0  # type: ignore[index]
    assert cache.get("AAPL")["price"] == 101.0  # type: ignore[index]


def test_apply_rebinds_rather_than_mutating_the_snapshot() -> None:
    """The lock-free contract: a reader's snapshot must not change under it."""
    cache = PriceCache()
    cache.apply({"AAPL": 100.0})
    held = cache.snapshot()

    cache.apply({"AAPL": 200.0})

    assert held["AAPL"]["price"] == 100.0
    assert cache.snapshot()["AAPL"]["price"] == 200.0


def test_price_of_returns_none_for_an_unpriced_ticker() -> None:
    """Callers must refuse to trade rather than substitute zero."""
    cache = PriceCache()
    assert cache.price_of("AAPL") is None

    cache.apply({"AAPL": 100.0})
    assert cache.price_of("aapl") == 100.0


def test_tickers_are_normalised_to_uppercase() -> None:
    cache = PriceCache()
    cache.apply({"aapl": 100.0})

    assert cache.get("AAPL") is not None
    assert cache.snapshot()["AAPL"]["ticker"] == "AAPL"
