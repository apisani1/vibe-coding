"""Check B1 — every row of the design's trading edge-case table.

Two properties here are the ones that make a paper-trading account either
trustworthy or quietly wrong, and both are asserted against state rather than
against a status code: **a rejected trade writes nothing at all**, and
**portfolio totals are derived from the cache** rather than from a stored price
column (D1).
"""

from __future__ import annotations

import threading
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from finally_app.api.portfolio import TradeRequest
from finally_app.config import Settings
from finally_app.db.connection import read_connection
from finally_app.db.init import ensure_initialized
from finally_app.market.cache import PriceCache
from finally_app.services import portfolio
from finally_app.services.tickers import InvalidTicker

PRICES = {"AAPL": 190.0, "MSFT": 400.0}
STARTING_CASH = 10000.0


@pytest.fixture
def db(settings: Settings) -> Path:
    """An initialised database — $10,000 cash, ten watchlist tickers, no positions."""
    ensure_initialized(settings.db_path)
    return settings.db_path


@pytest.fixture
def cache() -> PriceCache:
    """A cache with prices for the two tickers these tests trade."""
    priced = PriceCache()
    priced.apply(PRICES)
    return priced


@pytest.fixture
def account(app: FastAPI, db: Path) -> FastAPI:  # pylint: disable=unused-argument
    """The application, wired to the initialised database, with prices available."""
    app.state.cache.apply(PRICES)
    return app


async def _post(app: FastAPI, path: str, payload: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=payload)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def _row_counts(db_path: Path) -> dict[str, int]:
    """Row counts for every table a trade can touch."""
    with read_connection(db_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("trades", "positions", "portfolio_snapshots")
        }


def _cash(db_path: Path) -> float:
    with read_connection(db_path) as connection:
        return float(connection.execute("SELECT cash_balance FROM users_profile").fetchone()["cash_balance"])


def _buy(db_path: Path, cache: PriceCache, ticker: str, quantity: float) -> portfolio.TradeResult:
    return portfolio.execute_trade(db_path, cache, portfolio.TradeOrder(ticker, "buy", quantity))


def _sell(db_path: Path, cache: PriceCache, ticker: str, quantity: float) -> portfolio.TradeResult:
    return portfolio.execute_trade(db_path, cache, portfolio.TradeOrder(ticker, "sell", quantity))


# --- the happy path -------------------------------------------------------


def test_a_buy_moves_cash_position_and_trade_log_together(db: Path, cache: PriceCache) -> None:
    result = _buy(db, cache, "AAPL", 10)

    assert result["price"] == 190.0
    assert result["total"] == 1900.0
    assert result["cash_balance"] == STARTING_CASH - 1900.0
    assert result["position_quantity"] == 10.0
    assert _cash(db) == STARTING_CASH - 1900.0
    assert _row_counts(db) == {"trades": 1, "positions": 1, "portfolio_snapshots": 1}


class TickingCache(PriceCache):
    """A cache whose price moves on every read — a 500 ms tick, compressed.

    Against a static cache, "read the price once" and "read it three times" are
    indistinguishable, so a test using one proves nothing about D1. Every read
    here returns a visibly different value and is counted per ticker.
    """

    def __init__(self, prices: dict[str, list[float]]) -> None:
        super().__init__()
        self.apply({ticker: values[0] for ticker, values in prices.items()})
        self._remaining = {ticker: list(values) for ticker, values in prices.items()}
        self.reads: dict[str, int] = {}

    def price_of(self, ticker: str) -> float | None:
        symbol = ticker.upper()
        self.reads[symbol] = self.reads.get(symbol, 0) + 1
        remaining = self._remaining.get(symbol)
        return remaining.pop(0) if remaining else None


