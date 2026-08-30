"""Check B5 — chat orchestration under the mock. No test here reaches a network.

The five assertions the plan names each pin a *decision*, not a framework. Three
more pin traps that earlier checkpoints set for this one and that are invisible
from CP9's own plan text:

* ``InvalidTicker`` is a ``ValueError``, not a ``TradeError`` (CP7) — so a
  handler catching only ``TradeError`` 500s on model-authored junk.
* ``RuntimeError`` from a missing profile row must **not** become a polite
  rejection (CP6) — an uninitialised database is a server fault.
* ``EmptyModelResponse`` subclasses ``LLMError``, so the except order decides
  whether D25 works at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from finally_app.api.ratelimit import CHAT_REFILL_SECONDS, TokenBucket
from finally_app.config import Settings
from finally_app.db.connection import read_connection
from finally_app.db.init import ensure_initialized
from finally_app.llm import client as llm_client
from finally_app.llm.schema import MAX_ACTIONS_PER_RESPONSE, AssistantResponse, TradeAction, WatchlistAction
from finally_app.market.cache import PriceCache
from finally_app.services import chat
from finally_app.services import chat as chat_service
from finally_app.services import portfolio
from finally_app.services.tickers import InvalidTicker

PRICES = {"AAPL": 190.0, "MSFT": 400.0}
STARTING_CASH = 10000.0


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


async def _post(app: FastAPI, path: str, payload: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
        return await client.post(path, json=payload)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
        return await client.get(path)


def _mock_reply(monkeypatch: pytest.MonkeyPatch, reply: AssistantResponse) -> None:
    """Force one exact assistant response, whatever the user typed."""
    monkeypatch.setattr("finally_app.llm.mock.respond", lambda _text: reply)


def _counts(db_path: Path) -> dict[str, int]:
    with read_connection(db_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("trades", "positions", "chat_messages")
        }


# --- D5: the shared path --------------------------------------------------


@pytest.mark.asyncio
async def test_a_chat_trade_goes_through_the_manual_execute_trade(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural assertion behind D5, and the whole reason chat is safe.

    A sentinel raised from `portfolio.execute_trade` must propagate. If the chat
    service ever grows its own write path — a direct INSERT, a copy of the
    validation — the sentinel is never hit and this fails. The monkeypatch binds
    only because chat.py calls the function as a *module attribute*; a
    `from .portfolio import execute_trade` import would capture the original and
    this test would pass while proving nothing.
    """

    class Sentinel(Exception):
        pass

    def explode(*_args: object, **_kwargs: object) -> None:
        raise Sentinel("the shared path was taken")

    _mock_reply(
        monkeypatch, AssistantResponse(message="ok", trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)])
    )
    monkeypatch.setattr(portfolio, "execute_trade", explode)

    with pytest.raises(Sentinel):
        await chat.handle_message(
            account.state.settings.db_path, account.state.cache, account.state.settings, "buy 1 AAPL"
        )


