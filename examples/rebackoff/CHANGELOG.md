# Changelog

All notable changes to rebackoff are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-07-20

Initial release.

### Added
- `retry` / `aretry` decorators and `Retrying` / `AsyncRetrying` context managers, all
  sharing one validated, immutable `RetryPolicy` (sync and async parity over one core).
- Exponential backoff with a cap and pluggable jitter: `full` (default), `equal`, `none`,
  and AWS `decorrelated`.
- Stop conditions: `max_attempts` and/or an overall wall-clock `deadline` (monotonic,
  abandon-before-overrun — no attempt starts at or after the deadline).
- Per-exception retry predicates via `on` (an exception type, a tuple of types, or a
  callable); `KeyboardInterrupt` / `SystemExit` are never retried.
- `RetryError` on exhaustion, chaining the last exception as `__cause__`.
- `before_sleep` hook (sync, and awaitable on the async surface).
- Injectable `sleep` / `asleep` / `timer` / `rng` seams for fully deterministic testing.
- **Zero runtime dependencies** (standard library only); fully typed, ships `py.typed`.

[0.1.0]: https://github.com/apisani1/rebackoff/releases/tag/v0.1.0
