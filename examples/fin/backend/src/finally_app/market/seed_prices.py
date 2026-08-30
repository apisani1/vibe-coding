"""Starting prices and per-ticker dynamics for the simulator.

``sigma`` is deliberately **not** market-realistic. See D23: at a 500 ms tick a
realistic annualised sigma of ~0.3 moves a price about 0.009% per tick and
~0.1% across the entire 60-second sparkline window — a flat line. This is a
simulator for watching, not a forecasting model, and the constants say so.

``rho`` is the loading on the single market factor. Pairwise correlation
between two tickers is ``rho_i * rho_j`` (D14), so the high-rho technology
names co-move as a bloc while JPM and V drift largely on their own.
"""

from __future__ import annotations

from typing import NamedTuple


class TickerProfile(NamedTuple):
    """Everything the simulator needs to evolve one ticker."""

    seed_price: float
    mu: float
    sigma: float
    rho: float


# Seed prices are roughly plausible; the dynamics are not, on purpose.
PROFILES: dict[str, TickerProfile] = {
    "AAPL": TickerProfile(190.0, 0.10, 1.8, 0.85),
    "GOOGL": TickerProfile(175.0, 0.12, 1.9, 0.85),
    "MSFT": TickerProfile(415.0, 0.11, 1.7, 0.88),
    "AMZN": TickerProfile(180.0, 0.13, 2.1, 0.82),
    "TSLA": TickerProfile(250.0, 0.05, 2.5, 0.70),
    "NVDA": TickerProfile(880.0, 0.20, 2.4, 0.80),
    "META": TickerProfile(500.0, 0.14, 2.0, 0.83),
    "JPM": TickerProfile(200.0, 0.07, 1.5, 0.30),
    "V": TickerProfile(275.0, 0.08, 1.5, 0.28),
    "NFLX": TickerProfile(610.0, 0.09, 2.0, 0.55),
}

# Anything the user adds that we have no profile for still has to be priced.
UNKNOWN_TICKER_DEFAULT = TickerProfile(100.0, 0.08, 1.9, 0.60)


def profile_for(ticker: str) -> TickerProfile:
    """The dynamics for a ticker, with a usable default for unknown symbols.

    An unknown symbol gets a price rather than an error: the spec allows adding
    any ticker to the watchlist, and a row that never prices looks like a bug.
    """
    return PROFILES.get(ticker.upper(), UNKNOWN_TICKER_DEFAULT)
