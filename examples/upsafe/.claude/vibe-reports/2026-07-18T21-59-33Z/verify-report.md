# Verify report

Plan under test: .claude/vibe-reports/2026-07-18T17-30-16Z/verification-plan.md
Build under test: .claude/vibe-reports/2026-07-18T17-30-16Z (checkpoints 0–8, all overseer-approved)

## Passed

**Automated gates**
- `uv run pytest` — **94 passed**, 0 failed (exit 0). Per-test results captured; every
  test file green (config, tokens, metadata, storage, validation, auth, logging, upload,
  download, e2e_security).
- `make pre-commit` — **exit 0**: isort clean, black clean, flake8 clean, **pylint 10.00/10**,
  **mypy --strict clean** (12 source files).
- No residue: no `./upsafe-data` created by the suite (tests use isolated tmp roots).

**Acceptance criteria (all 12 verified)**
1. **Auth enforced** — `test_upload.py::test_missing_key_rejected_and_nothing_persisted`
   (401 + no file + no row), `test_wrong_key_rejected`, `test_happy_path…` (201 + token);
   `test_auth.py` unit matrix.
2. **Allow-list by extension** — `test_upload.py::test_disallowed_extension_rejected`
   (415, nothing persisted) + `test_validation.py` unit.
3. **Allow-list by content signature** — `test_upload.py::test_bad_magic_rejected` (script
   as `.png` → 415) + `test_validation.py::test_sniff_signature_rejects_script_as_png`,
   `test_resolve_type_rejects_binary_as_text`.
4. **Size limit (streaming, no buffer)** — `test_storage.py::test_oversize_aborts_early_with_no_residue`
   (early abort via counting reader + no residue), `test_peak_buffer_bounded_by_chunk_size`
   (memory bound independent of size); `test_upload.py::test_oversize_rejected_mid_stream_no_residue`
   (413 + nothing persisted).
5. **Path-traversal defense** — `test_storage.py` `open_within_root` accept/reject matrix
   (`../`, absolute, backslash, empty/`.`/`..`); `test_e2e_security.py::test_traversal_filenames_are_stored_safely`
   (4 HTTP variants → CSPRNG name, attacker fragments absent under data root).
6. **Random storage names** — `test_tokens.py` (128-bit hex, distinctness);
   `test_e2e_security.py::test_identical_uploads_get_distinct_names_and_tokens`.
7. **Token round-trip** — `test_download.py::test_round_trip_returns_exact_bytes_with_safe_headers`
   (sha256 match, `attachment`, `image/png`, `nosniff`).
8. **Token opacity** — `test_download.py::test_unknown_and_expired_are_indistinguishable`
   (equal status + byte-identical body); **additionally confirmed live in this verify run**
   that the header sets are identical modulo `Date` (both `content-length: 22`,
   `content-type: application/json`). See finding VF-1 — the header equality is not yet
   asserted in the automated test.
9. **Expiry** — `test_metadata.py::test_get_expired_token_returns_none`,
   `test_expiry_boundary_is_exclusive`; `test_download.py::test_expired_token_returns_404`.
10. **No secret leakage** — `test_logging.py` (field allow-list; route template not concrete
    path); `test_e2e_security.py::test_full_cycle_leaks_no_secrets_in_logs` (key/token/filename
    absent, buffer non-empty). File-contents facet: structural only (see finding VF-2).
11. **Filename sanitization (outbound)** — `test_validation.py::test_content_disposition_neutralizes_header_injection`
    (strips CR/LF/`;`/quotes/path-seps, percent-encoded `filename*`).
12. **Health check** — `test_download.py::test_healthz_needs_no_auth_and_leaks_nothing`.

## Failed

None. No acceptance criterion is failing; no automated check failed.

## Not run

- **True crash-consistency across power loss** — declared not-locally-verifiable in the
  verification plan (needs fault injection). Ordering + cleanup are covered by
  `test_storage.py` (fsync/rename spies, orphan-unlink).
- **Timing-channel constant-time** (token lookup & API-key compare) — declared out-of-scope;
  covered by code inspection (single PK lookup; `secrets.compare_digest`).
- **E2E peak-memory under real load** — declared not-locally-verifiable (TestClient buffers
  client-side); the load-bearing proof is the storage-layer bounded-buffer test.
- **uvicorn access-log redaction (production form)** — declared out-of-scope (TestClient
  emits no uvicorn access log). Reviewer note: keep tokens in the path, not query, in prod.

## Coverage gaps (from vibe-test-designer)

- **VF-1 (risk, criterion 8):** opacity test asserts body+status but not header-set equality
  the plan promised. The behavior is verified passing this run; the *test assertion* is
  missing → latent-regression risk. Close in `build` by asserting normalized header equality.
- **VF-2 (advisory, criterion 10):** file-contents secret class not sentinel-scanned e2e
  (rests on the structural field-allow-list unit test).
- **VF-3 (advisory, criterion 5):** NUL-in-filename variant not exercised at the HTTP layer
  (structurally moot — filename is never a path component).

## Security spot-check (from vibe-security-auditor)

No blockers, no risks. Verified sound: structural path-traversal defense, streaming size cap
+ many-parts/spool DoS bounds, constant-time key compare, 256-bit token opacity,
redacting logs, secure defaults (no CORS, debug off, 127.0.0.1, 0600 temp files, `.env`
gitignored), attachment+nosniff+sanitized Content-Disposition, parameterized SQLite. Three
hardening advisories: unauthenticated FastAPI docs/openapi (VF-4), head-only content
validation (VF-5, mitigated by attachment+nosniff), open-ended dependency floors (VF-6,
mitigated by committed uv.lock).

## Verdict

**PASS.** All 12 acceptance criteria are verified (criterion 8's header opacity confirmed
live in this run). Full test suite green, lint/type gate clean. The 6 findings are 1 test
`risk` (missing opacity header assertion) + 5 advisories (test-hardening + security-hardening);
**none block** — no criterion is failing or unverified.

Routing: findings are non-blocking, so verification does not force a return to `build`.
Recommended next mode: `review` (independent quality/security pass). The 6 findings are
optional hardening items a follow-up `build` could pick up (VF-1 first).
