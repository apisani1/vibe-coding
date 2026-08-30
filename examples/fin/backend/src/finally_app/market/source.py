"""The market-data contract both sources satisfy.

A ``typing.Protocol`` rather than an ABC: the two implementations are checked
structurally at type-check time and never need a shared base at runtime. ``mypy
src`` is the only thing that proves conformance, which is why it is part of
check A2.
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict

Direction = Literal["up", "down", "flat"]


class Quote(TypedDict):
    """One ticker's current state, as held in the cache and sent over SSE.

    ``previous_price`` and ``session_open`` are **not** interchangeable, and
    conflating them is the trap this type exists to prevent:

    * ``previous_price`` is the immediately preceding tick. Its only job is
      deciding whether the row flashes green or red.
    * ``session_open`` is the first price seen for this ticker in this process,
      stamped once and never rewritten. The watchlist's *daily change %* comes
      from this. Deriving that percentage from ``previous_price`` yields a
      ±0.01% figure that flips sign twice a second, which is not a daily change
      by any reading (D19).
    """

    ticker: str
    price: float
    previous_price: float
    session_open: float
    timestamp: str
    direction: Direction


class MarketDataSource(Protocol):
    """Anything that can produce quotes for a set of tickers."""

    @property
    def interval_seconds(self) -> float:
        """How long the producer should sleep between polls of this source."""

    async def fetch(self, tickers: list[str]) -> dict[str, float]:
        """Return the latest price for each requested ticker.

        May omit tickers it has no price for — the producer keeps the previous
        cache entry rather than inventing one. Must not raise for a single bad
        ticker; guard per-ticker so one failure cannot discard a whole poll.
        """

    async def aclose(self) -> None:
        """Release whatever the source holds open. Called once, from the lifespan.

        Part of the Protocol rather than something the lifespan reaches for with
        ``getattr``: a duck-typed teardown is invisible to ``mypy --strict``, so
        the day a third source arrives with a connection pool and no ``aclose``,
        nothing would say so. A source with nothing to release implements it as
        a no-op — which is a sentence someone has to write on purpose, and that
        is the point.
        """