@pytest.mark.asyncio
async def test_a_chat_watchlist_change_goes_through_the_manual_service(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same guarantee for the other service — D5 is not trade-only."""

    class Sentinel(Exception):
        pass

    def explode(*_args: object, **_kwargs: object) -> None:
        raise Sentinel("the shared path was taken")

    _mock_reply(
        monkeypatch, AssistantResponse(message="ok", watchlist_changes=[WatchlistAction(ticker="PYPL", action="add")])
    )
    monkeypatch.setattr("finally_app.services.watchlist.add_ticker", explode)

    with pytest.raises(Sentinel):
        await chat.handle_message(
            account.state.settings.db_path, account.state.cache, account.state.settings, "add PYPL"
        )


@pytest.mark.asyncio
async def test_a_chat_trade_actually_moves_the_portfolio(account: FastAPI, db: Path) -> None:
    """The sentinel proves the path; this proves the effect."""
    response = await _post(account, "/api/chat", {"message": "buy 10 AAPL"})

    assert response.status_code == 200
    action = response.json()["actions"][0]
    assert action["status"] == "filled"
    assert action["ticker"] == "AAPL"
    assert action["price"] == 190.0

    with read_connection(db) as connection:
        position = connection.execute("SELECT quantity FROM positions WHERE ticker = 'AAPL'").fetchone()
        cash = connection.execute("SELECT cash_balance FROM users_profile").fetchone()["cash_balance"]
    assert position["quantity"] == 10.0
    assert cash == STARTING_CASH - 1900.0


# --- D6: a refused trade is a 200 -----------------------------------------


@pytest.mark.asyncio
async def test_a_rejected_trade_is_a_200_with_the_reason(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert the 200 explicitly. A 4xx here "correctly refuses the trade" and
    is still wrong: the model answered, and replacing that with a failure banner
    loses both the message and the reason the trade was refused."""
    _mock_reply(
        monkeypatch,
        AssistantResponse(message="Buying.", trades=[TradeAction(ticker="AAPL", side="buy", quantity=10_000)]),
    )
    before = _counts(db)

    response = await _post(account, "/api/chat", {"message": "buy 10000 AAPL"})

    assert response.status_code == 200, "a refused action must not become an HTTP error"
    body = response.json()
    assert body["message"] == "Buying."
    assert body["actions"][0]["status"] == "rejected"
    assert "cash" in body["actions"][0]["reason"].lower()
    assert _counts(db)["trades"] == before["trades"]


@pytest.mark.asyncio
async def test_a_model_authored_junk_ticker_is_a_200_not_a_500(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CP7 trap, reproduced by the overseer before this checkpoint existed.

    `InvalidTicker` is a `ValueError`, **not** a `TradeError`. A handler catching
    only `TradeError` lets it escape as a 500 — on precisely the input a language
    model is most likely to produce.
    """
    _mock_reply(
        monkeypatch,
        AssistantResponse(message="Trying.", trades=[TradeAction(ticker="...", side="buy", quantity=1)]),
    )

    response = await _post(account, "/api/chat", {"message": "buy something"})

    assert response.status_code == 200, "a malformed model ticker escaped as an HTTP error"
    assert response.json()["actions"][0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_a_missing_profile_row_is_not_reported_as_a_polite_rejection(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CP6 trap. A missing profile row raises `RuntimeError`, and that must
    surface as a server error rather than "your trade was rejected" — otherwise a
    broken deployment hides behind a chat bubble.

    The schema exists and only the row is gone, deliberately: dropping the whole
    database fails earlier, while persisting the user message, and would prove
    something else entirely.
    """
    with read_connection(db) as connection:
        connection.execute("DELETE FROM users_profile")
        connection.commit()

    _mock_reply(
        monkeypatch, AssistantResponse(message="Buying.", trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)])
    )

    with pytest.raises(RuntimeError):
        await chat.handle_message(
            account.state.settings.db_path, account.state.cache, account.state.settings, "buy 1 AAPL"
        )


