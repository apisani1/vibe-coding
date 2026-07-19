# Plan: upsafe — secure file-upload & token-download service

Upstream design: .claude/vibe-reports/2026-07-18T17-09-56Z/design.md
Upstream spec:   .claude/vibe-reports/2026-07-18T17-03-13Z/spec.md

## Risk factors (ArjanCodes step 5 — identified first)

- **Streaming size-cap depends on Starlette internals** (`max_part_size` abort + the
  `SpooledTemporaryFile` spool threshold). This is the least-owned behavior. → Mitigation:
  CP3 lands an *independent* running-byte-count guard in `storage.store_stream` first, so
  the cap holds even if the framework path surprises us; CP6 then verifies the framework
  abort itself against the installed version (pin the version, assert a peak-memory bound).
- **Content-signature validation must actually catch a script-as-`.png`.** → CP4 builds the
  signature table with adversarial unit tests (mismatched magic, disallowed type, text
  safety) before it's wired into the endpoint.
- **Atomic publish + crash-durability ordering** (temp→fsync→rename→dir-fsync→commit). →
  CP3 implements and unit-tests atomicity/traversal in isolation, before any HTTP layer.
- **Path-traversal-by-construction** is structurally simple but must be *proven*, not
  asserted. → CP3 tests the `open_within_root` guard; CP6/CP7 test the adversarial
  filenames end-to-end (they never reach the filesystem).
- **Token opacity** (missing vs expired indistinguishable) is easy to get subtly wrong. →
  CP7 tests both paths return byte-identical 404s.

## Checkpoints

### Checkpoint 1: Project scaffold + config + token primitives
- Does: Seed the repo (build CP0: profile assets verbatim + synthesized `pyproject.toml`
  from prefs — fastapi, uvicorn[standard], python-multipart; dev: pytest, httpx). Create
  `src/upsafe/` package, `config.load_settings()` (frozen `Settings`, fail-fast if
  `UPSAFE_API_KEY` unset), `tokens.new_token()`/`new_stored_name()`.
- Touches: `pyproject.toml`, profile assets, `src/upsafe/__init__.py`, `config.py`,
  `tokens.py`, `errors.py`, `tests/test_config.py`, `tests/test_tokens.py`.
- Verify: `uv run pytest tests/test_config.py tests/test_tokens.py` green; `uv run python -c "import upsafe"`.

### Checkpoint 2: Metadata store (SQLite)
- Does: `metadata.init_db/insert_object/get_object` with expiry semantics; `objects` table
  (token PK, stored_name UNIQUE, …).
- Touches: `src/upsafe/metadata.py`, `tests/test_metadata.py`.
- Verify: `uv run pytest tests/test_metadata.py` — insert+lookup, expiry returns None, UNIQUE on stored_name.

### Checkpoint 3: Storage core (streaming writer + traversal guard)
- Does: `storage.store_stream` (temp → fsync → atomic rename → **dir fsync** → return
  stored_name/size/sha256; running-byte-count size guard aborts + unlinks temp on breach),
  `storage.open_within_root` (realpath, assert inside root), `quarantine_path`.
- Touches: `src/upsafe/storage.py`, `src/upsafe/errors.py` (adds `PathEscape`, raised by
  `open_within_root`), `tests/test_storage.py`.
  *(Touches amended 2026-07-18 with human approval after vibe-overseer flagged the errors.py
  edit as outside the original list; `errors.py` is the established home for domain errors.)*
- Verify: `uv run pytest tests/test_storage.py` — sha256/size correct; **load-bearing
  streaming proofs live here** (per vibe-test-designer): a counting reader proves abort
  before over-reading with the temp unlinked, and a max-single-buffer probe proves peak
  memory ≤ chunk_size+const independent of file size; `open_within_root` rejects a crafted
  escaping name (no file outside root); fsync/rename spies assert temp-fsync→rename→dir-fsync
  ordering and insert-fails-after-publish unlinks the orphan.

### Checkpoint 4: Validation (allow-list, signatures, text-safety, filename sanitize)
- Does: `validation.check_extension`, signature table + `sniff_signature`, `is_safe_text`
  (UTF-8 + no NUL/control; optional `<` flag), `resolve_type`, `content_disposition`
  (RFC 5987, strips CR/LF/`;`/quotes/path-seps).
- Touches: `src/upsafe/validation.py`, `tests/test_validation.py`.
- Verify: `uv run pytest tests/test_validation.py` — disallowed ext rejected; script-as-png
  rejected; NUL/control text rejected; header-injection filename neutralized.

