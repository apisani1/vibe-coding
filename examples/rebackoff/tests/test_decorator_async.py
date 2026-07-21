"""The async `@aretry` decorator: behavior over coroutines + identity preservation."""

import asyncio
import inspect

import pytest

from rebackoff.decorators import aretry
from rebackoff.errors import RetryError


# --- AC11 via @aretry: success / exhaustion / non-retryable ---

def test_aretry_success_on_nth(fake_asleep):
    calls = []

    @aretry(max_attempts=5, jitter="none", asleep=fake_asleep)
    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert len(calls) == 3
    assert len(fake_asleep.calls) == 2


def test_aretry_exhaustion_raises(fake_asleep):
    @aretry(max_attempts=3, jitter="none", asleep=fake_asleep)
    async def always_fail():
        raise ConnectionError("nope")

    with pytest.raises(RetryError) as excinfo:
        asyncio.run(always_fail())
    assert excinfo.value.attempts == 3


def test_aretry_non_retryable_propagates(fake_asleep):
    calls = []

    @aretry(max_attempts=5, on=ConnectionError, asleep=fake_asleep)
    async def fatal():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        asyncio.run(fatal())
    assert len(calls) == 1
    assert fake_asleep.calls == []


# --- AC15 for coroutines: identity + passthrough, wrapper is a coroutine function ---

def test_aretry_preserves_identity(fake_asleep):
    async def add(a, b, *, c=0):
        """Async sum with an optional keyword addend."""
        return a + b + c

    wrapped = aretry(max_attempts=3, asleep=fake_asleep)(add)
    assert wrapped.__name__ == "add"
    assert wrapped.__doc__ == "Async sum with an optional keyword addend."
    assert wrapped.__wrapped__ is add
    assert inspect.iscoroutinefunction(wrapped)


def test_aretry_passes_through_args_and_return(fake_asleep):
    seen = {}

    @aretry(max_attempts=3, asleep=fake_asleep)
    async def echo(a, b, *, c):
        seen["args"] = (a, b)
        seen["c"] = c
        return (a, b, c)

    assert asyncio.run(echo(1, 2, c=3)) == (1, 2, 3)
    assert seen == {"args": (1, 2), "c": 3}
