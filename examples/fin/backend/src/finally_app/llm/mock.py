"""Deterministic responses for ``LLM_MOCK=true``.

Makes no network call, so it is free, instant and reproducible — which is what
lets the E2E suite exercise the chat flow without a key and without a bill.

The mock is keyword-driven rather than a single canned reply: the E2E scenarios
need a turn that fills a trade and a turn that gets rejected, and inventing a
second mechanism for that would be more code than reading the message.
"""

from __future__ import annotations

import re
from typing import Literal

from .schema import AssistantResponse, TradeAction, WatchlistAction

_BUY = re.compile(r"\bbuy\b", re.IGNORECASE)
_SELL = re.compile(r"\bsell\b", re.IGNORECASE)
_ADD = re.compile(r"\badd\b", re.IGNORECASE)
_REMOVE = re.compile(r"\bremove\b", re.IGNORECASE)
_TICKER = re.compile(r"\b([A-Z][A-Z.\-]{0,9})\b")
_QUANTITY = re.compile(r"\b(\d+(?:\.\d+)?)\b")

_DEFAULT_MESSAGE = (
    "Mock assistant. Your portfolio is loaded and I can see your positions. "
    "Ask me to buy or sell a ticker and I will act on it."
)


def _first_ticker(text: str, fallback: str = "AAPL") -> str:
    """Pick the first plausible ticker, ignoring common capitalised words."""
    stop = {"I", "AI", "P", "L", "USD", "OK", "ADD", "BUY", "SELL", "REMOVE"}
    for candidate in _TICKER.findall(text):
        if candidate not in stop and len(candidate) >= 2:
            return str(candidate)
    return fallback


def _quantity(text: str, fallback: float = 1.0) -> float:
    """The first number in the message, or the fallback.

    Clamped to something the schema accepts: `TradeAction` requires `gt=0`, so
    "buy 0 AAPL" used to make this function's own return value raise inside the
    model constructor — an HTTP 500 on the path the E2E suite, the screenshots
    and the documented dev loop all use. A mock that cannot produce a valid
    action is a mock that tests nothing.
    """
    match = _QUANTITY.search(text)
    parsed = float(match.group(1)) if match else fallback
    return parsed if parsed > 0 else fallback


def respond(user_message: str) -> AssistantResponse:
    """Produce a deterministic reply for the given message."""
    text = user_message or ""

    if _BUY.search(text) or _SELL.search(text):
        side: Literal["buy", "sell"] = "sell" if _SELL.search(text) and not _BUY.search(text) else "buy"
        ticker = _first_ticker(text)
        quantity = _quantity(text)
        return AssistantResponse(
            message=f"Mock assistant: placing a {side} order for {quantity} {ticker}.",
            trades=[TradeAction(ticker=ticker, side=side, quantity=quantity)],
        )

    if _ADD.search(text) or _REMOVE.search(text):
        action: Literal["add", "remove"] = "remove" if _REMOVE.search(text) else "add"
        ticker = _first_ticker(text, fallback="PYPL")
        return AssistantResponse(
            message=f"Mock assistant: {action}ing {ticker} on your watchlist.",
            watchlist_changes=[WatchlistAction(ticker=ticker, action=action)],
        )

    return AssistantResponse(message=_DEFAULT_MESSAGE)
