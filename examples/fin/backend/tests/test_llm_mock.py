"""The mock is deterministic and covers the two shapes E2E needs: a fill and a rejection."""

from __future__ import annotations

import pytest

from finally_app.llm import mock


def test_buy_message_produces_a_buy_trade() -> None:
    result = mock.respond("buy 5 MSFT please")

    assert len(result.trades) == 1
    assert result.trades[0].side == "buy"
    assert result.trades[0].ticker == "MSFT"
    assert result.trades[0].quantity == 5


def test_sell_message_produces_a_sell_trade() -> None:
    result = mock.respond("sell 2 TSLA")

    assert result.trades[0].side == "sell"
    assert result.trades[0].ticker == "TSLA"


def test_watchlist_add_and_remove() -> None:
    assert mock.respond("add PYPL to my watchlist").watchlist_changes[0].action == "add"
    assert mock.respond("remove NFLX from my watchlist").watchlist_changes[0].action == "remove"


def test_plain_question_produces_message_only() -> None:
    result = mock.respond("how is my portfolio doing?")

    assert result.trades == []
    assert result.watchlist_changes == []
    assert result.message


def test_is_deterministic() -> None:
    """E2E depends on this: the same input must always give the same output."""
    assert mock.respond("buy 5 MSFT") == mock.respond("buy 5 MSFT")


def test_an_oversized_buy_is_expressible() -> None:
    """The rejected-trade E2E scenario needs a quantity no cash balance can cover."""
    result = mock.respond("buy 100000 AAPL")

    assert result.trades[0].quantity == 100000


def test_a_zero_quantity_message_still_produces_a_valid_action() -> None:
    """The CP18 blocker, at its source.

    `buy 0 AAPL` made this function's own return value fail `TradeAction`'s
    `gt=0`, and the mock branch of `handle_message` had no guard where the live
    branch does — so the documented development mode answered **HTTP 500** and
    orphaned the user's turn in the transcript.

    This calls the real `respond`. The test that was supposed to cover this value
    built its action with `model_construct` (which skips validation) and
    monkeypatched `respond` away, so the test named after the value never ran the
    code that produced it.
    """
    reply = mock.respond("buy 0 AAPL")

    assert reply.trades[0].quantity > 0


@pytest.mark.parametrize("message", ["buy 0 AAPL", "sell 0 MSFT", "buy -0 TSLA", "buy 0.0 NVDA"])
def test_no_message_can_make_the_mock_raise(message: str) -> None:
    """Whatever the user types, the mock must produce something the schema accepts."""
    assert mock.respond(message).message
