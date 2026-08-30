# Design decisions

Decisions taken while turning `SPEC.md` into `design.md`. Append-only across re-runs.
Choices the spec already made (SSE over WebSockets, SQLite over Postgres, static Next.js
export, single container, market orders only) are not re-litigated here — its §3 table
records those. What follows is what the *design* had to decide.

## D1: Prices live in memory only; every derived number is computed at read time

- **Decision:** No price column in any table. `PriceCache` is the sole home of current
  prices, and market value / unrealized P&L / total portfolio value are computed on each
  read by joining a durable `positions` row against the cache.
- **Alternatives considered:**
  - *A `current_price` column on `positions`, updated by the producer.* Rejected: it
    makes the producer a writer to the portfolio's own table, turns a 500 ms tick into a
    500 ms write burst, and guarantees the column is stale the instant it is read.
  - *A `prices` history table written every tick.* Rejected: ~2 writes/second/ticker
    forever, to serve charts the spec explicitly says are accumulated client-side.
- **Consequences:** Portfolio numbers are always consistent with what the user sees
  ticking. A restart loses all price history (sparklines restart empty — the spec accepts
  this). Real intraday charts would need the history table added back deliberately.

## D2: One producer task, one cache, many readers — the SSE endpoint never writes

- **Decision:** Exactly one background task writes the cache; every SSE generator is a
  pure reader. No lock: the producer builds a new dict and rebinds one reference, so a
  reader's snapshot cannot change underneath it and a slow client cannot stall the producer.
- **Alternatives considered:**
  - *Per-connection price generation.* Rejected: N clients would see N different prices
    for the same ticker at the same instant, and with Massive it would multiply API calls
    by the number of open tabs straight through the rate limit.
  - *A pub/sub fan-out with per-client queues.* Rejected as premature: it adds a client
    registry and a leak surface to solve a backpressure problem that a 500 ms polling
    generator does not have at this scale.
- **Consequences:** Adding clients costs only reads. The design is single-process by
  construction — multi-replica requires replacing `market/cache.py` with a shared store,
  which is the one change the module boundary is drawn to make cheap.

## D3: The ticker universe is watchlist ∪ open positions, re-read each tick

- **Decision:** The producer prices the union, and re-reads it from SQLite every
  iteration rather than being signalled on watchlist change.
- **Alternatives considered:**
  - *Watchlist only.* Rejected: removing a ticker you hold would freeze that position's
    price and silently corrupt total portfolio value.
  - *Event-driven invalidation from the watchlist endpoints.* Rejected: cross-task
    signalling for a query that reads ~10 rows from a local file is complexity with no
    payoff.
- **Consequences:** A newly added ticker is priced within one tick with zero coordination
  code. Cost is one trivial SELECT per tick, which is noise next to the HTTP poll it sits
  beside.

## D4: SSE sends only changed quotes, after one full snapshot

- **Decision:** First frame is the whole cache; subsequent frames carry only tickers
  whose producer timestamp advanced. Plus a `: keepalive` comment every ~15 s.
- **Alternatives considered:**
  - *Emit everything every tick.* Rejected: under the Massive source (15 s poll, 500 ms
    emit) it would push 30 identical frames per real quote, and each one would fire a
    price-flash animation on a price that did not move — the flash would become
    meaningless noise.
  - *Only send changes, no initial snapshot.* Rejected: a client connecting to a quiet
    market renders empty prices until something moves.
- **Consequences:** Bandwidth tracks real market activity. The generator carries a small
  per-connection `last_sent` map — the only per-client state in the system.

## D5: Chat actions run through the same service functions as manual actions

- **Decision:** `services/chat.py` calls `services/portfolio.execute_trade` and
  `services/watchlist.*` — the identical functions the REST endpoints call. There is no
  LLM-specific write path.
- **Alternatives considered:**
  - *A dedicated LLM execution path with its own validation.* Rejected outright: two
    validation implementations diverge, and the one that gets less attention is the one
    driven by unpredictable model output.
  - *Requiring user confirmation before LLM trades.* Rejected — the spec (§9
    Auto-Execution) makes auto-execution a deliberate demo choice with fake money.