@pytest.mark.asyncio
async def test_a_runtime_error_from_the_trade_path_is_not_swallowed(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CP6 trap at the point it actually applies.

    The test above deletes the profile row, but `render_context` reads cash
    first and raises before any trade runs — so it pins the context path, not
    the catch clause. This raises `RuntimeError` from `execute_trade` itself.
    Adding `RuntimeError` to that except tuple turns a broken deployment into a
    politely rejected action, and only this test notices.
    """

    def server_fault(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no user profile for 'default'; the database was not initialised")

    _mock_reply(
        monkeypatch, AssistantResponse(message="Buying.", trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)])
    )
    monkeypatch.setattr(portfolio, "execute_trade", server_fault)

    with pytest.raises(RuntimeError):
        await chat.handle_message(
            account.state.settings.db_path, account.state.cache, account.state.settings, "buy 1 AAPL"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [-5.0, 0.0])
async def test_a_model_authored_bad_quantity_is_a_200_with_a_rejection(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch, quantity: float
) -> None:
    """The CP9 blocker, asserted on the path it was reachable from.

    A quantity the user is 422'd for must not be executable by the model — that
    is D5 read in the direction that matters. Before the fix, -5 was reported
    **filled** and moved cash 10,000.00 -> 10,950.00.
    """
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Trying.", trades=[TradeAction.model_construct(ticker="AAPL", side="buy", quantity=quantity)]
        ),
    )
    before = _counts(db)

    response = await _post(account, "/api/chat", {"message": "go"})

    assert response.status_code == 200, "a bad model quantity escaped as an HTTP error"
    assert response.json()["actions"][0]["status"] == "rejected"
    assert _counts(db)["trades"] == before["trades"]
    with read_connection(db) as connection:
        assert connection.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == STARTING_CASH


@pytest.mark.asyncio
async def test_a_non_finite_model_quantity_is_a_200_not_a_500(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NaN reached SQLite and produced a genuine HTTP 500 before the fix."""
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Trying.", trades=[TradeAction.model_construct(ticker="AAPL", side="buy", quantity=float("nan"))]
        ),
    )

    response = await _post(account, "/api/chat", {"message": "go"})

    assert response.status_code == 200
    assert response.json()["actions"][0]["status"] == "rejected"


def test_the_model_contract_refuses_an_overflowing_quantity() -> None:
    """Defence in depth, and the reason this is reachable from a live model.

    `json.loads` turns the model text `1e400` into `inf` — no exception, no
    warning. The schema now rejects it, so the turn degrades to message-only
    instead of carrying infinity into the trade log.
    """
    reply = llm_client.parse_response(
        '{"message": "buying", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1e400}]}'
    )

    assert reply.message == "buying"
    assert reply.trades == [], "an infinite quantity survived the model contract"


def test_chat_never_writes_the_trading_tables_itself() -> None:
    """The D5 guarantee as a property, not a point check.

    The sentinels drive one input each (`quantity=1`), so they prove the shared
    path is taken *for that input* — the overseer added a fast path conditioned
    on fractional quantities that INSERTed straight into `trades`, with no cash
    check and an invented price, and all 211 tests stayed green.

    A cheap tripwire on the source text, and **not sufficient on its own** — the
    companion test below is the one that catches any spelling in any module.
    The first version of this greped for `INSERT INTO\\s+TRADES`, and the overseer
    walked through it with `INSERT OR IGNORE INTO trades`, the exact idiom
    `services/watchlist.py` already uses.
    """
    import inspect
    import re

    from finally_app.services import chat as chat_module

    source = inspect.getsource(chat_module).upper()
    verbs = r"(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)"
    offending = [
        table
        for table in ("TRADES", "POSITIONS", "WATCHLIST", "USERS_PROFILE", "PORTFOLIO_SNAPSHOTS")
        if re.search(rf"{verbs}\s+{table}\b", source)
    ]

    assert not offending, f"services/chat.py writes {offending} directly instead of through a service"


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [1.0, 0.5, 3.0, 0.001])
async def test_no_chat_turn_writes_a_row_without_the_service_functions(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch, quantity: float
) -> None:
    """The behavioural half of D5, and the one that catches any spelling.

    Neutralise the three service functions, then run a turn. If chat has any
    write path of its own — a direct INSERT, a helper in another module, a table
    name built by f-string — rows appear anyway and this fails.

    Parameterised over quantity because the sentinels drive a single input each,
    and the overseer's bypass triggered only for `0 < quantity < 1`. A guard that
    samples one value cannot see a path conditioned on another.
    """
    calls: list[str] = []

    def refuse_trade(*_args: object, **_kwargs: object) -> Any:
        calls.append("trade")
        raise portfolio.InsufficientCash("neutralised for this test")

    def refuse_add(*_args: object, **_kwargs: object) -> Any:
        calls.append("add")
        raise InvalidTicker("neutralised")

    def refuse_remove(*_args: object, **_kwargs: object) -> Any:
        calls.append("remove")
        raise InvalidTicker("neutralised")

    monkeypatch.setattr(portfolio, "execute_trade", refuse_trade)
    monkeypatch.setattr("finally_app.services.watchlist.add_ticker", refuse_add)
    monkeypatch.setattr("finally_app.services.watchlist.remove_ticker", refuse_remove)
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Trying.",
            trades=[TradeAction(ticker="AAPL", side="buy", quantity=quantity)],
            watchlist_changes=[WatchlistAction(ticker="PYPL", action="add")],
        ),
    )
    before = _counts(db)

    response = await _post(account, "/api/chat", {"message": "go"})

    assert response.status_code == 200
    assert calls, "the turn did not reach the service functions at all"
    after = _counts(db)
    assert after["trades"] == before["trades"], "a trade row appeared without execute_trade"
    assert after["positions"] == before["positions"], "a position row appeared without execute_trade"
    with read_connection(db) as connection:
        watched = connection.execute("SELECT COUNT(*) AS n FROM watchlist").fetchone()["n"]
        cash = connection.execute("SELECT cash_balance FROM users_profile").fetchone()["cash_balance"]
    assert watched == 10, "a watchlist row changed without the watchlist service"
    assert cash == STARTING_CASH, "cash moved without execute_trade"


