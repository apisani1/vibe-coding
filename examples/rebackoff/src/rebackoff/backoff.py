"""Pure backoff/jitter math: ``attempt number -> delay in seconds``.

Everything here is a pure function of its arguments (including an injected RNG), so the
delay for any attempt is exactly reproducible under a seeded ``random.Random`` — which is
what makes the whole library deterministically testable without ever sleeping.
"""

from __future__ import annotations

import math
from random import Random
from typing import (
    Final,
    Protocol,
)

from .policy import (
    JITTER_NAMES,
    RetryPolicy,
)


def _cap(base: float, factor: float, max_backoff: float, attempt_number: int) -> float:
    """The capped, un-jittered exponential term for the delay after attempt ``n``.

    ``O(1)`` and safe for any finite valid policy and any attempt number. ``base * factor **
    exponent`` is computed directly (``**`` is a single ``pow``, not a loop) whenever
    ``factor ** exponent`` is guaranteed finite; the exact bit-for-bit value is preserved
    there. Only for an absurdly large exponent (where ``factor ** exponent`` would overflow)
    do we fall back to comparing/adding *separate* logs — avoiding the ``log(0)`` /
    ``log(inf)`` domain errors a ``log(max_backoff / base)`` ratio would hit — and the exact
    bits of such a delay are immaterial. ``factor <= 1`` and ``base <= 0`` are handled first.
    """
    if base <= 0.0:
        return 0.0
    if factor <= 1.0:
        return min(max_backoff, base)
    exponent = attempt_number - 1
    log_factor = math.log(factor)
    # Capped? Compare the (possibly astronomically large int) exponent to a finite float
    # threshold via SEPARATE logs — this never converts a huge int exponent to float, and
    # never hits the log(0)/log(inf) a ``log(max_backoff / base)`` ratio would.
    if exponent >= (math.log(max_backoff) - math.log(base)) / log_factor:
        return max_backoff
    # Below the cap ⇒ the exponent is within a finite float bound (so it is float-safe). The
    # value is exact via ``**`` (one pow, O(1)); only a tiny base can still overflow the
    # intermediate factor**exponent, so fall back to log space there (its bits are immaterial).
    try:
        return min(max_backoff, base * factor**exponent)
    except OverflowError:
        return math.exp(math.log(base) + exponent * log_factor)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class _JitterStrategy(Protocol):  # pylint: disable=too-few-public-methods
    """A jitter strategy. Uniform signature so the registry dispatches without branching.

    Strategies ignore the keyword arguments they do not need.
    """

    def __call__(self, *, cap: float, prev: float, base: float, max_backoff: float, rng: Random) -> float: ...


# The strategies share one uniform signature (see _JitterStrategy) so the registry can
# dispatch without branching; each ignores the arguments it does not need.
# pylint: disable=unused-argument
def _full(*, cap: float, prev: float, base: float, max_backoff: float, rng: Random) -> float:
    return rng.uniform(0.0, cap)


def _equal(*, cap: float, prev: float, base: float, max_backoff: float, rng: Random) -> float:
    half = cap / 2
    return half + rng.uniform(0.0, half)


def _none(*, cap: float, prev: float, base: float, max_backoff: float, rng: Random) -> float:
    return cap


def _decorrelated(*, cap: float, prev: float, base: float, max_backoff: float, rng: Random) -> float:
    # AWS "decorrelated jitter": next = min(cap_ceiling, uniform(base, prev*3)). The carried
    # value (see compute_delay's caller) is this capped result, so it never runs away.
    return min(max_backoff, rng.uniform(base, prev * 3))


# pylint: enable=unused-argument


JITTER_STRATEGIES: Final[dict[str, _JitterStrategy]] = {
    "full": _full,
    "equal": _equal,
    "none": _none,
    "decorrelated": _decorrelated,
}

# The registry and the validating name list must stay in lockstep. Raised (not asserted) so
# the invariant holds even under `python -O`, which strips asserts.
if set(JITTER_STRATEGIES) != set(JITTER_NAMES):  # pragma: no cover - import-time invariant
    raise RuntimeError("JITTER_STRATEGIES and JITTER_NAMES are out of sync")


def compute_delay(policy: RetryPolicy, attempt_number: int, prev_delay: float, rng: Random) -> float:
    """Delay (seconds) to wait after ``attempt_number`` failed, before the next attempt.

    ``attempt_number`` is the 1-based number of the attempt that just failed. ``prev_delay``
    is the previous computed delay, used only by the stateful ``decorrelated`` strategy
    (seed it at ``policy.base``). The result is clamped to ``[0, max_backoff]`` as a final
    safety net — no delay is ever negative or above the cap.
    """
    cap = _cap(policy.base, policy.factor, policy.max_backoff, attempt_number)
    raw = JITTER_STRATEGIES[policy.jitter](
        cap=cap,
        prev=prev_delay,
        base=policy.base,
        max_backoff=policy.max_backoff,
        rng=rng,
    )
    return _clamp(raw, 0.0, policy.max_backoff)
