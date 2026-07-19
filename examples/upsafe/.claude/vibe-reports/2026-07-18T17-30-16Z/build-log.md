# Build log

Autopilot run (`--auto`). Grant: `/vibe build --auto` at 2026-07-18T17:40:48Z,
max_checkpoints=10. vibe-overseer is the per-checkpoint approver. Dependency install
was approved directly by the human (out-of-band, since `--auto` does not cover installs).

## 2026-07-18T17:40:48Z — Checkpoint 0: Seed repo from preference profile
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — reviewed with CP1.
- Changed: `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml`, `.vscode/settings.json` (copied verbatim from profile); skipped `.DS_Store` (macOS noise). `pyproject.toml` synthesized base-and-augment (profile [tool.*] + dev deps verbatim; added [build-system] hatchling, [project] metadata, runtime deps, httpx dev).
- Verified: files present, add-only (no pre-existing files overwritten).
- Notes: `.gitignore` already ignores `.env` + `.DS_Store`.

## 2026-07-18T17:41Z — Checkpoint 1: Project scaffold + config + token primitives
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto").
- Changed: `src/upsafe/__init__.py`, `src/upsafe/errors.py`, `src/upsafe/config.py`, `src/upsafe/tokens.py`, `README.md` (stub), `tests/test_config.py`, `tests/test_tokens.py`.
- Verified: `uv sync` installed deps (human-approved; starlette 1.3.1, python-multipart 0.0.32); `uv run python -c "import upsafe"` OK; `uv run pytest tests/test_config.py tests/test_tokens.py` → 18 passed.
- Notes: Overseer advisory (non-blocking) — README.md is nominally CP8's Touches but is a required consequence of pyproject `readme` field; CP8 still owes full docs. `python-multipart` present for CP6.

## 2026-07-18T17:48Z — Checkpoint 2: Metadata store (SQLite)
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — clean, no findings.
- Changed: `src/upsafe/metadata.py`, `tests/test_metadata.py`.
- Verified: `uv run pytest tests/test_metadata.py` → 7 passed. Schema matches design erDiagram; get_object returns None for both unknown and expired (opacity precondition); commit inside insert_object preserves D9 ordering.
- Notes: Overseer noted isolation_level=None + explicit commit is redundant-but-harmless; no change required.

## 2026-07-18T17:55Z — Checkpoint 3: Storage core — REJECTED by vibe-overseer (autopilot stop)
- Verdict: REJECT. Autopilot run halted; control returned to human.
- Reason (blocker, design-drift): CP3 modified `src/upsafe/errors.py` (added `PathEscape`) but CP3's authorized Touches list is only `src/upsafe/storage.py` + `tests/test_storage.py`. Scope/Touches expansion is a mandatory stop under --auto — not a self-approvable deviation.
- Technical evidence (independently re-run by overseer): `uv run pytest tests/test_storage.py` → 11 passed. All security claims verified sound: early streaming abort (read 5120 of 1,000,000 bytes), temp cleanup, chunk-bounded peak memory, temp-fsync→rename→dir-fsync ordering, post-publish orphan unlink, traversal guard rejects ../ + absolute + nested-escape. No tautological tests.
- Overseer advisory (non-blocking): open_within_root treats empty stored_name as root; a basename/non-empty check would harden it (unreachable given server-generated names).
- CP3 NOT ticked. Awaiting human decision: (a) amend CP3 Touches to include errors.py and resume, or (b) route back to `plan`.

## 2026-07-18T18:00Z — Checkpoint 3: Storage core — APPROVED (re-submission)
- Approval: auto-approved by vibe-overseer per --auto grant after human-approved Touches amendment + advisory hardening.
- Changed: `src/upsafe/storage.py`, `src/upsafe/errors.py` (PathEscape), `tests/test_storage.py`.
- Verified: `uv run pytest tests/test_storage.py` → 15 passed. Load-bearing streaming/atomicity/traversal proofs all green; open_within_root hardened to reject empty/./../separator names.
- Notes: Resolves the prior REJECT. CP3 Touches amended in plan.md with logged human approval.

