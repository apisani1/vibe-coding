"""RetryPolicy validates at construction, normalizes `on`, and carries the right defaults."""

import asyncio
import time

import pytest

from rebackoff.policy import (
    DEFAULT_BASE,
    DEFAULT_FACTOR,
    DEFAULT_JITTER,
    DEFAULT_MAX_BACKOFF,
    RetryPolicy,
)


# --- AC13: invalid configs raise ValueError AT CONSTRUCTION, not mid-retry ---

@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # no effective stop condition (neither max_attempts nor deadline)
        {"max_attempts": 0},
        {"max_attempts": -1},
        {"max_attempts": 3, "base": -0.1},
        {"max_attempts": 3, "factor": 0.5},
        {"max_attempts": 3, "max_backoff": 0},
        {"max_attempts": 3, "max_backoff": -5},
        {"deadline": 0},
        {"deadline": -1},
        {"max_attempts": 3, "jitter": "bogus"},
        # non-finite bounds (inf/NaN) must be rejected at construction
        {"deadline": float("inf")},
        {"deadline": float("nan")},
        {"max_attempts": 3, "base": float("inf")},
        {"max_attempts": 3, "base": float("nan")},
        {"max_attempts": 3, "factor": float("inf")},
        {"max_attempts": 3, "factor": float("nan")},
        {"max_attempts": 3, "max_backoff": float("inf")},
        {"max_attempts": 3, "max_backoff": float("nan")},
        # max_attempts must be a genuine positive int — reject NaN/inf/float/bool
        {"max_attempts": float("inf")},
        {"max_attempts": float("nan")},
        {"max_attempts": 3.0},
        {"max_attempts": True},
    ],
)
def test_invalid_config_raises_valueerror_at_construction(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_max_attempts_alone_is_valid():
    RetryPolicy(max_attempts=1)  # a single stop condition is enough


def test_deadline_alone_is_valid():
    RetryPolicy(deadline=0.5)


# --- AC9 (a/b/c): `on` normalization for type / tuple / callable ---

def test_on_single_type():
    policy = RetryPolicy(max_attempts=3, on=ConnectionError)
    assert policy.predicate(ConnectionError()) is True
    assert policy.predicate(ValueError()) is False


def test_on_tuple_of_types():
    policy = RetryPolicy(max_attempts=3, on=(ConnectionError, TimeoutError))
    assert policy.predicate(ConnectionError()) is True
    assert policy.predicate(TimeoutError()) is True
    assert policy.predicate(ValueError()) is False


def test_on_callable_predicate():
    policy = RetryPolicy(max_attempts=3, on=lambda exc: isinstance(exc, KeyError))
    assert policy.predicate(KeyError()) is True
    assert policy.predicate(ValueError()) is False


def test_on_defaults_to_exception():
    policy = RetryPolicy(max_attempts=3)
    assert policy.predicate(ValueError()) is True
    assert policy.predicate(RuntimeError()) is True
    # BaseExceptions outside Exception are not matched by the default predicate.
    assert policy.predicate(KeyboardInterrupt()) is False


def test_on_bad_tuple_rejected():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=3, on=(ConnectionError, "not-a-type"))


# --- Defaults ---

def test_numeric_and_seam_defaults():
    policy = RetryPolicy(max_attempts=3)
    assert policy.base == DEFAULT_BASE == 0.1
    assert policy.factor == DEFAULT_FACTOR == 2.0
    assert policy.max_backoff == DEFAULT_MAX_BACKOFF == 30.0
    assert policy.jitter == DEFAULT_JITTER == "full"
    assert policy.timer is time.monotonic
    assert policy.sleep is time.sleep
    assert policy.asleep is asyncio.sleep


def test_policy_is_frozen():
    policy = RetryPolicy(max_attempts=3)
    with pytest.raises(Exception):
        policy.max_attempts = 9  # type: ignore[misc]