def test_the_traded_ticker_is_priced_exactly_once(db: Path) -> None:
    """D1: one cache read for the traded ticker, and that value does everything.

    Per ticker, not in total — the snapshot legitimately prices every *other*
    open position, so a total-reads assertion would hold only for a
    single-position portfolio and would fail correct code the moment a second
    position existed. What must never happen is the traded ticker being read
    again: the fill would then disagree with the check that permitted it, and the
    trade log would record a price nobody validated. The values below are 15%
    apart so an extra read shows up in the assertions, not in the rounding.
    """
    ticking = TickingCache({"AAPL": [190.0, 220.0, 250.0], "MSFT": [400.0, 460.0]})
    _buy(db, ticking, "MSFT", 1)  # a second position, so the snapshot has work to do
    ticking.reads.clear()

    result = _buy(db, ticking, "AAPL", 3)

    with read_connection(db) as connection:
        logged = connection.execute("SELECT price, quantity FROM trades WHERE ticker = 'AAPL'").fetchone()

    assert ticking.reads["AAPL"] == 1, f"AAPL was priced {ticking.reads['AAPL']} times; D1 allows exactly one"
    # 190.0 is AAPL's *first* value: the MSFT trade above draws only from MSFT's
    # queue, so a second read here would surface as 220.0 in one of these three.
    assert logged["price"] == result["price"] == 190.0
    assert result["cash_balance"] == _cash(db)


def test_the_ticker_is_normalised_before_it_reaches_a_row(db: Path, cache: PriceCache) -> None:
    """Two spellings of one symbol must be one position, not two.

    Untested until the overseer broke it at CP6 review: dropping `.strip().upper()`
    left the whole suite green while `aapl` and `AAPL` accumulated as separate
    rows — a holding you can see but not sell. The service normalises rather than
    the API model because from CP9 the chat orchestrator calls this function
    directly (D5), with a ticker that came out of a language model.
    """
    _buy(db, cache, " aapl ", 2)
    _buy(db, cache, "AAPL", 3)

    with read_connection(db) as connection:
        rows = connection.execute("SELECT ticker, quantity FROM positions").fetchall()
        logged = connection.execute("SELECT DISTINCT ticker FROM trades").fetchall()

    assert [(row["ticker"], row["quantity"]) for row in rows] == [("AAPL", 5.0)]
    assert [row["ticker"] for row in logged] == ["AAPL"]


def test_the_service_refuses_a_malformed_ticker_without_the_api_model(db: Path, cache: PriceCache) -> None:
    """The guard that matters on the CP9 path.

    `TradeRequest` is a boundary guard the chat orchestrator never passes
    through — it calls `execute_trade` directly (D5). So the format rule has to
    hold in the service, or model output is unvalidated on the one path where it
    is least trustworthy.
    """
    before = _row_counts(db)

    with pytest.raises(InvalidTicker):
        _buy(db, cache, "...", 1)
    with pytest.raises(InvalidTicker):
        _buy(db, cache, "AAPL'; DROP TABLE positions;--", 1)

    assert _row_counts(db) == before


@pytest.mark.asyncio
async def test_a_lowercase_ticker_is_accepted_over_http(account: FastAPI, db: Path) -> None:
    """Normalisation, not rejection: the format guard runs after stripping."""
    response = await _post(account, "/api/portfolio/trade", {"ticker": " aapl ", "side": "buy", "quantity": 1})

    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AA PL", "ABCDEFGHIJK", "AAPL'; DROP TABLE positions;--", ""])
async def test_a_malformed_ticker_is_a_422(account: FastAPI, ticker: str) -> None:
    """The injection-surface guard, and it matters more here than on the
    watchlist: from CP9 this field is fed by model output, not by a form."""
    response = await _post(account, "/api/portfolio/trade", {"ticker": ticker, "side": "buy", "quantity": 1})

    assert response.status_code == 422


def test_a_sell_returns_cash_and_leaves_avg_cost_alone(db: Path, cache: PriceCache) -> None:
    _buy(db, cache, "AAPL", 10)
    cache.apply({"AAPL": 200.0})

    result = _sell(db, cache, "AAPL", 4)

    assert result["price"] == 200.0
    assert result["position_quantity"] == 6.0
    # The sale realises P&L; it does not change what the remaining shares cost.
    assert result["position_avg_cost"] == 190.0


