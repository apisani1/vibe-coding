#!/usr/bin/env bash
# Seed an approved library spec so `design` has its upstream doc.
set -euo pipefail
mkdir -p vibe
cat > vibe/spec.md <<'EOF'
# Spec: rebackoff — retry/backoff library

## Goal
Give Python callers one small, dependency-free way to retry flaky operations with
predictable timing, so they stop hand-rolling sleep loops.

## Users & user stories
- As a caller, I decorate a function with `@retry(...)` so transient failures are retried.
- As a caller, I wrap a block with `with retrying(...) as attempt:` when a decorator
  doesn't fit.
Smallest usage: `@retry(max_attempts=5, backoff=expo(base=0.1, cap=2.0), retry_on=(TimeoutError,))`.

## Scope
- In (MVP): `retry` decorator, `retrying` context manager, `expo` backoff with full
  jitter, `retry_on` exception tuple or predicate, overall `deadline` (seconds).
- Out: async support — sync callers are the stated users; async doubles the surface.
- Out: logging/metrics hooks — callers can wrap; adds API surface before demand.
- Out: per-attempt timeouts — cannot interrupt arbitrary sync code safely.

## Constraints
- Python 3.11+, zero runtime dependencies; UV; pytest.

## Acceptance criteria
- AC1: With `max_attempts=3` and a function that always raises a matching error, the
  function is called exactly 3 times and the last exception is re-raised (test).
- AC2: A non-matching exception is raised immediately after 1 call (test).
- AC3: Sleep durations are within `[0, min(cap, base * 2**n)]` for attempt n, verified
  with an injected clock/sleep and a seeded RNG (test).
- AC4: With `deadline=1.0`, no attempt starts after 1.0 s of injected-clock time and
  `RetryError` is raised carrying the last exception (test).
- AC5: The context-manager form honors the same attempts/backoff/deadline rules (test).
- AC6: Tests never sleep in real time; the full suite runs in < 2 s.

## Assumptions
- Sleep and clock are injectable for tests.

## Open questions
- None.
EOF
