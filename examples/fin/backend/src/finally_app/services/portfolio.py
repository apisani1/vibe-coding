"""Portfolio state: the only place money moves.

Two rules shape this module, and both are checks rather than style.

**No FastAPI here (B6).** Services raise domain errors; ``api/`` translates them
into status codes. The moment a service raises ``HTTPException`` the chat
orchestrator (D5) can no longer call it, and the "one validation path for manual
and AI trades" property starts eroding silently.

**One price read per trade (D1).** The cache price is read once, at the top of
the transaction, and the same value validates the trade, fills it, and is
written to the trade log. Re-reading it after validation lets a fill disagree
with the check that permitted it — the tick between them is 500 ms wide.

Everything a trade does — the position write, the trade-log append, the cash
update and the snapshot — happens inside one ``BEGIN IMMEDIATE`` transaction, so
a rejection leaves nothing behind and two concurrent buyers cannot spend the
same dollar (D21, exercised by check B2 with real threads).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from ..db.connection import read_transaction, transaction
from ..db.init import DEFAULT_USER_ID, new_id, utc_now
from ..market.cache import PriceCache
from .tickers import normalise

Side = Literal["buy", "sell"]

# Money is float (D8). These two constants are the whole defence: round before
# every write, and compare quantities with a tolerance so accumulated float dust
# cannot leave a phantom position of 1e-17 shares.
MONEY_PRECISION = 4
DUST_TOLERANCE = 1e-9


class TradeError(Exception):
    """A trade the service refused.

    ``reason`` is user-facing text: the REST layer returns it as ``detail`` and
    the chat orchestrator quotes it back as the rejection reason (D6). That
    shared use is why the message is built here and not at either boundary.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InsufficientCash(TradeError):
    """Buy priced above the available cash balance."""


class InsufficientShares(TradeError):
    """Sell larger than the held quantity."""


class NoPosition(TradeError):
    """Sell of a ticker with no open position."""


class PriceUnavailable(TradeError):
    """No cached quote yet — filling at an invented price would corrupt the portfolio."""


class InvalidSide(TradeError):
    """The order is neither a buy nor a sell."""


class DustQuantity(TradeError):
    """A buy so small that the resulting position would be rounded away.

    ``_valid_quantity`` lets ``1e-12`` through — it is finite and it is
    positive, which is everything that rule was ever asked to check. What it
    cannot see is *state*: ``_write_position`` deletes any position at or below
    ``DUST_TOLERANCE``, so the buy appended a row to the immutable trade log,
    moved cash by ``round(price * 1e-12, 4)`` — which is ``0.0`` — and then
    deleted the position it had just created. The log ended up holding a fill
    with no counterpart anywhere in the account.

    A ``TradeError`` rather than an ``InvalidQuantity``: the quantity is
    perfectly valid arithmetic, and what is wrong is what it would *do* here.
    That distinction is why the check lives in ``_settle``, beside the other
    state-dependent rejections, rather than beside the finiteness test.
    """


class InvalidQuantity(TradeError):
    """A quantity that is not a finite positive number.

    This lives in the service, not only in ``api/``'s Pydantic model, because
    the chat orchestrator never constructs that model (D5). While the rule lived
    only at the REST boundary, a model-authored ``quantity: -5`` **filled and
    credited cash** — the sign flowed straight through ``price * quantity`` into
    the cash update — and ``NaN`` reached SQLite as a genuine 500. Reachable from
    live output too: ``json.loads`` turns the model text ``1e400`` into ``inf``.

    A ``TradeError``, so the chat path reports it as a rejected action with a
    reason (D6) rather than raising.
    """


@dataclass(frozen=True)
class TradeOrder:
    """What to trade. Market orders only, so there is nothing else to carry."""

    ticker: str
    side: Side
    quantity: float


class PositionView(TypedDict):
    """A position joined against the live cache. Nothing here is stored (D1)."""

    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class PortfolioView(TypedDict):
    """The whole account, valued at the current cache prices."""

    cash_balance: float
    positions: list[PositionView]
    positions_value: float
    total_value: float
    unrealized_pnl: float


