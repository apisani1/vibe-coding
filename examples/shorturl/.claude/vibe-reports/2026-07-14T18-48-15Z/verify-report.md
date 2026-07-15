# Verify report (re-verify) — URL Shortener Service

Plan under test: ../2026-07-14T17-04-58Z/verification-plan.md
Build under test: ../2026-07-14T17-04-58Z/ (8 checkpoints — 7 original + CP8 remediation)
Supersedes: ../2026-07-14T18-33-33Z/ (prior verify, FAIL on AC #10)

## Passed

- `uv run pytest` (full suite) — **86 passed** (exit 0; was 85 before CP8).
- `uv run pytest tests/test_cli.py` — 8 passed (was 7; +test_expire_keeps_prior_clicks).
- `uv run pytest tests/test_serve.py -W error::pytest.PytestUnhandledThreadExceptionWarning` — 4 passed.
- `uv run black --check src tests` — 0; `isort --check-only src` — 0; `flake8 src` — 0.
- `uv run pylint src/shorturl` — 10.00/10; `uv run mypy src/shorturl` — Success.
- Empirical `shorturl list` — renders `CODE / STATUS / CLICKS / CREATED / EXPIRES / TARGET`.

### The two prior findings — both CLOSED

- **AC #10 (was blocker → CLOSED).** `cli._print_codes` now emits a `CREATED` column from
  `row['created_at']`. `test_list_reflects_db` asserts the created date, target URL, expiry
  date, and the `CREATED` header all appear — so it cannot silently regress.
- **AC #8 (was risk → CLOSED).** `test_expire_keeps_prior_clicks` seeds a code with 3
  clicks, runs `shorturl expire`, and asserts the code row and all 3 clicks survive —
  pinning the keep-history clause that distinguishes expire from delete.

### Acceptance-criteria coverage (vibe-test-designer)

**All 15 of 15 acceptance criteria have a real, passing covering check. None is unverified
or partial.** (Full per-AC table in the sub-agent output; AC #8 and #10 rows now green.)

## Failed

- None.

## Not run (declared out of local scope — unchanged)

- True high-concurrency / production load (R1) — best-effort 20-thread test only.
- Production reverse-proxy `base_url` behind nginx/Caddy — `SHORTURL_BASE_URL` echo is
  exercised locally; real proxy-origin behavior is not.
- "API key never logged" — code-review invariant (confirmed by inspection), no runtime check.

## Coverage gaps (residual advisories, non-blocking)

- **AC #11 clicks-cascade** — transitively covered via the db-layer test against the same
  `db.delete_code` the CLI calls (advisory; unchanged).
- **R6 auto-code collision retry / 500-exhaustion** — unexercised risk-based-expansion
  item, not one of the 15 ACs (advisory; unchanged).

## Security (carried forward — not re-audited)

The CP8 diff touched only CLI display (`_print_codes`) and tests — no trust boundary, SQL,
auth, or dependency change — so the prior audit (run 2026-07-14T18-33-33Z: no blockers, no
risks) still holds. Three defense-in-depth advisories carried forward: dependency
pins/lockfile, `MAX_CONTENT_LENGTH`, and stored-then-echoed Referer/User-Agent. Spec-deferred
items (no rate limiting, single API key, no IP capture) remain acknowledged limitations.

## Verdict

**PASS** — all 15 acceptance criteria met with passing checks; 86 tests green; all static
gates clean; security clean (no blockers/risks). The AC #10 blocker and AC #8 risk from the
prior verify are closed and regression-locked.

**Findings:** 0 blocker, 0 risk, 5 advisory (2 test-coverage, 3 security hardening) — all
optional, tracked for a later pass.

**Route:** clean verify → proceed to `review` (independent quality/security pass; the
carried security advisories are natural review material), or ship. To re-enter `build`
against the plan, pass its path explicitly (`.claude/vibe-reports/2026-07-14T17-04-58Z`) —
`latest` now points here.
