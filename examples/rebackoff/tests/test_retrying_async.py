"""The async retry engine: same contracts as sync, over coroutines, never blocking."""

import asyncio
import time

import pytest

from rebackoff.errors import RetryError
from rebackoff.policy import RetryPolicy
from rebackoff.retrying import AsyncRetrying


# --- AC11 → AC1: success on the Nth attempt (coroutine) ---

def test_async_success_on_nth(fake_asleep):
    calls = []

    async def scenario():
        policy = RetryPolicy(max_attempts=5, jitter="none", asleep=fake_asleep)
        result = None
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(1)
                if len(calls) < 3:
                    raise ConnectionError("transient")
                result = "ok"
        return result

    assert asyncio.run(scenario()) == "ok"
    assert len(calls) == 3
    assert len(fake_asleep.calls) == 2


def test_async_success_on_last_permitted_attempt(fake_asleep):
    # AC1 boundary on the async surface: succeed on exactly the max_attempts-th attempt.
    calls = []

    async def scenario():
        policy = RetryPolicy(max_attempts=3, jitter="none", asleep=fake_asleep)
        result = None
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                if len(calls) < 3:
                    raise ConnectionError("transient")
                result = "ok"
        return result

    assert asyncio.run(scenario()) == "ok"
    assert len(calls) == 3
    assert len(fake_asleep.calls) == 2


# --- AC11 → AC2: exhaustion → RetryError with __cause__ ---

def test_async_exhaustion_raises_with_cause(fake_asleep):
    async def scenario():
        policy = RetryPolicy(max_attempts=3, jitter="none", asleep=fake_asleep)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                raise ConnectionError("nope")

    with pytest.raises(RetryError) as excinfo:
        asyncio.run(scenario())
    assert excinfo.value.attempts == 3
    assert isinstance(excinfo.value.__cause__, ConnectionError)


# --- AC11 → AC3: non-retryable propagates, no sleep ---

def test_async_non_retryable_propagates(fake_asleep):
    calls = []

    async def scenario():
        policy = RetryPolicy(max_attempts=5, on=ConnectionError, asleep=fake_asleep)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(1)
                raise ValueError("not retryable")

    with pytest.raises(ValueError):
        asyncio.run(scenario())
    assert len(calls) == 1
    assert fake_asleep.calls == []


# --- AC11: the async path awaits asleep and NEVER calls time.sleep ---

def test_async_never_blocks_the_loop(monkeypatch, fake_asleep):
    def boom(_delay):
        raise AssertionError("time.sleep must not be called on the async path")

    monkeypatch.setattr(time, "sleep", boom)
    calls = []

    async def scenario():
        policy = RetryPolicy(max_attempts=3, jitter="none", asleep=fake_asleep)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(1)
                raise ConnectionError("boom")

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert len(calls) == 3
    assert fake_asleep.calls == [pytest.approx(0.1), pytest.approx(0.2)]


# --- AC11 → AC7: deadline abandon-before-overrun (async) ---

def test_async_deadline_abandons(clock, async_clock_sleep):
    calls = []

    async def scenario():
        policy = RetryPolicy(
            deadline=1.0, jitter="none", base=0.1, factor=2.0, asleep=async_clock_sleep, timer=clock.time
        )
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(1)
                raise ConnectionError("boom")

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert len(calls) == 4
    assert async_clock_sleep.calls == [0.1, 0.2, 0.4]
    assert clock.now == pytest.approx(0.7)


def test_async_deadline_rechecked_after_oversleep(clock):
    # Async counterpart: an oversleeping asleep must not let an attempt start past the deadline.
    async def oversleep(delay):
        clock.advance(delay + 1.0)

    calls = []

    async def scenario():
        policy = RetryPolicy(deadline=1.0, jitter="none", base=0.1, asleep=oversleep, timer=clock.time)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert len(calls) == 1


def test_async_deadline_rechecked_after_slow_hook(clock, async_clock_sleep):
    # Async awaitable before_sleep hook that burns the budget must not let a new attempt
    # begin past the deadline (exercises the awaited-hook branch + the post-wait recheck).
    async def slow_hook(number, delay, exc):
        clock.advance(5.0)

    calls = []

    async def scenario():
        policy = RetryPolicy(
            deadline=1.0,
            jitter="none",
            base=0.1,
            asleep=async_clock_sleep,
            timer=clock.time,
            before_sleep=slow_hook,
        )
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert len(calls) == 1
    assert async_clock_sleep.calls == []  # hook blew the budget → must NOT sleep past the deadline


# --- AC11 → AC10: async context-manager bind-only wrapper ---

def test_async_bind_only_context_manager(fake_asleep):
    async def scenario():
        policy = RetryPolicy(max_attempts=3, asleep=fake_asleep)
        retryer = AsyncRetrying(policy=policy)
        async with retryer as bound:
            assert bound is retryer

    asyncio.run(scenario())


# --- AC12 (async): awaitable hook is awaited; plain hook is called; not after final failure ---

def test_async_awaitable_hook_is_awaited(fake_asleep):
    events = []
    raised = []

    async def hook(number, delay, exc):
        events.append((number, delay, exc))

    async def scenario():
        policy = RetryPolicy(max_attempts=3, jitter="none", asleep=fake_asleep, before_sleep=hook)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                exc = ConnectionError(f"e{len(raised) + 1}")
                raised.append(exc)
                raise exc

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert [e[0] for e in events] == [1, 2]  # awaited once per sleep, N-1, none after the last
    assert [e[1] for e in events] == fake_asleep.calls  # delay == the awaited value
    # the awaited hook receives the specific triggering exception instance (identity)
    assert events[0][2] is raised[0]
    assert events[1][2] is raised[1]


def test_async_before_sleep_raising_propagates_unwrapped(fake_asleep):
    class HookBoom(Exception):
        pass

    async def hook(number, delay, exc):
        raise HookBoom("hook failed")

    calls = []

    async def scenario():
        policy = RetryPolicy(max_attempts=3, jitter="none", asleep=fake_asleep, before_sleep=hook)
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                calls.append(1)
                raise ConnectionError("x")

    with pytest.raises(HookBoom):
        asyncio.run(scenario())
    assert len(calls) == 1  # only the first attempt ran
    assert fake_asleep.calls == []  # hook raised before the await-sleep


def test_async_plain_hook_is_called(fake_asleep):
    events = []

    async def scenario():
        policy = RetryPolicy(
            max_attempts=3, jitter="none", asleep=fake_asleep, before_sleep=lambda n, d, e: events.append(n)
        )
        async for attempt in AsyncRetrying(policy=policy):
            with attempt:
                raise ConnectionError("boom")

    with pytest.raises(RetryError):
        asyncio.run(scenario())
    assert events == [1, 2]