class TradeResult(TypedDict):
    """What a filled trade did, at the price it actually filled at."""

    trade_id: str
    ticker: str
    side: Side
    quantity: float
    price: float
    total: float
    cash_balance: float
    position_quantity: float
    position_avg_cost: float
    executed_at: str


def _money(value: float) -> float:
    """Round to the stored precision. Applied before every write, never after a read."""
    return round(value, MONEY_PRECISION)


def _read_cash_balance(connection: sqlite3.Connection, user_id: str) -> float:
    """The current cash balance.

    A missing profile row means the database was never initialised, which is a
    server fault rather than a rejected trade — hence not a ``TradeError``.
    """
    row = connection.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"no user profile for {user_id!r}; the database was not initialised")
    return float(row["cash_balance"])


def _read_position(connection: sqlite3.Connection, ticker: str, user_id: str) -> sqlite3.Row | None:
    """The open position in one ticker, or None."""
    row: sqlite3.Row | None = connection.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return row


def _read_positions(connection: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    """Every open position, ordered so the response is stable between reads."""
    return connection.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()


def _value_position(row: sqlite3.Row, price: float | None) -> PositionView:
    """Value one stored position at a resolved price.

    The price arrives as an argument rather than being fetched here, so a caller
    that has already read the cache (a trade, mid-transaction) values the
    position at the same instant it filled at, instead of at whatever the
    producer wrote since.
    """
    ticker = str(row["ticker"])
    quantity = float(row["quantity"])
    avg_cost = float(row["avg_cost"])
    cost_basis = quantity * avg_cost

    if price is None:
        # No quote yet — the first tick after a ticker is added, or a source
        # that skipped the symbol. Carry the position at cost and disclose the
        # gap with a null price, rather than dropping it from the total: a
        # position that vanishes for one tick renders as a cliff on the P&L
        # chart, which is a worse lie than "we have no mark for this yet".
        return PositionView(
            ticker=ticker,
            quantity=quantity,
            avg_cost=avg_cost,
            current_price=None,
            market_value=_money(cost_basis),
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
        )

    market_value = _money(quantity * price)
    unrealized = _money(market_value - cost_basis)
    return PositionView(
        ticker=ticker,
        quantity=quantity,
        avg_cost=avg_cost,
        current_price=price,
        market_value=market_value,
        unrealized_pnl=unrealized,
        unrealized_pnl_percent=_money(unrealized / cost_basis * 100) if cost_basis else 0.0,
    )


def _positions_value(
    connection: sqlite3.Connection,
    cache: PriceCache,
    user_id: str,
    marks: dict[str, float],
) -> float:
    """Market value of every open position.

    ``marks`` pre-empts the cache for tickers whose price the caller has already
    read, so a trade's snapshot cannot mix the price it filled at with a newer
    one for the same ticker.
    """
    total = 0.0
    for row in _read_positions(connection, user_id):
        ticker = str(row["ticker"])
        # Not `marks.get(ticker, cache.price_of(ticker))`: that evaluates the
        # default eagerly and reads the cache even for a marked ticker, which is
        # the exact extra read this argument exists to avoid.
        price = marks[ticker] if ticker in marks else cache.price_of(ticker)
        total += _value_position(row, price)["market_value"]
    return _money(total)


def _write_position(
    connection: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str,
) -> None:
    """Upsert the position, deleting it once the remaining quantity is dust.

    Selling a fractional position leaves a residue like 5.5e-17 shares. Left in
    the table it shows in the UI as a holding of 0.00 shares that cannot be sold
    away, so the row goes rather than being written back at ~zero.
    """
    if quantity <= DUST_TOLERANCE:
        connection.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))
        return

    connection.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (new_id(), user_id, ticker, quantity, avg_cost, utc_now()),
    )


def _append_trade(connection: sqlite3.Connection, order: TradeOrder, price: float, user_id: str) -> tuple[str, str]:
    """Append to the immutable trade log. Returns (id, executed_at)."""
    trade_id, executed_at = new_id(), utc_now()
    connection.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade_id, user_id, order.ticker, order.side, order.quantity, price, executed_at),
    )
    return trade_id, executed_at


