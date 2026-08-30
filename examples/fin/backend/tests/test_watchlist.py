"""Check B3 — the watchlist rules.

The load-bearing one is the last section: **removing a ticker you hold must not
stop it being priced.** That is the D3 corruption path, and it is asserted
against the producer's own universe query rather than against a status code,
because a 204 says nothing about whether the position silently froze.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finally_app.config import Settings
from finally_app.db.connection import read_connection
from finally_app.db.init import DEFAULT_TICKERS, ensure_initialized
from finally_app.market.cache import PriceCache
from finally_app.market.producer import read_universe
from finally_app.services import portfolio, watchlist
from finally_app.services.tickers import InvalidTicker, normalise

PRICES = {"AAPL": 190.0, "MSFT": 400.0}


@pytest.fixture
def db(settings: Settings) -> Path:
    ensure_initialized(settings.db_path)
    return settings.db_path


@pytest.fixture
def cache() -> PriceCache:
    priced = PriceCache()
    priced.apply(PRICES)
    return priced


@pytest.fixture
def account(app: FastAPI, db: Path) -> FastAPI:  # pylint: disable=unused-argument
    app.state.cache.apply(PRICES)
    return app


async def _request(app: FastAPI, method: str, path: str, payload: object | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=payload)


def _stored(db_path: Path) -> list[str]:
    with read_connection(db_path) as connection:
        return [row["ticker"] for row in connection.execute("SELECT ticker FROM watchlist ORDER BY ticker")]


# --- normalisation and the format rule ------------------------------------


@pytest.mark.parametrize("raw", [" aapl ", "AAPL", "aapl", "AaPl", "\taapl\n"])
def test_every_spelling_normalises_to_one_symbol(raw: str) -> None:
    assert normalise(raw) == "AAPL"


@pytest.mark.parametrize("raw", ["AA PL", "ABCDEFGHIJK", "", "   ", "AAPL1", "AAPL'; DROP TABLE watchlist;--"])
def test_a_malformed_symbol_is_refused_by_the_service(raw: str) -> None:
    """The service, not just the boundary: the chat orchestrator calls these
    functions directly and never builds a Pydantic model (D5)."""
    with pytest.raises(InvalidTicker):
        normalise(raw)


@pytest.mark.parametrize("raw", ["...", "---", ".", "-.-"])
def test_an_all_punctuation_symbol_is_refused(raw: str) -> None:
    """The CP6 condition. `^[A-Z.\\-]{1,10}$` accepts these, and the simulator
    seeds a price for any unknown symbol — so admitting one to the watchlist
    would make punctuation tradeable."""
    with pytest.raises(InvalidTicker):
        normalise(raw)


@pytest.mark.parametrize("raw", ["BRK.B", "RDS-A"])
def test_dots_and_dashes_are_still_accepted(raw: str) -> None:
    """Real symbols use both. The letter requirement must not cost us these."""
    assert normalise(raw) == raw


# --- add ------------------------------------------------------------------


def test_adding_a_duplicate_is_a_no_op_not_an_error(db: Path, cache: PriceCache) -> None:
    before = _stored(db)

    first = watchlist.add_ticker(db, cache, "AAPL")
    second = watchlist.add_ticker(db, cache, "aapl")

    assert _stored(db) == before, "a duplicate add changed the watchlist"
    assert first["added_at"] == second["added_at"], "the duplicate add rewrote the original row"


@pytest.mark.asyncio
async def test_a_duplicate_add_returns_200_not_500(account: FastAPI) -> None:
    """AAPL is in the seed watchlist, so this is a duplicate on a fresh database.
    A UNIQUE violation escaping as a 500 is the default behaviour here."""
    response = await _request(account, "POST", "/api/watchlist", {"ticker": "AAPL"})

    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_a_lowercase_add_is_stored_uppercase(account: FastAPI, db: Path) -> None:
    response = await _request(account, "POST", "/api/watchlist", {"ticker": " pypl "})

    assert response.status_code == 200
    assert response.json()["ticker"] == "PYPL"
    assert "PYPL" in _stored(db)
    assert "pypl" not in _stored(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AA PL", "ABCDEFGHIJK", "...", "", "AAPL\nX"])
async def test_a_malformed_add_is_a_422(account: FastAPI, db: Path, ticker: str) -> None:
    before = _stored(db)

    response = await _request(account, "POST", "/api/watchlist", {"ticker": ticker})

    assert response.status_code == 422
    assert _stored(db) == before


def test_a_never_priced_ticker_has_no_quote_yet(db: Path, cache: PriceCache) -> None:
    """`None`, not zero. The producer re-reads its universe next tick (D3), so a
    price arrives within one interval — the UI must render an em dash until then.

    *Never priced*, not merely *newly added*: the distinction is the next test.
    """
    entry = watchlist.add_ticker(db, cache, "PYPL")

    assert entry["quote"] is None


def test_re_adding_a_removed_ticker_returns_its_stale_quote(db: Path, cache: PriceCache) -> None:
    """Documents a real edge the overseer found, rather than asserting a wish.

    `PriceCache` never evicts, so removing a ticker and re-adding it hands back
    the pre-removal quote immediately instead of `None`. Under the simulator that
    is stale for one tick; under Massive, a symbol the provider does not
    recognise never refreshes at all, and the run-wide condition forbids building
    a staleness indicator on `timestamp`.

    Pinned here so CP11/CP12 treat the REST entry as a seed and the SSE stream as
    the authority — not so the behaviour is endorsed.
    """
    watchlist.remove_ticker(db, "AAPL")

    entry = watchlist.add_ticker(db, cache, "AAPL")

    assert entry["quote"] is not None
    assert entry["quote"]["price"] == 190.0


# --- list -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_list_carries_the_whole_quote(account: FastAPI) -> None:
    """Not a pre-computed change percentage: the SSE stream already sends these
    six fields and the frontend already derives change % from session_open (D19).
    Computing it here too gives one number two implementations."""
    response = await _request(account, "GET", "/api/watchlist")

    assert response.status_code == 200
    body = response.json()
    assert {entry["ticker"] for entry in body} == set(DEFAULT_TICKERS)

    aapl = next(entry for entry in body if entry["ticker"] == "AAPL")
    assert set(aapl["quote"]) == {"ticker", "price", "previous_price", "session_open", "timestamp", "direction"}
    unpriced = next(entry for entry in body if entry["ticker"] == "NVDA")
    assert unpriced["quote"] is None


# --- remove ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_removing_a_watched_ticker_is_a_204(account: FastAPI, db: Path) -> None:
    response = await _request(account, "DELETE", "/api/watchlist/AAPL")

    assert response.status_code == 204
    assert "AAPL" not in _stored(db)


@pytest.mark.asyncio
async def test_removing_a_ticker_not_on_the_list_is_a_404(account: FastAPI) -> None:
    """Here the resource genuinely is missing — unlike a sell with no position,
    which is a 400 because the request is what is wrong."""
    response = await _request(account, "DELETE", "/api/watchlist/PYPL")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_lowercase_removal_finds_the_stored_row(account: FastAPI, db: Path) -> None:
    response = await _request(account, "DELETE", "/api/watchlist/aapl")

    assert response.status_code == 204
    assert "AAPL" not in _stored(db)


@pytest.mark.asyncio
async def test_a_malformed_removal_is_a_422_not_a_404(account: FastAPI) -> None:
    """A 404 would say "no such ticker", which invites a retry with the same junk."""
    response = await _request(account, "DELETE", "/api/watchlist/...")

    assert response.status_code == 422


def test_removing_a_held_ticker_leaves_the_position_priced(db: Path, cache: PriceCache) -> None:
    """The D3 corruption path, asserted against the producer's own query.

    You stop watching it; you do not sell it. If the producer stopped pricing
    the position, its market value would freeze at whatever the cache last held
    and total portfolio value would go quietly wrong — with nothing on screen to
    say so, because the row simply disappears from the watchlist as requested.
    """
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 5))

    watchlist.remove_ticker(db, "AAPL")

    assert "AAPL" not in _stored(db)
    with read_connection(db) as connection:
        held = connection.execute("SELECT quantity FROM positions WHERE ticker = 'AAPL'").fetchone()
    assert held is not None and held["quantity"] == 5.0
    assert "AAPL" in read_universe(db), "the producer stopped pricing a ticker the user still holds"


def test_a_removed_ticker_with_no_position_leaves_the_universe(db: Path, cache: PriceCache) -> None:
    """The other half: the union must actually shrink when nothing holds it open,
    or 'removed' would mean nothing and the universe would only ever grow."""
    watchlist.add_ticker(db, cache, "PYPL")
    assert "PYPL" in read_universe(db)

    watchlist.remove_ticker(db, "PYPL")

    assert "PYPL" not in read_universe(db)


def test_removing_a_ticker_never_touches_a_position_row(db: Path, cache: PriceCache) -> None:
    """Explicit, because 'clean up the orphaned position' is a plausible-looking
    change that silently liquidates a holding."""
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 2))
    with read_connection(db) as connection:
        before = connection.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]

    watchlist.remove_ticker(db, "AAPL")

    with read_connection(db) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"] == before
        assert connection.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"] == 1