## 2026-07-18T18:00Z — Phase A boundary
- Phase A (config, tokens, metadata, storage) complete. Full suite green (see build-log verify below). No re-plan needed. Entering Phase B.

## 2026-07-18T18:05Z — Checkpoint 4: Validation
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — clean, no findings.
- Changed: `src/upsafe/validation.py`, `tests/test_validation.py`.
- Verified: `uv run pytest tests/test_validation.py` → 26 passed. Two-layer fail-closed: extension allow-list + magic-byte table (rejects script-as-png) + is_safe_text (rejects NUL/control/invalid-UTF-8, tolerates split multibyte); content_disposition neutralizes header injection. D1 honored (hand-rolled table, optional `<` heuristic omitted as required, stdlib-only).

## 2026-07-18T18:10Z — Checkpoint 5: Auth + redacting logging
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — clean, no findings.
- Changed: `src/upsafe/auth.py`, `src/upsafe/logging.py`, `tests/test_auth.py`, `tests/test_logging.py`.
- Verified: `uv run pytest tests/test_auth.py tests/test_logging.py` → 8 passed. Constant-time compare_digest over utf-8 bytes (length/non-ASCII safe); log_request redacting by construction (keyword-only allow-list, logs route template not concrete /downloads/{token} path). logging.py does not shadow stdlib (absolute import).

## 2026-07-18T18:20Z — Checkpoint 6: Upload endpoint + app factory
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — 3 non-blocking advisories.
- Changed: `src/upsafe/routes.py` (POST /uploads via create_router), `src/upsafe/app.py` (create_app factory), `src/upsafe/__main__.py` (uvicorn entry), `tests/test_upload.py`.
- Verified: `uv run pytest tests/test_upload.py` → 9 passed; overseer re-ran full suite → 83 passed. Security ordering confirmed: auth before body parse; Starlette max_part_size aborts oversize mid-stream (413) + storage byte guard; extension+signature before publish; server-resolved content_type; publish-then-insert with file unlink on insert failure.
- Fixes during build: (a) isinstance against starlette.datastructures.UploadFile (not fastapi subclass); (b) empty-file check before signature (→400 not 415); (c) HTTP_413_CONTENT_TOO_LARGE (new constant). Confirmed Starlette 1.3.1 form(max_part_size=...) + MultiPartException behavior against installed source.
- Advisories (follow-ups, NOT blocking): (1) Plan said "pin Starlette" — not pinned; 413-vs-400 discrimination relies on Starlette message strings; pinning needs a pyproject edit (outside remaining Touches) → carried to end-of-build follow-ups. (2) sqlite insert runs sync in async handler (brief event-loop block). (3) oversized non-file field → 413 not 400.

## 2026-07-18T18:26Z — Checkpoint 7: Download + health endpoints
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") — 1 non-blocking advisory (unknown/expired timing diff; body+status byte-identical per criterion; timing declared out-of-scope in verification-plan).
- Changed: `src/upsafe/routes.py` (download + healthz added to create_router; app.py untouched), `tests/test_download.py`.
- Verified: `uv run pytest tests/test_download.py` → 5 passed. Round-trip exact bytes + sha256; server-resolved Content-Type + nosniff + sanitized attachment; token opacity (unknown==expired byte-identical 404); read-time expiry; download needs no API key (capability), upload still authed; healthz 200 no-auth.

## 2026-07-18T18:26Z — Phase B boundary
- Phase B (validation, auth/logging, upload, download/health) complete. Full suite green. No re-plan needed. Entering Phase C.

## 2026-07-18T18:40Z — Checkpoint 8: Hardening + docs — IMPLEMENTED, overseer review INCOMPLETE
- Status: code complete and objectively verified, but the vibe-overseer approval did NOT
  complete — the approver subagent was terminated early by an external monthly spend limit
  (not a rejection, not a finding). Under --auto the skill must not self-approve, so CP8 is
  NOT ticked and the run is paused for human decision.
