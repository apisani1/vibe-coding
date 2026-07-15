# Verify report (re-verify #3) — URL Shortener Service

Plan under test: ../2026-07-14T17-04-58Z/verification-plan.md
Build under test: ../2026-07-14T17-04-58Z/ (10 checkpoints — 7 original + CP8 verify-fix + CP9/CP10 review-fix)
Supersedes: ../2026-07-14T18-48-15Z/ (prior PASS, before CP9/CP10)

## Passed

- `uv run pytest` (full suite) — **87 passed** (was 86; +test_non_ascii_key_fails_closed_403).
- `uv run pytest tests/test_auth.py` — 4 passed (incl. non-ASCII key → 403).
- `uv run pytest tests/test_serve.py -W error::pytest.PytestUnhandledThreadExceptionWarning` — 4 passed.
- `uv run black --check src tests` — 0; `isort --check-only src` — 0; `flake8 src` — 0.
- `uv run pylint src/shorturl` — 10.00/10; `uv run mypy src/shorturl` — Success.
- `uv.lock` present; `types-pyyaml` absent from pyproject.toml (grep count 0) and the venv.

### Changes since the prior PASS (both verified)

- **CP9 (review advisory #1 → CLOSED).** The `/api/*` auth gate compares utf-8 bytes, so a
  non-ASCII `X-API-Key` now returns a clean **403** instead of a `TypeError`-driven 500.
  Pinned by `test_non_ascii_key_fails_closed_403`; ASCII behavior (401 missing / 403 wrong /
  pass correct / public redirect) unchanged and still green.
- **CP10 (review advisories #2/#3 → CLOSED).** `types-pyyaml` dropped (mypy still Success →
  it was genuinely unused); `uv.lock` generated for reproducible installs.

## Failed

- None.

## Acceptance criteria

**15 of 15 met** — coverage carried forward from run 2026-07-14T18-48-15Z (all ACs had
passing checks there and none of CP9/CP10 removed or weakened any). AC #3 (auth) is now
*strengthened* by the added non-ASCII-key case. Sub-agents not re-dispatched: CP9/CP10 were
minimal, and both were already independently reviewed in the review pass
(2026-07-14T18-52-16Z), which recommended exactly these fixes.

## Not run (declared out of local scope — unchanged)

- True high-concurrency / production load (R1); production reverse-proxy `base_url`;
  "API key never logged" (code-review invariant, confirmed by inspection).

## Findings (4 advisory — all optional, deferred by choice)

- **security** — no `MAX_CONTENT_LENGTH` (authenticated-only); referer/UA echo (safe as JSON).
- **tests** — AC #11 cascade transitive; R6 collision-retry unexercised.

Review advisories #1 (non-ASCII key), #2 (types-pyyaml), #3 (uv.lock) are now **closed** by
CP9/CP10 and no longer appear.

## Verdict

**PASS** — all 15 acceptance criteria met; 87 tests green; all static gates clean; the
API-key robustness fix and dependency hygiene are verified. 0 blocker, 0 risk, 4 advisory
(all optional hardening/coverage, consciously deferred).

**Route:** clean verify. The build is complete, verified, and reviewed. Optional next:
`git init` + initial commit (`.gitignore` + `uv.lock` ready), or `env` to persist a repo
CLAUDE.md. To re-enter `build`, pass the plan path explicitly
(`.claude/vibe-reports/2026-07-14T17-04-58Z`) — `latest` now points here.