def _record_snapshot(
    connection: sqlite3.Connection,
    cache: PriceCache,
    cash_balance: float,
    user_id: str,
    marks: dict[str, float],
) -> float:
    """Record total portfolio value inside the trade's own transaction.

    Inside, not after: a snapshot written by a separate call could land between
    the position write and the cash write of the *next* trade and record a total
    that never existed.
    """
    total_value = _money(cash_balance + _positions_value(connection, cache, user_id, marks))
    connection.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (new_id(), user_id, total_value, utc_now()),
    )
    return total_value


def record_snapshot(db_path: Path, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> float:
    """Record one standalone snapshot of total portfolio value. Returns it.

    The periodic snapshot task (CP8) calls this; a trade records its own inside
    its transaction instead. It lives here rather than in ``snapshots.py`` so
    both paths share one definition of ``total_value`` — including the ratified
    rule that a position with no cached price is carried at cost. Two
    implementations of that number would diverge the moment either is edited.

    No ``marks``: a standalone snapshot has no fill price to pin, so every
    position is valued at whatever the cache holds right now.

    Cash is read inside the same transaction as the positions, so the total can
    never mix one trade's cash with another's holdings.
    """
    with transaction(db_path) as connection:
        return _record_snapshot(connection, cache, _read_cash_balance(connection, user_id), user_id, {})


def get_portfolio(db_path: Path, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> PortfolioView:
    """Cash, positions and every derived number, computed at read time (D1)."""
    with read_transaction(db_path) as connection:
        cash_balance = _read_cash_balance(connection, user_id)
        positions = [
            _value_position(row, cache.price_of(str(row["ticker"]))) for row in _read_positions(connection, user_id)
        ]

    positions_value = _money(sum(position["market_value"] for position in positions))
    return PortfolioView(
        cash_balance=cash_balance,
        positions=positions,
        positions_value=positions_value,
        total_value=_money(cash_balance + positions_value),
        unrealized_pnl=_money(sum(position["unrealized_pnl"] for position in positions)),
    )


@dataclass(frozen=True)
class _Settlement:
    """What a validated order does to the position and the cash balance."""

    quantity: float
    avg_cost: float
    cash_balance: float
    gross: float


def _settle(order: TradeOrder, price: float, position: sqlite3.Row | None, cash_balance: float) -> _Settlement:
    """Validate against current state and compute the resulting balances.

    Pure arithmetic and rejection: it reads no database and writes nothing, so
    every edge case in check B1's table can be exercised without a transaction.
    """
    held = float(position["quantity"]) if position is not None else 0.0
    avg_cost = float(position["avg_cost"]) if position is not None else 0.0
    gross = _money(price * order.quantity)

    if order.side == "buy":
        quantity = held + order.quantity
        # Before the cash check, and before anything is written: a dust buy
        # costs $0.00, so it passes every affordability test there is and would
        # otherwise reach the trade log.
        if quantity <= DUST_TOLERANCE:
            raise DustQuantity(
                f"Quantity too small: buying {order.quantity:g} {order.ticker} would leave no position at all"
            )
        if gross > cash_balance + DUST_TOLERANCE:
            raise InsufficientCash(f"Insufficient cash: need ${gross:,.2f}, have ${cash_balance:,.2f}")
        # Weighted average across every lot. Using the latest fill price instead
        # would make unrealised P&L read ~0 after every buy.
        return _Settlement(
            quantity=quantity,
            avg_cost=_money((held * avg_cost + order.quantity * price) / quantity),
            cash_balance=_money(cash_balance - gross),
            gross=gross,
        )

    if position is None:
        # 400, not 404: the request is invalid, the resource is not missing.
        raise NoPosition(f"No position in {order.ticker} to sell")
    if order.quantity > held + DUST_TOLERANCE:
        raise InsufficientShares(f"Insufficient shares: tried to sell {order.quantity:g}, hold {held:g}")
    return _Settlement(
        quantity=held - order.quantity,
        # A sale realises P&L; it does not change what the remaining shares cost.
        # Recomputing avg_cost here is the classic way to make a partial sell
        # silently rewrite the position's basis.
        avg_cost=avg_cost,
        cash_balance=_money(cash_balance + gross),
        gross=gross,
    )


def _valid_side(side: str) -> Side:
    """Reject anything that is not `buy` or `sell`.

    The last field whose only guard was a `Literal` in the API and LLM models —
    exactly the arrangement this module's own history says is not enough, since
    the assistant constructs neither. `_settle` has a `buy` branch and an
    `else`, so any other value would have executed as a **sell**. Unreachable
    through today's callers, and the same shape as the `quantity: -5` defect
    that did ship once.
    """
    # Returned as literals rather than as the argument, so the `Side` type is
    # something mypy proves rather than something the caller promises. The point
    # of the function is to hand back a value the rest of the module can trust,
    # not merely to raise.
    if side == "buy":
        return "buy"
    if side == "sell":
        return "sell"
    raise InvalidSide(f"Side must be 'buy' or 'sell', got {side!r}")


def _valid_quantity(quantity: float) -> float:
    """Reject anything that is not a finite positive number.

    The finiteness test is not redundant with the sign test: every comparison
    against ``NaN`` is False, so ``quantity <= 0`` **alone** waves NaN straight
    through to SQLite, where the trade log turns it into a 500.

    Both checks are needed; their order is **not** load-bearing. An earlier
    version of this docstring claimed it was, and the overseer disproved it by
    reversing the two lines and getting a green suite — NaN fails the sign test
    and is then caught by the finiteness test either way.
    """
    if not math.isfinite(quantity):
        raise InvalidQuantity(f"Quantity must be a finite number, got {quantity}")
    if quantity <= 0:
        raise InvalidQuantity(f"Quantity must be greater than zero, got {quantity:g}")
    return quantity


def execute_trade(
    db_path: Path,
    cache: PriceCache,
    order: TradeOrder,
    user_id: str = DEFAULT_USER_ID,
) -> TradeResult:
    """Validate and fill a market order, or raise ``TradeError`` and write nothing.

    This is the single write path for both the REST endpoint and the chat
    orchestrator (D5). Quantity has already been validated as a finite positive
    number at the API boundary; everything that depends on *state* is validated
    here, inside the transaction that will do the writing.
    """
    # Normalised once, here, so every message, query and stored row below uses
    # the same symbol — a lowercase request must not create a second position.
    # `normalise` also validates: the chat orchestrator reaches this function
    # without passing through any Pydantic model (D5), so the boundary guard in
    # api/ is not the guard that matters on the path model output takes.
    normalised = TradeOrder(
        ticker=normalise(order.ticker),
        side=_valid_side(order.side),
        quantity=_valid_quantity(order.quantity),
    )
    symbol = normalised.ticker

    with transaction(db_path) as connection:
        price = cache.price_of(symbol)
        if price is None:
            raise PriceUnavailable(f"No price available for {symbol} yet")

        cash_balance = _read_cash_balance(connection, user_id)
        settled = _settle(normalised, price, _read_position(connection, symbol, user_id), cash_balance)

        _write_position(connection, symbol, settled.quantity, settled.avg_cost, user_id)
        trade_id, executed_at = _append_trade(connection, normalised, price, user_id)
        connection.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (settled.cash_balance, user_id))
        # The traded ticker is marked at the price this trade filled at, so
        # the snapshot records one instant rather than a blend of two.
        _record_snapshot(connection, cache, settled.cash_balance, user_id, {symbol: price})

    remaining = settled.quantity if settled.quantity > DUST_TOLERANCE else 0.0
    return TradeResult(
        trade_id=trade_id,
        ticker=symbol,
        side=order.side,
        quantity=order.quantity,
        price=price,
        total=settled.gross,
        cash_balance=settled.cash_balance,
        position_quantity=remaining,
        position_avg_cost=settled.avg_cost if remaining else 0.0,
        executed_at=executed_at,
    )
