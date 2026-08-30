"""The periodic portfolio snapshot, and the history the P&L chart reads.

This module owns **timing and retrieval only**. The value itself is computed by
``portfolio.record_snapshot`` so that both writers — the 30-second task here and
the one inside every trade — share a single definition of ``total_value``,
including the ratified rule that a position with no cached price is carried at
cost. A second implementation of that number would diverge the first time either
was edited, and the divergence would show up as a step in the chart with no
trade to explain it.

The task is ``async`` because it owns a timer; the actual database work hops to a
thread, because ``sqlite3`` blocks and this is the event loop (D21).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..db.connection import read_connection
from ..db.init import DEFAULT_USER_ID
from ..market.cache import PriceCache
from . import portfolio

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0
RESTART_DELAY_SECONDS = 5.0
DEFAULT_HISTORY_LIMIT = 500


def read_history(
    db_path: Path,
    limit: int = DEFAULT_HISTORY_LIMIT,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, float | str]]:
    """The most recent snapshots, oldest first.

    Newest ``limit`` rows, then reversed: a chart wants the *recent* window but
    must plot it left to right. Selecting the oldest ``limit`` rows instead would
    show the first hours after install forever, and the table grows ~2,880 rows a
    day.
    """
    with read_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT total_value, recorded_at FROM portfolio_snapshots
            WHERE user_id = ? ORDER BY recorded_at DESC, rowid DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [
        {"total_value": float(row["total_value"]), "recorded_at": str(row["recorded_at"])} for row in reversed(rows)
    ]


async def run_snapshotter(
    db_path: Path,
    cache: PriceCache,
    interval_seconds: float = SNAPSHOT_INTERVAL_SECONDS,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Record total portfolio value forever, surviving its own failures.

    Writes immediately and then every ``interval_seconds``, so the chart has a
    point from boot rather than a blank half-minute — and so a session shorter
    than one interval still produces a line.

    Failures are logged and retried rather than killing the task: an unhandled
    exception in a background task dies silently, and the symptom would be a
    chart that simply stops extending while everything else looks healthy.
    """
    while True:
        try:
            await asyncio.to_thread(portfolio.record_snapshot, db_path, cache, user_id)
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("snapshot task stopping")
            raise
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("snapshot task failed; retrying in %ss", RESTART_DELAY_SECONDS)
            await asyncio.sleep(RESTART_DELAY_SECONDS)
