# Env report — upsafe

## Current state

- **No agent instructions** exist (`CLAUDE.md`, `AGENTS.md`, `.cursorrules` all absent).
- **Docs present:** `README.md` (usage/API/config/limitations), `.env.example` (all env
  vars), and a full spec/design/decisions/plan/build/verify/review trail under
  `.claude/vibe-reports/`.
- **Tooling encoded:** UV (`pyproject.toml` + `uv.lock`), `Makefile`
  (`format`/`lint`/`typecheck`/`test`/`pre-commit`/`run`), pre-commit config, src-layout,
  Black@119 / isort / flake8 / pylint / mypy --strict, pytest.
- **Recurring context an agent would otherwise re-derive each session:** the *security
  invariants* that the whole design exists to uphold (they're spread across design.md and
  code docstrings), the exact command set, and the fact that design rationale lives in
  vibe-reports rather than in-tree docs.

**Assessment:** a single short `CLAUDE.md` is warranted. A separate `agent-knowledge/`
directory is **not** — the durable rationale already lives in `.claude/vibe-reports/`
(spec, design, decisions D1–D9); CLAUDE.md should point there, not duplicate it.

## Proposed changes

**One new file: `CLAUDE.md`** (repo root). Full proposed content below — NOT yet written.

---

```markdown
# Agent Instructions — upsafe

Security-first file-upload HTTP service (FastAPI, UV, Python 3.12+). Read this before
changing code. Full rationale: `.claude/vibe-reports/` (latest `spec.md`, `design.md`,
`decisions.md` D1–D9). User/API docs: `README.md`; config: `.env.example`.

## Project Context
- **Purpose:** accept authenticated multipart uploads, validate (type allow-list + size
  cap), quarantine under a randomized name, serve back only via an unguessable, expiring
  download token. Security is the product, not a feature.
- **Entrypoints:** `src/upsafe/app.py` (`create_app(settings)` factory) → `routes.py`
  (`POST /uploads`, `GET /downloads/{token}`, `GET /healthz`); `python -m upsafe`
  (`__main__.py`).
- **Layout:** flat single-responsibility modules under `src/upsafe/` — `config`, `tokens`,
  `metadata` (SQLite), `storage` (streaming/atomic/traversal-safe), `validation`, `auth`,
  `logging`, `routes`, `app`, `errors`. State lives under one data root: `quarantine/` +
  `upsafe.db`.

## Security invariants (do NOT break these — they are the point)
1. **No client string is ever a filesystem path component.** On-disk names come from
   `tokens.new_stored_name()` (CSPRNG); the download token is only ever a DB key.
2. **`storage.open_within_root` is the fail-closed traversal guard** — keep it; never
   build a path from user input.
3. **Size cap is enforced while streaming** (`request.form(max_part_size=...)` +
   `store_stream`'s running byte guard). Never buffer the whole body or read a part
   unbounded.
4. **Two-layer, fail-closed type check:** extension allow-list AND content signature
   (`validation.resolve_type`). Never trust the client's declared content type.
5. **Atomic publish then commit:** temp → fsync → rename → dir-fsync → insert metadata;
   unlink the file if the insert fails. Never commit a token over an unpublished file.
6. **Constant-time API-key compare** (`secrets.compare_digest`); the key is never logged.
7. **`logging.log_request` is redacting by construction** — only the field allow-list;
   log the route *template*, never the concrete `/downloads/<token>` path. Don't add a
   field that could carry the token, key, filename, or bytes.
8. **Downloads are served `attachment` + `X-Content-Type-Options: nosniff`** with a
   sanitized `Content-Disposition`. Never serve inline or echo a client filename raw.
9. **Unknown and expired tokens return an identical 404** (body + headers). Preserve.

## How To Work Here
- Read existing patterns before changing code; prefer small, reviewable diffs.
- Functions over classes; type-annotate public functions; no bare `except`; docstrings
  explain *why*. Black @ 119 cols, isort.
- Define verification before implementation; every acceptance-affecting change gets a test.
- Report commands run and checks skipped.

## Common Commands
- **Install:** `uv sync`
- **Test:** `make test`  (or `uv run pytest`)
- **Typecheck:** `make typecheck`  (`mypy --strict`, must stay clean)
- **Lint/format:** `make lint` / `make format`  (flake8 + pylint 10/10; Black + isort)
- **Full gate:** `make pre-commit`  (run before every commit)
- **Run:** `make run`  (needs `UPSAFE_API_KEY`; see `.env.example`)

## Guardrails
- **Always:** run `make pre-commit` and the test suite before proposing a change is done;
  read `.claude/vibe-reports/` for design rationale.
- **Ask first:** installing/adding dependencies (network fetch); editing `pyproject.toml`
  or `uv.lock`; changing any security invariant above; touching `.env`.
- **Never:** commit or push without being asked; log secrets; weaken a security invariant
  for convenience; use a client-supplied string as a path.

## Approval Boundary
Do not edit files, install packages, run migrations, commit, deploy, or delete data
without explicit written approval. A vague "ok/sure" is not approval.
```

---

## Applied

- **2026-07-18T22:44Z** — Wrote `CLAUDE.md` (repo root, ~55 lines) exactly as proposed.
  Approval: user — "Yes, write CLAUDE.md as proposed" (explicit written approval).
- Add-only: no pre-existing file overwritten (`CLAUDE.md` did not exist). No knowledge-base
  directory created (rationale lives in `.claude/vibe-reports/`).
