"""The producer's universe rule (D3) and the lifespan wiring deferred from CP3."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

import finally_app.market.producer as producer_module
from finally_app.config import Settings
from finally_app.db.connection import transaction
from finally_app.db.init import ensure_initialized, new_id, utc_now
from finally_app.main import lifespan
from finally_app.market.cache import PriceCache
from finally_app.market.producer import read_universe, run_producer
from finally_app.market.simulator import Simulator


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "finally.db"
    ensure_initialized(path)
    return path


def test_universe_is_the_seeded_watchlist(db: Path) -> None:
    assert len(read_universe(db)) == 10
    assert "AAPL" in read_universe(db)


def test_universe_includes_positions_not_on_the_watchlist(db: Path) -> None:
    """D3: a held ticker removed from the watchlist must still be priced.

    Otherwise its market value freezes at whatever it was and the portfolio
    total goes quietly wrong -- the corruption path this rule exists to close.
    """
    with transaction(db) as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, 'default', 'AAPL', 5, 190.0, ?)",
            (new_id(), utc_now()),
        )

    universe = read_universe(db)
    assert "AAPL" in universe, "a held ticker off the watchlist lost its price"
    assert len(universe) == 10


def test_universe_excludes_zero_quantity_positions(db: Path) -> None:
    with transaction(db) as conn:
        conn.execute("DELETE FROM watchlist")
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, 'default', 'ZZZZ', 0, 1.0, ?)",
            (new_id(), utc_now()),
        )

    assert read_universe(db) == []


@pytest.mark.asyncio
async def test_producer_populates_the_cache_and_stops_cleanly(db: Path) -> None:
    cache = PriceCache()
    source = Simulator(tick_seconds=0.01, rng=random.Random(5))
    task = asyncio.create_task(run_producer(db, source, cache))

    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(cache.snapshot()) == 10:
            break

    assert len(cache.snapshot()) == 10
    assert cache.price_of("AAPL") is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_producer_survives_a_failing_source(db: Path) -> None:
    """A dead producer looks exactly like a quiet market -- the worst failure mode."""

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def interval_seconds(self) -> float:
            return 0.01

        async def fetch(self, tickers: list[str]) -> dict[str, float]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider exploded")
            return {t: 100.0 for t in tickers}

    source = Flaky()
    cache = PriceCache()
    task = asyncio.create_task(run_producer(db, source, cache))  # type: ignore[arg-type]

    for _ in range(300):
        await asyncio.sleep(0.02)
        if cache.snapshot():
            break

    assert cache.snapshot(), "producer did not recover from a source failure"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_lifespan_initialises_the_database_before_the_producer_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deferred from CP3: ASGITransport does not run startup, so nothing covered this.

    D12's ordering is load-bearing -- the producer reads the watchlist to learn
    which tickers to price, so an empty database at producer start means an
    empty universe forever.

    Asserts the ORDER directly rather than the end state. An end-state check
    would not fail a reversed ordering: a producer started first would create
    the database file itself via sqlite3.connect, ensure_initialized would then
    complete, and every end-state assertion would still pass.
    """
    import finally_app.main as main_module

    events: list[str] = []
    real_init = main_module.ensure_initialized
    real_universe = producer_module.read_universe

    def spy_init(path: Path) -> None:
        # Record COMPLETION, not entry. Recording entry is decided by an
        # executor submission race: under a reversed ordering both calls go to
        # the same default executor and whichever appends first wins a coin
        # flip, so `events[0] == "init"` passed about half the time against the
        # very bug it exists to catch.
        real_init(path)
        events.append("init-done")

    def spy_universe(path: Path, user_id: str = "default") -> list[str]:
        events.append("universe-attempted")
        try:
            tickers = real_universe(path, user_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # The producer's own broad `except` swallows this, so without
            # recording it here the pre-init read is invisible and the test
            # only ever sees the successful post-init retry.
            events.append(f"universe-ERROR:{type(exc).__name__}")
            raise
        events.append(f"universe:{len(tickers)}")
        return tickers

    monkeypatch.setattr(main_module, "ensure_initialized", spy_init)
    monkeypatch.setattr(producer_module, "read_universe", spy_universe)

    class Stub:
        state = type("S", (), {})()

    db_path = tmp_path / "finally.db"
    Stub.state.settings = Settings(  # type: ignore[attr-defined]
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=True,
        db_path=db_path,
    )

    assert not db_path.exists()
    async with lifespan(Stub):  # type: ignore[arg-type]
        for _ in range(200):
            await asyncio.sleep(0.01)
            if Stub.state.cache.snapshot():  # type: ignore[attr-defined]
                break
        assert Stub.state.cache.snapshot(), "no prices after startup"  # type: ignore[attr-defined]

    assert "init-done" in events, "initialisation never completed"
    assert "universe-attempted" in events, "the producer never read the universe"

    # The discriminating assertion: init must have FINISHED before the producer
    # first reached for the database.
    assert events.index("init-done") < events.index(
        "universe-attempted"
    ), f"the producer queried the database before initialisation completed: {events[:6]}"
    # And that first read must have succeeded. A pre-init read raises
    # "no such table: positions", which run_producer swallows -- so without
    # this the test only ever inspects the successful post-init retry.
    assert not [
        e for e in events if e.startswith("universe-ERROR")
    ], f"the producer's read failed against an uninitialised database: {events[:6]}"
    first_universe = next(e for e in events if e.startswith("universe:"))
    assert first_universe != "universe:0", "the producer started against an empty universe"


@pytest.mark.asyncio
async def test_the_configured_poll_interval_reaches_the_producer_loop(db: Path) -> None:
    """D24: a paid-tier MASSIVE_POLL_SECONDS must change how often the producer polls.

    The factory test pins the client's `interval_seconds` property; this pins
    that the producer actually sleeps on it. Verified by reading was not enough
    -- a producer that hardcoded its own interval would satisfy the property
    check and still poll at the wrong rate.
    """
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def spy_sleep(delay: float, *args: object, **kwargs: object) -> None:
        slept.append(delay)
        await real_sleep(0)

    class FixedInterval:
        def __init__(self, interval: float) -> None:
            self._interval = interval

        @property
        def interval_seconds(self) -> float:
            return self._interval

        async def fetch(self, tickers: list[str]) -> dict[str, float]:
            return {t: 1.0 for t in tickers}

    import finally_app.market.producer as prod

    original = prod.asyncio.sleep
    prod.asyncio.sleep = spy_sleep  # type: ignore[assignment]
    try:
        task = asyncio.create_task(run_producer(db, FixedInterval(2.0), PriceCache()))  # type: ignore[arg-type]
        for _ in range(100):
            await real_sleep(0.005)
            if len(slept) >= 3:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        prod.asyncio.sleep = original  # type: ignore[assignment]

    assert slept, "the producer never slept"
    assert all(delay == 2.0 for delay in slept), f"producer ignored the configured interval: {slept[:5]}"


@pytest.mark.asyncio
async def test_a_source_returning_nothing_leaves_the_cache_byte_identical(db: Path) -> None:
    """D13, provenance at the producer — covers a fallback added HERE rather than in the client.

    A degrade path in `_tick` that applies invented prices after N empty polls
    passed every other check, because nothing asserted the cache stays put when
    the source yields nothing.

    Paired with `test_the_fetch_path_makes_no_freshness_decisions`, which is
    what closes the time-gated variant: this test can only observe the window it
    runs in, so the structural guard carries the unbounded half.
    """

    class Silent:
        """A source that never has a price -- a bad key, a rate limit, an outage."""

        @property
        def interval_seconds(self) -> float:
            return 0.001

        async def fetch(self, tickers: list[str]) -> dict[str, float]:
            return {}

    cache = PriceCache()
    cache.apply({"AAPL": 190.0, "MSFT": 415.0})
    before = dict(cache.snapshot())

    task = asyncio.create_task(run_producer(db, Silent(), cache))  # type: ignore[arg-type]
    await asyncio.sleep(0.3)  # hundreds of ticks, and hours of simulated time
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert cache.snapshot() == before, "the producer invented prices when the source had none"


@pytest.mark.asyncio
async def test_the_producer_only_caches_prices_its_source_returned(db: Path) -> None:
    """Every cached price must trace to something the source actually produced."""

    class Fixed:
        served: list[dict[str, float]] = []

        @property
        def interval_seconds(self) -> float:
            return 0.001

        async def fetch(self, tickers: list[str]) -> dict[str, float]:
            prices = {t: 100.0 + i for i, t in enumerate(tickers)}
            Fixed.served.append(prices)
            return prices

    Fixed.served = []
    cache = PriceCache()
    task = asyncio.create_task(run_producer(db, Fixed(), cache))  # type: ignore[arg-type]
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    served_values = {price for batch in Fixed.served for price in batch.values()}
    for quote in cache.snapshot().values():
        assert quote["price"] in served_values, f"{quote['ticker']} holds an invented price"


@pytest.mark.asyncio
async def test_the_lifespan_closes_the_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The other end of #19's fix: one client for the process means someone has
    to close it.

    `aclose` is on the `MarketDataSource` Protocol rather than fished out with
    `getattr`, so `mypy --strict` is what proves a source implements it. This
    asserts the lifespan actually *calls* it — a Protocol member nothing invokes
    is a slower way of having no teardown.

    Ordered after the tasks are cancelled and awaited: closing a connection pool
    while the producer still has a poll in flight turns an orderly shutdown into
    a traceback.
    """
    import finally_app.main as main_module  # pylint: disable=import-outside-toplevel

    closed: list[str] = []

    class ClosableSource:
        interval_seconds = 0.01

        async def fetch(self, tickers: list[str]) -> dict[str, float]:
            return {ticker: 1.0 for ticker in tickers}

        async def aclose(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(main_module, "create_source", lambda _settings: ClosableSource())

    class Stub:
        state = type("S", (), {})()

    Stub.state.settings = Settings(  # type: ignore[attr-defined]
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=True,
        db_path=tmp_path / "finally.db",
    )

    async with lifespan(Stub):  # type: ignore[arg-type]
        assert not closed, "the source was closed while the app was still serving"

    assert closed == ["closed"]