- **Consequences:** "The LLM cannot do anything you could not do manually" is enforced by
  structure, not discipline. A validation fix lands in both paths at once. The cost is
  that `services/` must stay free of FastAPI types so both callers can use it — the
  layering rule exists to protect this decision.

## D6: Chat returns 200 with per-action outcomes, not an error, when a trade is rejected

- **Decision:** Rejected actions are recorded as
  `{"status": "rejected", "reason": "..."}` in the response's `actions` array and shown
  inline in the transcript. HTTP stays 200.
- **Alternatives considered:**
  - *4xx on any failed action.* Rejected: the assistant's *message* succeeded; failing
    the whole request would throw away a good answer because one suggested trade was too
    large.
  - *Silently dropping rejected actions.* Rejected: the user would see the assistant
    claim it bought something that never happened — the worst possible failure mode for a
    trust-dependent feature.
- **Consequences:** The frontend must render two action states. The transcript is honest
  about what the assistant tried and failed to do.

## D7: Actions capped at 10 per LLM response

- **Decision:** At most 10 trades + watchlist changes execute per turn; the rest are
  rejected with an explicit reason.
- **Alternatives considered:** *No cap.* Rejected: one malformed generation could execute
  hundreds of trades against the portfolio before anyone could intervene, and there is no
  undo.
- **Consequences:** Bounds the blast radius of a bad generation to something a user can
  read and understand. A legitimate "rebalance all 10 positions" request stays inside the
  cap.

## D8: Money is `float`, with rounding and an epsilon at the boundaries

- **Decision:** REAL/`float` throughout, matching the spec's schema. Writes round to 4
  decimals; a position with `quantity <= 1e-9` is deleted rather than kept.
- **Alternatives considered:**
  - *`Decimal` in Python with integer cents in SQLite.* Rejected: it contradicts the
    spec's stated schema, and it forces conversion at every JSON and SSE boundary for a
    portfolio of fake money that no one reconciles.
- **Consequences:** Sub-cent drift is possible over thousands of trades. The epsilon is
  what prevents the visible symptom — a phantom position of 1e-17 shares that the UI
  renders as `0.00` and refuses to let you sell.

## D9: `OPENROUTER_MODEL` is added to the environment contract; no default is baked in

- **Decision:** The model id comes from `OPENROUTER_MODEL` and is passed to LiteLLM
  verbatim. Missing or empty → chat returns 503 naming the variable. This adds a fourth
  variable to spec §5's three.
- **Alternatives considered:**
  - *Hardcoding the model in source* (as spec §9 does, naming
    `openrouter/openai/gpt-oss-120b`). Rejected on the user's explicit instruction that
    the model lives in `OPENROUTER_MODEL`, and independently because swapping models is
    the single most common thing anyone will want to change.
  - *A default model when the variable is unset.* Rejected: it would bill the user for a
    model they did not choose, and a typo in `.env` would look like the app working
    rather than like a misconfiguration.
- **Consequences:** `.env.example` and the README must document four variables, not
  three. Model behavior — including how well structured outputs are honoured — becomes
  configuration-dependent, which is why the parser is tolerant (D10).

## D10: No provider pinning on OpenRouter; structured outputs with a tolerant parser

- **Decision:** The request names only the model. No `provider.order`, no
  `allow_fallbacks: false` — OpenRouter routes. `response_format` carries a strict
  `json_schema` generated from the Pydantic models, and the parser still falls back to
  fence-stripping and outermost-brace extraction before giving up.
