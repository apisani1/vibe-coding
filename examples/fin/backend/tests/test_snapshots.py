"""Check B4 — the snapshot task and the history endpoint.

The P&L chart is only as honest as this table. Two properties carry that weight
and both are asserted against stored rows rather than against a return value:
**the recorded total is the same number `GET /api/portfolio` reports**, and
**exactly one row per fill, none per rejection**.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finally_app.config import Settings
from finally_app.db.connection import read_connection
from finally_app.db.init import ensure_initialized
from finally_app.market.cache import PriceCache
from finally_app.services import portfolio, snapshots

PRICES = {"AAPL": 190.0, "MSFT": 400.0}
STARTING_CASH = 10000.0


@pytest.fixture
def db(settings: Settings) -> Path:
    ensure_initialized(settings.db_path)
    return settings.db_path


@pytest.fixture
def cache() -> PriceCache:
    priced = PriceCache()
    priced.apply(PRICES)
    return priced


@pytest.fixture
def account(app: FastAPI, db: Path) -> FastAPI:  # pylint: disable=unused-argument
    app.state.cache.apply(PRICES)
    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def _rows(db_path: Path) -> list[tuple[float, str]]:
    with read_connection(db_path) as connection:
        return [
            (float(row["total_value"]), str(row["recorded_at"]))
            for row in connection.execute("SELECT total_value, recorded_at FROM portfolio_snapshots ORDER BY rowid")
        ]


# --- the periodic task ----------------------------------------------------


@pytest.mark.asyncio
async def test_the_task_records_repeatedly_at_its_configured_interval(db: Path, cache: PriceCache) -> None:
    """Interval injected at 0.05 s. Breaks if the task records once and stops,
    or sleeps before its first write instead of after.

    Asserts the **value** each row carries, not only how many there are. Counting
    rows alone leaves the entire periodic series unguarded: the task can keep
    calling `record_snapshot` and then write anything it likes, and a row-count
    test stays green while the P&L line flatlines at cash. Found by the overseer
    at CP8 review, which appended a cash-only rewrite and kept 190/190 passing.
    """
    # A price with cents, deliberately. Round-dollar fixtures let a divergence
    # that only loses precision survive — the overseer truncated the recorded
    # total to whole dollars and all 190 tests passed.
    cache.apply({"AAPL": 190.37})
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10.5))
    # The price must MOVE after the fill, or the total is exactly the starting
    # cash however many cents the price carries — buying at the mark shifts
    # value between cash and position without changing the sum. The guard
    # below caught precisely that on the first attempt at this fixture.
    cache.apply({"AAPL": 203.19})
    expected = portfolio.get_portfolio(db, cache)["total_value"]
    assert expected != round(expected), "the fixture must carry cents or it cannot detect truncation"
    baseline = len(_rows(db))

    task = asyncio.create_task(snapshots.run_snapshotter(db, cache, interval_seconds=0.05))
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    rows = _rows(db)[baseline:]
    assert len(rows) >= 2, f"only {len(rows)} snapshots in 0.3s at a 0.05s interval"
    # ~6 expected. A task that ignored its interval and spun would produce
    # thousands; the bound excludes that by orders of magnitude while leaving
    # room for scheduling jitter.
    assert len(rows) <= 30, f"{len(rows)} snapshots in 0.3s — the interval is not being honoured"
    assert all(row[0] == expected for row in rows), f"the task wrote {[r[0] for r in rows]}, expected {expected}"


@pytest.mark.asyncio
async def test_the_first_snapshot_lands_before_the_first_interval_elapses(db: Path, cache: PriceCache) -> None:
    """Sleep-then-write would leave the chart blank for a full 30 s after boot,
    and a session shorter than one interval would produce no line at all."""
    task = asyncio.create_task(snapshots.run_snapshotter(db, cache, interval_seconds=30.0))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(_rows(db)) == 1


@pytest.mark.asyncio
async def test_the_task_survives_a_failing_write(db: Path, cache: PriceCache, monkeypatch: pytest.MonkeyPatch) -> None:
    """A background task that dies on one bad write leaves a chart that silently
    stops extending while everything else looks healthy."""
    calls = {"n": 0}
    original = portfolio.record_snapshot

    def flaky(*args: object, **kwargs: object) -> float:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(portfolio, "record_snapshot", flaky)
    monkeypatch.setattr(snapshots, "RESTART_DELAY_SECONDS", 0.02)

    task = asyncio.create_task(snapshots.run_snapshotter(db, cache, interval_seconds=0.02))
    await asyncio.sleep(0.25)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls["n"] > 1, "the task stopped after the first failure"
    assert _rows(db), "the task never recovered enough to write anything"


@pytest.mark.asyncio
async def test_cancelling_the_task_unwinds_it(db: Path, cache: PriceCache) -> None:
    """A swallowed cancellation makes uvicorn's shutdown hang until it times out."""
    task = asyncio.create_task(snapshots.run_snapshotter(db, cache, interval_seconds=0.05))
    await asyncio.sleep(0.06)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


