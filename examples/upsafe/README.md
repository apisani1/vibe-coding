# upsafe

Security-first file-upload HTTP service. It accepts authenticated multipart uploads,
validates each file against a type allow-list and a size cap, stores it in a **quarantine**
directory under a randomized name, and serves it back only through an unguessable, expiring
**download token**. Security is the primary requirement: the happy path is intentionally
small so the boundary around it can be reasoned about completely.

## Security properties

- **Path traversal is impossible by construction.** No client-supplied string is ever a
  filesystem path component. On-disk names are generated server-side from a CSPRNG; the
  download token is only ever a database key and never touches the filesystem. A
  resolve-within-root check backs this up as a fail-closed guard.
- **The size cap is enforced while streaming.** Oversize uploads abort mid-request (413)
  instead of being buffered whole; a partial file is never left behind.
- **Type validation is two-layered and fail-closed.** The declared extension must be on the
  allow-list *and* the content must match it — magic bytes for binary types, valid-UTF-8 /
  no-NUL for text. A script renamed `.png` is rejected.
- **Downloads are capability-gated and safe.** Tokens are 256-bit, URL-safe, and expiring;
  an unknown and an expired token return an identical `404`. Files are served as
  `attachment` with `X-Content-Type-Options: nosniff` and a sanitized `Content-Disposition`,
  so a malicious filename cannot inject headers and content is never rendered inline.
- **No secret leakage.** The API key is compared in constant time and never logged; request
  logs carry only method, route template, status, size, and duration — never the token, key,
  filename, or contents.

## Requirements

- Python 3.12+
- [UV](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
cp .env.example .env
# set UPSAFE_API_KEY in .env, e.g.:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Run

```bash
# reads configuration from the environment (see .env.example)
export UPSAFE_API_KEY=... UPSAFE_DATA_ROOT=./upsafe-data
make run          # or: uv run python -m upsafe
```

The service listens on `127.0.0.1:8000` by default (`UPSAFE_HOST` / `UPSAFE_PORT`).

## API

### `POST /uploads`

Authenticated multipart upload of a single file part.

- Header: `X-API-Key: <your key>`
- Body: `multipart/form-data` with one file field.

```bash
curl -sS -X POST http://127.0.0.1:8000/uploads \
  -H "X-API-Key: $UPSAFE_API_KEY" \
  -F "file=@photo.png"
```

```json
{
  "token": "u1x…urlsafe…",
  "original_name": "photo.png",
  "content_type": "image/png",
  "size": 20481,
  "sha256": "…",
  "expires_at": "2026-07-19T17:40:48+00:00"
}
```

Responses: `201` created · `401` missing/invalid key · `400` empty/malformed/multi-part ·
`413` too large · `415` disallowed extension or content-signature mismatch.

### `GET /downloads/{token}`

Retrieve the original bytes. No API key — the token is the capability.

```bash
curl -sS -OJ http://127.0.0.1:8000/downloads/<token>
```

Responses: `200` with the file (`Content-Disposition: attachment`, `nosniff`) ·
`404` unknown **or** expired token (indistinguishable).

### `GET /healthz`

Unauthenticated liveness check → `200 {"status": "ok"}`.

## Configuration

All configuration is via environment variables — see [`.env.example`](.env.example).
`UPSAFE_API_KEY` is required; the service refuses to start without it.

## Development

```bash
make test          # uv run pytest
make pre-commit    # isort + black + flake8 + pylint + mypy
```

## Limitations (by design, MVP)

- No malware/AV scanning — the allow-list + quarantine isolation is the boundary, not
  content safety. A permitted-type file may still be malicious content.
- No physical purge of expired files — expiry is enforced at read time; a background
  sweeper is a future addition.
- Single static API key (no per-caller identity, revocation, or rate limiting) and a
  single-node SQLite metadata store.
- Tokens are bearer capabilities: run behind TLS in production (terminate at a proxy).

## License

MIT
