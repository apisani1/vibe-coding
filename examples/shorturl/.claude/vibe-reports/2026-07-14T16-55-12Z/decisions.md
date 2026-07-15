# Design decisions

## D1: Flask for the HTTP API
- Decision: Use Flask (WSGI, synchronous) with a `create_app(config)` factory.
- Alternatives considered: **FastAPI** — rejected: pulls in Starlette + pydantic and an
  async model that buys nothing over blocking `sqlite3` for this I/O-trivial workload.
  **stdlib `http.server`** — rejected: hand-rolled routing, JSON, and error handling is
  more code and more defect surface than one small dependency. **Bottle** — comparable
  to Flask but smaller ecosystem/testing story.
- Consequences: One dependency; trivial routing and `app.test_client()` testing; sync
  code matches the DB. Not async — irrelevant at target scale.

## D2: waitress as the production server
- Decision: `shorturl serve` runs the Flask app under waitress (pure-Python WSGI server).
- Alternatives considered: **Flask dev server** — rejected: explicitly not for
  production; undermines "single deployable service." **gunicorn** — rejected:
  Unix-only (no Windows), heavier; the profile targets cross-platform simplicity.
  **uvicorn** — ASGI, mismatched with a WSGI/sync app.
- Consequences: Real, production-safe serving with one extra small dependency and no
  platform lock-in. Multithreaded → drives the per-request-connection decision (D4).

## D3: argparse for the CLI
- Decision: stdlib `argparse` with subcommands `serve`, `list`, `expire`, `delete`, all
  under the single `shorturl` console script.
- Alternatives considered: **click / typer** — rejected: nicer ergonomics but an added
  dependency for four simple subcommands; profile favors minimal surface.
- Consequences: Zero CLI dependencies; one entry point reinforces "single deployable."
  Slightly more boilerplate than click, but small and explicit.

## D4: SQLite with WAL + per-request connection
- Decision: stdlib `sqlite3`, WAL journal mode, `foreign_keys=ON`, a `busy_timeout`, and
  a fresh connection per HTTP request (opened in `before_request`, closed in teardown);
  the CLI opens one connection per command. Data-access functions receive `conn`.
- Alternatives considered: **One shared connection** — rejected: `sqlite3` connections
  aren't safe to share across waitress's worker threads. **An ORM (SQLAlchemy)** —
  rejected: overkill for two tables; profile favors simplicity and functions over
  classes. **A connection pool** — rejected: SQLite opens are cheap; a pool is premature.
- Consequences: Thread-safe; WAL lets readers (stats/list) not block the redirect writer;
  passing `conn` in keeps data-access functions pure and unit-testable with an in-memory
  DB. Cost: a connection open per request (negligible for SQLite).

## D5: Random base62 codes (default length 7), not sequential
- Decision: Generate codes with `secrets.choice` over `[A-Za-z0-9]`, default length 7;
  rely on the PRIMARY KEY uniqueness and retry up to 5× on collision.
- Alternatives considered: **Sequential counter / hashids** — rejected: enumerable codes
  leak creation volume and let anyone walk the namespace; the shortener is publicly
  reachable. **Longer codes** — unnecessary; 62⁷ ≈ 3.5×10¹² is ample and collisions are
  astronomically rare.
- Consequences: Unpredictable, non-enumerable codes; negligible collision handling.
  Length is configurable (`Config.code_length`) if volume ever demands it.

## D6: 302 (temporary) redirects, lazy expiry checked at read time
- Decision: Redirects return `302`; expiry is evaluated on each redirect (no scheduler,
  no background job). A code is expired if `active = 0` or `expires_at <= now`.
- Alternatives considered: **301 permanent** — rejected: aggressively cached by clients,
  which suppresses click analytics and blocks repointing a code. **Background expiry
  sweeper** — rejected: adds a scheduler/process, breaking the single-process model for
  no functional gain.
- Consequences: Every hit is counted and targets stay repointable; the trade-off is that
  expired rows linger until an admin deletes them (acceptable; pruning is out of scope).

## D7: API key via env, checked with constant-time compare, fail-closed
- Decision: `SHORTURL_API_KEY` from the environment; `/api/*` requires header
  `X-API-Key`, compared with `hmac.compare_digest`. `serve` refuses to start if the key
  is unset. Redirect route stays public.
- Alternatives considered: **No auth** — rejected per spec (open shortener invites
  abuse). **Plain `==` compare** — rejected: timing side channel. **Per-user keys /
  OAuth** — deferred (out of scope; single operator).
- Consequences: Simple single-operator protection; never serves an unauthenticated
  create endpoint. Missing key → `401`, wrong key → `403`. Key is never logged.

## D8: Architect review resolutions
- Decision: Folded the vibe-architect review (1 risk, 4 advisories) into design.md.
  Resolutions: (1) **risk** — restored the spec's three-way status
  (active / expired / **deactivated**): a single `codes.status(row, now)` helper backs
  both the redirect gate (410 for expired *or* deactivated) and the CLI/stats display,
  so a manually-expired code is reported distinctly from a TTL-lapsed one (spec AC #10).
  (2) Finalized per-day bucketing for the stats series (`substr(clicked_at,1,10)`,
  `{date,count}`) — the spec explicitly deferred this to design. (3) Moved `code_length`
  from env config to a module constant `codes.CODE_LENGTH` — keeps the config surface to
  the spec's four env vars; length is still trivially changeable in one place. (4)
  Specified `base_url` as optional, defaulting to `http://{host}:{port}` with a
  `SHORTURL_BASE_URL` override for reverse-proxy deployments. (5) Noted `list_codes`
  aggregates the per-code click count via `LEFT JOIN ... GROUP BY` (no N+1).
- Alternatives considered: Keeping `code_length` as env config (architect flagged it as
  YAGNI but acceptable) — rejected in favor of the constant to hold the config surface to
  spec. No disagreements recorded; all findings accepted.
- Consequences: Design now traces cleanly to every acceptance criterion; no open drift.
