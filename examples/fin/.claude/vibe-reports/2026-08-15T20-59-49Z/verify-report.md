# Verify report — Gate B (end of Phase B)

Phase B: checkpoints 6, 7, 8, 9 — all built and overseer-approved.
Build run: `.claude/vibe-reports/2026-08-13T23-18-51Z/`. HEAD at verify: 44 commits.

## Passed

| Check | Result |
| --- | --- |
| **B1** trading edge cases | 37 tests — every row of the design's table: insufficient cash → 400 with need/have and **nothing written**; oversell → 400 naming held quantity; sell with no position → 400 not 404; quantity ≤ 0 / NaN / ±inf → refused **at the service**; no cached price → 409; exact and fractional full sells leave no ghost row; weighted-average cost across three unequal lots; `avg_cost` untouched by a partial sell |
| **B2** concurrent trades serialize | 2 tests, 10 rounds, two threads on a `Barrier` with their own connections. Exactly one fill, one rejection, one new trade row, cash never negative, no lock error escaping. **Demonstrated failing at CP6** |
| **B3** watchlist rules | 35 tests — duplicate add → 200 not 500; `" pypl "` → `PYPL`; malformed → 422 with the list unchanged; remove a held ticker → position survives **and stays in `read_universe`**; remove absent → 404 |
| **B4** snapshots and history | 16 tests — ≥2 rows in 0.3 s at an injected 0.05 s interval (and ≤30, so a spinning task fails too); `total_value == cash_balance` exactly when flat; one row per fill, zero per rejection; history ascending, newest window; lifespan starts the task **against the live cache** |
| **B5** chat orchestration | 30 tests — D5 sentinels (both services) plus a behavioural no-write guard; D6 200-with-rejected; D7 cap (three ways, and the cap follows the constant); degradation; D25 apology; D18 transcript; D20 prompt window |
| **B6** layering | grep clean: no web-framework import in `services/`, `market/` or `db/` |
| **B7** the suite cannot bill | **226 tests pass with `socket.connect`, `socket.create_connection`, `litellm.acompletion` and `litellm.completion` all raising on contact**, and both API keys unset |
| **A7** regression | The only `price` column in the schema is still `trades.price` — the historical fill price, which is not a current price (D1) |
| Static gates | `mypy --strict` clean over 31 files; flake8 clean; black/isort clean; **pylint 10.00/10** |

**Verdict: Phase B passes.**

### B7 is stronger than the plan specified, and the harness is not mine

The plan's B7 is `env -u OPENROUTER_API_KEY`. That proves only that no test reads the key — a
test could still call a model with a hardcoded string. The standard adopted at CP9 blocks the
network itself, and the harness used is **the overseer's own**, written during its CP9 review:
it makes `socket.connect`, `socket.create_connection` and both litellm entry points raise. Being
authored by the reviewer rather than by the author is the point — I did not build the instrument
that measures me.

**Positive control run:** a temporary test calling `socket.create_connection(("example.com", 80))`
fails under the harness with `_Blocked: BLOCKED: a test attempted a real network connection`. The
silence therefore means something. Control deleted after the run; `git status` clean.

## Not run

- **A5 — the live structured-output spike.** Still excluded: one billable call, spent at CP2,
  and the run-wide condition forbids a second. Nothing in Phase B needed it.
- **A live boot smoke.** Not run this gate. The lifespan test now asserts a database row whose
  value only a live cache can produce, plus that the task is cancelled at shutdown — which the
  overseer confirmed is strictly stronger than reading a startup log line, *once* those two
  assertions existed (they did not at the first CP8 submission, and it said so).

## What Phase B cost, honestly

Four checkpoints, **four rejections**, one of which was a live vulnerability rather than a test
defect.

