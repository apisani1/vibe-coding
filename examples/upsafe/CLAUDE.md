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
3. **Size cap is enforced at the transport layer** by `middleware.BodySizeLimitMiddleware`
   (counts body bytes off ASGI `receive` → 413 before buffering) — Starlette's
   `max_part_size` does NOT bound file parts, only in-memory fields. `store_stream`'s
   running byte guard enforces the exact per-file limit and cleans its temp. Never buffer
   the whole body or rely on `max_part_size` for files.
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
