"""Chat orchestration: context → model → actions → transcript.

**The rule this module exists to honour is D5: AI actions run through the same
service functions as manual ones.** There is no privileged write path here.
Every trade goes through ``portfolio.execute_trade`` and every watchlist change
through ``watchlist.add_ticker`` / ``remove_ticker``, so a model asking for
something the user could not do themselves is refused by the same code that
would refuse the user — and the reason it gives is the same sentence.

Two consequences shape the error handling, and both were traps set by earlier
checkpoints rather than anything visible here:

* ``InvalidTicker`` is a ``ValueError``, **not** a ``TradeError`` (CP7). Catching
  only ``TradeError`` would let a model-authored junk symbol escape as a 500,
  which is exactly the input a language model is most likely to produce.
* ``RuntimeError`` from a missing profile row is **deliberately not caught**
  (CP6). An uninitialised database is a server fault, and reporting it as a
  politely rejected action would hide a broken deployment behind a chat bubble.

Rejections are outcomes, not errors (D6): the turn returns 200 and the rejected
action is recorded with its reason, because the model *did* answer and the user
needs to see what it tried.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import ValidationError

from ..config import Settings
from ..db.connection import read_connection, transaction
from ..db.init import DEFAULT_USER_ID, new_id, utc_now
from ..llm import client, mock
from ..llm.schema import MAX_ACTIONS_PER_RESPONSE, AssistantResponse
from ..market.cache import PriceCache
from . import portfolio, watchlist
from .tickers import InvalidTicker

logger = logging.getLogger(__name__)

# D20. The full transcript stays in SQLite and is served by GET /api/chat/messages;
# only this much goes into the prompt, so a long session cannot grow the request
# without bound.
HISTORY_FOR_PROMPT = 10

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant embedded in a simulated \
trading workstation. You can analyse the user's portfolio and execute trades and \
watchlist changes on their behalf.

Rules:
- Only trade tickers the user holds or watches unless they name a new one explicitly.
- Market orders only. There are no limit orders, stops or short sales.
- You cannot spend more cash than the user has, and you cannot sell shares they do not \
hold. Requests that break those rules will be rejected and shown to the user.
- Be concise and specific. Quote actual numbers from the portfolio context.
- If the user only asks a question, answer it and request no actions."""

MOCK_COULD_NOT_ACT = "Mock assistant: I could not turn that into an action — check the quantity and try again."

APOLOGY_FOR_EMPTY_RESPONSE = (
    "Sorry — I didn't manage to produce a reply that time. Nothing was executed. "
    "Please try asking again, ideally a little more specifically."
)

# What goes in the transcript when the model could not be reached at all. The
# `{reason}` is the service's own sentence — either which variable is unset, or
# `client.UNREACHABLE_MESSAGE`. Never a provider's exception text: that string's
# shape is not under this repository's control and it is rendered to the user.
UNANSWERED_TEMPLATE = "I couldn't answer that — {reason} Nothing was executed."


class Action(TypedDict, total=False):
    """One executed or refused action, recorded as an **outcome** (D6).

    ``status`` is ``filled``/``applied`` or ``rejected``; a rejection carries the
    ``reason`` the service gave, which is the same sentence the REST API would
    have returned as ``detail``.
    """

    type: Literal["trade", "watchlist"]
    ticker: str
    side: str
    action: str
    quantity: float
    status: str
    reason: str
    price: float


class ChatTurn(TypedDict):
    """What one exchange produced."""

    message: str
    actions: list[Action]


class StoredMessage(TypedDict):
    """A persisted transcript row (D18)."""

    id: str
    role: str
    content: str
    actions: list[Action]
    created_at: str


def _persist(db_path: Path, role: str, content: str, actions: list[Action] | None, user_id: str) -> None:
    """Append one message to the transcript."""
    with transaction(db_path) as connection:
        connection.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_id(), user_id, role, content, json.dumps(actions) if actions is not None else None, utc_now()),
        )