- **Alternatives considered:**
  - *Pinning Cerebras as the inference provider* (spec §9). Rejected on the user's
    explicit instruction, and it holds up on its own: pinning one provider means a hard
    outage whenever that provider drops the model, and it conflicts with a
    user-selectable `OPENROUTER_MODEL` since not every model is served by every provider.
  - *Prompt-only JSON ("respond with JSON") with no `response_format`.* Rejected: the
    whole point of structured outputs is that `trades[]` and `watchlist_changes[]` arrive
    as typed fields rather than being scraped out of prose.
  - *Trusting `strict` mode and parsing with `json.loads` alone.* Rejected: structured-
    output support across OpenRouter's catalogue is uneven, and the model is
    user-configurable, so the client cannot assume the best case.
- **Consequences:** Latency is whatever OpenRouter's routing gives, not a pinned fast
  provider — acceptable because the spec already chose a loading indicator over token
  streaming. The JSON Schema is generated from the Pydantic models rather than written
  twice, so the wire contract and validation cannot drift.
- **Note:** The spec's §9 instruction to use a `cerebras-inference` skill is superseded
  by this decision. That skill is also not installed in this environment — see
  `summary.md` § Open questions.

## D11: Stdlib `sqlite3`, no ORM; explicit transactions at the service layer

- **Decision:** Hand-written SQL in `db/`, with a `transaction()` context manager using
  `BEGIN IMMEDIATE`. A trade's position update, trade-log append, cash update, and
  snapshot are one transaction.
- **Alternatives considered:**
  - *SQLAlchemy (+ an async driver).* Rejected: six flat tables with no relationships
    worth mapping, against a dependency that brings a session lifecycle and an
    async-driver decision with it.
- **Consequences:** A failed trade validation leaves nothing behind. Queries are visible
  and tunable. Schema changes are hand-edited DDL — fine, since lazy `CREATE TABLE IF NOT
  EXISTS` initialization is the spec's stated migration strategy.

## D12: DB initialization at lifespan startup, not lazily per request

- **Decision:** `ensure_initialized()` runs once in the lifespan startup, before the
  producer starts.
- **Alternatives considered:** *Lazy init on first request* (spec §7 allows either).
  Rejected: it needs a lock on every request to keep two concurrent first-requests from
  racing the DDL, and it would leave the producer with no ticker list at boot.
- **Consequences:** Startup does one idempotent DDL pass. A corrupt database file fails
  loudly at boot rather than on a random first request.

## D13: An invalid `MASSIVE_API_KEY` does not fall back to the simulator

- **Decision:** Key set → Massive, always. Auth failures log loudly and retry with
  backoff; the app never silently switches to simulated prices.
- **Alternatives considered:** *Fall back to the simulator on repeated failure.*
  Rejected: a user who supplied a key and is shown plausible fake prices has been
  actively misled — the one failure mode in this system with real-world consequences,
  since someone might act on those numbers.
- **Consequences:** A bad key means visibly stale prices and loud logs, which is the
  correct signal. The choice of source stays a pure function of one env var.

## D14: `numpy` is deliberately not a dependency; correlation is one-factor

- **Decision:** GBM uses `random.gauss` and `math.exp` from the stdlib. Correlation is a
  one-factor model (`Z = ρ·Z_m + √(1−ρ²)·Z_i`), not a Cholesky decomposition.
- **Alternatives considered:** *numpy + a full covariance matrix.* Rejected: ~40 MB of
  wheel and a matrix-algebra concept to vectorize arithmetic over 10–30 tickers twice a
  second, producing a visual effect indistinguishable from the one-factor version.
- **Consequences:** A smaller image and no build-time compilation. The structural cost is
  that pairwise correlation is forced to `ρ_i·ρ_j`, so one factor cannot give two blocs
  strong internal correlation and weak correlation between them — high-ρ tech co-moves,
  and JPM/V are left low-ρ rather than being their own bloc. A second sector factor is one
  extra term if that ever matters. If the simulator grows to thousands of tickers, this is
  the first decision to revisit.

## D15: Backend `src/` layout with the package named `finally_app`

