# Checklist: URL Shortener Service

One line per checkpoint; `build` ticks these as evidence lands — never pre-tick.

## Phase A — Foundation & risk retirement (front-loaded)
- [x] 1. Project scaffold + profile seed — verify: `uv sync`; `import shorturl`; `Config.from_env` test; black/isort/flake8/mypy clean
- [x] 2. Persistence layer + domain helpers — verify: `uv run pytest tests/test_db.py tests/test_codes.py` (CRUD, FK cascade, three-way status, stats bucketing, gen/validation, collision retry)
- [x] 3. Redirect + click + expiry core — verify: `uv run pytest tests/test_redirect.py` (302+1 click, 404, 410 TTL & deactivated no-click, /api not swallowed, concurrent-insert)
- [x] Phase A boundary — verify (overseer boundary review, --auto): full gate green, R1–R5 retired

## Phase B — HTTP write & analytics surface
- [x] 4. Create endpoint + API-key auth — verify: `uv run pytest tests/test_create.py tests/test_auth.py` (201 auto/alias, 409, 400 bad url/expires_at, 401/403)
- [x] 5. Stats endpoint — verify: `uv run pytest tests/test_stats.py` (total, multi-day series, top_referers cap, status, 404, auth)
- [x] Phase B boundary — verify (overseer boundary review, --auto): full gate green, HTTP API complete

## Phase C — CLI admin, packaging & docs
- [x] 6. CLI admin (list / expire / delete) — verify: `uv run pytest tests/test_cli.py` (list reflects DB, expire→410, delete→404+gone, unknown exit 1, shared-store cross-check)
- [x] 7. serve entry point, README, quality gate — verify: `shorturl serve` ephemeral-port smoke; `shorturl --help`; full `uv run pytest`; black/isort/flake8/pylint/mypy clean
- [x] Phase C boundary — verify (overseer boundary review, --auto): full acceptance set (AC #1–15) green; 85 tests, all static gates clean

## Remediation (routed from verify 2026-07-14T18-33-33Z)
- [x] 8. AC #10 created column + AC #8 clicks-remain test — verify: `uv run pytest tests/test_cli.py` + full suite; `shorturl list` shows CREATED; gates clean

## Remediation (routed from review 2026-07-14T18-52-16Z)
- [x] 9. API-key non-ASCII robustness (bytes compare → 403) — verify: `uv run pytest tests/test_auth.py` + full suite; gates clean
- [x] 10. Dependency hygiene (drop types-pyyaml + uv.lock) — verify: `uv sync`; uv.lock present; full suite green; gates clean [install boundary — human approval]
- [x] 11. Edge-case bug fixes (CRLF URL → 400; delete-race → 404) [Codex review] — verify: full suite + new regression tests; gates clean
- [x] 12. Require ASCII URLs (close high-codepoint redirect-500 residual) — verify: full suite + non-ASCII→400 tests; gates clean
