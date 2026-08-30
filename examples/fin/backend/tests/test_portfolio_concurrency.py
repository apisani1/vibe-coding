"""Check B2 — concurrent trades serialize. **Demonstrated failing at CP6.**

This is the check R2 exists for, and it is worthless unless two things are true
at once: the threads genuinely overlap, and their read–write window is wide
enough that overlap is *certain* rather than lucky.

Sequential calls on a single thread pass identically under ``BEGIN IMMEDIATE``,
``BEGIN DEFERRED`` and autocommit — there is never a second open write
transaction — so a version of this test without threads proves nothing. And with
threads but a microsecond-wide window between "read the cash balance" and "write
the new one", both orderings still usually serialize by accident, so the test
still passes with the guarantee removed.

Hence ``_widen_the_read_write_window``: it monkeypatches a real seam in the
service (the cash read) to sleep after reading, which forces both threads to
hold a stale balance at the same instant. Under ``BEGIN IMMEDIATE`` that changes
nothing — the second thread never gets past ``BEGIN`` until the first commits.
Under ``BEGIN DEFERRED`` it turns an intermittent failure into a certain one.

Recorded demonstration (CP6, `build-log.md`): with ``BEGIN DEFERRED`` this test
fails as ``sqlite3.OperationalError: database is locked`` — WAL refuses to
upgrade a read transaction whose snapshot another writer has already superseded
— not as a double fill.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from finally_app.config import Settings
from finally_app.db.connection import read_connection
from finally_app.db.init import ensure_initialized
from finally_app.market.cache import PriceCache
from finally_app.services import portfolio

PRICE = 190.0
ROUNDS = 10
READ_WRITE_WINDOW_SECONDS = 0.05


@pytest.fixture
def db(settings: Settings) -> Path:
    ensure_initialized(settings.db_path)
    return settings.db_path


@pytest.fixture
def cache() -> PriceCache:
    priced = PriceCache()
    priced.apply({"AAPL": PRICE})
    return priced


@pytest.fixture
def widened(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Hold the cash balance across a 50 ms window inside the transaction.

    Patches the module-level ``_read_cash_balance`` that ``execute_trade`` looks
    up at call time. This is a real seam in the service, not a hook added for
    the test: no production signature changes to accommodate it.
    """
    original: Callable[[sqlite3.Connection, str], float] = portfolio._read_cash_balance

    def slow_read(connection: sqlite3.Connection, user_id: str) -> float:
        balance = original(connection, user_id)
        threading.Event().wait(READ_WRITE_WINDOW_SECONDS)
        return balance

    monkeypatch.setattr(portfolio, "_read_cash_balance", slow_read)
    yield


def _cash(db_path: Path) -> float:
    with read_connection(db_path) as connection:
        return float(connection.execute("SELECT cash_balance FROM users_profile").fetchone()["cash_balance"])


def _trade_count(db_path: Path) -> int:
    with read_connection(db_path) as connection:
        return int(connection.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"])


def _attempt(db_path: Path, cache: PriceCache, quantity: float, barrier: threading.Barrier, out: list[str]) -> None:
    """One thread's buy, released simultaneously with the other's."""
    barrier.wait(timeout=10)
    try:
        portfolio.execute_trade(db_path, cache, portfolio.TradeOrder("AAPL", "buy", quantity))
        out.append("filled")
    except portfolio.InsufficientCash:
        out.append("rejected")
    except sqlite3.OperationalError as exc:  # pragma: no cover - the DEFERRED failure mode
        out.append(f"locked: {exc}")


@pytest.mark.usefixtures("widened")
def test_two_threads_cannot_spend_the_same_cash(db: Path, cache: PriceCache) -> None:
    """Ten rounds, because scheduling luck survives one.

    Each round both threads try to buy 60% of the *current* balance, so exactly
    one of them can be afforded. The assertions are on state, not on timing:
    one fill, one rejection, one new trade row, and cash never negative.
    """
    for round_number in range(ROUNDS):
        starting_cash = _cash(db)
        quantity = round(starting_cash * 0.6 / PRICE, 6)
        trades_before = _trade_count(db)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        threads = [threading.Thread(target=_attempt, args=(db, cache, quantity, barrier, outcomes)) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive(), f"round {round_number}: a trade thread never finished"

        locked = [outcome for outcome in outcomes if outcome.startswith("locked")]
        assert not locked, f"round {round_number}: a lock error escaped to the caller: {locked}"
        assert sorted(outcomes) == ["filled", "rejected"], f"round {round_number}: outcomes were {outcomes}"
        assert _trade_count(db) == trades_before + 1, f"round {round_number}: wrong number of trade rows"
        assert _cash(db) >= 0.0, f"round {round_number}: cash went negative"
        assert _cash(db) == pytest.approx(
            starting_cash - round(PRICE * quantity, 4)
        ), f"round {round_number}: cash does not match exactly one fill"


@pytest.mark.usefixtures("widened")
def test_the_losing_thread_writes_nothing(db: Path, cache: PriceCache) -> None:
    """The rejected side must not leave a position, a trade, or a snapshot behind."""
    quantity = round(_cash(db) * 0.6 / PRICE, 6)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    threads = [threading.Thread(target=_attempt, args=(db, cache, quantity, barrier, outcomes)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["filled", "rejected"]
    with read_connection(db) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"] == 1
        assert connection.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"] == 1
        assert connection.execute("SELECT COUNT(*) AS n FROM portfolio_snapshots").fetchone()["n"] == 1
        assert connection.execute("SELECT quantity FROM positions").fetchone()["quantity"] == quantity
