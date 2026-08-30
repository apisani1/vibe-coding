"""Checks A6 and A7 — idempotent initialisation, correct shape, no stored price."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from finally_app.db import init as db_init
from finally_app.db.connection import connect, transaction
from finally_app.db.init import DEFAULT_TICKERS, ensure_initialized

EXPECTED_COLUMNS = {
    "users_profile": {"id", "cash_balance", "created_at"},
    "watchlist": {"id", "user_id", "ticker", "added_at"},
    "positions": {"id", "user_id", "ticker", "quantity", "avg_cost", "updated_at"},
    "trades": {"id", "user_id", "ticker", "side", "quantity", "price", "executed_at"},
    "portfolio_snapshots": {"id", "user_id", "total_value", "recorded_at"},
    "chat_messages": {"id", "user_id", "role", "content", "actions", "created_at"},
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "finally.db"
    ensure_initialized(path)
    return path


def test_initialisation_is_idempotent(tmp_path: Path) -> None:
    """A6: running twice against one file must not error or double-seed."""
    path = tmp_path / "finally.db"
    ensure_initialized(path)
    ensure_initialized(path)

    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == len(DEFAULT_TICKERS)


def test_seed_values_match_the_spec(db: Path) -> None:
    with connect(db) as conn:
        profile = conn.execute("SELECT id, cash_balance FROM users_profile").fetchone()
        assert profile["id"] == "default"
        assert profile["cash_balance"] == 10000.0

        tickers = {row["ticker"] for row in conn.execute("SELECT ticker FROM watchlist")}
        assert tickers == set(DEFAULT_TICKERS)
        assert len(DEFAULT_TICKERS) == 10


def test_all_tables_exist_with_the_designed_columns(db: Path) -> None:
    """A6: an inventory assertion, not a spot check."""
    with connect(db) as conn:
        names = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r["name"].startswith("sqlite_")
        }
        # Equality, not issubset: a table added later must fail this rather than
        # slip past both A6 and A7's hardcoded list.
        assert names == set(EXPECTED_COLUMNS)

        for table, expected in EXPECTED_COLUMNS.items():
            actual = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            assert actual == expected, f"{table} columns drifted"


def test_wal_is_enabled(db: Path) -> None:
    """A long read must not block a write; without WAL a chart view can refuse a trade."""
    with connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_busy_timeout_is_set(db: Path) -> None:
    """Without it the second writer errors instead of waiting, which reads as a flake."""
    with connect(db) as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_unique_constraints_and_checks_exist(db: Path) -> None:
    with connect(db) as conn:
        sql = " ".join(r["sql"] or "" for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert "UNIQUE (user_id, ticker)" in sql
    assert "CHECK (side IN ('buy', 'sell'))" in sql
    assert "CHECK (role IN ('user', 'assistant'))" in sql


def test_both_indexes_exist(db: Path) -> None:
    with connect(db) as conn:
        indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_snapshots_user_time" in indexes
    assert "idx_chat_user_time" in indexes


def test_side_check_actually_rejects_a_bad_value(db: Path) -> None:
    """The CHECK is only worth having if it fires."""
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(db) as conn:
            conn.execute(
                "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
                "VALUES ('x', 'default', 'AAPL', 'hodl', 1, 1, 'now')"
            )


def test_no_table_stores_a_current_price(db: Path) -> None:
    """A7 / D1: derived values are computed against the cache, never stored.

    trades.price is excluded by the table list, not by a name pattern -- it is
    a historical fill price, which is a different thing from a current one.
    """
    with connect(db) as conn:
        # Derived from the live schema minus `trades`, so a table added later is
        # covered automatically instead of silently escaping a hardcoded list.
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r["name"].startswith("sqlite_")
        } - {"trades"}
        for table in tables:
            columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            assert not {c for c in columns if "price" in c.lower()}, f"{table} stores a price"


def test_transaction_rolls_back_on_exception(db: Path) -> None:
    """A failed trade must leave nothing behind."""
    with pytest.raises(RuntimeError):
        with transaction(db) as conn:
            conn.execute("UPDATE users_profile SET cash_balance = 1 WHERE id = 'default'")
            raise RuntimeError("validation failed after a write")

    with connect(db) as conn:
        assert conn.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 10000.0


def test_a_failure_part_way_through_the_seed_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B8: the seed is one transaction, which it only *looked* like before.

    `ensure_initialized` ran the DDL and the seed inside a single
    `transaction(db_path)`. `executescript` issues an implicit COMMIT before it
    runs, so that `BEGIN IMMEDIATE` was gone by the time the DDL executed and
    the seed ran in autocommit — profile row and watchlist rows committing
    independently, with nothing to roll back between them.

    `new_id` is the lever because of *where* it sits: the profile INSERT does
    not call it (the id is the constant `DEFAULT_USER_ID`) and the watchlist
    INSERT calls it once per ticker. Raising there interrupts the seed exactly
    between its two statements, which is the only window the bug lived in.

    Revert the split and this test reports one profile row instead of none.
    """
    path = tmp_path / "finally.db"

    def interrupted() -> str:
        raise RuntimeError("seed interrupted")

    monkeypatch.setattr(db_init, "new_id", interrupted)

    with pytest.raises(RuntimeError, match="seed interrupted"):
        ensure_initialized(path)

    with connect(path) as conn:
        # The DDL is still committed, deliberately — it is idempotent, and this
        # assertion needs the table to exist in order to be able to fail.
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "users_profile" in tables, "the DDL should have committed on its own"
        assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0
