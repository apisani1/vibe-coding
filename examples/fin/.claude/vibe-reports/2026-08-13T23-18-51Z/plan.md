# Plan: FinAlly — AI Trading Workstation

Upstream design: `.claude/vibe-reports/2026-08-13T23-03-27Z/design.md` (+ `decisions.md`,
24 decisions). Upstream spec: `SPEC.md`.

## Risk factors (ArjanCodes step 5 — identified first)

Ordered by *how late they would hurt*, which is what drives the phasing below.

**R1 — `openai/gpt-oss-120b` may not honor strict `json_schema` through OpenRouter.**
The whole chat feature assumes structured outputs land as typed fields (D10). OpenRouter's
structured-output support is uneven per model, and this model is now fixed by `.env`.
Finding out in Phase C would invalidate the chat panel's entire contract.
→ *Mitigation:* CP2 makes one live call against the real model on day one and records what
came back. D10's tolerant parser already covers degradation to fenced or bare JSON; if the
model ignores the schema *shape* too, the fallback is few-shot prompting with the schema
inlined, decided at CP2 rather than discovered at CP14.

**R2 — Blocking `sqlite3` under a threadpool is a correctness risk, not a perf one.**
D21 puts sync service functions on Starlette's threadpool with a connection per call. Get
this wrong (shared connection, missing WAL, `async def` handler) and the symptom is an
intermittently stalled SSE stream or a `database is locked` under concurrent trades —
both of which look like flakes and get "fixed" by a retry.
→ *Mitigation:* CP3 establishes the connection contract and CP6 ships a concurrent-trade
test that would fail loudly if the transaction boundary is wrong. Never a manual check.

**R3 — Next.js `output: 'export'` served under FastAPI's catch-all.** The classic single-
origin failure: asset paths, `trailingSlash`, and the SPA fallback all interact, and
`StaticFiles(html=True)` must not shadow `/api/*`. This is the kind of thing that works in
`npm run dev` and breaks only in the container.
→ *Mitigation:* CP10 proves the mount with a real exported bundle before any component is
written — the point is to fail on a hello-world page, not on a finished UI.

**R4 — Docker multi-stage build (Node 20 → Python 3.12 + uv).** Layer ordering, `uv sync
--frozen` against a committed lockfile, and where stage 1's `out/` lands in stage 2. Time
sink, low intellectual content, and it blocks E2E entirely.
→ *Mitigation:* CP15 is its own checkpoint with a build-and-curl check. The `db/` mount
shadowing rule from the design is an explicit test, not a comment.

**R5 — SSE end-to-end has no cheap partial verification.** Producer, cache, change
detection, heartbeat, and `EventSource` reconnection either work as a chain or not at all.
→ *Mitigation:* CP5 verifies with `curl -N` against raw frames — no browser involved — so
the backend half is proven before the frontend exists. Reconnection is the one part that
needs a browser and lands in E2E (CP16).

**R6 — Massive API path is unverifiable in this environment.** `MASSIVE_API_KEY` is empty,
and the prior build's key returned 403 on `/v2/snapshot`.
→ *Mitigation:* Accept it. `market/massive.py` is written against the documented response
shape and tested with recorded fixtures only. Declared under "Cannot be verified" — nobody
should claim this path works.

**R7 — Live LLM calls cost money and E2E defaults to `LLM_MOCK=false`.** `.env` currently
has `LLM_MOCK=false`, so a careless test run bills real credits.
→ *Mitigation:* `test/docker-compose.test.yml` sets `LLM_MOCK=true` explicitly (CP16), and
CP9's unit tests never touch the network. The only sanctioned live call is CP2's spike.

**R8 — A live API key sits in an unignored, un-gitted project root.** Highest-consequence
item in the plan and the only one with a real-world blast radius.
→ *Mitigation:* CP0, before anything else, and before any `git init`.

## Phases

### Phase A: Prove the unknowns
- Goal: every risky integration (LLM structured output, SQLite-under-async, SSE) is
  demonstrated working, and the repo is safe to commit.
- Checkpoints: 0, 1, 2, 3, 4, 4b, 5
- Boundary: run `verify` before entering Phase B

### Phase B: Business logic
- Goal: every `/api/*` endpoint in the design exists, is transactional, and is covered by
  tests that run without a network or a browser.
- Checkpoints: 6–9
- Boundary: run `verify` before entering Phase C

### Phase C: The workstation
- Goal: the UI the spec describes, running against the real backend in dev.
- Checkpoints: 10–14
- Boundary: run `verify` before entering Phase D

### Phase D: Package & prove
- Goal: one command starts it; E2E proves it from a browser.
- Checkpoints: 15–17
- Boundary: run `verify`, then `review`

Phases B–D are committed in outline; **C and D should be re-cut after Phase A's verify**
if CP2 changes the chat contract or CP5 changes the SSE frame shape.

## Checkpoints

Every `Verify:` line names checks defined in `verification-plan.md` — that file is the
authority on how each one runs. Three checkpoints additionally carry a **demonstration
requirement**: the guarding check must be *seen to fail* against a locally mutated copy
that is never committed (A8 at CP4, B2 at CP6, C3 at CP11). A test that guards a subtle
decision and has never failed is a comment, not a check.

### Checkpoint 0: Repo hygiene and safety
- Does: Creates `.gitignore` **before** `git init`, ignoring **`.env*` with a
  `!.env.example` negation** (not a literal `.env` — the copied file's own comment refers
  to a `.env.bak-massive` holding the original Massive key, and a literal entry would miss
  it), plus `.DS_Store` (already present in this repo root), `db/*.db`, `__pycache__`,
  `node_modules`, `.next`, `out`, `.venv`. Seeds `.editorconfig`,
  `.pre-commit-config.yaml`, `.vscode/settings.json` from the user preference profile
  (add-only); writes `.env.example` with all five variables; creates `db/.gitkeep`,
  `planning/`, `LICENSE` (MIT). Then `git init` and the first commit.
- Touches: `.gitignore`, `.env.example`, `.editorconfig`, `.pre-commit-config.yaml`,
  `.vscode/settings.json`, `db/.gitkeep`, `planning/`, `LICENSE`
- Verify: check **A1** — `git check-ignore -v .env` exits 0; no `.env*` path other than
  `.env.example` appears in any commit's file list; `git log --oneline | wc -l` is 1; and a
  three-needle blob scan: **(a)** the credential *shape* `sk-[A-Za-z0-9_-]{8,}`, which
  catches a rotated key, a second provider credential, or the `.env.bak-massive` old key —
  `{8,}` keeps prose clean because `sk-or-v1` as written in these documents has only 5
  characters after `sk-`; **(b)** the live key value, regex-escaped; **(c)** a positive
  control proving the scan can find a string that *is* committed. A value-only scan is
  insufficient — it goes blind on exactly the rotated-key case that motivates `.env*` over a
  literal `.env`.

### Checkpoint 1: Backend skeleton
- Does: `uv` project at `backend/` (Python 3.12, `src/finally_app/` layout per D15),
  `pyproject.toml` with black/isort/flake8/pylint/mypy at line length 119, FastAPI app
  factory, frozen `Settings` from env, `GET /api/health`, pytest + pytest-asyncio wiring
  with one passing test.
  System python here is 3.10, so `uv` must pin 3.12 explicitly rather than inheriting.
