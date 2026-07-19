# Verify report (re-verify)

Plan under test: .claude/vibe-reports/2026-07-18T17-30-16Z/verification-plan.md
Prior verify:    .claude/vibe-reports/2026-07-18T21-59-33Z (full specialist audits)
Trigger: re-verify after the follow-up build that closed VF-1 (opacity header assertion)
and VF-4 (unauthenticated docs disabled by default).

## Passed

**Automated gates**
- `uv run pytest` — **102 passed**, 0 failed (was 94; +8 tests from the follow-up build).
- `make pre-commit` — **exit 0**: isort/black/flake8 clean, **pylint 10.00/10**,
  **mypy --strict clean** (12 files).

**Acceptance criteria** — all 12 remain verified (see the prior verify report for the full
per-criterion mapping; unchanged except the two strengthened below).

**Closed findings (this re-verify confirms):**
- **VF-1 (was risk → resolved).** `test_download.py::test_unknown_and_expired_are_indistinguishable`
  now asserts normalized header-set equality (`_norm_headers`, dropping `Date`) in addition to
  status + body. Live probe this run: unknown and expired 404s share identical headers
  (`content-length: 22`, `content-type: application/json`). Criterion 8 opacity is now
  regression-guarded in the suite.
- **VF-4 (was security advisory → resolved).** Docs/OpenAPI are off by default. Live probe:
  `/openapi.json`, `/docs`, `/redoc` → **404** with default settings; **200** only when
  `UPSAFE_ENABLE_DOCS=true`. Covered by `test_docs_and_openapi_disabled_by_default` and
  `test_docs_served_when_explicitly_enabled`, plus config-parse tests.

## Failed

None.

## Not run

Unchanged from the prior verify (all pre-declared not-locally-verifiable): true crash
durability, timing-channel constant-time, e2e peak-memory under load, uvicorn access-log
redaction. Covered by code inspection / storage-layer proofs.

## Coverage gaps / security (remaining, all advisory)

- **VF-2 (tests)** — file-contents secret class not sentinel-scanned e2e.
- **VF-3 (tests)** — NUL-in-filename not exercised at HTTP layer (structurally moot).
- **VF-5 (security)** — head-only content validation (contained by attachment + nosniff).
- **VF-6 (dependency)** — open-ended dep floors (mitigated by committed uv.lock).

Specialist sub-agents were not re-dispatched this run: the surface changed only in the two
targeted fixes plus a default-off config flag, and the prior verify (21-59-33Z) carried full
vibe-test-designer + vibe-security-auditor passes that remain valid. The four items above are
carried forward verbatim from that run.

## Verdict

**PASS.** All 12 acceptance criteria verified; VF-1 and VF-4 closed and confirmed live.
Full suite green (102), lint/type gate clean. 4 advisory findings remain — none block.

Recommended next mode: `review`.
