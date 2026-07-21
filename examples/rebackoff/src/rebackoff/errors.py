"""Exceptions raised by rebackoff."""

from __future__ import annotations


class RetryError(Exception):
    """Raised when retries are exhausted without a successful attempt.

    The last real exception is attached as ``__cause__`` (via ``raise ... from``) and is
    also available as :attr:`last_exception`, so callers can inspect what actually failed
    rather than only learning that retrying gave up.
    """

    def __init__(self, last_exception: BaseException, attempts: int, elapsed: float) -> None:
        self.last_exception = last_exception
        self.attempts = attempts
        self.elapsed = elapsed
        super().__init__(
            f"retries exhausted after {attempts} attempt(s) in {elapsed:.3f}s; " f"last error: {last_exception!r}"
        )
