"""The watchlist: which symbols the user wants priced and shown.

Two rules here are load-bearing and both are checks (B3).

**Adding is idempotent.** Re-adding a symbol you already watch is not an error;
it is a no-op that returns the existing row. Enforced by catching the UNIQUE
violation rather than by SELECT-then-INSERT, because those are two steps a
concurrent caller can interleave and the constraint already states the rule
exactly.

**Removing is not deleting a position.** The producer's universe is
watchlist ∪ open positions (D3), so a ticker you still hold keeps being priced
after you stop watching it. Removing it must not freeze that position's market
value — which would silently corrupt total portfolio value while the UI looks
fine.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypedDict

from ..db.connection import read_connection, transaction
from ..db.init import DEFAULT_USER_ID, new_id, utc_now
from ..market.cache import PriceCache
from ..market.source import Quote
from .tickers import normalise


class NotWatched(LookupError):
    """Removal of a symbol that is not on the list.

    Here the resource genuinely is missing, so this maps to 404 — unlike a sell
    with no position, which is a 400 because the *request* is what is wrong.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self.reason = f"{ticker} is not on the watchlist"
        super().__init__(self.reason)


class WatchlistEntry(TypedDict):
    """A watched symbol and its current quote, if it has one yet."""

    ticker: str
    added_at: str
    quote: Quote | None


def _entry(row: sqlite3.Row, cache: PriceCache) -> WatchlistEntry:
    """Join a stored row against the live cache.

    The whole quote travels rather than a pre-computed change percentage: the
    SSE stream already sends these six fields and the frontend already derives
    change % from ``session_open`` (D19). Computing it here as well would give
    the same number two implementations to disagree about.
    """
    ticker = str(row["ticker"])
    return WatchlistEntry(ticker=ticker, added_at=str(row["added_at"]), quote=cache.get(ticker))


def list_watchlist(db_path: Path, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> list[WatchlistEntry]:
    """Every watched symbol, oldest first, each with its quote or ``None``.

    ``None`` means "not priced yet" and must render as an em dash rather than as
    zero — during the first tick after an add, and permanently for a symbol the
    real market source does not recognise.
    """
    with read_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker",
            (user_id,),
        ).fetchall()
    return [_entry(row, cache) for row in rows]


def add_ticker(db_path: Path, cache: PriceCache, ticker: str, user_id: str = DEFAULT_USER_ID) -> WatchlistEntry:
    """Add a symbol, or return the existing entry unchanged. Raises ``InvalidTicker``.

    The returned quote is almost always ``None`` on a fresh add: the producer
    re-reads its universe on the next tick (D3), so a price appears within one
    interval rather than immediately.
    """
    symbol = normalise(ticker)

    with transaction(db_path) as connection:
        # OR IGNORE, not a prior existence check: the UNIQUE constraint is the
        # rule, and checking first leaves a window for a concurrent add.
        connection.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), user_id, symbol, utc_now()),
        )
        row = connection.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, symbol),
        ).fetchone()

    return _entry(row, cache)


def remove_ticker(db_path: Path, ticker: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Remove a symbol. Raises ``InvalidTicker`` or ``NotWatched``.

    An open position in the removed symbol is deliberately untouched: you stop
    watching it, you do not sell it, and the producer keeps pricing it because
    its universe is the union (D3).
    """
    symbol = normalise(ticker)

    with transaction(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, symbol),
        )
        if cursor.rowcount == 0:
            raise NotWatched(symbol)
