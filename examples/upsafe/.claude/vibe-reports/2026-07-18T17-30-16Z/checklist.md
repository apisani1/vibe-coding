# Checklist: upsafe — secure file-upload service

## Phase A: Storage & data foundation
- [x] 1. Project scaffold + config + token primitives — verify: `uv run pytest tests/test_config.py tests/test_tokens.py`; `import upsafe` — 18 passed ✓
- [x] 2. Metadata store (SQLite) — verify: `uv run pytest tests/test_metadata.py` — 7 passed ✓
- [x] 3. Storage core (streaming writer + traversal guard) — verify: `uv run pytest tests/test_storage.py` — 15 passed ✓ (rejected once on Touches, resolved w/ human approval)
- [x] Phase A boundary — run `verify` — Phase A suite green (see below)

## Phase B: Validation & HTTP surface
- [x] 4. Validation (allow-list, signatures, text-safety, filename sanitize) — verify: `uv run pytest tests/test_validation.py` — 26 passed ✓
- [x] 5. Auth + redacting logging — verify: `uv run pytest tests/test_auth.py tests/test_logging.py` — 8 passed ✓
- [x] 6. Upload endpoint + app factory — verify: `uv run pytest tests/test_upload.py` — 9 passed ✓
- [x] 7. Download + health endpoints — verify: `uv run pytest tests/test_download.py` — 5 passed ✓
- [x] Phase B boundary — run `verify` (12 acceptance criteria) — full suite green

## Phase C: Hardening & docs
- [x] 8. End-to-end adversarial suite + docs — verify: `uv run pytest` (94 passed); `make pre-commit` (pylint 10/10, mypy strict clean) ✓
- [x] Phase C boundary — build complete; next: `verify` (final) → `review`