- **Decision:** `backend/src/finally_app/`, per the user profile's `src_layout: true`.
- **Alternatives considered:**
  - *A package literally named `finally`.* **Impossible** — `finally` is a Python
    reserved word; `import finally` is a `SyntaxError`. The project name stays "FinAlly"
    everywhere user-visible (repo, container, README); only the importable package is
    renamed.
  - *Flat `backend/app/`* (as the sibling `finally/` build used). Rejected: the profile
    specifies `src` layout, and it prevents the accidental-import-from-cwd class of test
    bug.
- **Consequences:** `pyproject.toml` needs the `src` layout configured for the build
  backend, and the Dockerfile copies `src/` accordingly.

## D16: Recharts over Lightweight Charts, and Recharts' `Treemap` over a hand-rolled one

- **Decision:** Recharts for all three visualizations — main chart, P&L chart, and the
  heatmap via `Treemap` with a custom cell renderer.
- **Alternatives considered:**
  - *TradingView Lightweight Charts* (named first in spec §10). Faster and more idiomatic
    for finance, but canvas-imperative and awkward beside a React tree; its real advantage
    is candlesticks and OHLC, which this app has no data for — every series here is a
    plain line of prices over time.
  - *A hand-rolled squarified treemap (~40 lines).* Rejected: Recharts is already a
    dependency for the line charts, so the hand-rolled version buys nothing and costs a
    layout algorithm to write, test, and maintain for exactly one visualization. It stays
    as the fallback only if Recharts' sizing proves unworkable.
- **Consequences:** One charting API across three visualizations, one dependency. If
  candlestick or volume charts are added later, Lightweight Charts becomes the right call
  and this decision should be revisited rather than worked around.

## D17: The frontend keeps one `EventSource` and a bounded price ring

- **Decision:** A single `EventSource` at the app root, shared by context; per-ticker
  price history capped at ~120 points.
- **Alternatives considered:**
  - *One `EventSource` per component that needs prices.* Rejected: browsers cap
    concurrent connections per origin, and every extra stream duplicates the same data.
  - *Unbounded history for richer sparklines.* Rejected: an hour-old tab accumulates
    7,200 points per ticker and the SVG path degrades until rendering stutters.
- **Consequences:** Sparklines show a fixed recent window (~60 s at 500 ms). Price-driven
  and state-driven components re-render on different triggers, which is what keeps a
  500 ms tick from re-rendering the whole page. The buffer is two-tier — see D22.

---

*Decisions below were added after the `vibe-architect` review pass.*

## D18: `GET /api/chat/messages` is added to spec §8's endpoint table

- **Decision:** One endpoint beyond the spec: `api/chat.py` serves the stored conversation
  so the panel repopulates after a reload.
- **Alternatives considered:**
  - *Keeping only the endpoints in spec §8.* Rejected: the chat panel is required to show
    "scrolling conversation history" (§10) and the design persists every turn to
    `chat_messages`, so without a read route the rows are written and never readable —
    history that exists only until F5.
  - *Holding history in browser state only.* Rejected: it makes the `chat_messages` table
    write-only, which is worse than not having it.
- **Consequences:** The endpoint table in the README and any agent-facing contract must
  list six routes, not five. Trivial handler; no new service logic.

## D19: `session_open` in the quote, distinct from `previous_price`

- **Decision:** `Quote` carries both. `previous_price` (last tick) drives the flash;
  `session_open` (first price of the process) drives the watchlist's change %.
- **Alternatives considered:**
  - *Computing change % from `previous_price`.* Rejected as simply wrong: at a 500 ms
    cadence it is a ±0.01% number that flips sign every tick, which no user would read as
    a "daily change".
  - *A real previous-close from Massive.* Rejected for the MVP: it exists only on the
    real-data path, so the simulator — the default — would still need a synthetic
    baseline, and the design would carry two.
- **Consequences:** Change % is honest within a process lifetime and re-baselines on
  restart. This is the one place the design knowingly renders something a real terminal
  would compute differently, and it is recorded in Limitations rather than hidden.

## D20: The prompt carries the last 10 messages

- **Decision:** 10 messages of history into the LLM prompt; the full transcript stays in
  SQLite and is served to the UI.
