# Agent Instructions — rebackoff

## Project Context
- Purpose: a tiny, **dependency-free** (stdlib-only) retry/backoff library — a `retry`/`aretry`
  decorator and `Retrying`/`AsyncRetrying` context managers sharing one validated `RetryPolicy`
  (exponential backoff, jitter, per-exception predicates, max-attempts and/or deadline).
- Main entrypoints: `src/rebackoff/__init__.py` re-exports the public API. Core:
  `policy.py` (config + validation), `backoff.py` (jitter math), `retrying.py` (engine:
  `_BaseRetrying` + `Attempt` + `Retrying`/`AsyncRetrying`), `decorators.py`, `errors.py`.
- Important boundaries: **zero runtime dependencies is a hard invariant** — the shipped package
  imports only the standard library (enforced by `tests/test_no_deps.py`). Determinism is a hard
  invariant too: `sleep`/`asleep`/`timer`/`rng` are injectable seams so tests never sleep for real.

## How To Work Here
- Read existing patterns before changing code; match the style (functions over classes where
  practical, explicit typing, no bare `except`, docstrings explain *why*).
- Prefer small, reviewable changes; define/adjust the test before the implementation.
- Every public behavior has a `pytest` test named for the behavior it pins. Keep the four surfaces
  (sync/async × decorator/context-manager) at parity over the shared core — don't fork the logic.
- Report commands run and checks skipped.

## Common Commands
- Install: `uv sync`
- Test: `uv run pytest`  (single file: `uv run pytest tests/test_backoff.py`)
- Format: `uv run black . && uv run isort .`
- Lint: `uv run flake8 src && uv run pylint src`
- Typecheck: `uv run mypy src`  (strict; `src` only — tests/scripts/docs are excluded)
- Full gate (all must exit 0): `uv run pytest && uv run black --check src && uv run isort --check-only src && uv run flake8 src && uv run pylint src && uv run mypy src`

## Guardrails
- Always: run tests and the linters/type-checker; read files; make surgical edits that trace to a
  clear reason.
- Ask first: adding ANY runtime dependency (this would break the zero-dep invariant — avoid it),
  changing the public API surface or `RetryPolicy` defaults, committing, tagging, or pushing.
- Never: introduce a third-party runtime import; retry `KeyboardInterrupt`/`SystemExit`; make the
  library sleep on the real clock inside tests; commit or push without an explicit request.

## Approval Boundary
Do not edit files, install packages, run migrations, commit, deploy, delete data, or perform other
mutating work without explicit written approval.
