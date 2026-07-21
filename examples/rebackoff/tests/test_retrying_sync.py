"""The sync retry engine: attempts, stop conditions, deadline, predicate, hook."""

import pytest

from rebackoff.errors import RetryError
from rebackoff.policy import RetryPolicy
from rebackoff.retrying import Retrying


def _policy(sleep, **kwargs):
    kwargs.setdefault("jitter", "none")
    return RetryPolicy(sleep=sleep, **kwargs)


# --- AC1: success on the Nth attempt ---

def test_success_on_nth_attempt(recording_sleep):
    policy = _policy(recording_sleep, max_attempts=5)
    calls = []
    result = None
    for attempt in Retrying(policy=policy):
        with attempt:
            calls.append(attempt.number)
            if len(calls) < 3:
                raise ConnectionError("transient")
            result = "ok"
    assert result == "ok"
    assert len(calls) == 3  # invoked exactly until success
    assert len(recording_sleep.calls) == 2  # slept between the 3 attempts


def test_success_on_last_permitted_attempt(recording_sleep):
    # AC1's literal boundary: succeed on exactly the max_attempts-th attempt. Guards a
    # `>=`→`>` slip in the count check that would raise RetryError just before success.
    policy = _policy(recording_sleep, max_attempts=3)
    calls = []
    result = None
    for attempt in Retrying(policy=policy):
        with attempt:
            calls.append(attempt.number)
            if len(calls) < 3:
                raise ConnectionError("transient")
            result = "ok"
    assert result == "ok"
    assert len(calls) == 3  # invoked exactly max_attempts times
    assert len(recording_sleep.calls) == 2


# --- AC2: exhaustion → RetryError with __cause__ = last exception ---

def test_exhaustion_raises_retryerror_with_cause(recording_sleep):
    policy = _policy(recording_sleep, max_attempts=3)
    calls = []
    last = None
    with pytest.raises(RetryError) as excinfo:
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                last = ConnectionError(f"fail-{len(calls)}")
                raise last
    assert len(calls) == 3
    assert excinfo.value.attempts == 3
    assert excinfo.value.__cause__ is last
    assert excinfo.value.last_exception is last
    assert len(recording_sleep.calls) == 2


# --- AC3: non-retryable exception propagates immediately, no sleep ---

