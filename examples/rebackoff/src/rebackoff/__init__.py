"""rebackoff — a tiny, dependency-free retry/backoff library.

A ``retry`` decorator and a matching ``Retrying`` context manager, in both sync and async
flavours, sharing one validated :class:`RetryPolicy`: exponential backoff with jitter,
per-exception retry predicates, a maximum attempt count, and/or an overall deadline.
"""

from __future__ import annotations

from .decorators import (
    aretry,
    retry,
)
from .errors import RetryError
from .policy import (
    JITTER_NAMES,
    RetryPolicy,
)
from .retrying import (
    AsyncRetrying,
    Attempt,
    Retrying,
)

__version__ = "0.1.0"

__all__ = [
    "retry",
    "aretry",
    "Retrying",
    "AsyncRetrying",
    "RetryPolicy",
    "RetryError",
    "Attempt",
    "JITTER_NAMES",
    "__version__",
]
