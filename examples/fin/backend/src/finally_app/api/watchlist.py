"""Watchlist endpoints: list, add, remove.

Sync handlers for the same reason as the portfolio routes — ``sqlite3`` blocks,
and Starlette runs ``def`` handlers on its threadpool (D21).

The status codes carry meaning the frontend acts on, and two of them are easy to
get wrong: a duplicate add is **200**, not 409, because re-adding what you
already watch is a no-op rather than a conflict; and removing a symbol that is
not on the list is **404**, because here the resource genuinely is missing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from ..services import watchlist
from ..services.tickers import TICKER_PATTERN, InvalidTicker

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Whitespace is stripped before the pattern runs, so `" aapl "` normalises
# rather than 422-ing. The pattern itself lives in services/tickers.py — the
# chat orchestrator bypasses this model entirely (D5), so the service is where
# the rule is actually enforced.
Ticker = Annotated[str, StringConstraints(strip_whitespace=True, pattern=TICKER_PATTERN)]


class AddTickerRequest(BaseModel):
    """The wire shape of an add."""

    # python-re rather than the default Rust engine: the shared pattern uses
    # look-ahead to require at least one letter. See api/portfolio.py.
    model_config = ConfigDict(regex_engine="python-re")

    ticker: Ticker


@router.get("")
def read_watchlist(request: Request) -> list[watchlist.WatchlistEntry]:
    """Watched symbols with their current quotes, oldest first."""
    return watchlist.list_watchlist(request.app.state.settings.db_path, request.app.state.cache)


@router.post("")
def add_ticker(payload: AddTickerRequest, request: Request) -> watchlist.WatchlistEntry:
    """Add a symbol. Idempotent: a duplicate returns the existing entry with 200."""
    try:
        return watchlist.add_ticker(request.app.state.settings.db_path, request.app.state.cache, payload.ticker)
    except InvalidTicker as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc


@router.delete("/{ticker}", status_code=204)
def remove_ticker(ticker: str, request: Request) -> Response:
    """Remove a symbol. Any open position in it survives and stays priced (D3)."""
    try:
        watchlist.remove_ticker(request.app.state.settings.db_path, ticker)
    except InvalidTicker as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except watchlist.NotWatched as exc:
        raise HTTPException(status_code=404, detail=exc.reason) from exc
    return Response(status_code=204)
