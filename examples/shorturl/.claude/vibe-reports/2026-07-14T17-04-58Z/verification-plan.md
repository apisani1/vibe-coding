# Verification plan — URL Shortener Service

Upstream plan: ./plan.md
Upstream design: ../2026-07-14T16-55-12Z/design.md
Upstream spec: ../2026-07-14T16-27-26Z/spec.md

Written by `plan` **before any code exists**; executed by `verify` at each phase boundary.
Greenfield repo — every check is net-new. Prefer `app.test_client()` + a temp/in-memory
SQLite DB per test (fixture) over process/socket-level checks; the only real-socket check is
the Checkpoint 7 smoke test. All checks run under `uv run`.

## Criteria

Each of the spec's 15 acceptance criteria maps to at least one observable check, tagged with
the checkpoint that should make it pass (so `verify` can run per phase boundary).

| AC | Criterion (short) | Observable check | Proves | CP / Phase |
|----|-------------------|------------------|--------|------------|
| 1 | Create (auto) | `test_create.py`: POST `/api/codes` valid url + key → `201`, JSON `code` non-empty base62; `db.get_code` returns row w/ matching target_url. | auto-code create persists | CP4 / B |
| 2 | Create (custom alias) | `test_create.py`: POST free `alias` → `201`, `code == alias`; repeat → `409`, count for code stays 1. | alias honored + uniqueness (R6) | CP4 / B |
| 3 | Auth enforced | `test_auth.py`: create + stats with no key → `401`, wrong key → `403`; row count unchanged. | API-key gate, no state change | CP4/CP5 / B |
| 4 | URL validation | `test_create.py`: malformed / non-http(s) url (`javascript:`, `ftp://`, `""`) → `4xx`, count unchanged; `test_codes.py`: `validate_url` raises. | bad URL rejected | CP4 (API), CP2 (unit) |
| 5 | Redirect + record | `test_redirect.py`: GET `/{code}` active → `302`, exact `Location`; exactly one `clicks` row; Referer/User-Agent stored when sent, else NULL. | redirect + single click + context | CP3 / A |
| 6 | Unknown code | `test_redirect.py`: GET `/{unknown}` → `404`; `clicks` count == 0. | 404, no click | CP3 / A |
| 7 | Expiry (TTL) | `test_redirect.py`: past `expires_at` → GET → `410`, no click; `test_codes.py`: `status` at/just-past boundary. | TTL gate + boundary (R3) | CP3/CP2 / A |
| 8 | Expiry (manual) | `test_cli.py`: `cli expire <code>` → GET `/{code}` → `410`; codes row + prior clicks still present. | manual deactivate keeps history | CP6 / C |
| 9 | Stats | `test_stats.py`: seed clicks across ≥2 UTC dates + repeated referers → stats (key) → `200`; `total` == count; `series` per-day ordered; `top_referers` desc, cap 10; `status` three-way. | stats aggregation correct | CP5 / B |
| 10 | CLI list | `test_cli.py`: seed active/expired/deactivated codes w/ clicks → `cli list` shows code, status label, target, dates, click_count matching DB. | list reflects DB | CP6 / C |
| 11 | CLI delete | `test_cli.py`: `cli delete <code>` → code + clicks gone (cascade); GET `/{code}` → `404`; `list` omits it. | delete cascades + disappears (R5) | CP6 / C |
| 12 | CLI unknown code | `test_cli.py`: `cli expire`/`delete` unknown → stderr message, `main()` non-zero (exit 1). | fail-loud non-zero exit | CP6 / C |
| 13 | Shared store | `test_cli.py` cross-surface: create via `test_client()` on a **temp-file** DB → same path to `cli list` shows it; `cli expire` → GET on app → `410`. | one file, both surfaces (R4) | CP6 / C |
| 14 | Single deployable | CP7 smoke: `shorturl serve` on ephemeral port over a real socket answers a redirect, then shuts down; `shorturl --help` lists subcommands; `import shorturl` works. | one package, one script, both paths | CP7 / C (import at CP1) |
| 15 | Quality gate | `uv run pytest` green; `black --check`, `isort --check`, `flake8`, `pylint`, `mypy` clean on `src/`. | toolchain + tests clean | CP7 (full), incrementally CP1–6 |

## Checks