@pytest.mark.asyncio
async def test_lifespan_starts_the_task_against_the_live_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring test, and it must assert the *value*, not that a row exists.

    ASGITransport does not run startup, so nothing else covers this at all. But
    "a row appeared" is far too weak: the overseer started the task with a fresh
    `PriceCache()` instead of the producer's, and 190/190 stayed green while
    every periodic snapshot would value positions at cost forever — a P&L chart
    flat at cost basis while the portfolio moves.

    So the position below is seeded with an `avg_cost` of 1.0 against a simulator
    that seeds AAPL at a fixed 190. A live cache records ~29,000 (10,000 cash
    plus 19,000 of position value); a dead one records exactly 10,090. There is no reading of the two that overlaps.
    """
    from finally_app.config import Settings as RealSettings
    from finally_app.db.init import new_id, utc_now
    from finally_app.main import ensure_initialized as _init
    from finally_app.main import lifespan

    db_path = tmp_path / "finally.db"
    _init(db_path)
    with read_connection(db_path) as connection:
        connection.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?,?,?,?,?,?)",
            (new_id(), "default", "AAPL", 100.0, 1.0, utc_now()),
        )
        connection.commit()

    cost_basis_total = STARTING_CASH + 100.0 * 1.0  # what a dead cache would record

    # Read from main's namespace at call time, so the interval can be shortened
    # without patching the task itself — patching the task is what the test is
    # for. A 30s default would give this test exactly one row and no second
    # chance if the first snapshot beat the producer's first fetch.
    monkeypatch.setattr("finally_app.main.SNAPSHOT_INTERVAL_SECONDS", 0.05)

    class Stub:
        state = type("S", (), {})()

    Stub.state.settings = RealSettings(  # type: ignore[attr-defined]
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=True,
        db_path=db_path,
    )

    async with lifespan(Stub):  # type: ignore[arg-type]
        for _ in range(300):
            await asyncio.sleep(0.01)
            if any(row[0] != cost_basis_total for row in _rows(db_path)):
                break
        totals = [row[0] for row in _rows(db_path)]
        assert totals, "lifespan never started the snapshot task"
        assert any(total != cost_basis_total for total in totals), (
            f"every snapshot recorded the cost-basis total {cost_basis_total} — the task is not "
            f"reading the producer's cache. Recorded: {totals[:5]}"
        )

    # Shutdown must have cancelled AND awaited the task. A leaked snapshotter
    # keeps writing after the context exits — at a 0.05s interval, several rows
    # inside the window below.
    after_shutdown = len(_rows(db_path))
    await asyncio.sleep(0.3)
    assert len(_rows(db_path)) == after_shutdown, "the snapshot task outlived lifespan — it was never cancelled"


# --- what gets recorded ---------------------------------------------------


def test_a_flat_portfolio_records_exactly_the_cash_balance(db: Path, cache: PriceCache) -> None:
    """Exactly, not approximately: with no positions there is nothing to value,
    so any drift here is arithmetic that should not be happening at all."""
    total = portfolio.record_snapshot(db, cache)

    assert total == STARTING_CASH
    assert [row[0] for row in _rows(db)] == [STARTING_CASH]


def test_the_recorded_total_matches_the_portfolio_endpoint(db: Path, cache: PriceCache) -> None:
    """One definition of total_value, not two.

    The trade path and the periodic task both go through
    `portfolio.record_snapshot`, which is why this holds. A second
    implementation in `snapshots.py` would show up in the chart as a step with
    no trade to explain it.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))
    cache.apply({"AAPL": 205.0})

    recorded = portfolio.record_snapshot(db, cache)

    assert recorded == portfolio.get_portfolio(db, cache)["total_value"]


