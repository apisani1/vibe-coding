"""The sync `@retry` decorator: behavior parity, identity preservation, passthrough."""

import pytest

from rebackoff.decorators import retry
from rebackoff.errors import RetryError
from rebackoff.policy import RetryPolicy
from rebackoff.retrying import Retrying


# --- AC1-3 via the decorator surface ---

def test_decorator_success_on_nth(recording_sleep):
    calls = []

    @retry(max_attempts=5, jitter="none", sleep=recording_sleep)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3
    assert len(recording_sleep.calls) == 2


def test_decorator_exhaustion_raises_retryerror(recording_sleep):
    @retry(max_attempts=3, jitter="none", sleep=recording_sleep)
    def always_fail():
        raise ConnectionError("nope")

    with pytest.raises(RetryError):
        always_fail()


def test_decorator_non_retryable_propagates(recording_sleep):
    calls = []

    @retry(max_attempts=5, on=ConnectionError, sleep=recording_sleep)
    def fatal():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        fatal()
    assert len(calls) == 1
    assert recording_sleep.calls == []


# --- AC15: identity preservation + passthrough ---

def test_decorator_preserves_identity(recording_sleep):
    def add(a, b, *, c=0):
        """Sum with an optional keyword addend."""
        return a + b + c

    wrapped = retry(max_attempts=3, sleep=recording_sleep)(add)
    assert wrapped.__name__ == "add"
    assert wrapped.__doc__ == "Sum with an optional keyword addend."
    assert wrapped.__wrapped__ is add


def test_decorator_passes_through_args_and_return(recording_sleep):
    seen = {}

    @retry(max_attempts=3, sleep=recording_sleep)
    def echo(a, b, *, c):
        seen["args"] = (a, b)
        seen["c"] = c
        return (a, b, c)

    assert echo(1, 2, c=3) == (1, 2, 3)
    assert seen == {"args": (1, 2), "c": 3}


# --- AC10: decorator ↔ Retrying parity ---

def test_decorator_and_context_manager_parity_success():
    def make():
        state = {"n": 0}

        def fn():
            state["n"] += 1
            if state["n"] < 3:
                raise ConnectionError("x")
            return "done"

        return fn

    sleeps_dec = []
    sleeps_ctx = []

    dec_fn = retry(max_attempts=5, jitter="none", sleep=sleeps_dec.append)(make())
    result_dec = dec_fn()

    policy = RetryPolicy(max_attempts=5, jitter="none", sleep=sleeps_ctx.append)
    fn = make()
    result_ctx = None
    for attempt in Retrying(policy=policy):
        with attempt:
            result_ctx = fn()

    assert result_dec == result_ctx == "done"
    assert sleeps_dec == sleeps_ctx == [pytest.approx(0.1), pytest.approx(0.2)]


def test_decorator_and_context_manager_parity_exhaustion():
    @retry(max_attempts=3, jitter="none", sleep=lambda d: None)
    def dec_fail():
        raise ConnectionError("x")

    with pytest.raises(RetryError) as dec_err:
        dec_fail()

    policy = RetryPolicy(max_attempts=3, jitter="none", sleep=lambda d: None)
    with pytest.raises(RetryError) as ctx_err:
        for attempt in Retrying(policy=policy):
            with attempt:
                raise ConnectionError("x")

    assert dec_err.value.attempts == ctx_err.value.attempts == 3
