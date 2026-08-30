# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the frontend to a static export.
#
# Node exists only here. The runtime image below never sees it, which is the
# whole reason this is a multi-stage build: the two `npm audit` highs this
# project accepts (next's nested postcss, and the optional unused sharp) are
# build-time only *exactly and only* because the toolchain stops at this line.
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /build

# Manifests before source, so editing a component does not re-resolve the
# dependency tree. `npm ci` rather than `npm install`: it installs the lockfile
# as written and fails if the two disagree, which is the property that makes a
# build reproducible.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — the runtime: Python, the backend, and stage 1's export.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv from its own published image rather than a curl|sh installer, and pinned by
# **digest**: the first version of this line said "digest-addressable" while
# referencing the mutable tag `0.5.11`, which is not the property it claimed.
# 0.9.5 also postdates this lockfile's `revision = 3`, where the pinned older uv
# did not.
COPY --from=ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Same ordering rule as stage 1, for the same reason.
COPY backend/pyproject.toml backend/uv.lock ./
# `--frozen`: install the lockfile, never re-resolve. `--no-dev`: pytest, mypy,
# pylint and the rest are not runtime dependencies and have no business in a
# shipped image.
RUN uv sync --frozen --no-dev --no-install-project

# `src` only. The schema travels inside the package (`db/schema.sql`), and
# `backend/db/` on a developer's machine holds a *runtime* database — copying it
# is the exact mistake check GD1 exists to catch.
COPY backend/src ./src
# `README.md` is a build input, not documentation, here: `pyproject.toml`
# declares it as the package readme, and hatchling refuses to build the project
# without it.
COPY backend/README.md ./
RUN uv sync --frozen --no-dev

# The built frontend, and nothing else from stage 1 — no node_modules, no
# .next cache, no toolchain.
COPY --from=frontend /build/out ./src/finally_app/static

# The volume mount point. It must exist and be **empty**: a file baked in here
# would shadow the mount, and the user's portfolio would silently reset on every
# `docker run` (check GD1 asserts the emptiness, not the intent).
RUN mkdir -p /app/db

# Non-root, and owning /app/db — on a fresh named volume Docker copies the
# image's ownership onto the mount, so a root-owned directory here leaves the
# runtime user unable to create the SQLite file at all.
RUN useradd --create-home --uid 10001 finally && chown -R finally:finally /app
USER finally

# No DB_PATH variable: `config.py` deliberately does not read the database
# location from the environment, so the path is `db/finally.db` relative to the
# working directory — which is why `WORKDIR /app` above is what puts the file on
# the volume. Stating it here rather than inventing a variable that nothing reads.
EXPOSE 8000

# GET, never HEAD: this application answers HEAD on a real route with a JSON 404
# rather than a 405, because `/api/{path:path}` is registered for every method
# after the routers (CP10). A HEAD healthcheck would report a healthy container
# as unhealthy forever.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "finally_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
