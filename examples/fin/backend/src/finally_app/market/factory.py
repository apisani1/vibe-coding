"""Choosing the market data source.

One rule, one branch: a non-empty ``MASSIVE_API_KEY`` selects Massive,
anything else selects the simulator.

**There is deliberately no fallback branch** (D13). If a key is present and
broken, the app shows stale prices and logs loudly; it does not quietly switch
to invented ones. Someone who supplied a key believes they are looking at the
market, and plausible fake prices are the one failure mode in this system with
consequences outside it.
"""

from __future__ import annotations

import logging

from ..config import Settings
from .massive import MassiveClient
from .simulator import Simulator
from .source import MarketDataSource

logger = logging.getLogger(__name__)


def create_source(settings: Settings) -> MarketDataSource:
    """Build the market data source this configuration asks for."""
    if settings.use_massive:
        client = MassiveClient(settings.massive_api_key, settings.massive_poll_seconds)
        # Built first, then logged, so this line reports the interval that will
        # actually be polled rather than the one that was asked for. They differ
        # whenever `MASSIVE_POLL_SECONDS` was out of range, and a startup line
        # that disagrees with the behaviour is worse than no line at all.
        logger.info("using Massive real market data, polling every %.1fs", client.interval_seconds)
        return client

    logger.info("using the built-in GBM simulator")
    return Simulator()