**CP9's blocker is the one that matters.** `TradeAction.quantity` was a bare `float` while the
REST boundary carried `gt=0, allow_inf_nan=False`. Measured on a real database: a model-authored
`quantity: -5` was reported to the user as **filled**, wrote a trade row, and moved cash
**10,000.00 → 10,950.00**. `0` raised `ZeroDivisionError`; `NaN` produced a genuine **HTTP 500**.
Reachable from live output, too — `json.loads` turns the model text `1e400` into `inf`.

It was the CP7 ticker asymmetry recurring for a different field, and the overseer had written
that prediction down at CP7 review: *"the API pattern is a boundary guard, not a service-level
guarantee — CP9 calls `execute_trade` directly and bypasses `TradeRequest` entirely."* The
condition was in the ledger; the generalisation was not. **A rule enforced in a Pydantic model is
invisible to every non-HTTP caller**, and that is now a run-wide condition.

### Three checks that could not fail, all caught by re-running rather than reading

1. **CP8's newest-window test compared identical constants.** Buying 1..5 shares at a constant
   price moves cash and position value by equal and opposite amounts, so every total was exactly
   10,000.00. The overseer served the *oldest* window with all 190 tests green.
2. **CP8's lifespan test asserted only "a row exists."** A fresh `PriceCache()` handed to the task
   left the suite green while every snapshot would value positions at cost forever.
3. **CP9's D5 sentinels drove one input each.** A privileged write path conditioned on
   `0 < quantity < 1` stayed green across all 211 tests.

### Two mutation-table entries that did not reproduce

Recorded because a mutation table is this gate's evidence, and both were found by the overseer
**re-running** the battery rather than reading it:

- **CP8**: the ASC-ordering mutant was attributed to the newest-window test; it actually died on
  the ordering test, and not at all once ordering was preserved.
- **CP9**: "sign checked before finiteness" was **mislabelled**. The mutation that ran removed the
  finiteness check (a real, reproducible kill — 3 tests). Reversing the two lines is behaviourally
  equivalent, and the false rationale had reached two docstrings before it was corrected.

Neither was fabricated; both were wrong as written. The lesson is narrow and worth keeping: **a
mutation table is only evidence if someone other than its author re-runs it.**

## Coverage gaps

Carried into Phase C rather than hidden:

1. **Boundary-only bounds remain.** `ChatRequest.message`'s 1..4000 cap and the two `limit`
   bounds live in Pydantic models, valid only while each service has exactly one caller. Any new
   caller of `handle_message`, `read_history` or `list_messages` must bring the bound with it.
   This is the same shape as CP9's blocker, still latent.
2. **The structural D5 tripwire is single-file by nature.** It cannot see a write factored into
   another module; the behavioural test can, and does. The docstrings now say so rather than
   overclaiming.
3. **`PriceCache` never evicts**, so `GET /api/watchlist` can return a pre-removal quote for a
   re-added ticker. Pinned by a test that documents it rather than wishes it away.
4. **No multi-user coverage.** `user_id` is threaded correctly but every test uses `default`;
   pylint's unused-argument warning, not a test, is what caught it being dropped in `chat.py`.
5. **One cost-basis snapshot per boot under Massive**, while the first snapshot races the first
   poll. Ratified as expected behaviour for CP13's chart.

## Findings

No blockers, no risks. 31 advisory conditions are recorded in
`.claude/vibe-reports/2026-08-13T23-18-51Z/state.json` under `open_conditions`.

## Verdict

**PASS.** Phase B delivered the portfolio, watchlist, snapshot and chat layers with one shared
validation path: `services/` is callable from both the REST handlers and the chat orchestrator,
and after CP9 there is no rule the HTTP boundary enforces that the chat path escapes. That
property — D5 — is now guarded structurally *and* behaviourally, and the overseer failed to
breach it in four attempts including a raw `sqlite3.connect` write with a string-assembled table
name.

Next: **Phase C** (checkpoints 10–14 — frontend skeleton and static mount, live price surface,
trading surface, visualizations, chat panel). `build` remains the only repo-mutating mode and
continues under the `--auto` grant with per-checkpoint overseer approval. The blanket install
approval covers `npm install`/`npm ci` inside `fin/`.
