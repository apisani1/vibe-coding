"""The single background task that writes the price cache.

Exactly one writer, many readers (D2). The task re-reads its ticker universe
from SQLite every iteration rather than being signalled on watchlist change:
that is one trivial query against a ten-row table, and it means a newly added
ticker is priced within one tick with no cross-task coordination at all (D3).

The universe is **watchlist ∪ open positions**. A position in a ticker you have
removed from the watchlist still needs a price, or its market value silently
freezes and total portfolio value goes quietly wrong.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..db.connection import read_connection
from ..db.init import DEFAULT_USER_ID
from .cache import PriceCache
from .source import MarketDataSource

logger = logging.getLogger(__name__)

RESTART_DELAY_SECONDS = 2.0

_UNIVERSE_SQL = """
    SELECT ticker FROM watchlist WHERE user_id = ?
    UNION
    SELECT ticker FROM positions WHERE user_id = ? AND quantity > 0
"""


def read_universe(db_path: Path, user_id: str = DEFAULT_USER_ID) -> list[str]:
    """Every ticker that needs a price right now. Blocking; call via to_thread.

    Uses the shared connection helper rather than a raw ``sqlite3.connect``, so
    the WAL / busy_timeout / row_factory policy lives in exactly one place.
    """
    with read_connection(db_path) as connection:
        rows = connection.execute(_UNIVERSE_SQL, (user_id, user_id)).fetchall()
    return sorted(row["ticker"] for row in rows)


async def _tick(db_path: Path, source: MarketDataSource, cache: PriceCache) -> None:
    """One production cycle: read the universe, fetch, fold into the cache."""
    tickers = await asyncio.to_thread(read_universe, db_path)
    if not tickers:
        return
    prices = await source.fetch(tickers)
    if prices:
        cache.apply(prices)


async def run_producer(db_path: Path, source: MarketDataSource, cache: PriceCache) -> None:
    """Drive the source forever, surviving its failures.

    An unhandled exception in a background task dies silently and leaves the
    app looking alive with frozen prices — indistinguishable from a quiet
    market, which is the worst way for this to fail. So the loop logs and
    restarts instead. Any occurrence during a verify run is a finding, not
    noise.
    """
    while True:
        try:
            await _tick(db_path, source, cache)
            await asyncio.sleep(source.interval_seconds)
        except asyncio.CancelledError:
            logger.info("price producer stopping")
            raise
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("price producer failed; restarting in %ss", RESTART_DELAY_SECONDS)
            await asyncio.sleep(RESTART_DELAY_SECONDS)