- **Alternatives considered:** *The whole transcript.* Rejected: it grows the prompt (and
  the bill) without bound on a single-turn assistant that mostly reasons over the current
  portfolio snapshot, which is regenerated fresh each turn anyway.
- **Consequences:** The assistant will lose the thread of a very long conversation. Spec
  §9 says only "recent"; this number is the design's, not the spec's, and it is a one-line
  change if turns out to be too short.

## D21: Blocking `sqlite3` is kept off the event loop by structure, not by an async driver

- **Decision:** `services/` functions are plain sync `def`; route handlers are declared
  `def` so Starlette runs them on its threadpool; background tasks reach them via
  `asyncio.to_thread`. One connection per call, WAL mode on.
- **Alternatives considered:**
  - *`aiosqlite` and async all the way down.* Rejected: it adds a dependency and makes
    every service function async — including in tests — to serialize onto a thread anyway,
    which is what `aiosqlite` does internally.
  - *Calling `sqlite3` directly from `async def` handlers.* Rejected: one slow write
    stalls every SSE generator and the producer with it. This is the failure that would
    have been found in production rather than in review.
- **Consequences:** The business layer stays sync and trivially testable, and D11's
  `BEGIN IMMEDIATE` claim becomes true rather than aspirational — with handlers on a
  threadpool there really are concurrent connections to serialize.

## D22: The client price buffer is two-tier (120 all / 1,800 selected)

- **Decision:** ~120 points per ticker for sparklines; ~1,800 for the selected ticker only.
- **Alternatives considered:**
  - *One cap for everything.* Rejected: 120 makes the "larger detailed chart" show the
    same 60-second window as the sparkline beside it; 1,800 for all tickers is 15× the
    memory and path complexity to feed charts nobody is looking at.
  - *A price-history endpoint.* Rejected here because it reverses D1; it is the right fix
    later, and it is listed as a future extension.
- **Consequences:** The main chart deepens the longer a ticker stays selected and resets
  on switch. Its horizon is minutes, not days — stated in Limitations.

## D23: Simulator volatility is deliberately unrealistic, and shocks are rated per minute

- **Decision:** Per-ticker σ ≈ 1.5–2.5 annualized (not a realistic ~0.3), and event shocks
  expressed as ~1% per ticker **per minute**.
- **Alternatives considered:**
  - *Realistic σ ≈ 0.3.* Rejected: at 500 ms ticks it moves ~0.009% per tick and ~0.1%
    across the entire visible sparkline window — a flat line. The spec asks for price
    action the user can watch.
  - *A per-tick shock probability of ~0.1%.* Rejected: at two ticks a second that is ~12%
    per minute per ticker, so shocks 20–50× the diffusion scale would arrive every few
    minutes on every symbol and the chart would become a staircase of jumps with flat
    stretches between them — shocks would *be* the price path instead of punctuating it.
- **Consequences:** The simulator is explicitly a watchability model, not a forecasting
  one, and the code should say so where the constants live. Anyone reading simulated
  volatility as market-realistic will be misled — which is also why D13 refuses to fall
  back to the simulator when a real-data key is present.

## D24: `MASSIVE_POLL_SECONDS` is configurable, defaulting to 15

- **Decision:** The Massive poll interval is an env var, default 15 s.
- **Alternatives considered:** *Hardcoding 15 s.* Rejected: spec §6 explicitly calls the
  interval configurable and gives paid tiers 2–15 s, so a hardcoded free-tier value means
  a paying user cannot use the tier they bought.
- **Consequences:** One more variable in `.env.example`. Lowering it below the user's tier
  limit will produce 429s, which D13's backoff already handles rather than crashing.

---

*D25 was added during `build` CP2, from live evidence the design could not have had.*

## D25: An empty model response is a distinct failure mode, and the chat endpoint answers 200

