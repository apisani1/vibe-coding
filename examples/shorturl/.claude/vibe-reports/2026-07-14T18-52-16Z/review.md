# Review — URL Shortener Service

Upstream artifacts (ground truth): spec.md (../2026-07-14T16-27-26Z/), design.md + decisions.md
(../2026-07-14T16-55-12Z/), plan.md + build-log.md (../2026-07-14T17-04-58Z/).
Scope: the full built tree (greenfield) — `src/shorturl/*.py`, `tests/*.py`, `pyproject.toml`,
`README.md`. Sub-agents: vibe-code-reviewer, vibe-security-auditor.

## Verdict: PASS — no blockers, no risks

Both reviewers independently reached PASS. The build traces cleanly to the design's module
table, honors every decision in `decisions.md` (Flask/waitress/argparse, SQLite WAL +
FK + busy_timeout, base62, 302, env API key with constant-time compare), and holds to the
"functions over classes, small units, separate construction from use, pass `conn` in"
philosophy throughout. 86 tests pass; all five static gates clean.

## Blockers

None.

## Risks

None.

## Advisories (5 — all optional hardening/cleanup)

1. **Non-ASCII API key → 500 instead of 403** (`api.py:62`, security; *flagged
   independently by both reviewers*). `hmac.compare_digest` raises `TypeError` on a str with
   non-ASCII characters; Werkzeug decodes headers latin-1, so an `X-API-Key` with a high byte
   reaches the gate and 500s instead of returning the contracted 403. **Fails closed** — no
   bypass, no state change — so it is robustness, not a hole. Fix: compare on bytes
   (`provided.encode("utf-8")` vs `expected.encode("utf-8")`) or treat any compare exception
   as a 403. *This is the one finding worth actioning — a ~2-line fix that also merits a test.*
2. **Unused dev dependency** (`pyproject.toml:30`, dependency). `types-pyyaml` is a
   profile-seed leftover; nothing imports yaml. Drop it.
3. **Dependency floors + no lockfile** (`pyproject.toml:9`, dependency; carried + reconfirmed).
   `flask>=3.0`, `waitress>=3.0` with no cap and no `uv.lock` → non-reproducible installs.
   Commit `uv.lock`; consider `<4` caps.
4. **No `MAX_CONTENT_LENGTH`** (`api.py:39`, security; carried + reconfirmed). Create body is
   buffered before validation; authenticated-only, so hardening. Set e.g. `16*1024`.
5. **Referer/User-Agent stored + echoed** (`db.py:164` / `api.py:131`, security; carried).
   Latent stored-XSS *only* if a future HTML UI renders `top_referers` unescaped. Safe as
   JSON today.

Carried from verify (test-coverage advisories, not re-litigated): AC #11 cascade covered
transitively via the db-layer test; R6 auto-code collision-retry path unexercised.

## Surgical-diff / design-fit audit

Clean. Every module maps to a design responsibility; no speculative abstraction, no
unrequested configurability, no impossible-scenario error handling. The reviewer confirmed
the load-bearing paths: the three-way `codes.status` helper is the single source of expiry
logic backing both the redirect gate and display; the 410 branch returns *before*
`insert_click` (no click on expired/deactivated); the per-request connection is closed in
`teardown_appcontext` even when the auth gate short-circuits (no leak); stats aggregation
uses parameterized `substr`/`LIMIT`; CLI exit codes map `False`→1 correctly.

Two micro-notes (not findings): `_open_connection` is registered before `_require_api_key`,
so an unauthenticated `/api/*` request opens+closes a connection before rejection
(negligible; reversing registration order avoids it).

## Security summary

No blockers, no risks. SQL fully parameterized (incl. the day-bucket and LIMIT queries); no
shell/subprocess/eval/template surfaces; open-redirect correctly scoped to http/https
(`javascript:`/`data:`/`file:` rejected), and the 302 is client-side so there is no SSRF;
API key constant-time + fail-closed + never logged; Flask debug off, waitress not the dev
server, loopback bind, no CORS; error bodies are static JSON with no trace/path leakage.
Spec-deferred items (no rate limiting, single shared key, no IP capture) are acknowledged
design limitations, not findings.

## Route

**Clean review → ship-ready.** No blocker routes anything back to `plan` or `build`. The 5
advisories are optional; if you want to action them, advisory #1 (the 500-on-non-ASCII-key)
is the highest-value — a tiny, well-scoped `build` checkpoint (bytes compare + a test), and a
natural place to also drop `types-pyyaml` and commit `uv.lock`. The MVP is verified (15/15
ACs) and independently reviewed.

Session-context worth persisting (suggest `env`): the profile config conflict
(`[tool.isort] lines_after_imports` vs Black) was fixed in the global profile this session;
a CLAUDE.md for this repo could record the run/test commands and the API-key/DB env vars.
