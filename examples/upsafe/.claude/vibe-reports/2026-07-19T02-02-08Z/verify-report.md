# Verify report

Plan under test: .claude/vibe-reports/2026-07-18T17-30-16Z/verification-plan.md
Trigger: substantive re-verify after the two P1 security fixes (transport-layer body cap
`BodySizeLimitMiddleware`; uvicorn `access_log=False`). Both specialists re-derived from
source rather than folding forward — the prior audit had missed the file-part DoS.

## Passed

- `uv run pytest` — **109 passed**, 0 failed (was 105; +4: 3 middleware unit tests + 1
  integration test proving `store_stream` is not reached for an oversize body).
- `make pre-commit` — **exit 0**: isort/black/flake8 clean, **pylint 10.00/10**,
  **mypy --strict clean** (13 files).

**Acceptance criterion 4 — now GENUINELY verified (previously passed for the wrong reason).**
- The transport cap is exercised at three layers: `test_middleware.py` covers the
  Content-Length fast path (413 without invoking the app), the streaming/no-Content-Length
  path (aborts before the full body reaches the app), and the under-limit pass-through.
- `test_upload.py::test_oversize_body_rejected_before_reaching_storage` monkeypatches
  `store_stream` to raise, posts a body far over the limit, and asserts 413 — proving the
  cap fires *before* the body is buffered. vibe-test-designer independently confirmed
  non-tautology: rebuilding the app **without** the middleware, the same upload **reaches
  `store_stream`** (413 only via its late catch). Live check: 5 MiB upload / 1 MiB limit →
  413 (was 201 before the fix).

**Other 11 criteria — no regressions.** The middleware only counts request-body bytes;
downloads/health carry no body and under-limit uploads pass through. Each criterion's
owning tests remain present and green (auth, both allow-list layers, traversal matrix,
distinct names/tokens, round-trip + safe headers, opacity, expiry, redacting log scan,
health).

## Failed

None. No acceptance criterion is failing.

## Not run

Unchanged, pre-declared not-locally-verifiable: true crash durability, timing-channel
constant-time, e2e peak-memory under real load, uvicorn access-log redaction (now moot for
tokens since access logging is off — but see VF-7 for the observability trade-off).

## Findings (0 blocker, 2 risk, 3 advisory)

- **VF-7 (security, risk) — REGRESSION I introduced with Fix 1.** `access_log=False`
  disabled uvicorn's per-request log, and `log_request` only fires on the 201/200 success
  paths, so **all 4xx/5xx rejects (401/413/415/400/404) are now unlogged** — no audit trail
  for API-key brute-force or upload abuse. Fix: log rejects through the redacting logger
  (route template only). *(Two facets in findings.json: security @ __main__.py and the tests
  coverage gap @ routes.py — same root cause.)*
- **VF-8 (tests, advisory).** The middleware streaming→413 path is only unit-tested;
  TestClient always sets Content-Length, so the exception→`_send_413` branch isn't exercised
  end-to-end. Defensive branches (non-http scope, non-integer CL, response-already-started)
  untested.
- **VF-9 (security, advisory).** No expiry reaper — expired files persist on disk forever
  (documented MVP deferral; auditor re-raised it as worth doing given the temp-disk theme).
- **VF-6 (dependency, advisory).** Open-ended dep floors (fastapi/uvicorn/python-multipart);
  mitigated by committed `uv.lock`.

**Auditor non-finding (noted):** on the `_BodyTooLarge` unwind, Starlette's spooled temp
file isn't explicitly closed, but CPython refcounting releases it promptly (self-healing);
worth knowing for a non-refcounting runtime, not an active leak.

## Verdict

**PASS.** All 12 acceptance criteria verified — criterion 4 now genuinely met end-to-end and
covered by non-tautological checks. Overall security risk assessed **LOW** (both P1s closed,
DoS re-derived as bounded). No blockers.

**However**, VF-7 is a real observability regression I introduced and should be closed in a
quick follow-up `build` (log rejects via the redacting logger) — it does not fail an
acceptance criterion, so it does not force a route-back, but it's the top recommended fix.
Route: `build` for VF-7 (+ optionally VF-8 test, VF-9 reaper, VF-6 pins), then `review`.
