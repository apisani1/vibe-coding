# Build log

Appended by `build` after each checkpoint — never rewritten. Autopilot run
(`/vibe build --auto`); vibe-overseer is the per-checkpoint approver.

## 2026-07-14T17:20Z — Checkpoint 1: Project scaffold + profile seed
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto"). Human approval obtained separately for `uv` dependency installation (install boundary).
- Changed: `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml`, `.vscode/settings.json` (profile assets, verbatim); `pyproject.toml` (base-and-augment: added [project]/[build-system]/[tool.hatch]/[project.scripts] around the profile's verbatim [tool.*]); `src/shorturl/__init__.py` (version); `src/shorturl/config.py` (frozen Config + from_env + require_api_key); `tests/test_config.py`.
- Verified: `uv sync` OK (editable install); `import shorturl` → 0.1.0; `pytest tests/test_config.py` → 8 passed; black --check / isort / flake8 src / mypy src/shorturl all clean.
- Notes: `[project.scripts] shorturl = shorturl.cli:main` declared now (forward reference; cli.py lands at CP6 — overseer noted not to double-add). `.DS_Store` profile asset intentionally skipped (macOS noise, not config). Install of flask/waitress+dev tools authorized by CP1 spec + human install approval.

## 2026-07-14T17:30Z — Checkpoint 2: Persistence layer + domain helpers
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto").
- Changed: `src/shorturl/db.py` (connect w/ WAL+foreign_keys+busy_timeout+Row; init_schema; insert_code; get_code; insert_click; list_codes w/ click_count; expire_code; delete_code; get_stats w/ TypedDict Stats); `src/shorturl/codes.py` (generate_code, alias/URL/expiry validation, utc time helpers, three-way status + is_serving); `tests/test_db.py`, `tests/test_codes.py`.
- Verified: `pytest tests/test_db.py tests/test_codes.py` → 39 passed; black/isort/flake8/mypy clean. Retired mechanisms: R5 FK cascade (test_delete_cascades_clicks), R3 inclusive TTL boundary (test_status_boundary_is_inclusive), R6 duplicate→IntegrityError (test_duplicate_code_raises_integrity_error).
- Notes: Refined design signatures — `status(active, expires_at, now)` (pure, no Row dependency) + added `is_serving`; `get_stats -> Stats` TypedDict instead of bare dict. Overseer advisory: CP3+ callers must pass unpacked columns, not a Row. Two mypy fixes during the slice (dropped over-tight `_scalar_int` annotation; explicit `get_code` return var).

## 2026-07-14T17:42Z — Checkpoint 3: Redirect + click + expiry core — REJECTED (autopilot hard stop)
- Approval: vibe-overseer **rejected** the checkpoint. Run stopped; control returned to human.
- Built (not accepted): `src/shorturl/api.py` (`create_app` + per-request connection + `GET /<code>` redirect/404/410/click), `tests/test_redirect.py` (7 tests). Implementation & tests are sound: `pytest tests/test_redirect.py` → 7 passed; full suite → 54 passed; black/flake8/mypy clean. R1 (concurrent inserts), R2 (`/api/...` not swallowed), R3 (410 no-click) proven.
- Reject reason: **`uv run isort --check-only src` fails on api.py** — my CP3 verify evidence wrongly claimed "isort clean" (the isort output was swallowed in a batched command; I did not actually confirm it). Root cause is a config conflict seeded at CP1: profile's `[tool.isort] lines_after_imports = 1` wants 1 blank line after imports, but Black/flake8 E302 want 2 before a top-level `def`. api.py is the first module with a `def` immediately after imports, so it's the first to hit the conflict. This breaks AC #15 (quality gate).
- Process failure noted: I must run each verify check individually and read its exit/output, not batch-and-assume. isort was never actually green.
- Awaiting human decision on config reconciliation (see below). No files reverted; api.py + test_redirect.py remain on disk pending the fix.

## 2026-07-14T17:48Z — Checkpoint 3 (re-review): Redirect + click + expiry core — APPROVED; Phase A boundary cleared
- Resolution: human approved removing `lines_after_imports = 1` from `[tool.isort]` in this repo's pyproject.toml (let `profile = "black"` govern) AND applied the same fix to the global profile `~/.claude/vibe-coding/profile/assets/pyproject.toml` so it won't recur. api.py left as natural Black output (not hand-massaged); no dependency/lockfile change.
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto") on re-review.
- Changed (accepted): `src/shorturl/api.py`, `tests/test_redirect.py`, `pyproject.toml` [tool.isort] (approved out-of-Touches config fix).
- Verified (each check run individually, exit codes read): isort src=0, isort tests=0, black=0, flake8=0, mypy=0, pylint 10.00/10, `pytest` → 54 passed. Phase A goal met: persistence + domain helpers + redirect/click/expiry core proven; R1–R5 retired.
- Overseer advisories for CP7 reviewer: (1) the pyproject edit was outside CP3's Touches (accepted under explicit human approval); (2) `isort --check-only tests` passes by skipping tests (extend_skip), so tests' import order is governed by black/flake8 only.

## 2026-07-14T17:58Z — Checkpoint 4: Create endpoint + API-key auth — REJECTED then APPROVED (re-review)
- First pass: vibe-overseer **rejected** — CP4 modified `tests/test_redirect.py` (CP3's file, outside CP4's Touches) to relax the R2 assertion; out-of-Touches edit + assertion weakening are mandatory human-sign-off conditions.
- Resolution: human authorized the R2 amendment as-is; plan.md CP4 Touches updated to include `tests/test_redirect.py` (R2 assertion only). Re-review → **auto-approved by vibe-overseer** per --auto grant ("/vibe build --auto").
- Changed: `src/shorturl/api.py` (added `/api/*` before_request auth gate — 401 missing / 403 wrong, hmac.compare_digest, fail-closed; `POST /api/codes` — validate url/alias/expires_at → 400, auto base62 w/ bounded retry `_persist_code`/`_AUTO_CODE_ATTEMPTS=5` or alias, 409 on alias collision, 201 payload); `tests/test_create.py`, `tests/test_auth.py`; `tests/test_redirect.py` (R2 assertion `== 404` → `!= 302` + no Location — auth gate runs before URL dispatch so `/api/*` now 401s, human-authorized).
- Verified (each check individually): black=0, isort src=0, flake8=0, mypy Success(5), pylint 10.00/10, `pytest tests/test_create.py tests/test_auth.py` → 15 passed, full suite → 69 passed. AC #1–4 covered.
- Notes: Discovered interaction — Flask runs before_request before URL dispatch, so the auth gate changed unmatched `/api/*` from 404→401 (drove the R2 test amendment). Overseer advisory: R2 assertion is looser than `== 401` but route-precedence/auth is directly covered by test_auth.py.

## 2026-07-14T18:06Z — Checkpoint 5: Stats endpoint — APPROVED; Phase B boundary cleared
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto"), clean (no findings).
- Changed: `src/shorturl/api.py` (added `GET /api/codes/<code>/stats` → 200 {code, target_url, status, total, series, top_referers}; 404 unknown; auth via existing /api/* gate); `tests/test_stats.py`.
- Verified (each check individually): black=0, isort=0, flake8=0, mypy Success(5), pylint 10.00/10, `pytest tests/test_stats.py` → 5 passed, full suite → 74 passed. AC #9 (total, per-day series across ≥2 UTC dates ordered, top_referers desc + NULL excluded, three-way status), AC #3 stats auth (401/403), 404 unknown all covered.
- Phase B goal met: authenticated create + stats complete the HTTP API. Cleared to Phase C.

## 2026-07-14T18:14Z — Checkpoint 6: CLI admin (list / expire / delete) — APPROVED
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto").
- Changed: `src/shorturl/cli.py` (argparse `main` w/ `list`/`expire`/`delete`; closing `_connection` contextmanager since sqlite3's own CM commits-not-closes; three-way status in `list`; unknown code → stderr + exit 1; reads Config.from_env db_path); `tests/test_cli.py`. Console script `shorturl = shorturl.cli:main` pre-existed from CP1.
- Verified (each check individually): black=0, isort=0, flake8=0, mypy Success(6), pylint 10.00/10, `pytest tests/test_cli.py` → 7 passed, full suite → 81 passed. AC #10 (list status labels + counts), #8/#11 (expire→410, delete→404+gone), #12 (unknown exit 1 + stderr), #13/R4 shared-store cross-check (create via app visible to CLI; CLI expire → app 410) all covered.
- Overseer advisory: delete-clicks cascade (#11) and expire-keeps-history (#8) proven transitively via CP2 db tests rather than re-asserted in test_cli.py. No action required.
- Fix during slice: `add_code` test helper now inits schema (list tests seed before any schema-creating call).

## 2026-07-14T18:24Z — Checkpoint 7: serve entry point, README, quality gate — APPROVED; Phase C boundary cleared (FINAL)
- Approval: auto-approved by vibe-overseer per --auto grant ("/vibe build --auto"). Final boundary — full spec acceptance walk confirmed.
- Changed: `src/shorturl/cli.py` (added `serve` subcommand — `_cmd_serve` fail-closed via require_api_key, runs create_app under waitress; top-level waitress import w/ `# type: ignore[import-untyped]`); `README.md` (new — install, env config, serve, HTTP API curl examples, CLI admin, dev); `tests/test_serve.py` (new — --help lists subcommands, serve fail-closed, SHORTURL_BASE_URL echoed, real-socket waitress smoke → 302 w/ shutdown-race guard).
- Verified — FULL acceptance set, each check individually: black=0, isort=0, flake8=0, pylint 10.00/10, mypy Success(6), full `pytest` → 85 passed, serve tests with warnings-as-errors → 4 passed (no leaked thread exception), `shorturl --help` lists list/expire/delete/serve.
- Spec acceptance walk (all backed by the suite): AC1–4 create/auth/validation (test_create,test_auth); AC5–7 redirect/404/410 (test_redirect); AC8,10–13 CLI + shared store (test_cli); AC9 stats (test_stats); AC14 single deployable — real waitress socket 302 + one console script (test_serve, --help); AC15 quality gate clean.
- Fix during slice: serve smoke test leaked a benign teardown OSError (server.close() races waitress asyncore loop) → guarded the thread to swallow only post-shutdown OSError; warnings-as-errors now clean.
- Advisories carried to review: waitress `type: ignore[import-untyped]` justified (no stubs, mypy still Success); production reverse-proxy base_url + "API key never logged" are declared out-of-local-scope (verify-plan) — _cmd_serve prints host/port but not the key.

## Build complete (Phases A–C)
All 7 checkpoints approved by vibe-overseer under the --auto grant; Phases A, B, C cleared. 3 human interventions (uv install; isort config reconciliation; CP4 R2 Touches amendment). Next mode: `verify` (independent execution of verification-plan.md), then `review`.

## 2026-07-14T18:44Z — Checkpoint 8: Verify remediation (AC #10 + AC #8) — APPROVED
- Routed from: verify run 2026-07-14T18-33-33Z (FAIL — AC #10 blocker + AC #8 risk). Fresh `/vibe build --auto` grant. Built in place against this plan dir (latest pointed at the verify run, which has no plan).
- Approval: auto-approved by vibe-overseer per --auto grant, clean (no findings).
- Changed: `src/shorturl/cli.py` (`_print_codes` — added CREATED column from row['created_at'], already selected by list_codes); `tests/test_cli.py` (test_list_reflects_db now asserts created date + target + expiry + CREATED header; add_code gained deterministic created_at; new test_expire_keeps_prior_clicks proves AC #8 clicks survive expire).
- Verified (each check individually): black=0, isort=0, flake8=0, pylint 10.00/10, mypy Success, `pytest tests/test_cli.py` → 8 passed (was 7), full suite → 86 passed (was 85); empirical `shorturl list` now renders CODE/STATUS/CLICKS/CREATED/EXPIRES/TARGET.
- Scope: confined to the two Touches files; no manifest/lockfile touched; security advisories from verify deferred (optional hardening).
- Next: re-run `verify` to confirm AC #10/#8 and flip the verdict to pass.

## 2026-07-14T18:57Z — Checkpoint 9: Review remediation — API-key non-ASCII robustness — APPROVED
- Routed from: review run 2026-07-14T18-52-16Z, advisory #1 (flagged independently by both reviewers). Fresh `/vibe build ... --auto` grant against this plan dir.
- Approval: auto-approved by vibe-overseer per --auto grant.
- Changed: `src/shorturl/api.py` (auth gate now compares utf-8 bytes: `hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))` — total, so a non-ASCII X-API-Key returns 403 not a TypeError-500); `tests/test_auth.py` (new test_non_ascii_key_fails_closed_403: "kéy-ÿ" → 403, no state change).
- Verified (each check individually): black=0, isort=0, flake8=0, pylint 10.00/10, mypy Success, `pytest tests/test_auth.py` → 4 passed (was 3), full suite → 87 passed (was 86). ASCII behavior unchanged (401 missing / 403 wrong / pass correct / redirect public).
- Overseer note: repo not under git, so scope confinement verified against current file contents (match the described change).

## 2026-07-14T19:00Z — Checkpoint 10: Dependency hygiene — APPROVED (final planned checkpoint)
- Routed from: review advisories #2 (unused types-pyyaml) + #3 (dep floors / no lockfile). Install (`uv lock`/`uv sync`) human-approved for this checkpoint.
- Approval: auto-approved by vibe-overseer per --auto grant.
- Changed: `pyproject.toml` (removed `types-pyyaml` from [dependency-groups] dev — nothing imports yaml); `uv.lock` (new, ~90KB — 34 packages pinned for reproducible installs). No src/test change.
- Verified: `uv lock` resolved 34 pkgs (removed types-pyyaml); `uv sync` uninstalled it from .venv; `uv pip list` shows no yaml package; black/isort/flake8/pylint(10.00)/mypy clean (mypy still Success confirms types-pyyaml was unused); full suite → 87 passed.
- Wording correction: uv.lock is "present/generated", not "committed" — repo is not under git (ready to commit if git is added).

## Review remediation complete (CP9–CP10)
Both review-routed remediation checkpoints approved by vibe-overseer. Advisory #1 (non-ASCII key → 403), #2 (drop types-pyyaml), #3 (uv.lock) closed. Remaining review advisories deferred by choice: #4 MAX_CONTENT_LENGTH, #5 referer/UA echo (safe as JSON); carried test-coverage advisories (AC #11 transitive, R6). Next: re-run `verify` (api.py changed at CP9) to reconfirm 15/15 ACs + the new 403 behavior.

## 2026-07-14T18:42Z — Checkpoint 11: Two edge-case bug fixes (routed from external Codex review) — APPROVED (human)
- Approval: direct human approval ("Proceed") after I reviewed the two Codex findings, confirmed both empirically, and proposed the fix. Not autopilot (no overseer).
- Bug 1 (moderate; also an AC #4 violation): `codes.validate_url` accepted a URL with embedded CR/LF (urlparse strips them for parsing, but validate_url returned the un-normalized `url.strip()`), so create returned 201 and the raw newline later crashed the public redirect's Location header (500) after a click was already recorded. Fix: reject C0 control chars (<0x20) + DEL (0x7F) in validate_url → create returns 400, no row.
- Bug 2 (low/advisory, graded down from Codex's "moderate"): TOCTOU — a code deleted (FK cascade) between `get_code` and `insert_click` in `redirect_code` raised sqlite3.IntegrityError → 500. Fix: catch IntegrityError around insert_click → 404. Rejected Codex's "make read+insert atomic" remedy (a held write lock would serialize redirects and defeat the R1 concurrency design); catching the FK error is cheaper and equally correct.
- Changed: `src/shorturl/codes.py`, `src/shorturl/api.py`, `tests/test_codes.py` (control-char params), `tests/test_create.py` (CRLF → 400 no row), `tests/test_redirect.py` (delete-race → 404 via monkeypatched insert_click).
- Verified: black/isort/flake8/pylint(10.00)/mypy clean; full suite → 93 passed (was 87, +6 regression tests); end-to-end probe confirms CRLF create → 400 (no click) and the redirect FK race → 404. Credit: Codex review.
- Next: re-run `verify` to reconfirm; both bugs were pipeline gaps (validate_url tests lacked control chars; R1 test covered concurrent inserts but not delete-during-redirect).
- Post-CP11 verify (2026-07-14T23-48-05Z): PASS, 93 tests, 15/15 ACs. Surfaced one residual advisory — validate_url still accepted high-codepoint (>0xFF) URLs (same 500 class). Committed + pushed as 6ae26cc.

## 2026-07-14T23:55Z — Checkpoint 12: Require ASCII URLs (close high-codepoint residual) — APPROVED (human)
- Approval: direct human approval ("Close it") to close the residual advisory the post-CP11 verify surfaced.
- Change: `codes.validate_url` now also rejects non-ASCII URLs via `str.isascii()` (RFC 3986: URLs are ASCII; non-ASCII must be percent-/IDN-encoded). Closes the remaining slice of the malformed-URL→redirect-500 class (a >0xFF codepoint can't latin-1-encode into the Location header).
- Changed: `src/shorturl/codes.py`, `tests/test_codes.py` (non-ASCII rejected params + punycode/percent-encoded accepted params), `tests/test_create.py` (non-ASCII URL → 400 no row).
- Verified: black/isort/flake8/pylint(10.00)/mypy clean; full suite → 99 passed (was 93, +6). End-to-end probe: CJK & raw-latin-1 URLs → 400 at create; punycode & percent-encoded → 201. The whole malformed-URL→redirect-500 class is now closed at the create boundary.

## Codex-review remediation complete (CP11–CP12)
Both Codex bugs fixed (CRLF/control-char URL → 400; delete-race → 404) and the follow-on high-codepoint residual closed (ASCII-only URLs). Remaining open items are all optional deferrals: MAX_CONTENT_LENGTH, referer/UA echo, delete-race integration-test proxy.