- Changed (within human-approved amended CP8 Touches): `tests/test_e2e_security.py` (new),
  `README.md` (full), `.env.example` (new), `Makefile` (new), `pyproject.toml` (Starlette pin
  `>=1.3.1,<2` — resolves CP6 advisory), mechanical isort/black normalization across src/tests,
  and 5 small pylint fixes in src (logging handler set_name; disable too-many-arguments on
  log_request; disable too-many-instance-attributes on StoredObject; import uvicorn at top of
  __main__; `raise ... from exc` in routes insert-failure path).
- Verified (objective): `uv run pytest` → 94 passed; `make pre-commit` → isort/black/flake8
  clean, pylint 10.00/10, mypy --strict clean (12 files).
- Awaiting: human approval to accept CP8 (human is a valid approver), or re-run vibe-overseer
  when budget allows.

## 2026-07-18T18:55Z — Checkpoint 8: APPROVED (overseer re-dispatch)
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") on clean re-dispatch after the prior spend-limit interruption.
- Verified (overseer re-ran independently): `uv run pytest` → 94 passed; isort/black/flake8 clean; pylint 10.00/10; mypy --strict clean (12 files). e2e adversarial tests substantively prove criteria 5 (traversal), 10 (no secret leakage), 6 (distinct names/tokens). Starlette pin resolves the CP6 advisory.
- Advisories (benign): (1) uv.lock recorded the human-approved Starlette specifier (still 1.3.1, no new package/bump). (2) Ran on venv Python 3.14, not the spec's 3.12 (requires-python>=3.12 satisfied); confirm on 3.12 if that is the deploy target.

## 2026-07-18T18:55Z — Phase C boundary / BUILD COMPLETE
- All 8 checkpoints implemented, verified, and overseer-approved. Phase A/B/C boundaries green.
- Next pipeline mode: `verify` (runs verification-plan.md against the 12 acceptance criteria; advances `latest` — pass this run-dir path explicitly to re-enter build), then `review`.

## 2026-07-18T22:20Z — Follow-up build: close verify findings VF-1 + VF-4 (manual, human-approved)
- Approval: user — "fold VF-1/VF-4 into a quick follow-up build first" (explicit, action-specific). Manual build (not --auto); no overseer gate.
- VF-4 (security advisory → resolved): docs/OpenAPI now OFF by default. Added `enable_docs` to Settings + `UPSAFE_ENABLE_DOCS` env flag (default false, `_bool` parser); app factory passes docs_url/redoc_url/openapi_url=None unless enabled. Documented in `.env.example`.
- VF-1 (test risk → resolved): opacity test now also asserts normalized header-set equality (drop Date) for unknown vs expired 404s.
- Changed: `src/upsafe/config.py`, `src/upsafe/app.py`, `.env.example`, `tests/test_config.py` (flag parse + default), `tests/test_download.py` (header-set assertion + docs on/off tests).
- Verified: `uv run pytest` → 102 passed (was 94; +8 new); `make pre-commit` → isort/black/flake8 clean, pylint 10.00/10, mypy --strict clean (12 files). One mypy issue found & fixed mid-build (explicit typed FastAPI args instead of **dict unpacking).
- Remaining verify findings (unaddressed, all advisory): VF-2 (e2e content-sentinel scan), VF-3 (NUL-in-filename HTTP variant), VF-5 (head-only content validation — mitigated by attachment+nosniff), VF-6 (dep floors — mitigated by uv.lock).