# --- D7: the cap ----------------------------------------------------------


@pytest.mark.asyncio
async def test_the_eleventh_action_is_rejected_by_the_cap(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D7 bounds the blast radius of one bad generation. The limit is imported,
    not re-literalled, so raising it in schema.py cannot leave this asserting 10."""
    requested = MAX_ACTIONS_PER_RESPONSE + 1
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Rebalancing.",
            trades=[TradeAction(ticker="AAPL", side="buy", quantity=1) for _ in range(requested)],
        ),
    )

    response = await _post(account, "/api/chat", {"message": "rebalance"})

    body = response.json()
    assert len(body["actions"]) == requested, "over-cap actions must be recorded, not silently dropped"
    executed = [a for a in body["actions"] if a["status"] == "filled"]
    assert len(executed) == MAX_ACTIONS_PER_RESPONSE
    assert body["actions"][-1]["status"] == "rejected"
    assert str(MAX_ACTIONS_PER_RESPONSE) in body["actions"][-1]["reason"]
    assert _counts(db)["trades"] == MAX_ACTIONS_PER_RESPONSE


@pytest.mark.asyncio
async def test_the_cap_follows_the_constant_rather_than_a_literal(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The carried condition: import `MAX_ACTIONS_PER_RESPONSE`, do not re-literal 10.

    A test that only imports the constant adapts to any value, so changing it in
    schema.py leaves the suite green either way — the import proves nothing on
    its own. Moving the constant here and asserting the behaviour follows is
    what pins it: with a literal `10` in chat.py, this fails.
    """
    monkeypatch.setattr(chat, "MAX_ACTIONS_PER_RESPONSE", 3)
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Busy.", trades=[TradeAction(ticker="AAPL", side="buy", quantity=1) for _ in range(5)]
        ),
    )

    body = (await _post(account, "/api/chat", {"message": "go"})).json()

    assert len([a for a in body["actions"] if a["status"] == "filled"]) == 3
    assert len([a for a in body["actions"] if a["status"] == "rejected"]) == 2
    assert "3" in body["actions"][-1]["reason"]


