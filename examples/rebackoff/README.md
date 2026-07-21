# rebackoff

A tiny, **dependency-free** retry/backoff library for Python 3.12+ — a `retry` decorator
and a matching context manager, in both **sync and async** flavours, with exponential
backoff, jitter, per-exception retry predicates, and an overall deadline.

- **Zero runtime dependencies** — standard library only.
- **Four surfaces, one core:** `retry` / `aretry` decorators and `Retrying` /
  `AsyncRetrying` context managers, all sharing one validated `RetryPolicy`.
- **Deterministically testable:** `sleep`, the monotonic clock, and the RNG are injectable
  seams, so retried code can be tested without ever really sleeping.
- Fully typed, ships `py.typed`.

## Install

```bash
uv add rebackoff
```

## Quick start

### Decorator (sync)

```python
from rebackoff import retry

@retry(max_attempts=5, on=ConnectionError)
def fetch():
    ...  # retried on ConnectionError, up to 5 attempts
```

### Context manager (sync)

The matching context-manager surface retries a *block* of code. Iterate the `Retrying`
object and guard each try with `with attempt:`:

```python
from rebackoff import Retrying

for attempt in Retrying(max_attempts=5, on=ConnectionError):
    with attempt:
        result = fetch()
# success ends the loop; if every attempt fails, RetryError is raised

# The optional outer `with ... as r:` form just binds the iterable:
with Retrying(max_attempts=5) as r:
    for attempt in r:
        with attempt:
            result = fetch()
```

### Async

```python
from rebackoff import aretry, AsyncRetrying

@aretry(max_attempts=5, deadline=30.0)
async def afetch():
    ...

async for attempt in AsyncRetrying(max_attempts=5, deadline=30.0):
    with attempt:                 # the per-attempt guard is a *sync* context manager
        result = await afetch()   # the await/sleep happens in the iterator itself
```

## Configuration

Every surface accepts the same keyword arguments (or a prebuilt `policy=RetryPolicy(...)`):

| Argument       | Default        | Meaning                                                        |
| -------------- | -------------- | -------------------------------------------------------------- |
| `max_attempts` | `None`         | Max number of attempts. `None` = unbounded by count.           |
| `deadline`     | `None`         | Overall wall-clock budget in seconds (monotonic).              |
| `base`         | `0.1`          | Base backoff in seconds.                                       |
| `factor`       | `2.0`          | Exponential growth factor.                                     |
| `max_backoff`  | `30.0`         | Per-attempt delay cap in seconds.                              |
| `jitter`       | `"full"`       | Jitter strategy (see below).                                   |
| `on`           | `Exception`    | Retryable exceptions: a type, a tuple of types, or a callable. |
| `before_sleep` | `None`         | Hook `(attempt_number, delay, exc)` called before each sleep.  |
| `sleep`        | `time.sleep`   | Sync sleep seam (inject a fake in tests).                      |
| `asleep`       | `asyncio.sleep`| Async sleep seam.                                              |
| `timer`        | `time.monotonic`| Clock used for the deadline.                                  |
| `rng`          | shared `Random`| RNG used for jitter (inject a seeded `Random` for determinism).|

**At least one of `max_attempts` or `deadline` must be set** — unbounded retrying is never
a default. Invalid configuration raises `ValueError` at construction, never mid-retry.

### Jitter strategies

The delay after attempt *n* is `min(max_backoff, base·factor^(n-1))`, then jittered:

| `jitter`         | Delay                                             |
| ---------------- | ------------------------------------------------- |
| `"full"` (default) | uniform in `[0, cap]` — best against thundering herds |
| `"equal"`        | `cap/2 + uniform(0, cap/2)`                        |
| `"none"`         | exactly `cap` (no jitter)                         |
| `"decorrelated"` | `min(cap, uniform(base, prev·3))` (AWS decorrelated) |

### Deadline semantics

The deadline is measured from the first attempt using a **monotonic** clock. rebackoff
**abandons before overrunning**: if the next backoff would push elapsed time to or past the
deadline, it stops immediately with `RetryError` rather than sleeping past it — no attempt
ever starts at or after the deadline.

### When retries are exhausted

`RetryError` is raised, with the last real exception attached as `__cause__` (and as
`.last_exception`), plus `.attempts` and `.elapsed`:

```python
from rebackoff import retry, RetryError

@retry(max_attempts=3)
def flaky(): ...

try:
    flaky()
except RetryError as err:
    print(err.attempts, err.__cause__)
```

`KeyboardInterrupt` and `SystemExit` are **never** retried, regardless of `on`.

## Testing your retried code

Because sleeping, timing, and randomness are injectable, tests are instant and
deterministic:

```python
import random

calls = []
delays = []

@retry(max_attempts=5, jitter="none", sleep=delays.append, rng=random.Random(0))
def flaky():
    calls.append(1)
    if len(calls) < 3:
        raise ConnectionError
    return "ok"

assert flaky() == "ok"
assert delays == [0.1, 0.2]   # no real sleeping happened
```

## License

MIT © Antonio Pisani
