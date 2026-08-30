# FinAlly backend

FastAPI application: REST API, SSE price stream, SQLite persistence, and the LLM chat
integration. Managed as a `uv` project on Python 3.12.

## Running locally

```bash
cd backend
uv sync
LLM_MOCK=true uv run uvicorn finally_app.main:app --reload --port 8000
```

**Use `LLM_MOCK=true` for local development.** The repo's `.env` carries `LLM_MOCK=false`,
so without the override every message you type into the chat panel is a billed OpenRouter
call. The startup log states which LLM path is active — read it if you are unsure.

## Checks

```bash
uv run pytest          # tests
uv run mypy src        # strict typing (src only; tests are excluded)
uv run flake8 src tests
uv run black --check . && uv run isort --check-only .
uv run pylint src      # 10.00/10 is the standard here, not an aspiration
```

Or `make check` from the repo root, which runs all of the above plus the frontend's.

No test reaches the network. `env -u OPENROUTER_API_KEY LLM_MOCK=true uv run pytest` is
expected to pass, and is what proves it.

## Layout

```
src/finally_app/
├── main.py        # app factory, lifespan, router order
├── config.py      # environment -> frozen Settings
├── api/           # HTTP layer only
├── services/      # business logic; imports no web framework
├── db/            # schema, connections, transactions
├── market/        # price sources, cache, producer task
└── llm/           # structured-output client and mock
```

`services/` never imports FastAPI. That is what lets the REST handlers and the chat
orchestrator share one validation path instead of two.

See the repo root's [README](../README.md) for the quickstart and the configuration table,
and [`planning/`](../planning/) for the design and the decisions behind it.
plan.
