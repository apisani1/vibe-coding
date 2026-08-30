"""A token bucket, for the one endpoint that costs money per request.

Every ``POST /api/chat`` is one billed completion at OpenRouter. Nothing else in
this application has that property: a trade moves simulated money, a quote comes
from a cache, and the worst a loop against them does is warm the CPU. So this is
not general-purpose request throttling — it is a spend limit, and it is applied
at exactly one route.

**Why it exists at all on a localhost app.** On true loopback with one user it
is inert, which is the honest description. It stops being inert the moment
either network assumption slips: a page published on ``0.0.0.0`` (which is what
both start scripts did until CP18), or a DNS-rebound origin (which is what
``TrustedHostMiddleware`` now refuses). Those were the two findings graded
`risk`; this one was graded `advisory` precisely because it is their
consequence rather than their cause. Fixing the causes does not make the
consequence uninteresting — it makes it the remaining layer.

**In-process, and therefore per-process.** There is no shared store, so two
uvicorn workers would each carry their own bucket and the effective limit would
double. The shipped ``CMD`` runs a single worker and the design is single-user;
a second worker would need a different mechanism, not a bigger number here.
"""

from __future__ import annotations

import time
from collections.abc import Callable

# Ten in hand, one back every six seconds: a sustained ten a minute, with a
# burst large enough that nobody typing at a keyboard will ever meet it. The
# E2E suite sends three turns in a run.
CHAT_BURST = 10
CHAT_REFILL_SECONDS = 6.0


class TokenBucket:
    """Allows ``capacity`` calls immediately, then one per ``refill_seconds``.

    The clock is injected. That is not decoration: a limiter tested by sleeping
    is a limiter tested in one direction only — you can watch it refuse, but
    watching it *forgive* would cost a minute of wall time per assertion, so in
    practice nobody writes that half and the refill arithmetic ships unproven.
    With a fake clock both halves are one test.

    Not locked, and called only from the event loop. ``POST /api/chat`` is the
    single caller and it is an ``async def`` handler, so the read-modify-write
    below cannot interleave with itself. A ``def`` handler would run on
    Starlette's threadpool and this would need a lock — worth knowing before
    reusing this class elsewhere.
    """

    def __init__(
        self,
        capacity: int,
        refill_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = capacity
        self._refill_seconds = refill_seconds
        self._clock = clock
        self._tokens = float(capacity)
        self._updated = clock()

    def take(self) -> float:
        """Spend one token. Returns 0.0 when allowed, else the seconds to wait.

        Returning the wait rather than a bool is what lets the caller answer
        with a ``Retry-After`` the client can actually act on, instead of a bare
        refusal that invites an immediate retry.
        """
        now = self._clock()
        # `monotonic` cannot go backwards, but the clock is injected and a test
        # (or a future caller) can pass anything; a negative elapsed would mint
        # tokens rather than refuse them.
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(float(self._capacity), self._tokens + elapsed / self._refill_seconds)

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return 0.0
        return (1.0 - self._tokens) * self._refill_seconds
