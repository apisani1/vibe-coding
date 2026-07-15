# Env report — URL Shortener Service

## Current state

- **No agent instructions exist** — no `CLAUDE.md`, `AGENTS.md`, or `.cursorrules`.
- `README.md` present (install, env config, HTTP/CLI usage, dev commands) — good for humans,
  but does not encode agent guardrails or the approval boundary.
- No `Makefile` / `run.sh`; commands are `uv run …` invocations.
- Toolchain fully configured in `pyproject.toml`: Black (119), isort (profile=black), flake8,
  pylint, mypy (strict on `src/`, tests excluded), pytest. Pre-commit config present.
- `.claude/vibe-reports/` holds the full lifecycle history — spec, design, decisions, plan,
  verification-plan, build-log, verify/review runs. This is the durable knowledge base; a
  separate `agent-knowledge/` would duplicate it, so **none is proposed**.
- Repo is **not under git** yet.

Context an agent otherwise has to rediscover each session: the run/test/lint commands, the
`SHORTURL_*` env vars (esp. that `serve` needs `SHORTURL_API_KEY`), the module layout and
style rules, one config gotcha (the isort `lines_after_imports` override was removed because
it conflicts with Black), and the safety invariants (fail-closed API key, never log the key).
A short `CLAUDE.md` captures these; that is the only proposed change.

## Proposed changes

**New file: `CLAUDE.md`** (repo root). Full proposed content below — NOT yet written; awaiting
your explicit approval.

````markdown
# Agent Instructions

## Project Context
- Purpose: `shorturl` — a self-hostable URL shortener as a single deployable service:
  SQLite persistence, an HTTP API (create / redirect / per-code stats), a CLI admin
  (list / expire / delete), and click analytics with optional expiry.
- Main entrypoints: the `shorturl` console script → `shorturl.cli:main`
  (`serve` / `list` / `expire` / `delete`); the Flask app factory `shorturl.api.create_app`.
- Layout (`src/` layout): `config.py` (env → frozen `Config`) · `db.py` (sqlite3 data access,
  conn passed in) · `codes.py` (pure gen/validate/status helpers) · `api.py` (Flask factory,
  per-request connection, `/api/*` auth gate) · `cli.py` (argparse).
- Important boundaries: SQLite single-file only (no networked DB); one process, one console
  script, one DB file; single shared API key; `GET /<code>` redirect is public, `/api/*`
  requires `X-API-Key`. The API and CLI share the same SQLite file — it is the one source of
  truth.
- Ground truth & history: `.claude/vibe-reports/` (spec, design, decisions, plan,
  verification-plan, build-log, verify/review). Read it before changing behavior.

## How To Work Here
- Read existing patterns before changing code; match the style (functions over classes;
  pass the `sqlite3.Connection` in, don't construct it inside data-access functions; explicit
  type annotations on public functions; no bare `except`).
- Prefer small, reviewable changes; every changed line should trace to a requirement.
- Define verification before implementation; every public behavior has a pytest test named
  for the behavior.
- Report commands run and checks skipped. Don't declare work done on a red gate.

## Common Commands
- Install / sync: `uv sync`
- Test: `uv run pytest`  (one file: `uv run pytest tests/test_api.py -q`)
- Typecheck: `uv run mypy src/shorturl`  (strict; tests are excluded)
- Lint/format: `uv run black --check src tests` · `uv run isort --check-only src` ·
  `uv run flake8 src` · `uv run pylint src/shorturl`
- Run the server: `SHORTURL_API_KEY=… uv run shorturl serve`
- Admin: `uv run shorturl list | expire <code> | delete <code>`

## Configuration (environment variables)
- `SHORTURL_DB` (default `shorturl.db`), `SHORTURL_API_KEY` (**required for `serve`**;
  never commit or log it), `SHORTURL_HOST` (default `127.0.0.1`), `SHORTURL_PORT`
  (default `8000`), `SHORTURL_BASE_URL` (default `http://{host}:{port}`; set behind a proxy).

## Conventions & gotchas
- Black line length 119; isort uses `profile = "black"`. **Do not re-add
  `[tool.isort] lines_after_imports`** — it conflicts with Black/flake8 (E302) on a top-level
  `def` right after imports.
- Timestamps are canonical ISO-8601 UTC text; the three-way `codes.status`
  (active/expired/deactivated) is the single source of expiry logic — reuse it, don't reinvent.
- Known deferred hardening (see latest review findings): no `MAX_CONTENT_LENGTH` on the create
  body; Referer/User-Agent are stored and echoed in stats JSON (safe as JSON only).

## Guardrails
- Always (autonomous): read code/artifacts; run tests, typecheck, lint, `shorturl --help`,
  and read-only DB inspection.
- Ask first: installing/changing dependencies or running `uv sync`/`uv lock`; editing
  `pyproject.toml` tool config or the profile; `git init`/commit/push; anything writing outside
  the repo; deleting a DB or data.
- Never: commit or push without being asked; log or echo `SHORTURL_API_KEY`; remove the
  fail-closed API-key check (`Config.require_api_key`) or expose `/api/*` unauthenticated;
  weaken a test's assertion to make it pass.

## Approval Boundary
Do not edit files, install packages, run migrations, commit, deploy, delete data, or perform
other mutating work without explicit written approval.
````

## Applied

- **2026-07-14T23:18Z — approved** ("Approved"). Wrote `CLAUDE.md` (repo root) with the
  proposed content verbatim. Add-only: no existing file was overwritten (none existed). No
  `agent-knowledge/` created. This is the only repo write from this `env` run.
