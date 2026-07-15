# Verify report (post-CP11) — URL Shortener Service

Plan under test: ../2026-07-14T17-04-58Z/verification-plan.md
Build under test: ../2026-07-14T17-04-58Z/ (11 checkpoints; CP11 = two Codex-review bug fixes)
Supersedes: ../2026-07-14T23-09-27Z/

## Passed

- `uv run pytest` (full suite) — **93 passed** (was 87; +6 CP11 regression tests).
- Targeted: control-char rejection (4 params) + CRLF-create-400-no-row + delete-race-404 — 6 passed.
- `uv run pytest tests/test_serve.py -W error::…ThreadException…` — 4 passed.
- black / isort / flake8 — exit 0; pylint — 10.00/10; mypy — Success.

### CP11 fixes verified

- **Bug 1 — CRLF URL (was: 201 then public 500; AC #4 violation) → FIXED.** `validate_url`
  rejects C0 control chars + DEL before parsing; create returns **400 with no row**, proven at
  three layers (unit, endpoint, no-row assertion). AC #4 is now strictly stronger than before.
- **Bug 2 — delete-during-redirect (was: 500) → FIXED.** `redirect_code` catches
  `sqlite3.IntegrityError` from `insert_click` → **404**. The R1 concurrency test is untouched,
  so the fix does not weaken the connection-per-writer design.

## Acceptance criteria

**15 of 15 met.** vibe-test-designer confirmed no AC regressed: the redirect happy/unknown/
expired branches (#5/#6/#7) are structurally intact (the try/except wraps only `insert_click`),
and AC #4 (URL validation) is strengthened. Coverage of the two fixes is by real assertions.

## Failed

- None.

## Not run (declared out of local scope — unchanged)

- True high-concurrency / production load (R1); production reverse-proxy `base_url`;
  "API key never logged" (code-review invariant).

## Findings (4 advisory — none blocking)

- **security** — `validate_url` still accepts high-codepoint (>0xFF) URLs that Werkzeug's
  latin-1 `Location` could reject at redirect time (same class as fixed bug #1, lower risk;
  optional one-rule fix = require ASCII URLs). *Not fixed here — outside CP11's approved scope.*
- **tests** — the delete-race test is a monkeypatch proxy, not a true end-to-end cascade race
  (fair proxy).
- **security (carried, deferred)** — no `MAX_CONTENT_LENGTH`; Referer/UA echo (safe as JSON).

## Verdict

**PASS** — all 15 acceptance criteria met; 93 tests green; all static gates clean; both Codex
bugs fixed and covered; no regression. 0 blocker, 0 risk, 4 advisory (all optional).

**Route:** clean verify. Next: commit + push the CP11 fixes. To re-enter `build` (e.g. to
close the high-codepoint-URL residual), pass the plan path explicitly
(`.claude/vibe-reports/2026-07-14T17-04-58Z`).
