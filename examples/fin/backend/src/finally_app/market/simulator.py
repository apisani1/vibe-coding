"""Geometric Brownian motion price simulator.

Runs in-process with no external dependency, and no numpy: the arithmetic is
``random.gauss`` and ``math.exp`` over 10-30 tickers twice a second, which is
noise. A covariance matrix would be real overkill (D14).
"""

from __future__ import annotations

import math
import random

from .seed_prices import profile_for

# Trading time, not wall time: 252 sessions of 6.5 hours.
SECONDS_PER_TRADING_YEAR = 252 * 6.5 * 3600

# Shocks are rated PER TICKER PER MINUTE, not per tick. At two ticks a second a
# "small" 0.1% per-tick probability is ~12% per minute -- roughly seven shocks
# per ticker per hour, each 20-50x the size of a diffusion step. That turns the
# chart into a staircase of jumps separated by flat stretches, which is the
# opposite of the drama the spec asks for (D23).
SHOCK_RATE_PER_MINUTE = 0.01
SHOCK_MIN_MAGNITUDE = 0.02
SHOCK_MAX_MAGNITUDE = 0.05


def gbm_step(price: float, mu: float, sigma: float, dt: float, z: float) -> float:
    """One GBM step. Pure, no rounding, RNG injected.

    ``S * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * z)``

    The ``- sigma**2 / 2`` term is the Jensen correction, and it is the whole
    reason this is a separate pure function. It makes the *expected* price
    follow ``S * e^(mu*t)``; without it every simulated stock quietly rallies.

    Purity is a testability requirement, not a style preference. At production
    parameters (dt = 500 ms of trading time, sigma ~2) dropping the correction
    shifts the price by a relative 1.7e-7 — unresolvable by any practical
    sample, and erased entirely by rounding to cents. Only a pure step callable
    with ``sigma=1, dt=1`` lets check A8 discriminate, where the expected mean
    log return is -0.5 against 0.0 for the uncorrected form.
    """
    drift = (mu - sigma**2 / 2) * dt
    diffusion = sigma * math.sqrt(dt) * z
    return price * math.exp(drift + diffusion)


def shock_probability_per_tick(tick_seconds: float, rate_per_minute: float = SHOCK_RATE_PER_MINUTE) -> float:
    """Convert the per-minute shock rate to a per-tick probability."""
    return rate_per_minute * tick_seconds / 60.0


class Simulator:
    """A ``MarketDataSource`` that invents prices.

    Holds mutable per-ticker state, which is why this is a class where the rest
    of the package is modules of functions.
    """

    def __init__(
        self,
        tick_seconds: float = 0.5,
        rng: random.Random | None = None,
        shock_rate_per_minute: float = SHOCK_RATE_PER_MINUTE,
    ) -> None:
        self._tick_seconds = tick_seconds
        self._rng = rng if rng is not None else random.Random()
        self._prices: dict[str, float] = {}
        self._shock_probability = shock_probability_per_tick(tick_seconds, shock_rate_per_minute)
        self._dt = tick_seconds / SECONDS_PER_TRADING_YEAR
        # Counts shocks actually applied inside advance(). Instrumentation, not
        # decoration: without it a test can only re-sample the probability,
        # which passes identically against a simulator that never shocks and
        # one that shocks every tick.
        self.shocks_fired = 0

    @property
    def interval_seconds(self) -> float:
        """How long the producer sleeps between ticks."""
        return self._tick_seconds

    @property
    def shock_probability(self) -> float:
        """Exposed so a test can assert the per-minute conversion, not re-derive it."""
        return self._shock_probability

    def _price_of(self, ticker: str) -> float:
        """The ticker's current price, seeded from its profile on first sight."""
        if ticker not in self._prices:
            self._prices[ticker] = profile_for(ticker).seed_price
        return self._prices[ticker]

    def _maybe_shock(self, price: float) -> tuple[float, bool]:
        """Occasionally jump the price, permanently.

        Permanent rather than mean-reverting: a spike that unwinds would undo
        P&L the user just watched themselves capture.
        """
        if self._rng.random() >= self._shock_probability:
            return price, False
        magnitude = self._rng.uniform(SHOCK_MIN_MAGNITUDE, SHOCK_MAX_MAGNITUDE)
        sign = 1.0 if self._rng.random() < 0.5 else -1.0
        return price * (1.0 + sign * magnitude), True

    def advance(self, tickers: list[str]) -> dict[str, float]:
        """Evolve every ticker one tick and return the new prices.

        One market factor is drawn per tick and shared across tickers; each
        ticker combines it with its own idiosyncratic draw as
        ``z = rho * z_market + sqrt(1 - rho^2) * z_own``. That gives pairwise
        correlation ``rho_i * rho_j`` in three lines of arithmetic.
        """
        z_market = self._rng.gauss(0.0, 1.0)
        out: dict[str, float] = {}

        for ticker in tickers:
            profile = profile_for(ticker)
            z_own = self._rng.gauss(0.0, 1.0)
            z = profile.rho * z_market + math.sqrt(max(0.0, 1.0 - profile.rho**2)) * z_own

            price = gbm_step(self._price_of(ticker), profile.mu, profile.sigma, self._dt, z)
            price, shocked = self._maybe_shock(price)
            if shocked:
                self.shocks_fired += 1

            # Guard against a pathological walk to zero; prices are strictly
            # positive under GBM but shocks are applied multiplicatively on top.
            price = max(price, 0.01)
            self._prices[ticker] = price
            out[ticker] = price

        return out

    async def fetch(self, tickers: list[str]) -> dict[str, float]:
        """The ``MarketDataSource`` entry point. Pure computation, never awaits."""
        return self.advance(tickers)

    async def aclose(self) -> None:
        """Nothing to release: this source holds no socket, no file, no pool."""