- **Decision:** `parse_response` raises `EmptyModelResponse` (a subclass of `LLMError`) when
  the model returns no content at all. The chat endpoint must turn it into **HTTP 200** with
  an apologetic assistant message recorded in the transcript — not a 503, and not a 500.
  `client.py` sets **no** `max_tokens`.
- **Why this is not theoretical:** during the CP2 spike, one of two live calls to
  `openai/gpt-oss-120b` returned `content: null`. It is a reasoning model, and the probe
  capped `max_tokens` at 400; roughly 250 tokens went to `reasoning_content` before the JSON
  body, so the budget was plausibly exhausted before any content was emitted. That is 50% of
  this build's live evidence, not a curiosity.
- **Alternatives considered:**
  - *Treating empty content like any other malformed reply — degrade to message-only.*
    Impossible: there is no message to degrade to. The distinction is real, which is why it
    gets its own exception type rather than a flag.
  - *Returning 503.* Rejected: 503 means "try again later", and retrying an identical prompt
    against a model that reasoned itself out of budget will most likely fail the same way.
    Worse, it implies the service is down when the call actually succeeded and was billed.
  - *Setting a generous `max_tokens` in `client.py`.* Rejected as insufficient on its own —
    it makes the failure rarer without making it impossible, and an unbounded request is
    already the correct default. The handling rule is what closes the gap.
- **Consequences:** CP9's orchestrator must catch `EmptyModelResponse` separately from
  `LLMError` and from `LLMNotConfigured`, and B5 needs a case for it. A user who hits this
  sees the assistant apologise for producing nothing, which is honest, instead of a spinner
  that never resolves or a red error toast implying the app is broken.
- **Standing caveat:** whether this model honours strict `json_schema` rests on **one**
  successful observation, on one OpenRouter route, at one moment. `verification-plan.md`
  § Cannot be verified item 2 says so explicitly. The tolerant parser is the standing
  mitigation, and changing `OPENROUTER_MODEL` re-opens the question — the risk-based
  expansion table already requires a fresh deliberate turn when it changes.

## D26: `litellm` stays, and the dependency surface is accepted rather than reduced

- **Decision:** the one live-model call keeps going through `litellm.acompletion`, and the
  ~60 transitive packages it brings into the runtime image are accepted. Not deferred, not
  "revisit later by default" — a considered no, taken by Antonio at CP19 when the alternative
  was put to him.
- **What the review actually found:** `litellm` is a large dependency for one POST to one
  OpenAI-compatible endpoint. The locked tree carries no outstanding advisories and
  `uv lock --check` reports no drift, which is why this was graded `advisory` and marked
  `Optional:` rather than `risk`. The cost is surface area and image size, not a known hole.
- **Why not swap it for a direct `httpx` POST:** because there is nothing to verify the
  replacement against. This build's **one sanctioned live LLM call was spent at CP2**, and
  what `build-log.md` recorded is the response **content** — not the HTTP envelope. A
  hand-rolled client could be tested only against an envelope written from memory of what
  OpenAI-compatible responses look like, which proves the test and the code agree, not that
  either matches OpenRouter. The first time it ran for real would be the first time a user
  sent a message.
- **What is being bought:** provider-error normalisation across OpenRouter's catalogue, and
  an envelope parser maintained by someone who can see live traffic. `client.py` already
  guards the two envelope shapes it knows can occur — empty `choices`, `content: null` (D25)
  — and both were learned from real responses, one of them the hard way.
- **Alternatives considered:**
  - *Swap now, verify on the next live call.* Rejected: that is shipping unverified code and
    calling the user's first real message the test.
  - *Vendor a minimal client behind the same interface and keep `litellm` as a fallback.*
    Rejected as strictly worse — it adds a code path and removes no packages, which inverts
    the only benefit on offer.
- **Consequences:** the image stays larger than it needs to be, and the dependency audit has
  a permanent standing item. Revisit when a live call is affordable: the interface
  (`complete(settings, messages) -> AssistantResponse`) is already narrow enough that the
  swap is a one-file change, and D25's two guards are the ones that would have to be
  reproduced.
