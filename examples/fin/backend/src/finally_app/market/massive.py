"""Massive (Polygon.io) REST poller.

REST polling, not WebSocket: simpler, and it works on every tier (SPEC §6).

**This path cannot be verified in this environment** — `MASSIVE_API_KEY` is
empty and the account used previously returned 403 `NOT_AUTHORIZED` on
`/v2/snapshot`. What is tested here is the parsing (against recorded fixtures)
and the Protocol conformance. Real response shapes, live rate limits, and the
backoff behaviour under an actual 429 are declared unverifiable in
`verification-plan.md § Cannot be verified`, and nothing in this build licenses
a claim that this path works.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from ..config import DEFAULT_MASSIVE_POLL_SECONDS

logger = logging.getLogger(__name__)

SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
REQUEST_TIMEOUT_SECONDS = 20.0

# Exponential backoff on rate limits and server errors, to a ceiling. Prices go
# stale and the app keeps working; the alternative -- clearing the cache -- would
# blank every price on one bad HTTP response.
BACKOFF_INITIAL_SECONDS = 2.0
BACKOFF_CEILING_SECONDS = 60.0

# The floor a poll interval is raised to. Massive's paid tiers support 2-15
# seconds; the free tier's 5 calls/min makes 15 the safe value there, which is
# why that is the default rather than this.
MINIMUM_POLL_SECONDS = 2.0


def valid_poll_seconds(poll_seconds: float) -> float:
    """Clamp a requested poll interval to something that can actually be polled.

    **Here rather than in ``config.py``, where the finding pointed.** The
    consumer is the guard — the same lesson the ``quantity: -5`` defect taught
    at CP9: a rule enforced only in the loader is invisible to everything that
    constructs this client directly, and this class is the only thing in the
    application that turns the number into a sleep.

    ``MASSIVE_POLL_SECONDS`` was validated as *a float* and nothing more, and
    each of these was measured rather than imagined:

    * ``0`` and ``-5`` give a hot loop against a metered, paid API;
    * ``inf`` freezes prices forever and logs nothing, because
      ``asyncio.sleep(inf)`` simply never returns;
    * ``nan`` drops the producer into its restart loop — every comparison
      against NaN is False, so ``max()`` propagates it into the sleep.

    Non-finite falls back to the default rather than to the floor: a NaN is not
    a request for a fast poll, it is an unreadable value, and answering it with
    the most aggressive legal interval would be inventing an intent.
    """
    if not math.isfinite(poll_seconds):
        logger.warning(
            "MASSIVE_POLL_SECONDS=%r is not a finite number; using the default of %.0fs",
            poll_seconds,
            DEFAULT_MASSIVE_POLL_SECONDS,
        )
        return DEFAULT_MASSIVE_POLL_SECONDS
    if poll_seconds < MINIMUM_POLL_SECONDS:
        logger.warning(
            "MASSIVE_POLL_SECONDS=%g is below the %.0fs floor; polling every %.0fs instead",
            poll_seconds,
            MINIMUM_POLL_SECONDS,
            MINIMUM_POLL_SECONDS,
        )
        return MINIMUM_POLL_SECONDS
    return poll_seconds


def parse_snapshot(payload: dict[str, Any]) -> dict[str, float]:
    """Extract ticker -> price from a snapshot response.

    Guarded **per entry**: one malformed ticker must not discard an otherwise
    good poll. A response where nine tickers parse and one is broken should
    price nine tickers, not zero.

    Price preference is last-trade, then day close, then previous close. A
    snapshot taken outside market hours has no last trade, and falling straight
    through to "no price" would leave the whole watchlist blank overnight.
    """
    out: dict[str, float] = {}
    for entry in payload.get("tickers") or []:
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue

        price: float | None = None
        for source, key in (("lastTrade", "p"), ("day", "c"), ("prevDay", "c")):
            block = entry.get(source)
            if isinstance(block, dict):
                candidate = block.get(key)
                if isinstance(candidate, (int, float)) and candidate > 0:
                    price = float(candidate)
                    break

        if price is None:
            logger.debug("no usable price for %s in snapshot", ticker)
            continue
        out[ticker.upper()] = price

    return out


class MassiveClient:
    """A ``MarketDataSource`` backed by the Massive REST snapshot endpoint."""

    def __init__(self, api_key: str, poll_seconds: float, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._poll_seconds = valid_poll_seconds(poll_seconds)
        # One client for the life of the source, not one per poll. Production
        # built a fresh `AsyncClient` on every `fetch` — a new connection pool
        # and a new TLS handshake every 15 seconds against the same host — which
        # went unnoticed because the injection seam below is only ever used by
        # tests, and a test passes an already-open client.
        self._owns_client = client is None
        self._client = client if client is not None else httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        self._backoff = 0.0

    async def aclose(self) -> None:
        """Release the connection pool. Called from the lifespan, once.

        An injected client is left alone: whoever passed it in owns it, and
        closing someone else's client from here is how a shared fixture starts
        failing the *next* test instead of this one.
        """
        if self._owns_client:
            await self._client.aclose()

    @property
    def interval_seconds(self) -> float:
        """Poll interval, extended while backing off after a failure."""
        return max(self._poll_seconds, self._backoff)

    def _note_failure(self) -> None:
        self._backoff = min(
            BACKOFF_CEILING_SECONDS,
            BACKOFF_INITIAL_SECONDS if self._backoff == 0.0 else self._backoff * 2,
        )

    def _note_success(self) -> None:
        self._backoff = 0.0

    async def fetch(self, tickers: list[str]) -> dict[str, float]:
        """Poll for the union of watched tickers.

        Returns an empty dict on failure rather than raising: the producer folds
        an empty result in as "nothing changed", which keeps the last known
        prices standing. Raising would restart the producer loop and log a
        traceback for an ordinary rate limit.
        """
        if not tickers:
            return {}

        try:
            response = await self._client.get(
                SNAPSHOT_URL,
                params={"tickers": ",".join(tickers), "apiKey": self._api_key},
            )
            if response.status_code in (401, 403):
                # Loud, and deliberately no fallback to the simulator (D13):
                # showing plausible invented prices to someone who supplied a
                # key is the one failure here with real-world consequences.
                logger.error(
                    "Massive rejected the API key (HTTP %s). Prices will go stale. "
                    "This will NOT fall back to the simulator.",
                    response.status_code,
                )
                self._note_failure()
                return {}
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning("Massive returned HTTP %s; backing off", response.status_code)
                self._note_failure()
                return {}
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # The exception TYPE and status, never the exception: `httpx`
            # formats `HTTPStatusError` as "... for url '<full url>'", and the
            # key travels in this request's query string — so interpolating it
            # would put a live credential into `docker logs`, which is exactly
            # what the start script tells a user to run when something breaks.
            status = getattr(getattr(exc, "response", None), "status_code", "n/a")
            logger.warning("Massive poll failed (%s, status %s); keeping previous prices", type(exc).__name__, status)
            self._note_failure()
            return {}

        self._note_success()
        if not isinstance(payload, dict):
            logger.warning("Massive returned a non-object payload; keeping previous prices")
            return {}
        return parse_snapshot(payload)