def test_an_unpriced_position_is_snapshotted_at_cost(db: Path, cache: PriceCache) -> None:
    """The ratified rule (human, 2026-08-14), asserted where the chart consumes it.

    Dropping the position from the total instead would render as a cliff and
    recovery on the P&L line, with no trade anywhere to explain either.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))

    total = portfolio.record_snapshot(db, PriceCache())

    assert total == STARTING_CASH  # 8100 cash + 10 shares carried at 190


def test_each_fill_writes_one_snapshot_and_each_rejection_writes_none(db: Path, cache: PriceCache) -> None:
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 1))
    with pytest.raises(portfolio.InsufficientCash):
        portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10_000))
    with pytest.raises(portfolio.PriceUnavailable):
        portfolio.execute_trade(db, cache, portfolio.TradeOrder("PYPL", "buy", 1))
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "sell", 1))

    assert len(_rows(db)) == 2


# --- history --------------------------------------------------------------


def test_history_comes_back_oldest_first(db: Path, cache: PriceCache) -> None:
    """The chart plots left to right; a reversed series draws the P&L backwards."""
    for price in (190.0, 200.0, 210.0):
        cache.apply({"AAPL": price})
        portfolio.record_snapshot(db, cache)

    history = snapshots.read_history(db)

    timestamps = [row["recorded_at"] for row in history]
    assert timestamps == sorted(timestamps)


def test_history_returns_the_newest_window_not_the_oldest(db: Path, cache: PriceCache) -> None:
    """The table grows ~2,880 rows a day. Selecting the oldest `limit` rows would
    show the first hours after install forever, which looks like a frozen chart.

    The prices below must **move**. An earlier version bought 1..5 shares at a
    constant price, which leaves cash and position value moving by equal and
    opposite amounts — every total was exactly 10,000 and the assertion compared
    identical numbers. The overseer served the oldest window with the whole suite
    green. Distinct totals are the entire test.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))
    for price in (200.0, 210.0, 220.0, 230.0, 240.0):
        cache.apply({"AAPL": price})
        portfolio.record_snapshot(db, cache)

    every = [row[0] for row in _rows(db)]
    assert len(set(every)) == len(every), "the fixture must produce distinct totals or it proves nothing"

    history = snapshots.read_history(db, limit=2)

    assert len(history) == 2
    assert [row["total_value"] for row in history] == every[-2:]
    assert [row["total_value"] for row in history] != every[:2]


@pytest.mark.asyncio
async def test_the_history_endpoint_serves_the_series(account: FastAPI, db: Path) -> None:
    portfolio.execute_trade(db, account.state.cache, portfolio.TradeOrder("AAPL", "buy", 2))

    response = await _get(account, "/api/portfolio/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert set(body[0]) == {"total_value", "recorded_at"}
    assert body[0]["total_value"] == STARTING_CASH


@pytest.mark.asyncio
async def test_an_empty_history_is_an_empty_list_not_an_error(account: FastAPI) -> None:
    """Before the first snapshot the chart must render empty, not break."""
    response = await _get(account, "/api/portfolio/history")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 5001])
async def test_an_out_of_range_limit_is_a_422(account: FastAPI, limit: int) -> None:
    """`limit=0` returning everything, or an unbounded limit, both turn a chart
    refresh into a full-table scan."""
    response = await _get(account, f"/api/portfolio/history?limit={limit}")

    assert response.status_code == 422