- Touches: `backend/pyproject.toml`, `backend/src/finally_app/{main,config}.py`,
  `backend/src/finally_app/api/system.py`, `backend/tests/`
- Verify: checks **A2**, **A3** — `uv run pytest`, `mypy src`, `flake8`,
  `black/isort --check` all clean; `GET /api/health` → 200

### Checkpoint 2: LLM client and the structured-output spike (R1)
- Does: `llm/schema.py` (Pydantic `AssistantResponse`, JSON Schema generated from it, not
  written twice), `llm/client.py` (one `litellm.acompletion` to OpenRouter, no provider
  routing, tolerant parser: fences → outermost braces → Pydantic), `llm/mock.py`.
  **Then one live call** against `openai/gpt-oss-120b` recording whether strict
  `json_schema` was honored.
- Touches: `backend/src/finally_app/llm/*`, `backend/tests/test_llm_client.py`,
  `backend/tests/test_llm_mock.py`
- Verify: checks **A4**, **A5** — the five-input parser table; the live spike's raw
  response pasted into `build-log.md` with a verdict on whether strict `json_schema` was
  honoured
- Note: the **only** sanctioned live LLM call in the plan (R7). If the schema is not
  honoured, the fallback (few-shot with the schema inlined) is decided here and **Phase C's
  chat contract is re-cut before any component is written**.

### Checkpoint 3: Database layer
- Does: `backend/src/finally_app/db/schema.sql` (6 tables, CHECK constraints, the 2
  indexes — note this is the *package* db/, not the gitignored repo-root `db/` volume mount),
  `db/connection.py`
  (connection-per-call, WAL, row factory, `transaction()` using `BEGIN IMMEDIATE`),
  `db/init.py` (`ensure_initialized()`: idempotent DDL + seed of the default profile and
  10 tickers), wired into lifespan startup.
  `busy_timeout` is set on every connection — B2's concurrency check depends on it.
- Touches: `backend/src/finally_app/db/*`, `main.py`, `backend/tests/test_db_init.py`,
  `backend/src/finally_app/config.py` and `backend/tests/conftest.py` (to drop the
  `_env("DB_PATH")` read — the env surface stays at the spec's five variables; `db_path` is
  injected by tests, which `conftest.py` already does, so the env read bought nothing)
- Verify: checks **A6**, **A7** — init twice → no error, no duplicate seed rows; schema
  inventory matches the design's table/constraint/index list; `PRAGMA journal_mode` is
  `wal`; **no table outside `trades` has a column matching `*price*`** (the D1 tripwire)

### Checkpoint 4: Price cache, simulator, producer (R2 boundary)
- Does: `market/source.py` (`MarketDataSource` Protocol, `Quote` TypedDict with both
  `previous_price` and `session_open`), `market/simulator.py` (GBM with the −σ²/2
  correction, one-factor correlation, per-minute shock rate per D23),
  `market/cache.py` (lock-free dict rebind), `market/producer.py` (background task,
  universe = watchlist ∪ positions re-read each tick via `asyncio.to_thread`),
  `market/seed_prices.py`. Producer started in lifespan after init.
  **Testability requirement:** the GBM step must be a pure function
  `gbm_step(price, mu, sigma, dt, z)` — no internal rounding, RNG injected. At production
  parameters the −σ²/2 term shifts the price by a relative 1.7e-7, which no test can
  resolve and which rounding to 2 decimals erases entirely; only a pure step callable with
  `sigma=1.0, dt=1.0` makes A8 able to fail. **No rounding exists anywhere in the market
  path** — not in the step, not at the cache boundary. Do not add any: rounding at the cache
  would break A8's premise and feed rounded prices into the P&L arithmetic that CP5 serialises
  and CP6 computes against. Money is rounded at write time in the *portfolio* service (D8),
  which is a different boundary.
- Touches: `backend/src/finally_app/market/*`, `main.py`, `backend/tests/test_market_*.py`,
  `backend/tests/test_producer.py`
- Verify: checks **A8**, **A9**, **A10**, **A11** — Jensen-correction drift band;
  shock rate per-minute, counted through `advance()` over 24 simulated hours (band 5..30; the original `0 < shocks < 3` per hour was unreachable at an expectation of 0.6); correlation across five seeds with
  shocks disabled — tech > 0.6, cross < 0.4, separation > 0.3 (bands set from the measured
  distribution; with shocks on, one 2-5% jump dwarfs a window whose typical |log return| is
  ~8e-4 and the tech figure ranges 0.30-0.77). Accepted consequence: A11 no longer covers the
  shipped shock configuration, so two dedicated checks pin shock magnitude against SPEC.md's
  literal 2-5% and against a typical tick; `session_open` stamped once while `previous_price`
  moves every tick
- Demonstration required: delete the `- sigma**2/2` term locally, confirm A8 fails, record
  the observed mean in `build-log.md`, revert without committing.

### Checkpoint 4b: Market source selection and the Massive client
- Does: `market/factory.py` — env-driven selection with **no fallback branch** (D13):
  `MASSIVE_API_KEY` empty → simulator, non-empty → Massive poller. `market/massive.py` —
  REST polling at `MASSIVE_POLL_SECONDS` (default 15, D24), per-ticker guarded parsing into
  the same `Quote` shape, exponential backoff to a 60 s ceiling on 429/5xx, loud auth-failure
  logging. Producer selects its source through the factory.
- Touches: `backend/src/finally_app/market/{factory,massive}.py`,
  `backend/src/finally_app/main.py` (the two-line swap from `Simulator()` to
  `create_source(settings)` — implied by the Does line, listed here so it is authorised),
  `backend/tests/test_market_factory.py`, `backend/tests/test_massive_client.py`,
  `backend/tests/test_producer.py` (the D24 interval assertion),
  `backend/tests/__init__.py` (makes `tests` a package so the guards can import siblings),
  `backend/tests/fixtures/massive_*.json`
- Verify: check **A12** — factory selection both ways with no fallback path; recorded-fixture
  parse produces the same `Quote` keys as the simulator; one malformed entry among good ones
  drops only itself; `mypy src` proves both sources satisfy the Protocol
- Note: spec §5 and §6 make env-driven source selection **required behavior**, so it cannot
  ride along inside CP4. The live HTTP path stays unverifiable here (R6) — this checkpoint
  buys everything that *is* checkable without a working key.

### Checkpoint 5: SSE endpoint (R5)
- Does: `api/stream.py` — `StreamingResponse` of `text/event-stream`; first frame is a
  full cache snapshot, subsequent frames carry only tickers whose producer timestamp
  advanced; `: keepalive` comment every ~15 s; `try/finally` unwind on cancel.
- Touches: `backend/src/finally_app/api/stream.py`, `backend/tests/test_stream.py`,
  `backend/src/finally_app/main.py` (router include), and — **amended before the code was
  written, on two conditions the overseer attached at CP4b** —
  `backend/src/finally_app/market/cache.py`: `apply()` currently restamps `timestamp` on every
  call, so an unchanged price would advance the timestamp and make D4's change-detection emit
  a frame every poll for a price that did not move. Freshness must derive from the quote, so
  an unchanged price must not restamp it. Plus an assertion that `app.state.source` is not
  reassignable once a second router exists.
