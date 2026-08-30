"""Portfolio endpoints: read the account, execute a market order.

Both handlers are ``def``, not ``async def``, on purpose. ``sqlite3`` blocks,
and Starlette runs sync handlers on its threadpool — so the event loop keeps
serving the SSE stream while a trade waits on the write lock (D21). Declaring
them ``async`` would put a blocking call directly on the loop and stall every
connected client for the duration.

The status-code mapping lives here and only here. Services raise domain errors
so that the chat orchestrator can call the same functions and turn the same
rejection into a chat message rather than an HTTP response (D5).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..services import portfolio, snapshots
from ..services.tickers import TICKER_PATTERN, InvalidTicker

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Whitespace is stripped *before* the pattern runs, so `" aapl "` normalises
# rather than 422-ing — the design's rule for the watchlist, applied here too.
# The pattern is shared with the watchlist and with the services, so the three
# cannot drift apart (services/tickers.py).
Ticker = Annotated[str, StringConstraints(strip_whitespace=True, pattern=TICKER_PATTERN)]


class TradeRequest(BaseModel):
    """The wire shape of a trade.

    ``allow_inf_nan=False`` is load-bearing: ``float("nan")`` passes ``gt=0``
    silently (every comparison against NaN is False, so no bound rejects it) and
    would reach the service, where ``quantity * price`` poisons cash with NaN
    permanently. This turns it into a 422 at the boundary.

    The ticker pattern is the design's watchlist format guard
    (``^[A-Z.\\-]{1,10}$``) relaxed to accept either case, because the service
    normalises. It is the injection-surface guard as much as a UX one, and this
    endpoint needs it more than the watchlist does: from CP9 onward the ticker
    can arrive from model output rather than from a form.
    """

    # pydantic-core's Rust regex engine has no look-around, and the shared
    # pattern needs one to require at least one letter. Duplicating the rule
    # look-around-free is how the two copies start disagreeing.
    model_config = ConfigDict(regex_engine="python-re")

    ticker: Ticker
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, allow_inf_nan=False)


@router.get("")
def read_portfolio(request: Request) -> portfolio.PortfolioView:
    """Cash, positions, market value and unrealised P&L at current cache prices."""
    return portfolio.get_portfolio(request.app.state.settings.db_path, request.app.state.cache)


@router.get("/history")
def read_history(
    request: Request, limit: int = Query(default=snapshots.DEFAULT_HISTORY_LIMIT, ge=1, le=5000)
) -> list[dict[str, float | str]]:
    """Total portfolio value over time, oldest first — the P&L chart's data."""
    return snapshots.read_history(request.app.state.settings.db_path, limit)


@router.post("/trade")
def execute_trade(payload: TradeRequest, request: Request) -> portfolio.TradeResult:
    """Fill a market order, or refuse it and write nothing."""
    order = portfolio.TradeOrder(ticker=payload.ticker, side=payload.side, quantity=payload.quantity)
    try:
        return portfolio.execute_trade(request.app.state.settings.db_path, request.app.state.cache, order)
    except InvalidTicker as exc:
        # Reachable only when the service rule is stricter than this endpoint's
        # model. Mapped anyway: the chat orchestrator shares this service and
        # its input never passes through TradeRequest at all (D5).
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except portfolio.InvalidQuantity as exc:
        # 422, per the design's edge-case table. Reachable only when the
        # service rule is stricter than TradeRequest — but the service is
        # what the chat path crosses, so both must agree.
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except portfolio.PriceUnavailable as exc:
        # 409, not 400: the request is well-formed and will succeed once the
        # producer has quoted this ticker, which is usually the next tick.
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    except portfolio.TradeError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc
