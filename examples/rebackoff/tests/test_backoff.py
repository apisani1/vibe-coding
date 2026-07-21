"""Backoff/jitter math: exact under a seeded RNG, correctly capped, never out of bounds."""

import random
import time

import pytest

from rebackoff.backoff import (
    JITTER_STRATEGIES,
    compute_delay,
)
from rebackoff.policy import (
    JITTER_NAMES,
    RetryPolicy,
)

SEED = 20260719
BASE = 0.1
FACTOR = 2.0
MAX_BACKOFF = 30.0


def _policy(jitter):
    return RetryPolicy(max_attempts=100, base=BASE, factor=FACTOR, max_backoff=MAX_BACKOFF, jitter=jitter)


def _cap(n):
    return min(MAX_BACKOFF, BASE * FACTOR ** (n - 1))


def test_registry_matches_valid_names():
    assert set(JITTER_STRATEGIES) == set(JITTER_NAMES)


# --- AC4: jitter="none" reproduces the exact capped exponential sequence ---

def test_none_sequence_is_exact_capped_exponential():
    policy = _policy("none")
    rng = random.Random(SEED)  # unused by "none", but pass a real one
    produced = [compute_delay(policy, n, BASE, rng) for n in range(1, 9)]
    expected = [BASE * FACTOR ** (n - 1) for n in range(1, 9)]
    assert produced == expected  # dyadic scaling of 0.1 by powers of two → exact equality
    # human-readable anchor
    assert produced[0] == pytest.approx(0.1)
    assert produced[7] == pytest.approx(12.8)


def test_none_saturates_at_max_backoff():
    policy = _policy("none")
    rng = random.Random(SEED)
    # 0.1 * 2**9 = 51.2 > 30.0 → capped
    assert compute_delay(policy, 10, BASE, rng) == MAX_BACKOFF


# --- AC5: per-strategy bounds + exact reproduction under a seeded RNG ---

def test_full_jitter_matches_seed_and_bounds():
    policy = _policy("full")
    rng = random.Random(SEED)
    mirror = random.Random(SEED)
    for n in range(1, 8):
        cap = _cap(n)
        got = compute_delay(policy, n, BASE, rng)
        assert got == mirror.uniform(0.0, cap)  # exact same draw sequence
        assert 0.0 <= got <= cap


def test_equal_jitter_matches_seed_and_bounds():
    policy = _policy("equal")
    rng = random.Random(SEED)
    mirror = random.Random(SEED)
    for n in range(1, 8):
        cap = _cap(n)
        half = cap / 2
        got = compute_delay(policy, n, BASE, rng)
        assert got == half + mirror.uniform(0.0, half)
        assert half <= got <= cap


def test_decorrelated_jitter_matches_seed_and_bounds():
    policy = _policy("decorrelated")
    rng = random.Random(SEED)
    mirror = random.Random(SEED)
    prev = BASE
    mirror_prev = BASE
    for n in range(1, 12):
        got = compute_delay(policy, n, prev, rng)
        expected = min(MAX_BACKOFF, mirror.uniform(BASE, mirror_prev * 3))
        assert got == expected
        assert BASE <= got <= MAX_BACKOFF
        # carried state is the (capped) recurrence output, seeding the next draw
        prev = got
        mirror_prev = expected


# --- AC6: every delay clamped to [0, max_backoff]; never negative, never over cap ---

@pytest.mark.parametrize("jitter", list(JITTER_NAMES))
def test_delay_never_out_of_bounds(jitter):
    policy = _policy(jitter)
    rng = random.Random(SEED)
    prev = BASE
    for n in range(1, 13):
        got = compute_delay(policy, n, prev, rng)
        assert 0.0 <= got <= MAX_BACKOFF
        prev = got


