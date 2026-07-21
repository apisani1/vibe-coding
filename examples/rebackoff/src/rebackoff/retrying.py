"""The retry engine: one shared decision core, driven by a sync and an async surface.

``_BaseRetrying`` holds all the retry *decisions* — predicate, stop conditions, delay,
``RetryError`` construction — as sleepless, pure-ish methods. ``Attempt`` is a *sleepless*
per-attempt context manager that only records the outcome. The concrete surfaces
(``Retrying`` here, ``AsyncRetrying`` in the async checkpoint) differ in exactly two small
ways: the literal sleep call, and (async only) awaiting an awaitable ``before_sleep`` hook.
"""

from __future__ import annotations

import inspect
from enum import (
    Enum,
    auto,
)
from types import TracebackType
from typing import (
    Any,
    Literal,
    Optional,
)

from .backoff import compute_delay
from .errors import RetryError
from .policy import RetryPolicy

# Outcome of the attempt currently being tracked.
_PENDING = "pending"  # no attempt has run yet
_RUNNING = "running"  # an attempt has been produced but its `with` block has not exited
_SUCCESS = "success"  # the last attempt's block completed without exception
_RETRY = "retry"  # the last attempt raised a retryable exception


class _Verdict(Enum):
    START = auto()  # produce the first attempt
    STOP = auto()  # success — end iteration
    RAISE = auto()  # exhausted — raise RetryError
    SLEEP = auto()  # retry — sleep, then produce the next attempt


class Attempt:
    """One execution try, used as a context manager: ``with attempt: ...``.

    Entering does nothing; exiting records the outcome on the owning iterator and, for a
    retryable exception, suppresses it so the loop can decide whether to sleep-and-continue
    or give up. A non-retryable exception is allowed to propagate immediately.
    """

    def __init__(self, retrying: "_BaseRetrying", number: int, elapsed: float) -> None:
        self.number = number
        self.elapsed = elapsed
        self.exception: Optional[BaseException] = None
        self._retrying = retrying

    def __enter__(self) -> "Attempt":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        self.exception = exc
        if exc is None:
            self._retrying._on_success()
            return False
        if self._retrying._should_retry(exc):
            self._retrying._on_retry(exc)
            return True  # suppress — the iterator decides sleep-vs-RetryError next
        return False  # non-retryable — propagate immediately (no sleep)


class _BaseRetrying:  # pylint: disable=too-few-public-methods
    """Shared retry state and decisions. Sleepless; concrete surfaces do the waiting."""

    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy
        self._attempt_number = 0
        self._start: Optional[float] = None
        self._prev_delay = policy.base
        self._last_exc: Optional[BaseException] = None
        self._outcome = _PENDING
        self._next_delay = 0.0

    # --- decisions (shared, sleepless) ---

    def _should_retry(self, exc: BaseException) -> bool:
        # KeyboardInterrupt / SystemExit are never retried, regardless of the predicate.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            return False
        return bool(self.policy.predicate(exc))

    def _on_success(self) -> None:
        self._outcome = _SUCCESS

    def _on_retry(self, exc: BaseException) -> None:
        self._last_exc = exc
        self._outcome = _RETRY

    def _elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return self.policy.timer() - self._start

    def _past_deadline(self, pending: float = 0.0) -> bool:
        """True if the deadline is set and ``elapsed + pending`` reaches/exceeds it now."""
        return self.policy.deadline is not None and self._elapsed() + pending >= self.policy.deadline

    def _decide(self) -> _Verdict:
        """Decide what happens before the next attempt (the design's ``_advance`` step).

        Returns a verdict; the concrete surface acts on it. Pure — no sleeping, no hook.
        """
        if self._outcome == _PENDING:
            self._start = self.policy.timer()
            return _Verdict.START
        if self._outcome == _SUCCESS:
            return _Verdict.STOP
        if self._outcome == _RUNNING:  # pragma: no cover - guards misuse of the API
            raise RuntimeError("attempt was not used as a context manager (`with attempt:`)")

        # _RETRY: decide count first (no RNG draw when count-exhausted), then the deadline.
        if self.policy.max_attempts is not None and self._attempt_number >= self.policy.max_attempts:
            return _Verdict.RAISE
        delay = compute_delay(self.policy, self._attempt_number, self._prev_delay, self.policy.rng)
        # Abandon before overrun: skip a sleep predicted to end at/after the deadline (so the
        # hook does not fire either). The surface re-checks again after the hook and after the
        # sleep, so a slow hook or an oversleep can't slip a sleep or an attempt past it.
        if self._past_deadline(delay):
            return _Verdict.RAISE
        self._next_delay = delay
        self._prev_delay = delay
        return _Verdict.SLEEP

    def _make_attempt(self) -> Attempt:
        self._attempt_number += 1
        attempt = Attempt(self, self._attempt_number, self._elapsed())
        self._outcome = _RUNNING
        return attempt

    def _make_error(self) -> RetryError:
        assert self._last_exc is not None  # RAISE is only reached from the _RETRY outcome
        return RetryError(self._last_exc, self._attempt_number, self._elapsed())