def test_non_retryable_propagates_without_sleep(recording_sleep):
    policy = _policy(recording_sleep, max_attempts=5, on=ConnectionError)
    calls = []
    with pytest.raises(ValueError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ValueError("not retryable")
    assert len(calls) == 1
    assert recording_sleep.calls == []


# --- AC7: deadline — abandon before overrun, no attempt after the deadline ---

def test_deadline_abandons_before_overrun(clock, clock_sleep):
    # delays (none jitter): 0.1, 0.2, 0.4, 0.8. deadline 1.0.
    policy = RetryPolicy(deadline=1.0, jitter="none", base=0.1, factor=2.0, sleep=clock_sleep, timer=clock.time)
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    # attempt4 fails at elapsed 0.7; 0.7 + 0.8 = 1.5 >= 1.0 → abandon.
    assert len(calls) == 4
    assert clock_sleep.calls == [0.1, 0.2, 0.4]
    assert clock.now == pytest.approx(0.7)  # never slept past the deadline


def test_deadline_boundary_equal_abandons(clock, clock_sleep):
    # deadline exactly equals elapsed+delay on the 2nd decision → must abandon (>=).
    policy = RetryPolicy(deadline=0.3, jitter="none", base=0.1, factor=2.0, sleep=clock_sleep, timer=clock.time)
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    # attempt2 fails at elapsed 0.1; 0.1 + 0.2 = 0.3 >= 0.3 → abandon.
    assert len(calls) == 2
    assert clock_sleep.calls == [0.1]


def test_deadline_rechecked_after_oversleep(clock):
    # The pre-sleep prediction says the next attempt fits, but a sleep that overshoots the
    # requested delay must not let that attempt actually begin past the deadline.
    def oversleep(delay):
        clock.advance(delay + 1.0)  # overshoot by a full second

    policy = RetryPolicy(deadline=1.0, jitter="none", base=0.1, sleep=oversleep, timer=clock.time)
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    # attempt 1 fails at elapsed 0; predicted 0 + 0.1 < 1.0 → sleep, but it overshoots to
    # 1.1; the post-sleep recheck sees elapsed >= 1.0 → abandon before attempt 2.
    assert len(calls) == 1


def test_deadline_rechecked_after_slow_hook(clock, clock_sleep):
    # A slow before_sleep hook (here it burns 5s of the budget) must likewise not let a new
    # attempt begin past the deadline.
    def slow_hook(number, delay, exc):
        clock.advance(5.0)

    policy = RetryPolicy(
        deadline=1.0, jitter="none", base=0.1, sleep=clock_sleep, timer=clock.time, before_sleep=slow_hook
    )
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    assert len(calls) == 1
    assert clock_sleep.calls == []  # the hook blew the budget → must NOT sleep past the deadline


def test_before_sleep_not_called_on_deadline_abandon(clock, clock_sleep):
    # When _decide abandons pre-hook (predicted overrun), the hook must NOT fire for that
    # decision — only for the sleeps that actually happen.
    hook_calls = []
    policy = RetryPolicy(
        deadline=0.3,
        jitter="none",
        base=0.1,
        factor=2.0,
        sleep=clock_sleep,
        timer=clock.time,
        before_sleep=lambda n, d, e: hook_calls.append(n),
    )
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    # attempt2 fails at elapsed 0.1; 0.1 + 0.2 >= 0.3 → abandon in _decide, no 2nd hook call.
    assert len(calls) == 2
    assert clock_sleep.calls == [0.1]
    assert hook_calls == [1]


def test_fast_hook_does_not_false_abandon(clock, clock_sleep):
    # A fast hook (doesn't touch the clock) with a comfortable deadline must not trip the
    # post-hook gate: all attempts proceed and the hook fires before each sleep.
    hook_calls = []
    policy = RetryPolicy(
        max_attempts=4,
        deadline=100.0,
        jitter="none",
        base=0.1,
        factor=2.0,
        sleep=clock_sleep,
        timer=clock.time,
        before_sleep=lambda n, d, e: hook_calls.append(n),
    )
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    assert len(calls) == 4  # deadline never false-abandoned
    assert hook_calls == [1, 2, 3]
    assert clock_sleep.calls == [0.1, 0.2, 0.4]


# --- AC8: max_attempts and deadline both set → first to trip wins ---

def test_max_attempts_trips_first(clock, clock_sleep):
    policy = RetryPolicy(
        max_attempts=2, deadline=100.0, jitter="none", base=0.1, sleep=clock_sleep, timer=clock.time
    )
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    assert len(calls) == 2  # stopped on count, deadline untouched


def test_deadline_trips_first(clock, clock_sleep):
    policy = RetryPolicy(
        max_attempts=100, deadline=0.3, jitter="none", base=0.1, factor=2.0, sleep=clock_sleep, timer=clock.time
    )
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(attempt.number)
                raise ConnectionError("boom")
    assert len(calls) == 2  # stopped on deadline well before 100 attempts


# --- AC9: predicate forms (type / tuple / callable) ---

@pytest.mark.parametrize(
    "on, retryable_exc, fatal_exc",
    [
        (ConnectionError, ConnectionError, ValueError),
        ((ConnectionError, TimeoutError), TimeoutError, ValueError),
        (lambda e: isinstance(e, KeyError), KeyError, ValueError),
    ],
)
def test_predicate_forms(recording_sleep, on, retryable_exc, fatal_exc):
    # retryable exception → retried to exhaustion
    policy = _policy(recording_sleep, max_attempts=2, on=on)
    calls = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(1)
                raise retryable_exc()
    assert len(calls) == 2

    # non-matching exception → propagates on the first attempt
    calls2 = []
    with pytest.raises(fatal_exc):
        for attempt in Retrying(policy=_policy(recording_sleep, max_attempts=2, on=on)):
            with attempt:
                calls2.append(1)
                raise fatal_exc()
    assert len(calls2) == 1


# --- AC9: KeyboardInterrupt / SystemExit never retried, even with a permissive predicate ---

@pytest.mark.parametrize("fatal", [KeyboardInterrupt, SystemExit])
def test_ki_se_never_retried_even_with_permissive_predicate(recording_sleep, fatal):
    policy = _policy(recording_sleep, max_attempts=5, on=lambda e: True)
    calls = []
    with pytest.raises(fatal):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(1)
                raise fatal()
    assert len(calls) == 1
    assert recording_sleep.calls == []


# --- AC10: context-manager outcomes + bind-only wrapper + attempt.exception ---

def test_context_manager_success_and_attempt_exception(recording_sleep):
    policy = _policy(recording_sleep, max_attempts=5)
    seen = []
    for attempt in Retrying(policy=policy):
        with attempt:
            seen.append(attempt)
            if attempt.number < 2:
                raise ConnectionError("x")
    assert isinstance(seen[0].exception, ConnectionError)  # first attempt failed
    assert seen[-1].exception is None  # last attempt succeeded


def test_bind_only_context_manager_does_not_swallow(recording_sleep):
    policy = _policy(recording_sleep, max_attempts=3)
    r = Retrying(policy=policy)
    with r as bound:
        assert bound is r
    # a bind-only wrapper must not suppress exceptions from its body
    with pytest.raises(RuntimeError):
        with Retrying(policy=_policy(recording_sleep, max_attempts=3)):
            raise RuntimeError("propagates")


# --- AC12: before_sleep hook fires before each sleep, never after the final failure ---

def test_before_sleep_hook_timing(recording_sleep):
    hook_calls = []
    policy = _policy(recording_sleep, max_attempts=3, before_sleep=lambda n, d, e: hook_calls.append((n, d, e)))
    raised = []
    with pytest.raises(RetryError):
        for attempt in Retrying(policy=policy):
            with attempt:
                exc = ConnectionError(f"e{len(raised) + 1}")
                raised.append(exc)
                raise exc
    assert len(hook_calls) == 2  # exactly N-1, never after the final failed attempt
    assert [h[0] for h in hook_calls] == [1, 2]  # the failed attempt's number
    assert [h[1] for h in hook_calls] == recording_sleep.calls  # delay == the slept value
    # the hook receives the SPECIFIC triggering exception instance (identity, not just type)
    assert hook_calls[0][2] is raised[0]
    assert hook_calls[1][2] is raised[1]


def test_before_sleep_raising_propagates_unwrapped(recording_sleep):
    # A hook that raises is the user's bug, not a retryable condition: the exception
    # propagates unwrapped (no RetryError), and no further attempt runs.
    class HookBoom(Exception):
        pass

    def hook(number, delay, exc):
        raise HookBoom("hook failed")

    calls = []
    policy = _policy(recording_sleep, max_attempts=3, before_sleep=hook)
    with pytest.raises(HookBoom):
        for attempt in Retrying(policy=policy):
            with attempt:
                calls.append(1)
                raise ConnectionError("x")
    assert len(calls) == 1  # only the first attempt ran; the hook raised before the 2nd
    assert recording_sleep.calls == []  # hook raised before the sleep


def test_before_sleep_hook_not_called_on_first_success(recording_sleep):
    hook_calls = []
    policy = _policy(recording_sleep, max_attempts=3, before_sleep=lambda n, d, e: hook_calls.append(n))
    for attempt in Retrying(policy=policy):
        with attempt:
            pass  # succeeds immediately
    assert hook_calls == []


def test_reject_policy_and_kwargs_together():
    with pytest.raises(TypeError):
        Retrying(policy=RetryPolicy(max_attempts=3), max_attempts=5)