def test_no_overflow_at_large_attempt_number():
    # factor ** (n-1) would overflow (2.0 ** 1024) if computed before the cap; the delay
    # must still resolve to max_backoff without raising OverflowError.
    policy = _policy("none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 2000, MAX_BACKOFF, rng) == MAX_BACKOFF
    # and it stays bounded for every strategy at an extreme attempt number
    for jitter in JITTER_NAMES:
        got = compute_delay(_policy(jitter), 5000, MAX_BACKOFF, random.Random(SEED))
        assert 0.0 <= got <= MAX_BACKOFF


def test_no_overflow_or_domain_error_at_extreme_finite_bounds():
    # Extreme-but-finite bounds must not raise (a ratio-based guard would: log(0) domain
    # error one way, OverflowError the other). base >> max_backoff (subnormal) → cap.
    rng = random.Random(SEED)
    p_under = RetryPolicy(max_attempts=100, base=1e308, factor=2.0, max_backoff=5e-324, jitter="none")
    assert compute_delay(p_under, 1, 1e308, rng) == 5e-324
    # base << max_backoff, both extreme → the true value at attempt 1025 is finite and small;
    # it must resolve without OverflowError and stay within bounds.
    p_over = RetryPolicy(max_attempts=2000, base=1e-308, factor=2.0, max_backoff=1e308, jitter="none")
    got = compute_delay(p_over, 1025, 1e-308, random.Random(SEED))
    assert 0.0 <= got <= 1e308


def test_cap_is_constant_time_for_huge_attempt_number():
    # factor barely > 1 with a billion attempts must resolve in O(1), not loop ~1e9 times.
    policy = RetryPolicy(max_attempts=10**9 + 1, base=1e-300, factor=1.0000001, max_backoff=1e300, jitter="none")
    rng = random.Random(SEED)
    start = time.perf_counter()
    got = compute_delay(policy, 10**9, 1e-300, rng)
    elapsed = time.perf_counter() - start
    assert 0.0 <= got <= 1e300
    assert elapsed < 1.0  # would be ~30s with an O(n) loop


def test_cap_handles_astronomically_large_int_attempt_number():
    # attempt_number too large to convert to float must not raise; it is trivially capped.
    policy = RetryPolicy(max_attempts=10**1000, base=1.0, factor=2.0, max_backoff=30.0, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 10**1000, 1.0, rng) == 30.0


def test_cap_is_bit_exact_near_the_overflow_boundary():
    # exponent 1023: 2.0**1023 is finite, so the exact power path must be used (a log-space
    # fallback would be ~100+ ULP off). attempt_number 1024 → exponent 1023.
    policy = RetryPolicy(max_attempts=2000, base=1.0, factor=2.0, max_backoff=1e308, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1024, 1.0, rng) == 2.0**1023


def test_factor_one_is_constant_and_safe_at_large_n():
    # factor == 1.0 is a valid constant-backoff policy; safe at any attempt number.
    policy = RetryPolicy(max_attempts=100, base=0.5, factor=1.0, max_backoff=MAX_BACKOFF, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1, 0.5, rng) == 0.5
    assert compute_delay(policy, 5000, 0.5, rng) == 0.5  # constant


def test_factor_one_caps_when_base_exceeds_max_backoff():
    # the base>max_backoff side of the `factor <= 1` min branch
    policy = RetryPolicy(max_attempts=100, base=100.0, factor=1.0, max_backoff=MAX_BACKOFF, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1, 100.0, rng) == MAX_BACKOFF
    assert compute_delay(policy, 50, 100.0, rng) == MAX_BACKOFF


def test_base_equal_to_max_backoff_caps_from_attempt_one():
    # cap_exp collapses to 0 → the short-circuit returns max_backoff for every attempt.
    policy = RetryPolicy(max_attempts=100, base=MAX_BACKOFF, factor=2.0, max_backoff=MAX_BACKOFF, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1, MAX_BACKOFF, rng) == MAX_BACKOFF
    assert compute_delay(policy, 2, MAX_BACKOFF, rng) == MAX_BACKOFF


def test_base_above_max_backoff_caps():
    # base > max_backoff → negative cap_exp → capped to max_backoff from the first attempt.
    policy = RetryPolicy(max_attempts=100, base=100.0, factor=2.0, max_backoff=MAX_BACKOFF, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1, 100.0, rng) == MAX_BACKOFF


def test_zero_base_yields_zero_delay():
    policy = RetryPolicy(max_attempts=5, base=0.0, factor=FACTOR, max_backoff=MAX_BACKOFF, jitter="none")
    rng = random.Random(SEED)
    assert compute_delay(policy, 1, 0.0, rng) == 0.0
    assert compute_delay(policy, 5, 0.0, rng) == 0.0
