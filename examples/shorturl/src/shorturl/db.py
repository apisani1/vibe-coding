"""SQLite persistence: connection setup, schema, and typed data-access functions.

Every function takes an open ``sqlite3.Connection`` as its first argument — connections
are created by :func:`connect` and passed in, never constructed inside a query function.
This keeps the data layer decoupled from where the connection comes from (a per-request
connection in the API, a per-command one in the CLI, an in-memory one in tests).
"""

from __future__ import annotations

import sqlite3
from typing import TypedDict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS codes (
    code       TEXT PRIMARY KEY,
    target_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL REFERENCES codes(code) ON DELETE CASCADE,
    clicked_at TEXT NOT NULL,
    referer    TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_clicks_code ON clicks(code);
"""

_TOP_REFERERS_LIMIT = 10


class DayCount(TypedDict):
    date: str
    count: int


class RefererCount(TypedDict):
    referer: str
    count: int


class Stats(TypedDict):
    total: int
    series: list[DayCount]
    top_referers: list[RefererCount]


def connect(db_path: str) -> sqlite3.Connection:
    """Open a configured connection: WAL, enforced foreign keys, row access by name.

    WAL lets the redirect writer and the stats/list readers coexist with less locking;
    ``busy_timeout`` turns a transient lock into a short wait instead of an error; and
    ``foreign_keys=ON`` (off by default in SQLite) is what makes the click cascade fire
    on delete. The pragma must be set per connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the tables and index if they do not yet exist."""
    conn.executescript(_SCHEMA)
    conn.commit()


def insert_code(
    conn: sqlite3.Connection,
    *,
    code: str,
    target_url: str,
    created_at: str,
    expires_at: str | None,
) -> None:
    """Insert a new code. Raises ``sqlite3.IntegrityError`` if the code already exists."""
    conn.execute(
        "INSERT INTO codes (code, target_url, created_at, expires_at, active) VALUES (?, ?, ?, ?, 1)",
        (code, target_url, created_at, expires_at),
    )
    conn.commit()


def get_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    """Return the code row, or None if there is no such code."""
    cur = conn.execute(
        "SELECT code, target_url, created_at, expires_at, active FROM codes WHERE code = ?",
        (code,),
    )
    row: sqlite3.Row | None = cur.fetchone()
    return row


def insert_click(
    conn: sqlite3.Connection,
    *,
    code: str,
    clicked_at: str,
    referer: str | None,
    user_agent: str | None,
) -> None:
    """Record one click for ``code``."""
    conn.execute(
        "INSERT INTO clicks (code, clicked_at, referer, user_agent) VALUES (?, ?, ?, ?)",
        (code, clicked_at, referer, user_agent),
    )
    conn.commit()


def list_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all codes with a ``click_count`` column, newest first.

    A LEFT JOIN + GROUP BY computes each code's click count in one query (no N+1).
    """
    cur = conn.execute("""
        SELECT c.code, c.target_url, c.created_at, c.expires_at, c.active,
               COUNT(k.id) AS click_count
        FROM codes c
        LEFT JOIN clicks k ON k.code = c.code
        GROUP BY c.code
        ORDER BY c.created_at DESC, c.code
        """)
    return cur.fetchall()


def expire_code(conn: sqlite3.Connection, code: str) -> bool:
    """Deactivate a code (manual expiry). Returns False if the code does not exist."""
    cur = conn.execute("UPDATE codes SET active = 0 WHERE code = ?", (code,))
    conn.commit()
    return cur.rowcount > 0


def delete_code(conn: sqlite3.Connection, code: str) -> bool:
    """Delete a code and (via cascade) its clicks. Returns False if it does not exist."""
    cur = conn.execute("DELETE FROM codes WHERE code = ?", (code,))
    conn.commit()
    return cur.rowcount > 0


def get_stats(conn: sqlite3.Connection, code: str) -> Stats:
    """Aggregate a code's clicks: total, per-day series, and top referers.

    The per-day series buckets on ``substr(clicked_at, 1, 10)`` — the ``YYYY-MM-DD`` date
    prefix of the ISO-8601 UTC timestamp — which is valid precisely because timestamps are
    stored as canonical UTC text.
    """
    total = _scalar_int(conn.execute("SELECT COUNT(*) FROM clicks WHERE code = ?", (code,)))
    series = [
        DayCount(date=row["day"], count=row["count"])
        for row in conn.execute(
            """
            SELECT substr(clicked_at, 1, 10) AS day, COUNT(*) AS count
            FROM clicks WHERE code = ?
            GROUP BY day ORDER BY day
            """,
            (code,),
        ).fetchall()
    ]
    top_referers = [
        RefererCount(referer=row["referer"], count=row["count"])
        for row in conn.execute(
            """
            SELECT referer, COUNT(*) AS count
            FROM clicks WHERE code = ? AND referer IS NOT NULL
            GROUP BY referer ORDER BY count DESC, referer
            LIMIT ?
            """,
            (code, _TOP_REFERERS_LIMIT),
        ).fetchall()
    ]
    return Stats(total=total, series=series, top_referers=top_referers)


def _scalar_int(cursor: sqlite3.Cursor) -> int:
    return int(cursor.fetchone()[0])
