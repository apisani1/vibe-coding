"""Idempotent schema creation and seeding.

Runs once at lifespan startup rather than lazily on first request. A lazy check
would need a lock on every request to stop two concurrent first-requests racing
the DDL, and it would leave the price producer with no ticker list at boot
(D12).
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .connection import connect, transaction

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10000.0
DEFAULT_TICKERS = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def utc_now() -> str:
    """An ISO-8601 UTC timestamp, the only time format this application stores."""
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    """A fresh UUID4 primary key."""
    return str(uuid.uuid4())


def _seed(connection: sqlite3.Connection) -> None:
    """Insert the default profile and watchlist if they are not already there.

    ``INSERT OR IGNORE`` against the UNIQUE constraints rather than a
    count-then-insert: the check and the insert would otherwise be two steps
    that a concurrent caller could interleave, and the constraint already
    expresses the rule exactly.
    """
    now = utc_now()
    connection.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), DEFAULT_USER_ID, ticker, now) for ticker in DEFAULT_TICKERS],
    )


def ensure_initialized(db_path: Path) -> None:
    """Create the schema, then seed defaults. Safe to call any number of times.

    **Two steps, because one of them could never have been what it looked
    like.** This used to run the DDL and the seed inside a single
    ``transaction(db_path)``. That reads as "all of it or none of it" and was
    not: ``sqlite3``'s ``executescript`` issues an implicit COMMIT before it
    runs anything, so the ``BEGIN IMMEDIATE`` was already gone by the time the
    DDL executed, and ``_seed`` ran in **autocommit** — its two statements
    independently committed, with no rollback between them.

    Harmless in practice, since the DDL is ``IF NOT EXISTS`` and the seed is
    ``INSERT OR IGNORE``. Not harmless as a *claim*: the helper advertised
    atomicity that the driver had already discarded, and the next person to add
    a third seed statement would have inherited the guarantee they read rather
    than the one they had.

    So: the DDL runs on a plain connection, where its own commits are exactly
    what is wanted and nothing pretends otherwise, and the seed gets a real
    transaction of its own — one that a failure part-way through actually rolls
    back.
    """
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    # Not `transaction()`: `executescript` would commit out from under it. This
    # is DDL, it is idempotent, and each statement standing alone is correct.
    with closing(connect(db_path)) as connection:
        connection.executescript(ddl)
    with transaction(db_path) as connection:
        _seed(connection)
    logger.info("database ready at %s", db_path)