# --- the edge-case table --------------------------------------------------


@pytest.mark.asyncio
async def test_insufficient_cash_is_a_400_that_writes_nothing(account: FastAPI, db: Path) -> None:
    """The load-bearing rejection: a refused trade must leave the account untouched."""
    before = _row_counts(db)

    response = await _post(account, "/api/portfolio/trade", {"ticker": "AAPL", "side": "buy", "quantity": 1000})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "need" in detail and "have" in detail
    assert "190,000.00" in detail and "10,000.00" in detail
    assert _row_counts(db) == before
    assert _cash(db) == STARTING_CASH


@pytest.mark.asyncio
async def test_overselling_is_a_400_naming_the_held_quantity(account: FastAPI, db: Path) -> None:
    _buy(db, account.state.cache, "AAPL", 5)
    before = _row_counts(db)

    response = await _post(account, "/api/portfolio/trade", {"ticker": "AAPL", "side": "sell", "quantity": 9})

    assert response.status_code == 400
    assert "5" in response.json()["detail"]
    assert _row_counts(db) == before


@pytest.mark.asyncio
async def test_selling_with_no_position_is_a_400_not_a_404(account: FastAPI) -> None:
    """The request is invalid; the resource is not missing. A 404 would send the
    frontend down its "route not found" path instead of showing the reason."""
    response = await _post(account, "/api/portfolio/trade", {"ticker": "MSFT", "side": "sell", "quantity": 1})

    assert response.status_code == 400
    assert "MSFT" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [0, -5])
async def test_non_positive_quantity_is_a_422_at_the_boundary(account: FastAPI, quantity: float) -> None:
    response = await _post(account, "/api/portfolio/trade", {"ticker": "AAPL", "side": "buy", "quantity": quantity})

    assert response.status_code == 422


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinite_quantities_are_rejected_by_the_model(quantity: float) -> None:
    """Asserted on the model, not over HTTP, because that is what discriminates.

    ``gt=0`` does not reject NaN — every comparison against NaN is False, so no
    bound rejects it — and an HTTP test would pass on the JSON parser refusing
    the literal instead. Only ``allow_inf_nan=False`` stops NaN reaching the
    service, where ``quantity * price`` poisons cash permanently.
    """
    with pytest.raises(ValidationError):
        TradeRequest(ticker="AAPL", side="buy", quantity=quantity)


@pytest.mark.parametrize("quantity", [-5.0, 0.0, float("nan"), float("inf"), float("-inf")])
def test_the_service_refuses_a_bad_quantity_without_the_api_model(
    db: Path, cache: PriceCache, quantity: float
) -> None:
    """The blocker the overseer found at CP9 review, guarded where it belongs.

    `TradeRequest` carries `gt=0, allow_inf_nan=False`, and the chat orchestrator
    never constructs one (D5). While the rule lived only at the REST boundary, a
    model-authored `-5` came back **filled** and *credited* cash 10,000 -> 10,950,
    `0` raised ZeroDivisionError, and NaN reached SQLite as a genuine HTTP 500.

    Both checks in `_valid_quantity` are needed and neither is redundant: every
    comparison against NaN is False, so a `quantity <= 0` test *alone* waves NaN
    straight through. Their **order** does not matter — reversing them leaves the
    suite green, which an earlier version of this docstring got wrong.
    """
    before = _row_counts(db)

    with pytest.raises(portfolio.InvalidQuantity):
        _buy(db, cache, "AAPL", quantity)

    assert _row_counts(db) == before
    assert _cash(db) == STARTING_CASH, "a refused quantity moved cash"


def test_a_negative_quantity_cannot_credit_cash(db: Path, cache: PriceCache) -> None:
    """Stated separately because this is the one with a dollar value on it.

    `price * -5` is negative, so `cash - gross` *adds* $950. The model would have
    been minting money, and the trade log would have recorded it as a normal buy.
    """
    with pytest.raises(portfolio.InvalidQuantity):
        _buy(db, cache, "AAPL", -5.0)

    assert _cash(db) == STARTING_CASH


