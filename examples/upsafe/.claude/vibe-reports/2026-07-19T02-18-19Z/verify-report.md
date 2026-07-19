# Verify report (re-verify — VF-7 closure)

Plan under test: .claude/vibe-reports/2026-07-18T17-30-16Z/verification-plan.md
Prior verify: .claude/vibe-reports/2026-07-19T02-02-08Z (full specialist pass)
Trigger: confirm VF-7 (failure-path logging regression) is closed.

## Passed

- `uv run pytest` — **112 passed** (was 109; +3 reject-logging tests).
- `make pre-commit` — **exit 0**: isort/black/flake8 clean, **pylint 10.00/10**,
  **mypy --strict clean** (13 files).
- All 12 acceptance criteria remain verified (no criteria behavior changed).

**VF-7 (was risk) → CLOSED, confirmed live this run.** Rejected requests are now logged
through the redacting logger, using the route TEMPLATE only:
- `POST /uploads` with a bad key → `method=POST route=/uploads status=401` — and the API key
  (`BADKEY_SECRET`) and filename (`LEAK`) are absent from the log.
- `GET /downloads/<token>` unknown → `method=GET route=/downloads/{token} status=404` — the
  concrete token (`TOKEN_SECRET_XYZ`) is absent.
- Oversize body → the middleware logs `route=<body-too-large> status=413`.
Covered by `test_upload.py::test_rejected_upload_is_logged_without_secrets` +
`test_oversize_body_rejection_is_logged` and
`test_download.py::test_download_404_logs_route_template_not_token`.

Redaction (criterion 10) is preserved: reject logs carry only the field allow-list and a
route template, never the key/token/filename.

## Failed

None.

## Not run

Unchanged, pre-declared not-locally-verifiable (crash durability, timing constant-time, e2e
peak-memory under load). uvicorn access-log token leak is moot (access_log off + rejects now
logged via the redacting path).

## Findings (0 blocker, 0 risk, 3 advisory)

- **VF-8 (tests, advisory)** — middleware streaming->413 path only unit-tested.
- **VF-9 (security, advisory)** — no expiry reaper (documented deferral).
- **VF-6 (dependency, advisory)** — open dep floors (mitigated by uv.lock).

Sub-agents not re-dispatched: the delta is reject-path logging with new tests, no
acceptance-criteria behavior change; the prior full audits (02-02-08Z) remain valid. VF-7's
closure was confirmed inline with a live redaction check.

## Verdict

**PASS.** All 12 acceptance criteria verified; VF-7 closed. 112 tests green, gate clean.
0 blockers, 0 risks, 3 advisories (all accepted/deferred). Clean to `review` or to ship.