## 2026-07-18T22:40Z — Follow-up build: close review findings D-1 + R-1 (manual, human-approved)
- Approval: user — "Do both D-1 and R-1" (explicit). Manual build (not --auto); no overseer gate.
- D-1 (design-drift → resolved): deleted the orphan `TooManyParts` from src/upsafe/errors.py (defined, imported/raised nowhere — grep-confirmed gone).
- R-1 (correctness → resolved): added 3 unit tests in tests/test_upload.py locking `_too_large_or_bad_request`'s message→status mapping ("Part exceeded maximum size" → 413; "Too many files/fields" → 400), so a Starlette message reword within the >=1.3.1,<2 pin fails loudly. The e2e oversize(413)/multi-file(400) tests remain the live-parser complement.
- Changed: `src/upsafe/errors.py`, `tests/test_upload.py`.
- Verified: `uv run pytest` → 105 passed (was 102; +3); `make pre-commit` → isort/black/flake8 clean, pylint 10.00/10, mypy --strict clean (12 files).
- Remaining review advisories (accepted/documented): R-2 (sqlite sync in async — MVP), R-3 (oversized field → 413 nit), S-1 (resolve_type redundant ext check — kept for standalone reuse), VF-5 (head-only validation — mitigated), VF-6 (dep floors — mitigated by uv.lock).

## 2026-07-18T23:05Z — Follow-up build: close 2 external (Codex) P1 security findings (manual, human-approved)
- Approval: user — "fold both into a follow-up build". Manual build (not --auto); no overseer gate.
- FINDING 1 (token leak via uvicorn access log → fixed): `__main__.py` now runs uvicorn with `access_log=False`. Uvicorn's default access log records `GET /downloads/<token>`, leaking the capability (contra D8). App's own redacting log_request covers observability.
- FINDING 2 (size cap not applied during file-part parsing → fixed): confirmed via Starlette 1.3.1 source (`on_part_data` only bounds non-file fields; file parts stream to SpooledTemporaryFile unchecked) and empirically (64KiB file passes a 1KiB max_part_size). Added `src/upsafe/middleware.py` `BodySizeLimitMiddleware` (counts body bytes off ASGI receive + Content-Length fast path → 413 before buffering), wired in `create_app` at `max_upload_bytes + MULTIPART_OVERHEAD_ALLOWANCE`. store_stream remains the exact per-file arbiter.
- Changed: `src/upsafe/__main__.py`, `src/upsafe/middleware.py` (new), `src/upsafe/app.py`, `tests/test_middleware.py` (new), `tests/test_upload.py`; docs `CLAUDE.md` (invariant #3 corrected), decisions.md (D10, corrects D2 premise).
- Verified: `uv run pytest` → 109 passed (+4). `make pre-commit` → pylint 10.00/10, mypy --strict clean (13 files). End-to-end: 5 MiB upload under a 1 MiB limit now returns 413 (was 201 pre-fix). Integration test proves store_stream never reached for an oversize body.
- Process note: both P1s were missed by the vibe verify/review passes. Criterion 4 now genuinely satisfied end-to-end; a fresh verify is warranted.

## 2026-07-19T02:30Z — Follow-up build: close VF-7 (failure-path logging regression) (manual, human-approved)
- Approval: user — "fold VF-7 into a follow-up build". Manual build; no overseer gate.
- VF-7 (risk → fixed): the prior access_log=False left 4xx/5xx rejects unlogged (log_request only ran on 201/200). Now every rejected request is logged through the redacting logger:
  - `app.py`: a StarletteHTTPException handler logs method + route TEMPLATE (via request.scope route.path_format, never the concrete path) + status, then delegates to FastAPI's default handler. Covers 401 (auth dep), 413/415/400 (routes), 404 (download).
  - `middleware.py`: the transport-cap 413 logs with a fixed `<body-too-large>` route label (never the path, since it fires pre-routing and the path could carry a token).
- Redaction preserved (criterion 10): route template only; no key/token/filename in reject logs (tested).
- Changed: `src/upsafe/app.py`, `src/upsafe/middleware.py`, `tests/test_upload.py`, `tests/test_download.py`.
- Verified: `uv run pytest` → 112 passed (was 109; +3). `make pre-commit` → pylint 10.00/10, mypy --strict clean (13 files). Tests assert: 401 logs route=/uploads sans key/filename; oversize 413 logged; download 404 logs route=/downloads/{token} not the token.
- Note: a fresh verify would move VF-7 to resolved; VF-8/VF-9/VF-6 remain (advisory).
