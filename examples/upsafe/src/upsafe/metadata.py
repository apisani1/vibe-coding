"""SQLite metadata store for quarantined objects.

One table, ``objects``, keyed by the download ``token`` (the capability) with
``stored_name`` UNIQUE. Expiry is enforced at read time: ``get_object`` returns ``None``
for an unknown *or* expired token, so callers cannot distinguish the two (criterion 8).

Timestamps are stored as UTC ISO-8601 strings and compared as ``datetime`` objects in
Python rather than in SQL, to avoid SQLite's date-handling quirks.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    token         TEXT PRIMARY KEY,
    stored_name   TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    size          INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredObject:  # pylint: disable=too-many-instance-attributes
    """A quarantined file's metadata row."""

    token: str
    stored_name: str
    original_name: str
    content_type: str
    size: int
    sha256: str
    created_at: datetime
    expires_at: datetime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with row access by name. Caller owns the lifecycle."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if absent. Idempotent — safe to call at every startup."""
    with closing(conn.cursor()) as cur:
        cur.execute(_SCHEMA)


def insert_object(conn: sqlite3.Connection, obj: StoredObject) -> None:
    """Persist a metadata row and commit.

    Committed *after* the file is durably published (see storage), so a committed token
    never points at a missing file. A ``stored_name`` collision (negligible at 128 bits)
    raises ``sqlite3.IntegrityError`` via the UNIQUE constraint.
    """
    with closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT INTO objects "
            "(token, stored_name, original_name, content_type, size, sha256, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                obj.token,
                obj.stored_name,
                obj.original_name,
                obj.content_type,
                obj.size,
                obj.sha256,
                obj.created_at.isoformat(),
                obj.expires_at.isoformat(),
            ),
        )
    conn.commit()


def get_object(conn: sqlite3.Connection, token: str, now: Optional[datetime] = None) -> Optional[StoredObject]:
    """Return the object for ``token``, or ``None`` if it is unknown or expired."""
    now = utcnow() if now is None else now
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT * FROM objects WHERE token = ?", (token,))
        row = cur.fetchone()
    if row is None:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= now:
        return None
    return StoredObject(
        token=row["token"],
        stored_name=row["stored_name"],
        original_name=row["original_name"],
        content_type=row["content_type"],
        size=row["size"],
        sha256=row["sha256"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=expires_at,
    )
