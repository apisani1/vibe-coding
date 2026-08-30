"""SQLite access: one connection per call, WAL, and explicit write transactions.

Three choices here are load-bearing and each exists for a specific failure.

**One connection per call.** ``sqlite3`` connections are not safe across
threads, and route handlers are declared ``def`` so Starlette runs them on its
threadpool — there really are multiple threads. A connection per call against a
local file costs microseconds; a shared connection with
``check_same_thread=False`` would trade that for a genuine correctness hazard.

**WAL.** A long read (the SSE generator's universe query, a history fetch) must
not block a write. Without it, a trade can be refused because someone is
looking at a chart.

**``BEGIN IMMEDIATE`` for writes.** SQLite's default deferred transaction takes
its write lock lazily, so two concurrent trades can both read the same cash
balance before either writes. ``IMMEDIATE`` takes the lock up front, so the
second blocks until the first commits and then sees the updated balance. This
is what makes the "you cannot spend the same cash twice" guarantee real rather
than lucky, and it is what check B2 exercises with two real threads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Without a busy timeout, the second writer raises "database is locked"
# immediately instead of waiting its turn — which looks like a flake and gets
# "fixed" by a retry, hiding the real serialisation.
BUSY_TIMEOUT_SECONDS = 5.0


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with the pragmas this application depends on."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    # isolation_level=None: we manage transactions explicitly below rather than
    # letting the driver open one implicitly on the first DML statement.
    connection.isolation_level = None
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_SECONDS * 1000)}")
    return connection


@contextmanager
def read_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection for reads. No transaction is opened."""
    connection = connect(db_path)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def read_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Several reads, one snapshot of the database.

    `read_connection` opens no transaction, so each statement sees its own
    snapshot — fine for a single SELECT and wrong for any figure derived from
    two. `get_portfolio` read cash and positions separately and could return a
    total that never existed: the review reproduced 8,100.00 where the truth was
    10,000.00, because a sell committed between the two statements.

    `BEGIN DEFERRED` rather than `IMMEDIATE`: this takes no write lock and, under
    WAL, does not block writers. It only pins the reader's view.
    """
    connection = connect(db_path)
    try:
        connection.execute("BEGIN DEFERRED")
        yield connection
    finally:
        connection.rollback()
        connection.close()


@contextmanager
def transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A write transaction: commits on success, rolls back on any exception.

    Everything a trade does — the position update, the trade-log append, the
    cash change and the snapshot — belongs inside one of these. A validation
    failure that raises mid-way must leave nothing behind.
    """
    connection = connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()