@pytest.mark.asyncio
async def test_an_unpriced_ticker_is_a_409(account: FastAPI, db: Path) -> None:
    """Honest during the first tick after a ticker is added. Filling at an
    invented price would corrupt the portfolio permanently."""
    before = _row_counts(db)

    response = await _post(account, "/api/portfolio/trade", {"ticker": "PYPL", "side": "buy", "quantity": 1})

    assert response.status_code == 409
    assert "PYPL" in response.json()["detail"]
    assert _row_counts(db) == before


def test_an_exact_full_sell_deletes_the_row(db: Path, cache: PriceCache) -> None:
    _buy(db, cache, "AAPL", 10)

    result = _sell(db, cache, "AAPL", 10)

    assert result["position_quantity"] == 0.0
    assert _row_counts(db)["positions"] == 0


def test_a_fractional_full_sell_leaves_no_ghost_position(db: Path, cache: PriceCache) -> None:
    """0.3 sold in thirds leaves ~5.5e-17 shares. Written back, that renders as a
    holding of 0.00 shares that can never be sold away."""
    _buy(db, cache, "AAPL", 0.3)
    for _ in range(3):
        _sell(db, cache, "AAPL", 0.1)

    with read_connection(db) as connection:
        rows = connection.execute("SELECT quantity FROM positions").fetchall()

    assert not rows, f"a residual position survived: {[row['quantity'] for row in rows]}"


def test_weighted_average_cost_across_three_unequal_lots(db: Path, cache: PriceCache) -> None:
    """Using the latest fill price instead would show unrealised P&L of ~0 after
    every buy, which is the most flattering possible lie."""
    cache.apply({"AAPL": 100.0})
    _buy(db, cache, "AAPL", 10)  # 1000 over 10
    cache.apply({"AAPL": 130.0})
    _buy(db, cache, "AAPL", 5)  # 650 over 5
    cache.apply({"AAPL": 160.0})
    result = _buy(db, cache, "AAPL", 1)  # 160 over 1

    # (1000 + 650 + 160) / 16 = 113.125
    assert result["position_quantity"] == 16.0
    assert result["position_avg_cost"] == 113.125


def test_a_partial_sell_does_not_rewrite_avg_cost(db: Path, cache: PriceCache) -> None:
    cache.apply({"AAPL": 100.0})
    _buy(db, cache, "AAPL", 10)
    cache.apply({"AAPL": 250.0})

    _sell(db, cache, "AAPL", 3)

    with read_connection(db) as connection:
        row = connection.execute("SELECT quantity, avg_cost FROM positions").fetchone()

    assert row["quantity"] == 7.0
    assert row["avg_cost"] == 100.0


# --- derived values (the value half of D1) --------------------------------


def test_portfolio_totals_reconcile_against_the_cache(db: Path, cache: PriceCache) -> None:
    """`total_value == cash + Σ(quantity × cached_price)`.

    This is what proves the totals come from the cache and not from a stored
    price: moving the cache alone must move the total.
    """
    _buy(db, cache, "AAPL", 10)  # at 190
    _buy(db, cache, "MSFT", 2)  # at 400

    cache.apply({"AAPL": 200.0, "MSFT": 380.0})
    view = portfolio.get_portfolio(db, cache)

    expected_positions = 10 * 200.0 + 2 * 380.0
    assert view["positions_value"] == expected_positions
    assert view["total_value"] == view["cash_balance"] + expected_positions
    assert view["cash_balance"] == STARTING_CASH - 1900.0 - 800.0


