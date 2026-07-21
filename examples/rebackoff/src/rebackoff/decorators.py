"""The decorator surfaces: thin wrappers that drive a fresh iterator per call."""

from __future__ import annotations

from collections.abc import (
    Awaitable,
    Callable,
)
from functools import wraps
from typing import (
    Any,
    Optional,
    ParamSpec,
    TypeVar,
)

from .policy import RetryPolicy
from .retrying import (
    AsyncRetrying,
    Retrying,
    _coerce_policy,
)

P = ParamSpec("P")
R = TypeVar("R")


def retry(*, policy: Optional[RetryPolicy] = None, **kwargs: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a sync callable so it is retried per the policy.

    Accepts either a prebuilt ``policy=`` or the same keyword arguments as
    :class:`~rebackoff.policy.RetryPolicy` (e.g. ``max_attempts``, ``deadline``, ``on``).
    """
    resolved = _coerce_policy(policy, kwargs)

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kw: P.kwargs) -> R:
            for attempt in Retrying(policy=resolved):
                with attempt:
                    return fn(*args, **kw)
            raise AssertionError("unreachable: the loop returns on success or raises")  # pragma: no cover

        return wrapper

    return decorator


def aretry(
    *, policy: Optional[RetryPolicy] = None, **kwargs: Any
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorate a coroutine function so it is retried per the policy (async surface).

    Accepts either a prebuilt ``policy=`` or the same keyword arguments as
    :class:`~rebackoff.policy.RetryPolicy`.
    """
    resolved = _coerce_policy(policy, kwargs)

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kw: P.kwargs) -> R:
            async for attempt in AsyncRetrying(policy=resolved):
                with attempt:
                    return await fn(*args, **kw)
            raise AssertionError("unreachable: the loop returns on success or raises")  # pragma: no cover

        return wrapper

    return decorator
