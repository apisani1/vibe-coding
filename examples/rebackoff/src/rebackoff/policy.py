"""The immutable retry policy: the single validated source of truth for a retry.

A :class:`RetryPolicy` is built once (validated at construction) and reused across many
calls. The four public surfaces (``retry``, ``aretry``, ``Retrying``, ``AsyncRetrying``)
all accept the same keyword arguments, construct one policy, and thread it into a fresh
per-call iterator — construction separated from use.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from dataclasses import (
    dataclass,
    field,
)
from typing import (
    Final,
    Optional,
    Union,
)

# Canonical jitter strategy names. Owned here (the validating module); ``backoff`` builds
# its implementation registry against exactly these names. Kept here so ``policy`` has no
# dependency on ``backoff`` (the dependency runs the other way).
JITTER_NAMES: Final = ("full", "equal", "none", "decorrelated")

DEFAULT_BASE: Final = 0.1
DEFAULT_FACTOR: Final = 2.0
DEFAULT_MAX_BACKOFF: Final = 30.0
DEFAULT_JITTER: Final = "full"

# A shared default RNG. Documented as not thread-safe when a single policy is reused across
# concurrent calls; deterministic tests inject their own seeded ``random.Random``.
_DEFAULT_RNG: Final = random.Random()

#: A predicate deciding whether a raised exception is retryable.
RetryPredicate = Callable[[BaseException], bool]

#: What the user may pass as ``on``: an exception type, a tuple of types, or a predicate.
OnType = Union[type[BaseException], tuple[type[BaseException], ...], RetryPredicate]

#: The ``before_sleep`` hook signature: ``(attempt_number, delay, exception)``. It may
#: return ``None`` or (on the async surface) an awaitable.
BeforeSleep = Callable[[int, float, BaseException], object]


def _normalize_on(on: OnType) -> RetryPredicate:
    """Turn the user's ``on`` into a uniform ``predicate(exc) -> bool``.

    A type or tuple of types becomes an ``isinstance`` check; a callable is used as-is.
    The predicate does *not* special-case ``KeyboardInterrupt``/``SystemExit`` — that
    hard-exclude lives in the retry engine's ``_should_retry`` so it holds regardless of
    the predicate the user supplies.
    """
    if isinstance(on, type):
        if not issubclass(on, BaseException):
            raise ValueError("on type must be an exception type")
        return lambda exc: isinstance(exc, on)
    if isinstance(on, tuple):
        if not on or not all(isinstance(t, type) and issubclass(t, BaseException) for t in on):
            raise ValueError("on tuple must contain only exception types")
        return lambda exc: isinstance(exc, on)
    if callable(on):
        return on
    raise ValueError("on must be an exception type, a tuple of exception types, or a callable")


@dataclass(frozen=True)
class RetryPolicy:  # pylint: disable=too-many-instance-attributes
    """Immutable, validated retry configuration.

    Validation happens in ``__post_init__`` so a contradictory policy raises ``ValueError``
    at construction time — never mid-retry.
    """

    max_attempts: Optional[int] = None
    deadline: Optional[float] = None
    base: float = DEFAULT_BASE
    factor: float = DEFAULT_FACTOR
    max_backoff: float = DEFAULT_MAX_BACKOFF
    jitter: str = DEFAULT_JITTER
    on: OnType = Exception
    before_sleep: Optional[BeforeSleep] = None
    timer: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    asleep: Callable[[float], Awaitable[object]] = asyncio.sleep
    rng: random.Random = _DEFAULT_RNG

    # Derived: the normalized retry predicate. Not an init argument; set in __post_init__.
    predicate: RetryPredicate = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.max_attempts is None and self.deadline is None:
            raise ValueError("at least one of max_attempts or deadline must be set")
        if self.max_attempts is not None:
            # Must be a genuine int: a float NaN/inf would slip past `< 1` (NaN fails every
            # comparison; inf never trips the count check) and re-enable unbounded retrying;
            # bool is an int subclass we reject to avoid True silently meaning 1.
            if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
                raise ValueError("max_attempts must be an integer")
            if self.max_attempts < 1:
                raise ValueError("max_attempts must be >= 1")
        # Non-finite bounds (inf/NaN) must be rejected: a NaN slips past every `<`/`<=`
        # comparison, and an infinite deadline never trips, silently re-enabling the
        # unbounded retrying the "at least one effective bound" rule forbids.
        if self.deadline is not None and (not math.isfinite(self.deadline) or self.deadline <= 0):
            raise ValueError("deadline must be a positive, finite number")
        if not math.isfinite(self.base) or self.base < 0:
            raise ValueError("base must be a non-negative, finite number")
        if not math.isfinite(self.factor) or self.factor < 1:
            raise ValueError("factor must be >= 1 and finite")
        if not math.isfinite(self.max_backoff) or self.max_backoff <= 0:
            raise ValueError("max_backoff must be a positive, finite number")
        if self.jitter not in JITTER_NAMES:
            raise ValueError(f"unknown jitter strategy {self.jitter!r}; valid: {JITTER_NAMES}")
        # frozen dataclass: bypass the immutability guard to set the derived field once.
        object.__setattr__(self, "predicate", _normalize_on(self.on))