- Verify: check **A13** — frozen cache emits the snapshot and then *nothing but heartbeats*
  (this is what fails an emit-everything loop); advancing one ticker yields a frame with
  that ticker only; each event body carries all six `Quote` keys including `session_open`;
  cancelling mid-stream returns `asyncio.all_tasks()` to its pre-stream membership; plus a
  raw `curl -N` wire smoke

### Checkpoint 6: Portfolio service and endpoints (R2)
- Does: `services/portfolio.py` — `execute_trade` (price read **once** at the top of the
  transaction, validation, weighted-average-cost on buy, `avg_cost` untouched on sell,
  `quantity <= 1e-9` deletes the row), `get_portfolio` (derived market value / unrealized
  P&L from the cache), snapshot-on-trade. `api/portfolio.py` for `GET /api/portfolio` and
  `POST /api/portfolio/trade`.
- Touches: `backend/src/finally_app/services/portfolio.py`,
  `backend/src/finally_app/api/portfolio.py`, `backend/tests/test_portfolio.py`,
  `backend/tests/test_portfolio_concurrency.py`,
  `backend/src/finally_app/main.py` (one line: `include_router` — a router that is never
  included is not an endpoint, and the Does line specifies two endpoints)
- Verify: checks **B1**, **B2**, **B6** — every row of the design's edge-case table;
  `get_portfolio` totals reconciling `cash + Σ(qty·cached_price)` (the value half of D1);
  and **two threads on a `Barrier`, each with its own connection**, both buying what only
  one can afford → exactly one fill, cash never negative, no `database is locked` escaping,
  over 10 rounds. Sequential calls on one thread pass under `BEGIN DEFERRED` too, so thread
  overlap is the entire point.
- Demonstration required: swap `BEGIN IMMEDIATE` → `BEGIN DEFERRED` locally, confirm B2
  fails and record *how* it failed (double fill vs. lock error) in `build-log.md`, revert.

### Checkpoint 7: Watchlist service and endpoints
- Does: `services/watchlist.py` (normalize `strip().upper()`, ticker format guard
  `^[A-Z.\-]{1,10}$`, idempotent add on UNIQUE violation, remove leaves an open position
  priced), `api/watchlist.py` for GET/POST/DELETE.
- Touches: `backend/src/finally_app/services/watchlist.py`,
  `backend/src/finally_app/api/watchlist.py`, `backend/tests/test_watchlist.py`,
  `backend/src/finally_app/main.py` (one line: `include_router`),
  and — discharging the CP6 condition that the ticker regex admits all-punctuation symbols —
  `backend/src/finally_app/services/tickers.py` (new: the one home of the format rule and of
  `normalise`), plus the three callers that must now share it rather than each carrying a
  copy: `backend/src/finally_app/api/portfolio.py`,
  `backend/src/finally_app/services/portfolio.py`, `backend/tests/test_portfolio.py`.
  *Amended before the code, not after — the CP6 rejection cause.*
- Verify: check **B3** — duplicate add → 200 not 500; lowercase normalized; bad format →
  422; remove a held ticker → position survives **and the producer's universe query still
  contains it** (the D3 corruption path, asserted directly); remove absent → 404

### Checkpoint 8: Snapshot task and history endpoint
- Does: `services/snapshots.py` — 30 s background task recording total value, plus
  `GET /api/portfolio/history`.
