"""The in-memory price cache — the only home of current prices.

No lock. This is single-threaded asyncio: the producer assembles a **new** dict
and rebinds one reference, which no reader can observe half-applied. Readers
take the current reference and hold an immutable snapshot for as long as they
like, so a slow SSE client cannot stall the producer.

A lock here would be ceremony, and worse, it would create the "never hold it
across a socket write" rule that the ceremony then requires (D2).
"""

from __future__ import annotations

from datetime import datetime, timezone

from .source import Direction, Quote


def _direction(price: float, previous: float) -> Direction:
    if price > previous:
        return "up"
    if price < previous:
        return "down"
    return "flat"


class PriceCache:
    """Holds the latest quote per ticker.

    The one class in ``market/`` with genuinely mutable shared state, which is
    what earns it the class where the rest of the package is functions.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}

    def snapshot(self) -> dict[str, Quote]:
        """The current quotes. Safe to hold and iterate — the producer rebinds."""
        return self._quotes

    def get(self, ticker: str) -> Quote | None:
        """The current quote for a ticker, or None if it has never been priced."""
        return self._quotes.get(ticker.upper())

    def price_of(self, ticker: str) -> float | None:
        """The current price, or None if this ticker has never been priced.

        Callers must treat None as "no price yet" and refuse to trade, rather
        than substituting zero — a fill at an invented price corrupts the
        portfolio permanently.
        """
        quote = self.get(ticker)
        return quote["price"] if quote else None

    def apply(self, prices: dict[str, float]) -> None:
        """Fold new prices in and rebind the dict atomically.

        Tickers absent from ``prices`` keep their previous quote: a source that
        omitted a symbol this poll (rate limit, malformed entry) must leave the
        last known price standing rather than blanking the row.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        updated = dict(self._quotes)

        for raw_ticker, price in prices.items():
            ticker = raw_ticker.upper()
            existing = updated.get(ticker)
            if existing is None:
                # First sighting: session_open is stamped here, once, and is
                # never rewritten while this process lives (D19). previous_price
                # equals price so the first tick neither flashes nor reports a
                # spurious change.
                updated[ticker] = Quote(
                    ticker=ticker,
                    price=price,
                    previous_price=price,
                    session_open=price,
                    timestamp=timestamp,
                    direction="flat",
                )
                continue

            if price == existing["price"]:
                # An unchanged price must NOT restamp the quote. The SSE stream
                # detects change by timestamp advance (D4), so restamping here
                # would emit a frame — and fire a price-flash animation — for a
                # price that did not move. Under the Massive source that is ~30
                # identical frames per real quote, which is exactly the noise
                # D4's change-only rule exists to prevent.
                continue

            updated[ticker] = Quote(
                ticker=ticker,
                price=price,
                previous_price=existing["price"],
                session_open=existing["session_open"],
                timestamp=timestamp,
                direction=_direction(price, existing["price"]),
            )

        self._quotes = updated