Deliberately narrow: fast `test_client()` + temp/in-memory SQLite, one real-socket smoke
test, one static toolchain pass. No load-test harness; no HTTP client against a spawned
server except the CP7 smoke.

**Phase A boundary (after CP3)** — retires R1–R5:
```
uv run pytest tests/test_config.py tests/test_db.py tests/test_codes.py tests/test_redirect.py
```
Covers AC 4(unit), 5, 6, 7. Includes: CRUD roundtrip; FK cascade on delete (R5); three-way
`status` at the TTL boundary (R3); base62 gen + alias/URL validation; auto-gen collision
retry (R6); redirect 302/404/410 with click-row assertions; `/api/...` not swallowed by
`/<code>` (R2); a **threaded concurrent-insert test on a temp-file DB** (not `:memory:`)
asserting all rows land with no `OperationalError` (R1, best-effort locally).

**Phase B boundary (after CP5):**
```
uv run pytest tests/test_create.py tests/test_auth.py tests/test_stats.py
```
Covers AC 1, 2, 3, 4(API), 9. Includes duplicate-alias 409 (R6), malformed url/`expires_at`
400, missing 401 / wrong 403, redirect-unaffected-by-auth, and stats seeded with
`clicked_at` across **≥2 distinct dates** so multi-bucket series + ordering are actually
exercised (not a single-bucket pass).

**Phase C boundary (after CP7)** — full acceptance set:
```
uv run pytest
black --check . && isort --check-only . && flake8 && pylint src/shorturl && mypy src/shorturl
# + shorturl serve ephemeral-port smoke test
```
Covers AC 8, 10, 11, 12, 13, 14, 15 and re-runs everything above. The CP7 smoke also sets
`SHORTURL_BASE_URL` to a fake proxy origin and asserts the create response echoes it.

## External signals

- **Real socket, ephemeral port (CP7 only):** bind `shorturl serve` to `127.0.0.1:0`, issue
  one real HTTP GET `/{code}` expecting `302`, then terminate — proves waitress actually
  boots and serves.
- **CLI stdout/stderr + exit code:** `cli list` content (AC 10) and non-zero exit on unknown
  code (AC 12) observed via captured stdout/stderr and `main()`'s return value.
- **SQLite file state:** cross-surface AC 13 uses a shared **temp-file** DB path (not
  `:memory:`, which is per-connection) so API and CLI provably touch the same bytes. Row
  counts / `get_code` inspected directly for AC 1, 2, 5, 6, 7, 8, 11.
- **No outbound signals:** the service fetches nothing; no third-party endpoints or deploy
  targets to assert against.

## Risk-based expansion

- **If the concurrent-insert test flakes / shows `database is locked` (R1):** expand to a
  multi-process writer test and tune `busy_timeout`; consider an `ab`/locust pass in CI.
  Until then, high-concurrency load stays out of local scope.
- **If any `/api/*` path is matched by `/<code>` (R2):** add explicit route-precedence tests
  for every `/api/*` prefix.
- **If `status()` boundary tests reveal tz drift (R3):** add tz-aware vs naive `expires_at`
  and DST-adjacent instants; assert all comparisons are UTC.
- **If code generation collides in tests (R6):** add a seeded/mocked-`secrets` test forcing a
  collision to verify bounded retry + the 500-after-exhaustion path.
- **If public-API / shared `db.py` signatures change across modules:** widen from focused
  per-file runs to the full `pytest` suite at that checkpoint.

## Cannot be verified locally (declared up front)

- **True high-concurrency / production load (R1).** Local checks prove correctness under
  modest thread contention, not behavior at production volume — out of local scope per plan.
- **Production reverse-proxy `base_url`.** Local smoke can set `SHORTURL_BASE_URL` and assert
  the echoed `short_url`, but real X-Forwarded / proxy-origin behavior behind nginx/Caddy is
  not exercised.
- **Networked/NFS "same DB file reachable" story.** AC 13 is proven with a shared temp-file
  path in one process tree; a networked SQLite file (which the spec discourages) is untested.
- **API-key secrecy in logs ("never logged").** We can assert the key isn't in a response
  body, but "never logged across all future log statements" is a code-review invariant, not a
  runtime check — flagged for the reviewer.
- **Collision safety at 62⁷ scale.** Only the retry mechanism is tested (forced collision);
  statistical collision-freeness is a design property, not observable.