- Touches: `backend/src/finally_app/services/snapshots.py`, `api/portfolio.py`,
  `backend/tests/test_snapshots.py`,
  `backend/src/finally_app/main.py` (lifespan starts and cancels the snapshot task — the
  design's startup order is init → producer → snapshotter), and
  `backend/src/finally_app/services/portfolio.py` (expose `record_snapshot` publicly: the
  standalone snapshot must reuse the *ratified* `total_value` definition, unpriced positions
  carried at cost, rather than growing a second one in `snapshots.py`).
  *Amended and committed on its own before the code — the CP7 process finding.*
- Verify: check **B4** — with the interval injected as 0.05 s, two rows within 0.3 s;
  `total_value == cash_balance` exactly when flat; a fill writes exactly one snapshot and a
  rejection writes zero; history ascending by `recorded_at`

### Checkpoint 9: Chat orchestration
- Does: `services/chat.py` — persist user message, load last 10 (D20), build the rendered
  portfolio context block, call the LLM, execute actions **through the CP6/CP7 service
  functions** (D5) capped at 10 (D7), record outcomes as `filled`/`rejected` with reasons,
  persist assistant message + actions JSON. `api/chat.py` for `POST /api/chat` and
  `GET /api/chat/messages` (D18).
  Also adds a startup log line naming which LLM path is active, and makes
  `LLM_MOCK=true uv run uvicorn …` the **documented** local-dev invocation — `.env` carries
  `LLM_MOCK=false`, so a developer poking the chat box during CP9–CP14 would otherwise bill
  real credits (R7 covers the test stack, not manual dev).
- Touches: `backend/src/finally_app/services/chat.py`,
  `backend/src/finally_app/api/chat.py`, `backend/tests/test_chat.py`,
  `backend/src/finally_app/main.py` (one line: `include_router`).
  **Not** `backend/README.md`: the Does line asks for `LLM_MOCK=true` to be the documented
  local-dev invocation, and CP1 already did that (README lines 11 and 14). Verified rather
  than re-done. **Not** `main.py`'s startup log either — the "which LLM path is active" line
  has existed since CP1.
  *Amended and committed on its own before the code.*
- **Touches extended after the CP9 review** (own commit, before the fix): quantity validation
  moves into `backend/src/finally_app/services/portfolio.py`, because the manual boundary's
  `gt=0, allow_inf_nan=False` lives in `TradeRequest` and the chat path never constructs one —
  so a model-authored `-5` filled and *credited* cash. Also
  `backend/src/finally_app/llm/schema.py` (constrain `TradeAction.quantity` as defence in
  depth), `backend/tests/test_portfolio.py` (service-level cases) and
  `backend/src/finally_app/api/portfolio.py` (map the new error to 422, matching the design's
  edge-case table). This is the ticker asymmetry CP7 fixed, recurring for quantity.
  Plus `backend/src/finally_app/llm/client.py` — **docstring only**: its module header claimed
  everything the parser extracts is re-validated by the same service functions a manual action
  crosses, which was false for quantity until this fix. Added on the overseer's CP9 rejection 2,
  which held the line on scope even for a change it had itself requested.
- Verify: checks **B5**, **B7** — monkeypatching `portfolio.execute_trade` to raise a
  sentinel proves the chat path goes through it (D5, structurally); a too-large mocked trade
  returns **200** with `status: "rejected"` and a reason (assert the 200 explicitly — a 4xx
  fails even though it "correctly refused"); an 11th action hits the cap; malformed output
  degrades to message-only with no 500; `GET /api/chat/messages` returns the turn after a
  reload; and the whole suite passes with `env -u OPENROUTER_API_KEY`, proving no test can
  bill.

### Checkpoint 10: Frontend skeleton and the static-export mount (R3)
- Does: Next.js 15 + TS + Tailwind at `frontend/` with `output: 'export'`, the spec's dark
  palette and three accent colors as theme tokens, a placeholder page, `lib/api.ts` +
  `lib/types.ts`, Vitest + RTL wiring with one passing test. FastAPI mounts the export
  **after** the API routers so `/api/*` is never shadowed.
- Touches: `frontend/*`, `backend/src/finally_app/main.py`,
  `backend/tests/test_static_mount.py` (new — C1's assertion, run in-process against a
  fixture export so the mount is covered by `pytest` and not only by a manual curl),
  `backend/tests/conftest.py` (added at the CP10 re-submission: the shared `app` fixture
  inherits the real `STATIC_DIR`, so on any checkout that has run `npm run build` plus the
  C1 copy, every "no export mounted" test silently tested the *mounted* arrangement. The
  fixture now pins `STATIC_DIR` to a path that does not exist, making the suite independent
  of whether the frontend has been built),
  `backend/tests/test_health.py` (docstring only, added at the CP10 approval: that pin means
  CP1's `test_unknown_api_path_is_a_json_404` can no longer see a mounted export, so its
  claim that the assertion "cannot regress once the export is mounted" is now false. The
  guarantee moved to `test_static_mount.py`, where it holds deterministically; the docstring
  has to say so),
  `.gitignore` (two entries: `backend/src/finally_app/static/`, which is where the
  Dockerfile and C1 both copy `frontend/out/` — a build artifact, never committed; and the
  runtime-database rule made path-independent, because `db/*.db` is anchored to the repo
  root while the README's documented run command writes `backend/db/finally.db`. Found by
  booting the app for C1).
  **Not** `backend/README.md`: nothing about the backend's own run instructions changes;
  how to build and serve the export is Phase D's documentation checkpoint (CP17, GD4).
- Verify: checks **C1**, **C2** — `npm run build` produces `out/`; with the export in place
  `/` serves the shell, `/api/health` is 200, **and an unknown `/api/…` path returns a JSON
  404, not the HTML shell**. That last assertion is the whole check: `StaticFiles(html=True)`
  mounted before the routers answers unknown `/api/*` with a 200 shell, and every frontend
  fetch then parses HTML as JSON. Asserting `/api/health == 200` alone does not catch it.

### Checkpoint 11: Live price surface
- Does: `usePriceStream` (one `EventSource`, app-wide context, two-tier ring buffer per
  D22, connection status from `readyState`), `Watchlist`, `Sparkline`, `Header`. CSS-only
  flash; change % from `session_open`.
- Touches: `frontend/src/hooks/usePriceStream.tsx` (**`.tsx`**, not `.ts` as planned: the
  hook ships the context *provider* that owns the single `EventSource`, so the file contains
  JSX), `frontend/src/components/{Watchlist,Sparkline,Header}.tsx`, plus:
  - the colocated tests these checks name — `usePriceStream.test.tsx`,
    `components/{Watchlist,Sparkline,Header}.test.tsx`, `lib/format.test.ts`;
  - `frontend/src/test/priceStream.tsx` (new, not a test file — the fake `EventSource` and
    a render helper. Three test files need to drive the same stream, and three hand-rolled
    copies of a fake would drift; C3 and C4 assert against the *same* fake the hook sees);
  - `frontend/src/lib/format.ts` (new — money and signed-percent formatting; the design's
    frontend tree lists it and C3 asserts an exact rendered string, so the formatter is part
    of what C3 measures rather than an incidental helper);
  - `frontend/src/app/page.tsx` and `page.test.tsx` — the placeholder regions CP10 left are
    replaced by the real Watchlist and Header, and the page becomes a client component
    wrapping the tree in the provider. A checkpoint that built the components without
    mounting them would leave C1's shell rendering placeholders;
  - `frontend/src/app/globals.css` — the two flash classes. CSS-only per the design, so the
    animation lives here rather than in a component;
  - `frontend/vitest.setup.ts` — `EventSource` joins `fetch` in the network block, which is
    the CP10 approval's carried condition. jsdom has no `EventSource`, so without this a
    test that forgets to stub it fails with a bare `ReferenceError` by accident rather than
    by guard.
  **Not** `frontend/tailwind.config.ts`: the `up`/`down` colour tokens the flash needs
  already landed at CP10. Verified rather than assumed.
- Verify: checks **C3**, **C4** — the discriminating fixture `{session_open: 100,
  previous_price: 199.99, price: 200}` must render `+100.00%`; a `previous_price`
  implementation renders `+0.01%` and fails, while a fixture where the two baselines are
  equal would pass under both and prove nothing. Flash asserts **both** the add and the
  removal (asserting only the add lets a permanently-green row pass). Sparkline with 0 and
  1 points renders a flat baseline. A stream that never opened must **not** render
  `connected`.
- Demonstration required: swap the component to `previous_price`, confirm C3 fails, revert.

### Checkpoint 12: Trading surface
- Does: `TradeBar` (ticker + quantity, buy/sell, no confirmation), `PositionsTable`,
  `usePortfolio` (fetch + refetch-after-mutation), watchlist add/remove UI.
- Touches: `frontend/src/components/{TradeBar,PositionsTable}.tsx`,
  `frontend/src/hooks/{usePortfolio,useWatchlist}.ts`, plus:
  - the colocated tests — `components/{TradeBar,PositionsTable}.test.tsx`,
    `hooks/{usePortfolio,useWatchlist}.test.tsx`;
  - `frontend/src/test/api.tsx` (new, not a test file — a `fetch` stub that records calls.
    Four test files need one, and C5's central assertion is a **call count**: "exactly one
    refetch" is only measurable against a shared, honest recorder);
  - `frontend/src/test/priceStream.tsx` (a `mountWithStream` helper: components that fetch on
    mount need their promises flushed inside `act`, or the assertion after the render is a
    race against a microtask. Declared late — it was edited in the first CP12 submission
    without being named, which the overseer called out);
  - `frontend/src/hooks/usePriceStream.tsx` — a `forget(ticker)` action. This is the CP11
    approval's carried condition: the client `quotes`/`history` maps never drop anything, so
    without it a removed symbol keeps rendering its last price until reload. The stream going
    quiet is **not** enough, because `PriceCache` never evicts either;
  - `frontend/src/components/Watchlist.tsx` and `Watchlist.test.tsx` — the add/remove UI in
    the Does line lives in this panel, and **membership comes from `GET /api/watchlist`
    alone**. A ticker added manually still appears before its first quote, because the
    entry's own `quote` field seeds the row's price; what does *not* contribute is the set of
    tickers the stream happens to be quoting. This bullet first said membership was that list
    "unioned with the stream's quotes", and the union was rejected at review: the producer
    prices watchlist ∪ open positions (D3), so a held symbol streams forever after being
    unwatched, and `PriceCache` never evicts while the SSE endpoint opens every connection
    with a full snapshot — so a removed row came back on the next frame and could not be
    removed again. A quote is not a membership claim;
  - `frontend/src/app/page.tsx` and `page.test.tsx` — mounting the two new components and
    feeding `Header` the fetched portfolio, which CP11 left as a prop with no supplier.
  **Not** `frontend/src/lib/api.ts`: every endpoint this checkpoint calls was already
  wrapped at CP10. Verified rather than assumed.
- Verify: check **C5** — a successful trade triggers exactly one portfolio refetch; a 400
  renders the server's `detail` and the inputs keep their values; the positions table shows
  six columns and `—` (not `$0.00`, not `NaN`) when a current price is missing

### Checkpoint 13: Visualizations
- Does: `MainChart` (selected ticker, long buffer), `PnlChart` (from
  `/api/portfolio/history`), `Heatmap` (Recharts `Treemap`, size = weight, fill = P&L
  ramp). Clicking a watchlist row selects the ticker — **the selector itself landed at
  CP11**, because D22's deep buffer is CP11's deliverable and is unreachable dead code
  without one, and CP13's Touches do not include `Watchlist.tsx`. What remains here is
  C6's substance: the selection changing which series the main chart draws.
- Touches: `frontend/src/components/{MainChart,PnlChart,Heatmap}.tsx`, plus:
  - the colocated tests — `components/{MainChart,PnlChart,Heatmap}.test.tsx`;
  - `frontend/package.json` + `package-lock.json` — **`recharts`**, the first dependency
    added since CP10. It is the design's own choice (dependency table: one charting API for
    all three visualizations, chosen over Lightweight Charts) and is named in this
    checkpoint's Does line, and the run's blanket install approval covers `npm install`
    inside `fin/`. Flagged rather than assumed, since the CP10 acknowledgement of the
    manifest is still outstanding;
  - `frontend/src/app/page.tsx` and `page.test.tsx` — mounting the three charts in the
    panels CP10 left as placeholders, and giving `PnlChart` the account it refetches against;
  - `frontend/src/components/{PositionsTable,Header}.test.tsx` — **fixtures only**, added at
    the third review. Both are CP12's and CP11's files; the overseer found their `account()`
    / `PORTFOLIO` helpers encoding states the backend cannot emit (`total_value: 0` beside a
    $1,100 position; `positions: []` beside a `positions_value` of 1,900), which is the exact
    class of defect that made this checkpoint's own P&L test pass falsely. Carried forward
    here rather than left for a later checkpoint because a fixture that cannot occur is a
    check that cannot fail, and both are one edit from being load-bearing. No production code
    in either file's subject is touched;
  - ~~`frontend/src/hooks/usePortfolio.ts`~~ — **withdrawn**, as this line said it would be
    if unneeded. The P&L chart takes the account as a prop and refetches when that **object**
    is replaced — `usePortfolio` produces a new one only when it has re-read the account — so
    no second fetcher exists and `usePortfolio` was not touched. It is deliberately *not*
    keyed on `total_value`: a fill at the mark leaves the total identical, so that trigger
    was dead code (measured, and rejected at review). Check C5's count is now measured
    against `/api/portfolio` exactly rather than by substring, because the history endpoint
    shares that prefix.
- Verify: checks **C6**, **C8** — empty portfolio renders explicit empty states, not a
  crash; heatmap fill is green above `avg_cost` and red below (assert the fill prop passed
  to the cell renderer, not a rendered pixel); clicking a ticker changes the main chart's
  series identity; the four spec palette hexes exist as theme tokens

### Checkpoint 14: Chat panel
- Does: `ChatPanel` — collapsible sidebar, scrolling history loaded from
  `GET /api/chat/messages`, input, loading indicator, inline rendering of both `filled`
  and `rejected` actions.
- Touches: `frontend/src/components/ChatPanel.tsx`, plus:
  - `frontend/src/components/ChatPanel.test.tsx` and `frontend/src/hooks/useChat.ts` with
    its test — the transcript, the in-flight state and the send are one piece of state, and
    a component that owns its own fetching is the thing C7's "present while in flight" claim
    cannot be asserted against without a gate. Same split as `usePortfolio`/`Header`;
  - `frontend/src/app/page.tsx` and `page.test.tsx` — the Assistant panel is still CP10's
    placeholder, and CP13 was rejected in part for exactly this: a component mounted
    nowhere, provable by nothing;
  - ~~`frontend/src/lib/types.ts`~~ — **withdrawn**, as this line said it would be if
    unneeded: `ChatAction` and `StoredMessage` already match `services/chat.py` field for
    field, including the over-cap rejection that carries only `type`/`ticker`/`status`/
    `reason`. Checked against the source, not assumed;
  - `frontend/src/hooks/useWatchlist.ts` and `useWatchlist.test.tsx` — **added at the first
    review**. CP11's files, and CP12's invariant: a removed ticker must be `forget`-ten from
    the price stream, because the client maps only grow and `PriceCache` never evicts. That
    guard sat inside `remove`, which guards **one caller** — and this checkpoint adds a
    second, since the assistant removes symbols through the same service functions a person
    does (D5) and reaches the hook only through `refresh`. Moving the guard onto the resource
    (diff the returned membership, forget what left) is a cross-checkpoint change to a hook
    the watchlist, the charts and the header all sit behind, so it is declared here rather
    than slipped in;
  - `frontend/src/components/Watchlist.tsx` and `Watchlist.test.tsx` — a `refreshKey` prop.
    The assistant executes through the *same* service functions a human uses (D5), so a
    chat turn can add or remove a watchlist symbol and buy or sell. The account is refetched
    through the page's existing `refresh`, but watchlist membership lives inside
    `useWatchlist`, and without a trigger a chat-added ticker would render in the transcript
    as `Applied NVDA` while the list beside it did not contain NVDA — the panel asserting
    something the rest of the UI denies, which is the D6 failure in a different coat.
  **Not** `frontend/src/lib/api.ts`: `getChatMessages` and `sendChatMessage` were both
  wrapped at CP10. Verified, not assumed.
- Verify: check **C7** — loading indicator present while in flight and gone after resolve;
  a `filled` action renders as a confirmation **and** a `rejected` one renders its `reason`
  (a panel that renders only `filled` silently reproduces the "assistant claims it bought
  something" failure D6 exists to prevent); mounting fires `GET /api/chat/messages`

### Checkpoint 15: Container and scripts (R4)
- Does: Multi-stage `Dockerfile` (node:20-slim build → python:3.12-slim runtime, `uv sync
  --frozen`, manifests copied before source, `db/` never baked in), `docker-compose.yml`,
  and the four idempotent start/stop scripts.
- Touches: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/*`, and:
  - `backend/README.md` — **only if** the documented local-dev run command changes. It does
    not today; withdrawn rather than left standing if so.
  Conditions this checkpoint inherits and must satisfy, each recorded during Phase C:
  - the `HEALTHCHECK` must use **`GET /api/health`**, never `HEAD` — CP10's `/api` catch-all
    answers `HEAD` on a real route with a JSON 404 rather than a 405;
  - the runtime stage copies **only** `frontend/out/`, which is the condition the two accepted
    `npm audit` highs (next's nested postcss, the optional unused sharp) rest on: build-time
    only exactly and only if the toolchain never reaches the runtime image;
  - `npm ci` must still resolve inside the build — the recharts install re-resolved the
    lockfile and dropped its `lightningcss` entries;
  - `uv sync --frozen --no-dev`, `WORKDIR /app`, and `/app/db` **owned by the non-root user**,
    or the container cannot create the SQLite file on a fresh volume.
- Verify: checks **GD1**, **GD2** — build succeeds; `/app/db` inside the image is **empty**
  (an image-baked file there shadows the volume and resets the portfolio on every run); a
  position survives stop + rm + re-run on the named volume; `start_mac.sh` twice leaves one
  container; `stop_mac.sh` leaves the volume intact — the last is the most destructive thing
  that could ship in this repo

### Checkpoint 16: E2E suite (R7)
- Does: `test/docker-compose.test.yml` (app container with `LLM_MOCK=true` and a fresh
  anonymous volume + Playwright container on the same network), `playwright.config.ts`,
  and the spec §12 scenarios.
  Also captures full-page screenshots at 1920×1080 and 1024×768 into `test/screenshots/`.
- Touches: `test/*` — specifically `test/docker-compose.test.yml`, `test/playwright.config.ts`,
  `test/specs/*.spec.ts`, `test/package.json` + `package-lock.json`, and `test/.gitignore`.
  - **A third dependency manifest.** `@playwright/test` is named in this checkpoint's Does
    line and in the design's dependency table, and the run's blanket install approval covers
    `npm install` inside `fin/` — but the human's acknowledgement at CP13 was about the
    *frontend* manifest, so this one is flagged rather than assumed covered. Pinned to the
    exact version of the Playwright image tag, because a mismatch between the two is a
    documented way to get browsers that do not match the runner.
  Conditions this checkpoint inherits:
  - the app service must **not** be named `app`: `.app` is HSTS-preloaded, Chrome force-
    upgrades `http://app:8000` to HTTPS, and the suite dies with `ERR_SSL_PROTOCOL_ERROR`;
  - `tmpfs` needs explicit `uid`/`gid` — the runtime user is 10001 and cannot otherwise
    create the SQLite file;
  - the test stack gets its **own compose project and no named volume**, so a routine
    `docker compose down -v` cannot reach `finally-data`;
  - `LLM_MOCK=true` and **no `env_file`**: R7's whole point is that a careless run cannot
    bill real credits, and the real `.env` must never reach the test stack;
  - `workers: 1` — the specs mutate one SQLite database, so parallelism is a correctness
    bug rather than a tuning knob.
- Verify: check **GD3** — the suite passes from a cold compose, covering fresh start (10
  tickers, $10k, prices streaming), add/remove ticker, buy, sell, heatmap + P&L render, and
  mocked chat producing both a `filled` and a `rejected` chip. Guards asserted on the compose
  file itself: `LLM_MOCK: 'true'` present, **no `env_file`** (the real `.env` must never
  reach the test stack), `tmpfs` for a fresh DB per run.
- Scope correction: the resilience spec covers **refused-then-allowed** reconnection only —
  the indicator must reach `connected` *and prices must resume changing*. Severing an
  already-established SSE stream is not stageable from Playwright (`setOffline` leaves it
  running, `route.abort` affects only new requests) and moves to "Cannot be verified", with
  the reason recorded in `test/README.md`.
- Three environment traps to encode as comments: the app service must **not** be named `app`
  (`.app` is HSTS-preloaded and Chrome force-upgrades to HTTPS), `tmpfs` needs explicit
  `uid`/`gid` for the non-root runtime user, and the Playwright image tag must match the
  pinned `@playwright/test` version. Specs run `workers: 1` — they share one SQLite file, so
  parallelism is a correctness bug, not a tuning knob.

### Checkpoint 17: Documentation and `make check`
- Does: root `README.md` (quickstart, the five env vars, the `docker volume rm` reset
  note), `backend/README.md` and `frontend/README.md` (running each half outside Docker,
  with `LLM_MOCK=true` as the documented dev invocation), `CLAUDE.md`, and copying the
  spec/design/plan into `planning/` as the agent contract. Plus a root **`Makefile` with
  `make check`** — backend pytest + mypy + flake8 + black/isort --check, frontend vitest +
  tsc + eslint — because there is no CI in this repo and nothing otherwise re-runs Phase A
  and B gates while Phase C and D are being built. `make check` is also the profile's
  documented pre-commit step.
- Touches: `README.md`, `backend/README.md`, `frontend/README.md`, `CLAUDE.md`, `planning/`,
  `Makefile`. Two notes on what "copying into `planning/`" means here:
  - the spec, design, decisions and plan are **copied, not moved** — `.claude/vibe-reports/`
    stays the run of record (CP0's human ruling), and `planning/` is the contract an agent
    reads without knowing this pipeline exists;
  - `make check` runs the gates that already exist, and must not invent new ones. It is the
    profile's documented pre-commit step, so a target that took minutes or needed Docker
    would simply stop being run — the E2E suite is a separate `make e2e`.
- Verify: checks **GD4**, **GD5** — every variable in `.env.example` appears in the README
  table (D9 and D24 both added variables beyond spec §5, so this is live drift risk);
  `make check` is green from a clean tree; A1 re-run now that the repo has many commits

### Checkpoint 18: Remediation (added after `review`, on the human's decision)

Not in the original plan. `review` returned **2 blockers and 5 risks**, and the run's grant
stops at a plan deviation, so this checkpoint exists because Antonio said to add it rather
than because the autopilot decided to.

- Does: fixes both blockers, both correctness risks and both network risks, each with a check
  that fails without the fix:
  1. **`handle_message` runs sqlite on the event loop** — `asyncio.to_thread` at the async
     boundary, keeping `services/` sync and framework-free (D21, B6). Measured: 0 loop beats
     during a stalled chat turn vs 162 through the `def` trade handler.
  2. **`buy 0 AAPL` under `LLM_MOCK=true` is a 500** — clamp in the mock *and* wrap the mock
     branch in the `try` the live path already has, because either alone leaves the other
     path unguarded.
  3. **`get_portfolio` is not atomic** — cash and positions in one read transaction, as
     `record_snapshot` already does.
  4. **`execute_trade` never validates `side`** — the last field whose only guard is a
     Pydantic model the assistant does not construct.
  5. **No Host validation** — `TrustedHostMiddleware`, so DNS rebinding cannot make an
     attacker's page same-origin with a no-auth app.
  6. **The published port binds `0.0.0.0`** — loopback in both start scripts and the compose
     file.
  7. **The Massive key can reach the logs** through an interpolated `httpx` exception.
- Touches: `backend/src/finally_app/services/{chat,portfolio}.py`,
  `backend/src/finally_app/llm/mock.py`, `backend/src/finally_app/db/connection.py`,
  `backend/src/finally_app/{main,config}.py`, `backend/src/finally_app/market/massive.py`,
  `backend/tests/{test_chat,test_portfolio,test_llm_mock,test_health,conftest}.py`,
  `backend/tests/test_event_loop.py` (new), `scripts/start_mac.sh`,
  `scripts/start_windows.ps1`, `docker-compose.yml`, `test/docker-compose.test.yml`,
  `.env.example`, `README.md`
- Verify: the full Gate D sweep re-run (**GD1–GD5**), plus a new **GD6** — a chat turn must
  not stop the event loop, counted in beats rather than asserted in prose.

### Checkpoint 19: The 13 advisories (added after `review`, on the human's decision)

Also not in the original plan. `review` recorded **13 advisories** alongside the blockers CP18
fixed, and they were deliberately left unfixed because an advisory is "an opportunity, not a
problem". Antonio then asked for all of them. This is the last checkpoint the run's
`max_checkpoints: 19` allows.

An advisory is not a defect, so the bar is different from CP18's: each fix must still be
falsifiable, but several of these are removals, and a removal is proved by the thing that
stops existing. Where a finding offers "fix it **or** state why", the choice is recorded
rather than silently taken.

- Does, in the order the findings are numbered:
  1. **No rate limit on `/api/chat`** (#8) — an in-process token bucket, per app rather than
     per module so tests cannot bleed into one another, with an injected clock so the check
     does not sleep. A 429 names the wait. Each request is one billed completion, and the
     bucket is the only thing standing between a loop and the meter.
  2. **`/docs`, `/redoc` and `/openapi.json` ship** (#9) — `openapi_url=None` removes all
     three. `/docs` loaded Swagger UI from a CDN on a floating tag with no SRI, into an origin
     that requires no authentication. The discovery they provided is replaced by #17's table.
  3. **`MASSIVE_POLL_SECONDS` is validated only as a float** (#10) — clamped in
     `MassiveClient.__init__`, **not** in `config.py` where the finding points. The consumer
     is the guard: that is the same lesson as `quantity: -5`, and a rule in the loader is
     invisible to every caller that constructs the client directly. Non-finite falls back;
     anything under 2.0 is raised to it, loudly.
  4. **A provider's exception text reaches the chat panel** (#11) — a fixed sentence in the
     503, with the exception kept in the existing `logger.exception`. The string's shape is
     not under this repo's control.
  5. **`spike.py` ships in the runtime image** (#12) — moved to `backend/scripts/spike.py`,
     which the `Dockerfile`'s `COPY backend/src` leaves behind, and which `pyproject.toml`
     already excludes from mypy and pylint. Check **A5**'s command changes with it.
  6. **`ensure_initialized` reads as atomic and is not** (#14) — `executescript` issues an
     implicit COMMIT, so the `BEGIN IMMEDIATE` was gone before the DDL ran and `_seed`
     executed in autocommit. Split: DDL on a plain connection, seed in its own transaction.
  7. **A dust buy writes a trade with no counterpart** (#15) — rejected in `_settle`, before
     anything is written. `_valid_quantity` passes `1e-12` (it is finite and positive) and
     `_write_position` then deletes the row, leaving a fill in the immutable log against no
     position and no cash movement.
  8. **A 503 orphans the user's turn** (#16) — an assistant row carrying the reason is
     recorded before the error propagates, so the transcript cannot accumulate unanswered
     bubbles that are then fed into every later prompt. The status code does not change: 503
     is still correct, and the panel still shows the banner.
  9. **`read_universe` hard-codes `'default'`** (#18) — import `DEFAULT_USER_ID`.
  10. **A fresh `httpx.AsyncClient` per poll** (#19) — new pool and new TLS handshake every
      15 seconds. Created once, closed from the lifespan through an optional `aclose`, since
      the simulator has nothing to close.
  11. **Three pieces of dead frontend API surface** (#13) — `useChat.reload` leaves the
      returned contract (the mount effect still calls it), `usePortfolio.loading` and
      `getHistory`'s `limit` go entirely, with the two tests that were the only thing keeping
      `loading` alive.
  12. **No endpoint table** (#17) — D18's stated consequence, still missing outside
      `planning/`. Added to `README.md`, marking the route D18 added.
  13. **litellm's ~60 transitive packages** (#20) — **kept**, and the judgement recorded as
      D26 rather than acted on. This is the one finding the reviewer marked `Optional:`, and
      the swap would put the only billable path in the application into production having
      never run: the single live call is spent, and `build-log.md` recorded the response
      *content*, not the HTTP envelope, so there is nothing to test a replacement against.
      Antonio chose this over the swap when asked.
- Touches: `backend/src/finally_app/api/{chat,ratelimit}.py` (`ratelimit.py` new),
  `backend/src/finally_app/{main,config}.py`,
  `backend/src/finally_app/market/{massive,producer,factory,simulator,source}.py`,
  `backend/src/finally_app/llm/client.py`, `backend/src/finally_app/db/init.py`,
  `backend/src/finally_app/services/{chat,portfolio}.py`,
  `backend/src/finally_app/llm/spike.py` → `backend/scripts/spike.py`,
  `backend/tests/{test_chat,test_portfolio,test_db_init,test_massive_client,test_health,test_producer}.py`,
  `backend/tests/test_ratelimit.py` (new), `frontend/src/hooks/{useChat,usePortfolio}.ts`,
  `frontend/src/hooks/usePortfolio.test.tsx`, `frontend/src/lib/api.ts`, `README.md`,
  `.env.example`, `planning/{PLAN,DECISIONS,DESIGN,VERIFICATION-PLAN,README}.md`
- Verify: `make check` green, plus one check per fix that fails when the fix is reverted —
  **A5**'s command re-pointed, a new **A14** (the rate limiter refuses the eleventh call and
  forgives it after the refill), a new **B8** (a mid-seed failure leaves no profile row
  behind), a new **B9** (a dust buy writes nothing at all), a new **B10** (a 503 leaves
  the transcript answered), and a new **GD7** (the interactive docs are gone and the endpoint
  table replaced them). The three findings whose fix is a *deletion* are verified by `tsc` and
  the suite: nothing may still reference what was removed.
- **`make e2e` is NOT in this checkpoint's verify line**, and that is deliberate rather than
  convenient: the Docker daemon is down on this machine and starting Docker Desktop is outside
  `fin/` and outside the run's grant. It is carried as an open condition instead — Gate D is
  not re-green until someone runs it.

**Touches amended after the overseer rejected the first presentation.** Three files the diff
modified were missing: `market/simulator.py` and `market/source.py` (the `aclose` no-op and
the Protocol member — substance covered by Does-line #10, but the list is the list) and
`.env.example` (a comment documenting the clamp, covered by no Does line at all). Two further
errors in the same list: it named `test_massive.py`, which does not exist — the file is
`test_massive_client.py` — and it named `test_llm_client.py`, which this checkpoint never
touched. Declaring the list *before* the diff is worth nothing if the list is wrong, and this
is the fourth time in this run that a Touches list has been corrected after the fact rather
than before.

**The second `A9` was a collision.** `A9` was already *shock rate is per minute* (D23), and
the coupling table still routes any change to `market/simulator.py` — which this checkpoint
made — to "A8, A9, A11 as a set". Anyone following that row would have run the rate-limiter
tests against a simulator change. The new check is **A14**.

### Checkpoint 20: `make e2e` must build what it tests (added on the human's decision)

Beyond `max_checkpoints: 19`, which is spent, so this exists because Antonio said "solve #1"
after the verify run recorded it — not because the autopilot decided to keep going.

- Does: adds `--build` to the `e2e` recipe. `docker compose up` builds only when the image is
  **missing**, so once `finally:e2e` exists the suite drives whatever was built last and
  reports green on it. That is not hypothetical: it happened on 2026-08-20 and produced a
  passing 21-spec run against an image built four days earlier, containing neither CP18 nor
  CP19. It was caught by one absent startup log line, not by anything in the harness.
- Touches: `Makefile`, `.claude/vibe-reports/2026-08-13T23-18-51Z/{plan,checklist,build-log,verification-plan}.md`,
  `planning/{PLAN,VERIFICATION-PLAN}.md`
- Verify: a new **GD8** — the `make e2e` transcript must contain the image build step, and the
  suite must still pass. The mutation is already on record and does not need re-manufacturing:
  removing `--build` is precisely what produced the 2026-08-20 run, whose transcript has no
  `Building` line, whose container never logged `allowed hosts:`, and whose image answered
  `0` to `grep -c TrustedHostMiddleware`. A check whose failure has been observed in
  production conditions does not need a synthetic one.
- **Not** changed, and deliberately: `scripts/start_mac.sh` keeps building only when the image
  is missing or `--build` is passed. That is a different trade — a start script that rebuilt
  every time would turn a five-second launch into a two-minute one, the behaviour is stated in
  the script's own comment, and `--build` is right there. It does carry the same trap after a
  `git pull`, which is how Antonio ended up running a pre-CP18 image tonight, so it is recorded
  as an advisory rather than silently widened into this checkpoint.

### Checkpoint 21: the stale-image trap in the README (added on the human's decision)

Also beyond `max_checkpoints: 19`. Antonio said "Fix it" to the advisory the overseer left
open at CP20 and I declined to fold in there.

- Does:
  1. **`README.md`'s Quickstart shows `./scripts/start_mac.sh` bare** and says the script
     "builds the image the first time" — accurate, and it never draws the consequence. After a
     `git pull` that command silently starts the *previous* build. Same shape as CP20's defect
     with a worse failure mode: this one **serves** stale code rather than merely testing it,
     and it is how a pre-CP18 image — no `TrustedHostMiddleware`, none of CP19 — came to be
     running on Antonio's machine on 2026-08-20.
  2. **`README.md:45` says "All five are optional".** There are **six**. CP18 added
     `ALLOWED_HOSTS` and no prose was updated. GD4 passes — it diffs variable *names* and
     `ALLOWED_HOSTS` is in the configuration table — so the check was right and the sentence
     beside it was wrong, which is the more embarrassing arrangement.
  3. The same stale "five" in `backend/src/finally_app/config.py`'s comment and in GD4's own
     claim text. Declared here rather than fixed quietly in passing.
- Touches: `README.md`, `backend/src/finally_app/config.py` (one comment),
  `.claude/vibe-reports/2026-08-13T23-18-51Z/{plan,checklist,build-log,verification-plan}.md`,
  `planning/{PLAN,VERIFICATION-PLAN}.md`
- Verify: **GD4** re-run, plus a new **GD9** that makes the count claim falsifiable — the
  number-word in the README's prose must match the count of variables in `.env.example`, and
  the rebuild trap must be documented. Adding a seventh variable, or removing the `--build`
  note, must fail it.
- **Stated plainly, because it is the weaker fix:** documentation is not a guard. Anyone who
  does not read the README hits this exactly as before. The strong version is a staleness
  warning in `start_mac.sh` — compare the image's creation time against the newest source
  mtime and say so — and that is a change to the script that starts Antonio's live container,
  so it is offered rather than taken. This checkpoint buys discoverability, not prevention,
  and the plan should not pretend otherwise.

### Checkpoint 22: close the stale-image trap instead of describing it (human's decision)

CP21 documented the trap. This one removes it. Antonio chose the recreating variant over the
warn-only one the overseer proposed, when both were put to him.

- Does: in **both** start scripts, the early-exit branch stops lying. Today it fires *after*
  the build, so `--build` against a running container rebuilds the image, prints
  `FinAlly is already running`, exits 0, and keeps serving the old container — a success
  message over a no-op. It becomes:
  1. Compare the **running container's image ID** against the image the script would run.
     Identity, not timestamps: `docker inspect` gives both, and an ID comparison cannot be
     fooled by a rebuild that produced identical layers (a cache hit legitimately yields the
     same ID, and in that case there is genuinely nothing to do).
  2. **Same ID** → "already running, and it is the current image", exit 0. Idempotence
     preserved; this is the common case and it must not restart anything.
  3. **Different ID** → say so, naming both IDs, then stop and recreate. The user asked for
     the new build by passing the flag; serving the old one is the defect. The named volume is
     not touched, so the portfolio survives — which is the only reason recreating is safe
     enough to do without asking every time.
  4. **No `--build`** → unchanged. A bare invocation of a start script must stay a five-second
     no-op when the app is up.
  5. **`start_windows.ps1` does not mirror `start_mac.sh`, despite its own header saying it
     does.** Its running-check is `docker ps --quiet --filter "name=^/$Container$"` with **no
     `status=running`** — the filter the mac script's comment calls load-bearing, because
     `docker ps -q` also lists a container in `restarting`, and `docker-compose.yml` ships
     `restart: unless-stopped`. So on Windows a crash-looping container reports as "already
     running" while serving nothing. Found while rewriting the branch above it; declared here
     before the diff rather than folded in, since no Does line covered it.
- Touches: `scripts/start_mac.sh`, `scripts/start_windows.ps1`, `README.md`,
  `.claude/vibe-reports/2026-08-13T23-18-51Z/{plan,checklist,build-log,verification-plan}.md`,
  `planning/{PLAN,VERIFICATION-PLAN}.md`
- Verify: a new **GD10**, run against a **stubbed `docker` on `PATH`** — the technique the
  overseer used at CP18 for the publish flags, and the only way to exercise these branches
  without a real container. Four cases, each asserted on the script's output and exit status:
  running + `--build` + different image → recreates; running + `--build` + same image → does
  not; running, no `--build` → unchanged early exit; not running → unchanged start path.
  *Mutation:* restore the old unconditional early exit and case 1 must fail.
- **This is prevention, where CP21 was discoverability.** The README paragraph stays, demoted
  from the whole defence to a backstop for anyone who reads it before running anything.

## Definition of Done

**Required** (the MVP cut from `SPEC.md`):
- All six endpoints live: portfolio (GET/trade/history), watchlist (GET/POST/DELETE),
  chat (POST + messages), health, SSE stream.
- Simulator is the default source and streams over SSE at ~500 ms; source selection is
  env-driven with no silent fallback, and the Massive client parses recorded fixtures.
- `make check` is green and the three demonstration mutations (A8, B2, C3) are recorded in
  `build-log.md` as having failed their guard before being reverted.
- Trades execute transactionally with correct weighted-average-cost math and every edge
  case in the design's table handled.
- Chat executes trades and watchlist changes through the shared service functions, with
  rejections surfaced rather than swallowed.
- All eight UI elements from spec §10 present and fed by live data.
- One command starts it; the Playwright suite passes with `LLM_MOCK=true`.
- `.env` is gitignored and no secret is in git history.

**Optional-later:**
- The Massive real-data path beyond fixture-level tests (R6 — unverifiable here).
- Terraform / App Runner deployment (spec §11 calls it a stretch goal).
- 100% coverage of either half — the acceptance criteria and the risks are the target,
  not a coverage number.

## Migration / one-off scripts

None. Schema creation is `CREATE TABLE IF NOT EXISTS` at lifespan startup (D12); there is
no prior deployed instance to migrate and no data to move — the sibling `finally/` build
is reference only, and its database is not carried over.