def test_unrealized_pnl_follows_the_cache_price(db: Path, cache: PriceCache) -> None:
    _buy(db, cache, "AAPL", 10)  # cost basis 1900

    cache.apply({"AAPL": 209.0})
    view = portfolio.get_portfolio(db, cache)
    position = view["positions"][0]

    assert position["current_price"] == 209.0
    assert position["unrealized_pnl"] == 190.0
    assert position["unrealized_pnl_percent"] == 10.0
    assert view["unrealized_pnl"] == 190.0


def test_a_position_with_no_quote_is_carried_at_cost_and_says_so(db: Path, cache: PriceCache) -> None:
    """Dropping it from the total would render as a cliff on the P&L chart. The
    null price is the disclosure; the cost basis is the valuation."""
    _buy(db, cache, "AAPL", 10)
    empty = PriceCache()

    view = portfolio.get_portfolio(db, empty)
    position = view["positions"][0]

    assert position["current_price"] is None
    assert position["market_value"] == 1900.0
    assert position["unrealized_pnl"] == 0.0
    assert view["total_value"] == view["cash_balance"] + 1900.0


@pytest.mark.asyncio
async def test_the_portfolio_endpoint_serves_the_same_view(account: FastAPI, db: Path) -> None:
    _buy(db, account.state.cache, "AAPL", 4)

    response = await _get(account, "/api/portfolio")

    assert response.status_code == 200
    body = response.json()
    assert body["cash_balance"] == STARTING_CASH - 760.0
    assert [p["ticker"] for p in body["positions"]] == ["AAPL"]
    assert body["total_value"] == body["cash_balance"] + body["positions_value"]


@pytest.mark.asyncio
async def test_an_empty_portfolio_is_all_cash(account: FastAPI) -> None:
    response = await _get(account, "/api/portfolio")

    body = response.json()
    assert body["positions"] == []
    assert body["positions_value"] == 0.0
    assert body["total_value"] == STARTING_CASH


# --- snapshot-on-trade (the CP8 half that belongs to the transaction) -----


def test_each_fill_writes_exactly_one_snapshot_and_each_rejection_writes_none(db: Path, cache: PriceCache) -> None:
    _buy(db, cache, "AAPL", 1)
    _buy(db, cache, "AAPL", 1)
    with pytest.raises(portfolio.InsufficientCash):
        _buy(db, cache, "AAPL", 10_000)

    with read_connection(db) as connection:
        rows = connection.execute("SELECT total_value FROM portfolio_snapshots ORDER BY recorded_at").fetchall()

    assert len(rows) == 2
    # Cash after two 190-dollar buys plus two shares marked at 190.
    assert rows[-1]["total_value"] == STARTING_CASH


def test_the_snapshot_records_the_post_trade_total(db: Path, cache: PriceCache) -> None:
    """Written inside the trade's transaction, so it can never record a total
    that mixes one trade's cash with another's positions."""
    cache.apply({"AAPL": 100.0})
    _buy(db, cache, "AAPL", 20)

    with read_connection(db) as connection:
        total = connection.execute("SELECT total_value FROM portfolio_snapshots").fetchone()["total_value"]

    assert total == STARTING_CASH  # 8000 cash + 20 shares at 100


# --- layering (check B6, asserted rather than grepped) --------------------


def test_the_services_package_imports_no_web_framework() -> None:
    """B6 as a test, so it runs in CI without the grep.

    A service that raises ``HTTPException`` cannot be called by the chat
    orchestrator without inventing a translation layer, and D5's "one validation
    path" property erodes from there.
    """
    import ast
    import importlib
    import inspect
    import pkgutil

    import finally_app.services as services_package

    offending: list[str] = []
    for module_info in pkgutil.iter_modules(services_package.__path__):
        module = importlib.import_module(f"finally_app.services.{module_info.name}")
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offending += [f"{module_info.name}: {a.name}" for a in node.names if a.name.split(".")[0] == "fastapi"]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "fastapi":
                offending.append(f"{module_info.name}: from {node.module}")

    assert not offending, f"services/ imports a web framework {offending}"