class Retrying(_BaseRetrying):
    """Synchronous retry surface: an iterable of :class:`Attempt` context managers.

    Canonical use::

        for attempt in Retrying(max_attempts=5, on=ConnectionError):
            with attempt:
                result = do_thing()

    The optional outer ``with Retrying(...) as r:`` form is a bind-only wrapper (it just
    names the iterable); it never retries a body by itself.
    """

    def __init__(self, *, policy: Optional[RetryPolicy] = None, **kwargs: Any) -> None:
        super().__init__(_coerce_policy(policy, kwargs))

    def __iter__(self) -> "Retrying":
        return self

    def __next__(self) -> Attempt:
        verdict = self._decide()
        if verdict is _Verdict.STOP:
            raise StopIteration
        if verdict is _Verdict.RAISE:
            raise self._make_error() from self._last_exc
        if verdict is _Verdict.SLEEP:
            exc = self._last_exc
            assert exc is not None  # SLEEP is only reached from the _RETRY outcome
            if self.policy.before_sleep is not None:
                self.policy.before_sleep(self._attempt_number, self._next_delay, exc)
            # The hook may have consumed the budget: don't sleep past the deadline.
            if self._past_deadline(self._next_delay):
                raise self._make_error() from self._last_exc
            self.policy.sleep(self._next_delay)
            # And an oversleeping sleep must not let an attempt begin past the deadline.
            if self._past_deadline():
                raise self._make_error() from self._last_exc
        return self._make_attempt()

    def __enter__(self) -> "Retrying":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Literal[False]:
        return False


class AsyncRetrying(_BaseRetrying):
    """Asynchronous retry surface over the same decision core as :class:`Retrying`.

    Canonical use::

        async for attempt in AsyncRetrying(max_attempts=5, deadline=30.0):
            with attempt:                 # the per-attempt guard is a *sync* context manager
                result = await do_thing()

    The waiting happens here in ``__anext__`` (``await policy.asleep``), never in the
    ``with attempt:`` guard — so the guard is identical to the sync surface. An awaitable
    ``before_sleep`` hook is awaited; a plain one is simply called.
    """

    def __init__(self, *, policy: Optional[RetryPolicy] = None, **kwargs: Any) -> None:
        super().__init__(_coerce_policy(policy, kwargs))

    def __aiter__(self) -> "AsyncRetrying":
        return self

    async def __anext__(self) -> Attempt:
        verdict = self._decide()
        if verdict is _Verdict.STOP:
            raise StopAsyncIteration
        if verdict is _Verdict.RAISE:
            raise self._make_error() from self._last_exc
        if verdict is _Verdict.SLEEP:
            exc = self._last_exc
            assert exc is not None  # SLEEP is only reached from the _RETRY outcome
            if self.policy.before_sleep is not None:
                result = self.policy.before_sleep(self._attempt_number, self._next_delay, exc)
                if inspect.isawaitable(result):
                    await result
            # The hook may have consumed the budget: don't sleep past the deadline.
            if self._past_deadline(self._next_delay):
                raise self._make_error() from self._last_exc
            await self.policy.asleep(self._next_delay)
            # And an oversleeping sleep must not let an attempt begin past the deadline.
            if self._past_deadline():
                raise self._make_error() from self._last_exc
        return self._make_attempt()

    async def __aenter__(self) -> "AsyncRetrying":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Literal[False]:
        return False


def _coerce_policy(policy: Optional[RetryPolicy], kwargs: dict[str, Any]) -> RetryPolicy:
    """Accept a prebuilt ``policy=`` or build one from keyword arguments — not both."""
    if policy is not None:
        if kwargs:
            raise TypeError("pass either policy=... or keyword arguments, not both")
        return policy
    return RetryPolicy(**kwargs)
