# Plan: URL Shortener Service

Upstream design: ../2026-07-14T16-55-12Z/design.md
Upstream spec: ../2026-07-14T16-27-26Z/spec.md

## Risk factors (ArjanCodes step 5 — identified first)

The stack is well-trodden; the real risk is in the **foundation integration**, not in any
single library. These are front-loaded into Phase A so infeasibility surfaces before the
CRUD/CLI work is built on top.

- **R1 — SQLite locking under a multithreaded server.** waitress serves requests on
  multiple threads; a shared or mis-configured connection yields `database is locked` or
  cross-thread errors. → *Mitigation:* WAL journal mode + `busy_timeout` + a **fresh
  connection per request** (and per CLI command). Proven in Phase A with a concurrent-write
  test; a true high-concurrency load test is declared out of local scope.
- **R2 — Route precedence `/<code>` vs `/api/*`.** A greedy catch-all could swallow API
  paths. → *Mitigation:* declare `/api/*` routes explicitly; `/<code>` is the fallback.
  Tested both ways in Phase A.
- **R3 — Expiry / status correctness.** Three-way status (active/expired/deactivated), the
  TTL boundary at "now", and "no click recorded on 410" are easy to get subtly wrong. →
  *Mitigation:* a single pure `codes.status(row, now)` helper, unit-tested at the boundary,
  backing both the redirect gate and display. Redirect integration tests assert no click on
  410.