def test_a_side_that_is_neither_buy_nor_sell_is_refused_at_the_service(db: Path, cache: PriceCache) -> None:
    """The last boundary-only rule, closed.

    `side` was guarded solely by a `Literal` in `api/portfolio.TradeRequest` and
    `llm/schema.TradeAction` — models the assistant never constructs. `_settle`
    has a `buy` branch and an `else`, so any other value would have been executed
    as a **sell**. Same shape as the `quantity: -5` defect that shipped once.
    """
    for side in ("short", "BUY", "", "sel"):
        with pytest.raises(portfolio.InvalidSide):
            portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", side, 1))  # type: ignore[arg-type]

    # And the two real sides still work.
    assert portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 1))["side"] == "buy"
    assert portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "sell", 1))["side"] == "sell"


def test_the_account_total_is_read_from_one_snapshot(
    db: Path, cache: PriceCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cash and positions must come from the same instant.

    They were two statements on a connection with no transaction, so a trade
    committing between them returned a total that never existed — the review
    reproduced 8,100.00 where the truth was 10,000.00.

    **The window is forced, not hoped for.** The first version of this test ran
    a reader and a seller against a `threading.Barrier` twenty times and passed
    with the fix reverted: at the mark, cash and position value move by equal and
    opposite amounts, so a torn read is invisible unless the tear lands between
    the two statements *in the right order*. That is CP8's lesson again — buying
    at the mark leaves the total unchanged — and it made the check unable to
    fail. Here the sale is committed **while the reader sits between its two
    reads**, which is the only arrangement that can show the difference.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))
    truth = portfolio.get_portfolio(db, cache)["total_value"]

    real_cash = portfolio._read_cash_balance  # pylint: disable=protected-access
    sold = threading.Event()

    def read_cash_then_let_a_sale_land(connection: object, user_id: str) -> float:
        value = real_cash(connection, user_id)  # type: ignore[arg-type]
        if not sold.is_set():
            sold.set()
            seller = threading.Thread(
                target=portfolio.execute_trade,
                args=(db, cache, portfolio.TradeOrder("AAPL", "sell", 10)),
            )
            seller.start()
            seller.join()
        return value

    monkeypatch.setattr(portfolio, "_read_cash_balance", read_cash_then_let_a_sale_land)

    total = portfolio.get_portfolio(db, cache)["total_value"]

    assert total == pytest.approx(truth, abs=0.01), (
        f"read a total that never existed: {total} (the account was worth {truth} before the sale "
        f"and the same after it, because the sale filled at the mark)"
    )


def test_a_dust_buy_is_refused_and_writes_nothing(db: Path, cache: PriceCache) -> None:
    """B9: a fill with no counterpart and no cash movement.

    `_valid_quantity` passes `1e-12` — it is finite and positive, which is all
    that rule was ever asked to check. What it cannot see is state:
    `_write_position` deletes any position at or below `DUST_TOLERANCE`, so the
    trade appended a row to the immutable log, moved cash by
    `round(190.0 * 1e-12, 4)` = `0.0`, and then deleted the position it had just
    created.

    Asserted against the tables rather than against the return value, because
    the return value was always plausible: it reported a fill, and a fill is
    what the log said had happened.
    """
    with pytest.raises(portfolio.DustQuantity) as refused:
        portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 1e-12))

    assert "too small" in refused.value.reason

    with read_connection(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 0
        cash = connection.execute("SELECT cash_balance FROM users_profile").fetchone()["cash_balance"]
    assert cash == STARTING_CASH


def test_a_dust_buy_on_top_of_a_real_position_is_still_allowed(db: Path, cache: PriceCache) -> None:
    """The other side of the rule, or it would be a quantity check in disguise.

    The rejection is about the **resulting position**, not about the order size:
    adding `1e-12` to ten held shares leaves ten shares, which is a real
    position, so it fills. Without this the guard could be silently narrowed to
    "reject small orders" and nothing would notice.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))

    result = portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 1e-12))

    assert result["position_quantity"] == pytest.approx(10.0)