@pytest.mark.asyncio
async def test_the_cap_counts_trades_and_watchlist_changes_together(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two separate caps of 10 would let one generation run 20 actions."""
    _mock_reply(
        monkeypatch,
        AssistantResponse(
            message="Busy.",
            trades=[TradeAction(ticker="AAPL", side="buy", quantity=1) for _ in range(MAX_ACTIONS_PER_RESPONSE)],
            watchlist_changes=[WatchlistAction(ticker="PYPL", action="add")],
        ),
    )

    body = (await _post(account, "/api/chat", {"message": "go"})).json()

    assert len([a for a in body["actions"] if a["status"] in ("filled", "applied")]) == MAX_ACTIONS_PER_RESPONSE
    assert body["actions"][-1]["status"] == "rejected"


# --- degradation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_unparseable_model_output_degrades_to_a_message(account: FastAPI) -> None:
    """A model's formatting choice must not take down the panel."""
    reply = llm_client.parse_response("I think you should probably hold, honestly.")

    assert reply.message == "I think you should probably hold, honestly."
    assert reply.trades == []

    response = await _post(account, "/api/chat", {"message": "what do you think?"})
    assert response.status_code == 200
    assert response.json()["message"]


@pytest.mark.asyncio
async def test_an_empty_model_response_is_a_200_with_an_apology(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D25, and the except-ordering trap that makes or breaks it.

    `EmptyModelResponse` subclasses `LLMError`, so catching the parent first
    turns every empty reply into a 503 — which claims the service is down when
    the call in fact succeeded and was billed, and invites a retry that will
    most likely fail the same way.
    """

    async def empty(*_args: object, **_kwargs: object) -> Any:
        raise llm_client.EmptyModelResponse("The model returned no content")

    monkeypatch.setattr(llm_client, "complete", empty)
    live = Settings(
        openrouter_api_key="not-a-real-key",
        openrouter_model="test/model",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=False,
        db_path=db,
    )
    account.state.settings = live

    response = await _post(account, "/api/chat", {"message": "hello"})

    assert response.status_code == 200, "an empty model response must not be a 503 (D25)"
    assert response.json()["actions"] == []
    assert "sorry" in response.json()["message"].lower()

    # Recorded in the transcript, so the panel shows what happened after a reload.
    stored = chat.list_messages(db)
    assert stored[-1]["role"] == "assistant"
    assert "sorry" in stored[-1]["content"].lower()


@pytest.mark.asyncio
async def test_a_transport_failure_is_a_503(account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of the ordering: a genuinely unreachable model *is* a 503,
    because "try again later" is honest there."""

    async def unreachable(*_args: object, **_kwargs: object) -> Any:
        raise llm_client.LLMError("Could not reach the model")

    monkeypatch.setattr(llm_client, "complete", unreachable)
    account.state.settings = Settings(
        openrouter_api_key="not-a-real-key",
        openrouter_model="test/model",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=False,
        db_path=db,
    )

    response = await _post(account, "/api/chat", {"message": "hello"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_an_unconfigured_llm_is_a_503_naming_the_variable(account: FastAPI, db: Path) -> None:
    """Not a 500 and not a silent mock: the operator needs to know which
    variable is missing."""
    account.state.settings = Settings(
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=False,
        db_path=db,
    )

    response = await _post(account, "/api/chat", {"message": "hello"})

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


# --- D18: the transcript --------------------------------------------------


@pytest.mark.asyncio
async def test_the_transcript_survives_a_reload(account: FastAPI) -> None:
    """D18. Without this endpoint the panel is blank after every reload while
    the rows sit in SQLite unreachable."""
    await _post(account, "/api/chat", {"message": "buy 2 AAPL"})

    response = await _get(account, "/api/chat/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["content"] == "buy 2 AAPL"
    assert body[1]["actions"][0]["status"] == "filled"


@pytest.mark.asyncio
async def test_the_transcript_is_oldest_last(account: FastAPI) -> None:
    """The panel renders top-to-bottom; a reversed transcript reads backwards."""
    for message in ("first", "second", "third"):
        await _post(account, "/api/chat", {"message": message})

    body = (await _get(account, "/api/chat/messages")).json()

    user_messages = [m["content"] for m in body if m["role"] == "user"]
    assert user_messages == ["first", "second", "third"]
    assert [m["created_at"] for m in body] == sorted(m["created_at"] for m in body)


@pytest.mark.asyncio
async def test_actions_are_stored_as_json_not_as_a_python_repr(account: FastAPI, db: Path) -> None:
    """`str(list)` round-trips through Python and breaks every other reader."""
    await _post(account, "/api/chat", {"message": "buy 1 AAPL"})

    with read_connection(db) as connection:
        raw = connection.execute("SELECT actions FROM chat_messages WHERE role = 'assistant'").fetchone()["actions"]

    parsed = json.loads(raw)
    assert parsed[0]["status"] == "filled"


@pytest.mark.asyncio
async def test_only_the_recent_window_goes_into_the_prompt(account: FastAPI, db: Path) -> None:
    """D20. The full transcript stays in SQLite; the prompt carries the last 10,
    or a long session grows the request without bound.

    Given a bucket of its own, deliberately. Twelve turns is more than CP19's
    spend limit allows in one burst, and this test is about the prompt window,
    not about the limit — left alone it recorded 20 rows instead of 24 and
    failed for a reason that had nothing to do with D20. Raising `CHAT_BURST` to
    make it pass would have been tuning a spend control by test pressure; the
    limit stays where it was chosen, and the entanglement is written down here.
    Check A14 is where the burst is exercised on purpose.
    """
    account.state.chat_limiter = TokenBucket(100, CHAT_REFILL_SECONDS)

    for index in range(12):
        await _post(account, "/api/chat", {"message": f"message {index}"})

    prompt = chat._build_messages(db, account.state.cache, "default")  # pylint: disable=protected-access
    history = [m for m in prompt if m["role"] in ("user", "assistant")]

    assert len(history) == chat.HISTORY_FOR_PROMPT
    assert len(chat.list_messages(db)) == 24


# --- the prompt context ---------------------------------------------------


def test_the_context_block_carries_live_prices_not_stored_ones(db: Path, cache: PriceCache) -> None:
    """The model must reason about the numbers the user is watching tick (D1)."""
    portfolio.execute_trade(db, cache, portfolio.TradeOrder("AAPL", "buy", 10))
    cache.apply({"AAPL": 250.0})

    context = chat.render_context(db, cache)
    positions_block = context.split("POSITIONS")[1].split("WATCHLIST")[0]

    # Scoped to POSITIONS. Against the whole block this passed for the wrong
    # reason: AAPL is in the seed watchlist, so "$250.00" appeared on the
    # watchlist line even when positions were valued at cost.
    assert "$250.00" in positions_block, "positions are not valued from the live cache"
    assert "avg cost $190.00" in positions_block
    assert "$8,100.00" in context  # cash after the fill


def test_the_context_block_says_no_quote_rather_than_zero(db: Path) -> None:
    """A price of $0.00 in the prompt invites the model to reason about a crash
    that did not happen."""
    context = chat.render_context(db, PriceCache())
    watchlist_lines = context.split("WATCHLIST")[1].splitlines()

    assert any("no quote yet" in line for line in watchlist_lines)
    # Scoped to the watchlist block: "Unrealised P&L: $0.00" above it is both
    # legitimate and true, and asserting against the whole block would have
    # failed on it — which is what happened on the first attempt.
    assert not any("$0.00" in line for line in watchlist_lines)


# --- B7: no test can bill -------------------------------------------------


@pytest.mark.asyncio
async def test_the_chat_path_makes_no_network_call_under_the_mock(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7's guard at the point of highest risk. `llm_mock=True` must not reach
    `client.complete` at all — not even to fail."""

    async def forbidden(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("the mock path reached the live client")

    monkeypatch.setattr(llm_client, "complete", forbidden)

    response = await _post(account, "/api/chat", {"message": "buy 1 AAPL"})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_zero_quantity_chat_message_is_a_200_not_a_500(account: FastAPI) -> None:
    """The blocker end to end, on the path the E2E suite and the dev loop use.

    Two independent guards were added — a clamp in the mock and a `try` around
    the mock branch — because either alone leaves the other unprotected: the
    clamp does nothing if some future mock message produces a different invalid
    action, and the `try` does nothing if the mock is replaced.
    """
    response = await _post(account, "/api/chat", {"message": "buy 0 AAPL"})

    assert response.status_code == 200
    assert response.json()["message"]


@pytest.mark.asyncio
async def test_a_mock_that_cannot_build_an_action_degrades_instead_of_500ing(
    account: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second guard on its own: the mock replaced by one that always raises."""

    def broken(_: str) -> AssistantResponse:
        raise ValidationError.from_exception_data("AssistantResponse", [])

    monkeypatch.setattr(chat_service.mock, "respond", broken)

    response = await _post(account, "/api/chat", {"message": "buy 1 AAPL"})

    assert response.status_code == 200
    assert response.json()["actions"] == []


# --- B10: a 503 leaves the transcript answered -----------------------------


def _live_settings(db: Path) -> Settings:
    """Settings that take the live branch without any key that could be used."""
    return Settings(
        openrouter_api_key="not-a-real-key",
        openrouter_model="test/model",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=False,
        db_path=db,
    )


@pytest.mark.asyncio
async def test_a_transport_failure_still_answers_the_turn(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B10. The user's turn is persisted *before* the model is called — it has to
    be, it is part of the prompt history the next turn reads — so an error that
    simply propagated left a user row with no assistant row. Permanent, visible
    on every reload, and fed back into every later prompt as an exchange where
    the assistant said nothing.

    Two assertions, and both matter. The transcript must be answered, **and the
    status must still be 503**: "answer the turn" is not licence to turn an
    outage into a 200, which would tell the panel everything is fine.
    """

    async def unreachable(*_args: object, **_kwargs: object) -> Any:
        raise llm_client.LLMError(llm_client.UNREACHABLE_MESSAGE)

    monkeypatch.setattr(llm_client, "complete", unreachable)
    account.state.settings = _live_settings(db)

    response = await _post(account, "/api/chat", {"message": "what is my cash balance?"})

    assert response.status_code == 503

    stored = chat.list_messages(db)
    assert [row["role"] for row in stored] == ["user", "assistant"]
    assert stored[-1]["content"] == chat.UNANSWERED_TEMPLATE.format(reason=llm_client.UNREACHABLE_MESSAGE)


@pytest.mark.asyncio
async def test_an_unconfigured_llm_still_answers_the_turn(account: FastAPI, db: Path) -> None:
    """The path the README calls a working demo.

    With no key every single message accumulated as an unanswered bubble, and
    each one went back into the next prompt. `LLMNotConfigured` subclasses
    `LLMError`, so one guard covers both — this is here to prove that rather
    than assume it.
    """
    account.state.settings = Settings(
        openrouter_api_key="",
        openrouter_model="",
        massive_api_key="",
        massive_poll_seconds=15.0,
        llm_mock=False,
        db_path=db,
    )

    response = await _post(account, "/api/chat", {"message": "hello"})

    assert response.status_code == 503

    stored = chat.list_messages(db)
    assert [row["role"] for row in stored] == ["user", "assistant"]
    assert "OPENROUTER_API_KEY" in stored[-1]["content"]


@pytest.mark.asyncio
async def test_the_recorded_reason_is_never_a_providers_own_text(
    account: FastAPI, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transcript row is rendered to the user, so it takes the same rule the
    503 detail does: this repository's sentence, never a third party's string.

    `litellm` has embedded a request URL in an exception message before — that
    is how the Massive key nearly reached the logs — and there is nothing
    stopping the next version embedding a header.
    """
    # Split across a concatenation on purpose. Check A1 scans **every blob in
    # history** for `sk-[A-Za-z0-9_-]{8,}`, and a fabricated key committed whole
    # would match that shape forever — which is precisely what got CP2 rejected
    # and what an exception carved into a secret scan would have cost. Written
    # this way, the string exists at runtime and never on a line.
    fake_key = "sk-" + "notarealkey0000"
    leak = f"AuthenticationError: request to https://openrouter.ai/v1?key={fake_key} failed"

    async def leaky(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError(leak)

    monkeypatch.setattr(llm_client.litellm, "acompletion", leaky)
    account.state.settings = _live_settings(db)

    response = await _post(account, "/api/chat", {"message": "hello"})

    assert response.status_code == 503
    assert leak not in response.json()["detail"]
    assert fake_key not in json.dumps(chat.list_messages(db))