- **R4 — Shared-store contract.** The API and CLI must operate on the *same* file with
  consistent semantics (spec AC #13). → *Mitigation:* one `db.py` used by both; foundation
  proven in Phase A, explicit cross-surface test in Phase C.
- **R5 — FK cascade needs `PRAGMA foreign_keys = ON` per connection.** Forgetting it
  silently orphans clicks on delete. → *Mitigation:* `connect()` always sets the pragma;
  cascade asserted by unit test in Phase A.
- **R6 — Code collision / alias uniqueness.** → *Mitigation:* PRIMARY KEY constraint +
  bounded retry for auto-gen; `409` for taken aliases. Unit + API tested.

## Phases

Three phases, each ending in a `verify` boundary (a legitimate re-plan point). **Phase A is
front-loaded** — it retires R1–R5, the foundation everything else stands on. Phases B and C
are committed at a lighter level of detail and may be revised by what Phase A reveals.

### Phase A — Foundation & risk retirement (riskiest, front-loaded)
- Goal: persistence, pure domain helpers, and the **redirect+click+expiry core** exist and
  are proven — the shared store works end-to-end for the read/redirect path. R1–R5 retired.
- Checkpoints: 1–3
- Boundary: run `verify` before entering Phase B.

### Phase B — HTTP write & analytics surface
- Goal: authenticated create and stats endpoints complete the HTTP API.
- Checkpoints: 4–5
- Boundary: run `verify` before entering Phase C.

### Phase C — CLI admin, packaging & docs
- Goal: the admin CLI, the `serve` entry point, README, and the full quality gate — a
  single deployable unit.
- Checkpoints: 6–7
- Boundary: run `verify` against the full acceptance-criteria set.

## Checkpoints

### Checkpoint 1: Project scaffold + profile seed
- Does: Seed the bare repo from the user preference profile (**build checkpoint 0**:
  `pyproject.toml`, `.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`,
  `.vscode/settings.json`, verbatim assets) augmented with project metadata + deps
  (flask, waitress; dev: pytest, black, isort, flake8, pylint, mypy). Create the `src/`
  layout: `src/shorturl/__init__.py` (version), `config.py` (frozen `Config.from_env`).
- Touches: `pyproject.toml`, tooling dotfiles, `src/shorturl/__init__.py`,
  `src/shorturl/config.py`, `tests/`.
- Verify: `uv sync` succeeds; `uv run python -c "import shorturl"` works; `Config.from_env`
  unit test (defaults + `serve`-requires-api-key) passes; black/isort/flake8/mypy clean.

### Checkpoint 2: Persistence layer + domain helpers
- Does: `db.py` — `connect` (WAL, `foreign_keys=ON`, `busy_timeout`, row factory),
  `init_schema`, and data-access functions (`insert_code`, `get_code`, `insert_click`,
  `list_codes` w/ click_count, `expire_code`, `delete_code`, `get_stats` w/ per-day series
  + top referers). `codes.py` — `generate_code`, `is_valid_alias`, `validate_url`, three-way
  `status`.
- Touches: `src/shorturl/db.py`, `src/shorturl/codes.py`, `tests/test_db.py`,
  `tests/test_codes.py`.
- Verify: `uv run pytest tests/test_db.py tests/test_codes.py` — CRUD roundtrip, FK cascade
  on delete (R5), three-way status at the TTL boundary (R3), stats per-day bucketing + top
  referers, `list_codes` click_count, base62 gen + alias/URL validation, auto-gen collision
  retry (R6).

### Checkpoint 3: Redirect + click + expiry core (retires R1–R3)
- Does: `api.py` `create_app(config)` with **only** `GET /<code>` for now — look up code,
  `404` unknown, `410` when status != active (no click recorded), else insert click
  (timestamp, Referer, User-Agent) and `302` to target. Per-request connection
  (before_request/teardown). JSON error handlers.
- Touches: `src/shorturl/api.py`, `tests/test_redirect.py`.
- Verify: `uv run pytest tests/test_redirect.py` via `app.test_client()` — 302 + exactly one
  click row + correct Location; 404 unknown (no click); 410 for TTL-expired and for
  deactivated (no click); `/api/...` path is **not** captured by `/<code>` (R2); a
  concurrent-insert test exercises WAL/busy_timeout (R1, best-effort locally).
- **Phase A boundary → `verify`.**

### Checkpoint 4: Create endpoint + API-key auth
- Does: `POST /api/codes` (auto code, optional custom alias, optional `expires_at`; URL +
  alias + timestamp validation → `201` with `{code, short_url, target_url, expires_at}`;
  `400` bad input; `409` alias taken). API-key gate over `/api/*` (`X-API-Key` +
  `hmac.compare_digest`; missing `401`, wrong `403`); redirect stays public. `serve` refuses
  to boot without a key.
- Touches: `src/shorturl/api.py`, `tests/test_create.py`, `tests/test_auth.py`,
  `tests/test_redirect.py` (R2 assertion only — added 2026-07-14 with human authorization:
  the CP4 auth gate changed `/api/*` behavior from 404→401, so the R2 test's assertion was
  amended from `== 404` to "not a redirect"; see build-log CP4).
- Verify: `uv run pytest tests/test_create.py tests/test_auth.py` — create auto (201 + row);
  create alias (201 exact); duplicate alias 409 (no dup); malformed URL 400; malformed
  `expires_at` 400; missing key 401; wrong key 403; redirect unaffected by auth.

### Checkpoint 5: Stats endpoint
- Does: `GET /api/codes/{code}/stats` (auth) → `{code, target_url, status, total, series[],
  top_referers[]}`; `404` unknown.
- Touches: `src/shorturl/api.py`, `tests/test_stats.py`.
- Verify: `uv run pytest tests/test_stats.py` — with seeded clicks across days: correct
  total, per-day `series` shape/order, `top_referers` order+limit, three-way `status`; 404
  unknown; auth enforced.
- **Phase B boundary → `verify`.**

### Checkpoint 6: CLI admin (list / expire / delete)
- Does: `cli.py` `main(argv)` with argparse subcommands `list`, `expire <code>`,
  `delete <code>` opening one connection per command. `list` prints code, status
  (three-way), target, created/expiry, click_count. `expire`/`delete` return bool → exit
  non-zero + stderr on unknown code. Console script `shorturl = shorturl.cli:main` in
  pyproject.
- Touches: `src/shorturl/cli.py`, `pyproject.toml`, `tests/test_cli.py`.
- Verify: `uv run pytest tests/test_cli.py` — `list` reflects DB (status labels + counts);
  `expire` then redirect 410; `delete` then redirect 404 and code gone from `list`; unknown
  code exits 1; **shared-store cross-check** — code created via app is seen by `list`, code
  expired via CLI is 410 on the app (R4, AC #13).

### Checkpoint 7: serve entry point, README, quality gate
- Does: `shorturl serve` subcommand builds the app from `Config.from_env` and runs it under
  waitress (fail-closed without api key). `README.md` (install, env vars, `serve`, admin
  commands, API examples). Final toolchain pass.
- Touches: `src/shorturl/cli.py`, `README.md`, minor `src/shorturl/*` cleanups.
- Verify: `shorturl serve` boots and answers a redirect over a real socket (smoke test on an
  ephemeral port, then shut down); `shorturl --help` lists all subcommands; README present;
  full `uv run pytest` green; black --check / isort --check / flake8 / pylint / mypy all
  clean (AC #15).
- **Phase C boundary → `verify` against the full acceptance set.**

### Checkpoint 8: Verify remediation — AC #10 created column + AC #8 test (routed from verify)
- Does: Close the `verify` FAIL (run 2026-07-14T18-33-33Z). (a) AC #10 blocker — add a
  CREATED column to `cli._print_codes` so `shorturl list` shows the created date (already
  selected by `list_codes`); (b) assert the `list` columns (target + created + expiry) in
  `test_list_reflects_db`; (c) AC #8 risk — add a CLI test proving prior clicks survive
  `expire` (the keep-history guarantee that distinguishes expire from delete).
- Touches: `src/shorturl/cli.py`, `tests/test_cli.py`.
- Verify: `uv run pytest tests/test_cli.py` + full `uv run pytest`; `shorturl list` renders a
  CREATED column; black/isort/flake8/pylint/mypy clean.
- Deferred (not in this checkpoint): security advisories (dep pins/lockfile,
  MAX_CONTENT_LENGTH, referer/UA echo) and the AC #11 CLI-cascade / R6 collision-retry
  advisories — optional hardening, tracked in the verify findings for a later pass.

### Checkpoint 9: Review remediation — API-key non-ASCII robustness (routed from review)
- Does: Close review advisory #1 (run 2026-07-14T18-52-16Z, flagged by both reviewers). The
  `/api/*` auth gate's `hmac.compare_digest(provided, expected)` raises `TypeError` on a
  non-ASCII `X-API-Key` (Werkzeug decodes headers latin-1) → generic 500 instead of the
  contracted 403. Compare on bytes so the check is total and returns a clean 403.
- Touches: `src/shorturl/api.py`, `tests/test_auth.py`.
- Verify: `uv run pytest tests/test_auth.py` (add a non-ASCII-key → 403 test) + full
  `uv run pytest`; black/isort/flake8/pylint/mypy clean.

### Checkpoint 10: Dependency hygiene (routed from review)
- Does: Close review advisories #2/#3 — drop the unused `types-pyyaml` dev dep (profile-seed
  leftover; nothing imports yaml) and generate a `uv.lock` for reproducible installs (repo is
  not under git; the lockfile is present/authoritative, ready to commit if git is added).
- Touches: `pyproject.toml`, `uv.lock` (new).
- Verify: `uv sync` succeeds; `uv.lock` present; full `uv run pytest` still green; gates clean.
- **Install boundary:** `uv lock` / `uv sync` re-resolve dependencies (network) → requires
  direct human approval even under `--auto`.

### Checkpoint 11: Two edge-case bug fixes (routed from external Codex review)
- Does: (a) `codes.validate_url` rejects C0 control characters (incl. CR/LF/TAB) — a URL like
  `https://example.com\r\nX-Test: x` was accepted (201) because `urlparse` silently strips
  CR/LF for parsing while `validate_url` returned the un-normalized `url.strip()`, so the raw
  newline reached the `Location` header and 500'd the public redirect (also violated AC #4:
  malformed URL must be 4xx / no row). (b) `api.redirect_code` catches `sqlite3.IntegrityError`
  from `insert_click` and returns 404 — a code deleted (FK cascade) between the lookup and the
  click insert previously raised → 500.
- Touches: `src/shorturl/codes.py`, `src/shorturl/api.py`, `tests/test_codes.py`,
  `tests/test_create.py`, `tests/test_redirect.py`.
- Verify: `uv run pytest` full; new regression tests (create CRLF URL → 400 no row; redirect
  when insert_click raises IntegrityError → 404); black/isort/flake8/pylint/mypy clean.
- Rejected remedy (for #2): holding a write lock across read+insert (BEGIN IMMEDIATE) would
  serialize all redirects and defeat the R1 concurrency design — catching the FK error is the
  cheaper, equally-correct fix.

### Checkpoint 12: Close the high-codepoint-URL residual (routed from post-CP11 verify)
- Does: `codes.validate_url` now also rejects non-ASCII URLs (`str.isascii()`), closing the
  remaining slice of the malformed-URL→redirect-500 class that CP11's control-char rule left
  open (a codepoint >0xFF can't be latin-1-encoded into the `Location` header). RFC 3986: URLs
  are ASCII — non-ASCII must be percent-encoded / IDN (punycode), both of which stay ASCII.
- Touches: `src/shorturl/codes.py`, `tests/test_codes.py`, `tests/test_create.py`.
- Verify: `uv run pytest` full; new tests (non-ASCII URL → InvalidURLError; punycode/percent-
  encoded still accepted; create non-ASCII URL → 400 no row); gates clean; probe confirms a
  >0xFF URL now 400s at create instead of 500ing the redirect.

## Definition of Done
- Required (MVP, spec ACs 1–15): persistence layer; redirect+click+expiry core; create
  endpoint with auth; stats endpoint; CLI list/expire/delete; `serve` under waitress; single
  console script + single SQLite file; all acceptance criteria verified; toolchain + pytest
  clean.
- Optional-later (explicitly deferred by spec): web dashboard; per-user keys/ownership; IP
  capture / unique visitors / geo; rate limiting; click retention/pruning; configurable
  301 redirects; custom domains / QR codes.

## Migration / one-off scripts
None. `init_schema` runs `CREATE TABLE IF NOT EXISTS` on first connect; there is no existing
data to migrate (greenfield).