### Checkpoint 5: Auth + redacting logging
- Does: `auth.require_api_key` (FastAPI dep, `secrets.compare_digest`), `logging.configure_logging`
  + `log_request` (field allow-list only; never token/key/filename/bytes).
- Touches: `src/upsafe/auth.py`, `src/upsafe/logging.py`, `tests/test_auth.py`, `tests/test_logging.py`.
- Verify: `uv run pytest tests/test_auth.py tests/test_logging.py` — wrong/missing key rejected,
  correct key accepted; log output contains none of the secret fields for a sample request.

### Checkpoint 6: Upload endpoint + app factory
- Does: `routes.upload` wiring auth → multipart (`max_part_size=MAX_UPLOAD_BYTES`,
  `max_files=1`) → extension → sniff → store → insert → 201; error mapping
  (401/400/413/415/500). `app.create_app(settings)`, `__main__`. Pin Starlette version;
  confirm `max_part_size` + spool-threshold behavior.
- Touches: `src/upsafe/routes.py`, `src/upsafe/app.py`, `src/upsafe/__main__.py`, `tests/test_upload.py`.
- Verify: `uv run pytest tests/test_upload.py` — happy 201 + token; each reject path
  (no-key 401, oversize 413 mid-stream, bad-ext 415, bad-magic 415, empty 400) with a
  filesystem+DB snapshot proving nothing persisted on reject. The e2e peak-memory bound is
  a *secondary* best-effort check (TestClient buffers the body client-side — the load-bearing
  memory proof is CP3); drive it via a streaming request body against the pinned Starlette.

### Checkpoint 7: Download + health endpoints
- Does: `routes.download` (lookup → expiry → `open_within_root` → `FileResponse` with
  server `Content-Type`, `nosniff`, sanitized `Content-Disposition: attachment`),
  `routes.healthz`.
- Touches: `src/upsafe/routes.py`, `tests/test_download.py`.
- Verify: `uv run pytest tests/test_download.py` — round-trip sha256 match; missing vs
  expired token both identical 404; `nosniff` + attachment headers present; healthz 200 no-auth.

### Checkpoint 8: End-to-end adversarial suite + docs
- Does: Cross-cutting acceptance tests (traversal filename variants incl. `..\\`/absolute/NUL;
  full upload→download cycle log scan proves no API key/token/contents logged; two identical
  uploads → distinct names/tokens). `README.md`, `.env.example`. Wire pre-commit/lint/mypy clean.
- Touches: `tests/test_e2e_security.py`, `README.md`, `.env.example`, `Makefile` (pre-commit
  target — profile shipped none), `pyproject.toml` (explicit Starlette pin, resolving the
  CP6 advisory), and mechanical isort/black normalization across `src/**` + `tests/**`.
  *(Touches amended 2026-07-18 with human approval — CP8 is the cross-cutting hardening
  checkpoint; formatting/lint-clean inherently spans the tree, and `make pre-commit` needs a
  Makefile the profile did not provide.)*
- Verify: `uv run pytest` full suite green; `make pre-commit` (isort/black/flake8/pylint/mypy) clean.

## Phases

### Phase A: Storage & data foundation
- Goal: config, token/name generation, SQLite metadata, and the streaming/atomic/traversal-safe
  storage core all exist and are unit-proven — no HTTP yet.
- Checkpoints: 1–3
- Boundary: run `verify` before Phase B (the risky storage/atomicity primitives must be
  green before anything depends on them).

### Phase B: Validation & HTTP surface
- Goal: the full request surface works end-to-end — validation, auth, logging, upload,
  download, health — with integration tests for happy + adversarial paths.
- Checkpoints: 4–7
- Boundary: run `verify` against the 12 acceptance criteria before Phase C.

### Phase C: Hardening & docs
- Goal: cross-cutting adversarial coverage, secret-in-logs scan, docs, clean lint/type gate.
- Checkpoints: 8
- Boundary: run `verify` (final) → `review`.

## Definition of Done

- **Required:** All 12 spec acceptance criteria have a passing check. Full `pytest` suite
  green. Streaming size cap proven (413 mid-stream + peak-memory bound). Traversal proven
  structurally (no write/read outside quarantine for any adversarial name). Token opacity
  (identical 404). No secret in logs (scan). `make pre-commit` clean. README + `.env.example`.
- **Optional-later:** Background expiry sweeper; AV scan hook; single-use tokens; per-caller
  keys + rate limiting; object-store backend. (All explicitly Out of scope per spec.)

## Migration / one-off scripts

None. SQLite schema is created idempotently by `metadata.init_db` at startup.
