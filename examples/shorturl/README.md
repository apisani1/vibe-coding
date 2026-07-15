# shorturl

A small, self-hostable URL shortener as a single deployable service: a SQLite
persistence layer, an HTTP API (create / redirect / per-code stats), a CLI admin
(list / expire / delete), and click analytics with optional expiry. One package, one
process for the API, one console script, one SQLite file.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

This installs the package (editable) and its dependencies into a project-local `.venv`.

## Configuration

All configuration is via environment variables:

| Variable             | Default                  | Purpose                                              |
| -------------------- | ------------------------ | ---------------------------------------------------- |
| `SHORTURL_DB`        | `shorturl.db`            | Path to the SQLite file (shared by the API and CLI). |
| `SHORTURL_API_KEY`   | *(unset)*                | API key for `/api/*`. **Required to run `serve`.**   |
| `SHORTURL_HOST`      | `127.0.0.1`              | Bind host for the server.                            |
| `SHORTURL_PORT`      | `8000`                   | Bind port for the server.                            |
| `SHORTURL_BASE_URL`  | `http://{host}:{port}`   | Base URL used to build `short_url` (set behind a reverse proxy / custom domain). |

The API key is never logged. `serve` refuses to start without one, so the create/stats
endpoints are never exposed unauthenticated.

## Run the server

```bash
export SHORTURL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
uv run shorturl serve
```

## HTTP API

The redirect endpoint is public; `POST /api/codes` and the stats endpoint require the
`X-API-Key` header.

Create an auto-generated code:

```bash
curl -sX POST http://127.0.0.1:8000/api/codes \
  -H "X-API-Key: $SHORTURL_API_KEY" -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com/some/long/path"}'
# {"code":"Ab3xK7q","short_url":"http://127.0.0.1:8000/Ab3xK7q","target_url":"...","expires_at":null}
```

Create a custom alias with an expiry:

```bash
curl -sX POST http://127.0.0.1:8000/api/codes \
  -H "X-API-Key: $SHORTURL_API_KEY" -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "alias": "launch", "expires_at": "2030-01-01T00:00:00+00:00"}'
```

Follow a short link (records a click):

```bash
curl -sI http://127.0.0.1:8000/launch   # 302 Location: https://example.com
```

Per-code stats:

```bash
curl -s http://127.0.0.1:8000/api/codes/launch/stats -H "X-API-Key: $SHORTURL_API_KEY"
# {"code":"launch","target_url":"...","status":"active","total":3,
#  "series":[{"date":"2026-07-14","count":3}],"top_referers":[{"referer":"...","count":2}]}
```

Status codes: `201` created, `302` redirect, `400` bad input, `401` missing key,
`403` wrong key, `404` unknown code, `409` alias taken, `410` expired/deactivated.

## CLI admin

The CLI operates directly on `SHORTURL_DB`:

```bash
uv run shorturl list                # all codes: status, click count, expiry, target
uv run shorturl expire <code>       # deactivate a code (stops redirecting; keeps history)
uv run shorturl delete <code>       # delete a code and its clicks
```

`expire` / `delete` exit non-zero if the code does not exist.

## Development

```bash
uv run pytest
uv run black --check src tests && uv run isort --check-only src && \
  uv run flake8 src && uv run pylint src/shorturl && uv run mypy src/shorturl
```