def list_messages(db_path: Path, limit: int = 100, user_id: str = DEFAULT_USER_ID) -> list[StoredMessage]:
    """The stored conversation, oldest last (D18).

    Newest ``limit`` rows, then reversed: the panel renders top-to-bottom and
    scrolls to the end, so it wants the most recent window in reading order.
    """
    with read_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, actions, created_at FROM chat_messages
            WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [
        StoredMessage(
            id=str(row["id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            actions=json.loads(row["actions"]) if row["actions"] else [],
            created_at=str(row["created_at"]),
        )
        for row in reversed(rows)
    ]


def render_context(db_path: Path, cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> str:
    """The portfolio, rendered as text for the prompt.

    Text rather than a JSON dump: the model reasons better over a table than
    over braces, and every number here comes from the same cache the user is
    watching tick, so the model and the user are looking at one set of prices.
    """
    account = portfolio.get_portfolio(db_path, cache, user_id)
    watched = watchlist.list_watchlist(db_path, cache, user_id)

    lines = [
        "CURRENT PORTFOLIO",
        f"Cash balance: ${account['cash_balance']:,.2f}",
        f"Total value:  ${account['total_value']:,.2f}",
        f"Unrealised P&L: ${account['unrealized_pnl']:,.2f}",
        "",
        "POSITIONS",
    ]
    if account["positions"]:
        for position in account["positions"]:
            price = f"${position['current_price']:,.2f}" if position["current_price"] is not None else "no quote"
            lines.append(
                f"  {position['ticker']}: {position['quantity']:g} shares, "
                f"avg cost ${position['avg_cost']:,.2f}, now {price}, "
                f"market value ${position['market_value']:,.2f}, "
                f"unrealised P&L ${position['unrealized_pnl']:,.2f}"
            )
    else:
        lines.append("  (none)")

    lines += ["", "WATCHLIST"]
    for entry in watched:
        quote = entry["quote"]
        lines.append(f"  {entry['ticker']}: ${quote['price']:,.2f}" if quote else f"  {entry['ticker']}: no quote yet")

    return "\n".join(lines)


def _build_messages(db_path: Path, cache: PriceCache, user_id: str) -> list[dict[str, str]]:
    """System prompt, portfolio context, then the last few turns (D20)."""
    history = list_messages(db_path, limit=HISTORY_FOR_PROMPT, user_id=user_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": render_context(db_path, cache, user_id)},
    ]
    messages += [{"role": message["role"], "content": message["content"]} for message in history]
    return messages


def _execute_trade(db_path: Path, cache: PriceCache, requested: Any, user_id: str) -> Action:
    """Run one requested trade through the manual path (D5)."""
    action = Action(
        type="trade", ticker=str(requested.ticker), side=str(requested.side), quantity=float(requested.quantity)
    )
    try:
        # Called as a module attribute on purpose: B5's D5 sentinel monkeypatches
        # `portfolio.execute_trade`, and a `from .portfolio import execute_trade`
        # binding would capture the original and never see the patch — the check
        # would then pass while proving nothing.
        result = portfolio.execute_trade(
            db_path,
            cache,
            portfolio.TradeOrder(str(requested.ticker), requested.side, float(requested.quantity)),
            user_id,
        )
    except (portfolio.TradeError, InvalidTicker) as exc:
        # InvalidTicker is a ValueError, not a TradeError (CP7). Catching only
        # TradeError sends a model-authored junk symbol out as a 500.
        action["status"] = "rejected"
        action["reason"] = exc.reason
        return action

    action["status"] = "filled"
    action["ticker"] = result["ticker"]
    action["price"] = result["price"]
    return action


def _apply_watchlist_change(db_path: Path, cache: PriceCache, requested: Any, user_id: str) -> Action:
    """Run one requested watchlist change through the manual path (D5)."""
    action = Action(type="watchlist", ticker=str(requested.ticker), action=str(requested.action))
    try:
        if requested.action == "add":
            entry = watchlist.add_ticker(db_path, cache, str(requested.ticker), user_id)
            action["ticker"] = entry["ticker"]
        else:
            watchlist.remove_ticker(db_path, str(requested.ticker), user_id)
    except (InvalidTicker, watchlist.NotWatched) as exc:
        action["status"] = "rejected"
        action["reason"] = exc.reason
        return action

    action["status"] = "applied"
    return action


def _run_actions(db_path: Path, cache: PriceCache, reply: AssistantResponse, user_id: str) -> list[Action]:
    """Execute up to the cap, recording every request as an outcome (D6, D7).

    Over-cap actions are **recorded as rejected**, not dropped: silently
    executing nine of eleven trades and saying nothing is worse than refusing
    two out of eleven and saying so.
    """
    actions: list[Action] = []
    requests: list[tuple[str, Any]] = [("trade", t) for t in reply.trades]
    requests += [("watchlist", w) for w in reply.watchlist_changes]

    for index, (kind, requested) in enumerate(requests):
        if index >= MAX_ACTIONS_PER_RESPONSE:
            over_cap = Action(
                type="trade" if kind == "trade" else "watchlist",
                ticker=str(requested.ticker),
                status="rejected",
                reason=f"Action limit reached: at most {MAX_ACTIONS_PER_RESPONSE} actions run per response",
            )
            actions.append(over_cap)
            continue

        if kind == "trade":
            actions.append(_execute_trade(db_path, cache, requested, user_id))
        else:
            actions.append(_apply_watchlist_change(db_path, cache, requested, user_id))

    return actions


async def handle_message(
    db_path: Path,
    cache: PriceCache,
    settings: Settings,
    text: str,
    user_id: str = DEFAULT_USER_ID,
) -> ChatTurn:
    """One conversational turn: persist, ask, act, persist, return.

    Raises ``LLMNotConfigured`` and transport ``LLMError`` for the API layer to
    map — but **not** ``EmptyModelResponse``, which is handled here as a normal
    turn with an apology (D25). The call succeeded and was billed; there is
    simply nothing to show, and "try again later" would be a lie about both the
    service's health and the odds of a retry helping.

    **Every database call goes through ``asyncio.to_thread``.** This is the one
    ``async def`` path in the application that touches SQLite, and D21's rule —
    blocking work never runs on the loop — is bought by Starlette's threadpool
    only for ``def`` handlers. This handler is ``async`` because it awaits the
    model, so nothing was buying it: the review measured **0 event-loop beats**
    during a stalled chat turn against 162 for the same work through the ``def``
    trade handler. Every SSE stream, the price producer and the snapshotter
    stopped for the whole turn, and ``BEGIN IMMEDIATE``'s five-second busy
    timeout meant contention with a manual trade could freeze the process for
    five seconds. ``services/`` stays sync and framework-free (B6); the hop
    happens here, at the async boundary, exactly as ``run_snapshotter`` and the
    lifespan already do.
    """
    await asyncio.to_thread(_persist, db_path, "user", text, None, user_id)
    messages = await asyncio.to_thread(_build_messages, db_path, cache, user_id)

    if settings.llm_mock:
        try:
            reply = mock.respond(text)
        except ValidationError:
            # The mock builds real `TradeAction`s, so a message like "buy 0
            # AAPL" makes its own `gt=0` constraint raise — and this branch had
            # no guard where the live one does, so it escaped as a 500 with the
            # user's turn already persisted and orphaned. The mock is clamped
            # too; both are needed, because either alone leaves the other path
            # unguarded, and `LLM_MOCK=true` is the mode the E2E suite, the
            # screenshots and the documented dev loop all run in.
            logger.warning("mock produced an unusable action for %r; answering message-only", text)
            reply = AssistantResponse(message=MOCK_COULD_NOT_ACT)
    else:
        try:
            reply = await client.complete(settings, messages)
        except client.EmptyModelResponse:
            # Ordered before the generic LLMError it inherits from. Reversing
            # these two lines turns every empty response into a 503.
            logger.warning("model returned no content; answering with an apology (D25)")
            await asyncio.to_thread(_persist, db_path, "assistant", APOLOGY_FOR_EMPTY_RESPONSE, [], user_id)
            return ChatTurn(message=APOLOGY_FOR_EMPTY_RESPONSE, actions=[])
        except client.LLMError as exc:
            # **Answer the turn, then re-raise.** The user's message is
            # persisted before the model is called (it has to be — it is part of
            # the prompt history the very next turn reads), so an error that
            # simply propagated left a user row with no assistant row: permanent,
            # visible on every reload, and fed back into every later prompt as an
            # exchange where the assistant said nothing. With an unset key —
            # which the README calls a working demo — every single message
            # accumulated that way.
            #
            # The status code does not change. This is still a 503: the service
            # genuinely cannot do this until someone sets a variable or the
            # provider comes back, and the panel still shows its banner. What
            # changes is that the *transcript* is consistent, which is the thing
            # a later prompt actually reads.
            #
            # Ordered after EmptyModelResponse, which subclasses this. Swapping
            # the two turns every empty reply into a 503 — the same trap the
            # comment above names, now with a second way to fall into it.
            await asyncio.to_thread(
                _persist, db_path, "assistant", UNANSWERED_TEMPLATE.format(reason=exc), [], user_id
            )
            raise

    actions = await asyncio.to_thread(_run_actions, db_path, cache, reply, user_id)
    await asyncio.to_thread(_persist, db_path, "assistant", reply.message, actions, user_id)
    return ChatTurn(message=reply.message, actions=actions)
