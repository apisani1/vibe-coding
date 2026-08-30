# Verification plan: FinAlly — AI Trading Workstation

Repo: `/Users/antonio/AI/MyCode/vibe-coding-course/fin` (referred to below as `$RR`).
Upstream: `SPEC.md`, `.claude/vibe-reports/2026-08-13T23-03-27Z/design.md` + `decisions.md`,
`.claude/vibe-reports/2026-08-13T23-18-51Z/plan.md`.

Drafted by `vibe-test-designer` **before any code exists**, per the plan runbook. Executed
by `verify` at each phase boundary.

**Nothing in this plan exists yet.** The repo is bare greenfield: no package manifests, no
test directories, no CI, no git history. There were no existing project checks to prefer
over invented ones — every check below is authored as part of the checkpoint that owns it.
The sibling `finally/` build was mined for realistic invocations and for which checks
earned their keep; none of its files belong to this repo.

Three checks are required to be **demonstrated failing** once, against a locally mutated
copy that is never committed (A8, B2, C3). A test that guards a subtle decision and has
never been seen to fail is a comment, not a check.

Gate-D check ids are prefixed `GD` to avoid collision with decision ids `D1`–`D24`.

## Criteria

Each criterion is observable. The gate column is the earliest phase boundary at which it
can run — assigned by when its code exists, not by when it would be nice to know.

| ID | Criterion | Source | Gate |
| --- | --- | --- | --- |
| AC-SEC | `.env` is ignored and absent from every commit; no key text in any reachable blob | R8, DoD | A |
| AC-BOOT | Backend installs, type-checks, lints, and `GET /api/health` returns 200 | CP1 | A |
| AC-LLM-PARSE | Structured-output parsing survives clean JSON, fenced JSON, prose-wrapped JSON, malformed text, and schema-violating JSON without a 500 | §9, §12, D10 | A |
| AC-LLM-LIVE | The configured model's actual behaviour under strict `json_schema` is recorded | R1, CP2 | A (one-shot) |
| AC-DB-INIT | Init is idempotent: twice against one file yields the schema plus exactly one seeded profile and 10 tickers; WAL is on | §7, D12 | A |
| AC-DB-SHAPE | Six tables with the spec's columns, both UNIQUE constraints, both CHECKs, both indexes | §7, design data model | A |
| AC-NO-PRICE | No table stores a current price; market value, unrealized P&L and total value are computed at read time | D1 | A (schema) / B (values) |
| AC-GBM | GBM applies the −σ²/2 correction, so expected log return is `(μ−σ²/2)·dt`, not `μ·dt` | D23 | A |
| AC-SHOCK | Event shocks arrive at ~1% per ticker **per minute**, not per tick | D23 | A |
| AC-CORR | Correlated tickers co-move; uncorrelated ones do not | §6, D14 | A |
| AC-SESSION-OPEN | `session_open` is stamped once per ticker per process and never rewritten; `previous_price` moves every tick | D19 | A |
| AC-SOURCE | `MASSIVE_API_KEY` empty selects the simulator; non-empty selects the Massive poller with no fallback; both satisfy the `MarketDataSource` Protocol | §5, §6, D13 | A |
| AC-SSE | First frame is a full cache snapshot; later frames carry only changed tickers; `: keepalive` every ~15 s; disconnect unwinds the generator; each event carries all six `Quote` keys | §6, D4 | A |
| AC-TRADE | Every row of the design's trading edge-case table behaves as specified, including weighted-average cost on buy, `avg_cost` untouched on sell, and full-sell row deletion | §12, design | B |
| AC-SERIAL | Two genuinely concurrent trades serialize; cash can never go negative | D21, R2 | B |
| AC-WATCH | Duplicate add → 200, lowercase normalized, bad format → 422, remove-held keeps the position priced, remove-absent → 404 | design | B |
| AC-SNAP | A snapshot row is written on an interval and immediately after each trade; history is time-ordered; total equals cash with no positions | §7, §8 | B |
| AC-CHAT-SHARED | LLM-requested trades execute through the *same* service function as manual trades | D5 | B |
| AC-CHAT-REJECT | A rejected LLM trade returns **HTTP 200** with `status: "rejected"` and a reason | D6 | B |
| AC-CHAT-CAP | Actions beyond 10 per response are rejected with an explicit reason | D7 | B |
| AC-CHAT-DEGRADE | A malformed LLM response degrades to message-only, never a 500 | design | B |
| AC-CHAT-HISTORY | `GET /api/chat/messages` returns the turn after a reload | D18 | B |
| AC-NO-BILL | The entire backend suite passes with no OpenRouter key present | R7 | B |
| AC-MOUNT | The static export serves `/` and does **not** shadow `/api/*` — an unknown `/api/…` path 404s as JSON, not as the HTML shell | R3 | C |
| AC-CHANGE-PCT | Watchlist change % derives from `session_open`, not `previous_price` | D19 | C |
| AC-FLASH | A new quote applies a flash class and removes it after ~500 ms | §2, §10 | C |
| AC-FE-DEGRADE | Sparkline with <2 points is a flat baseline; missing price renders `—`; empty portfolio renders empty states, not a crash | design | C |
| AC-STATUS | The connection dot maps `readyState` to green / yellow / red and never shows green without evidence | §2 | C / D |
| AC-TRADE-UI | Successful trade refetches the portfolio; a 400 renders the error without clearing the form; positions table shows six columns | §10 | C |
| AC-VIZ | Heatmap is sized by weight and coloured by P&L sign; clicking a watchlist ticker changes the main chart series | §10 | C |
| AC-CHAT-UI | Loading indicator while in flight; `filled` and `rejected` actions both render inline; history repopulates on mount | §10, D6 | C |
| AC-THEME | The spec's dark background and three accent hexes exist as theme tokens | §2 | C |
| AC-DOCKER | `docker build` succeeds; the container serves `/` and `/api/health` on 8000; `db/` is not baked into the image | §11, R4 | D |
| AC-PERSIST | Portfolio survives stop + restart on the named volume; `stop` never removes the volume; `start` twice is a no-op | §11 | D |
| AC-E2E | The spec §12 scenarios pass from a cold compose, with `LLM_MOCK=true` and no real key in the test stack | §12, R7 | D |
| AC-DOCS | Every variable in `.env.example` appears in the README table | CP17 | D |

## Checks

Working directory is given for every command. `$RR` = `/Users/antonio/AI/MyCode/vibe-coding-course/fin`.

### Gate A — end of Phase A (CP0–CP5)

**A1 — secret hygiene.** *Proves AC-SEC.*
```bash
cd $RR
git check-ignore -v .env                      # exits 0
! git ls-files --error-unmatch .env 2>/dev/null
git log --all --pretty=format: --name-only | sort -u \
  | grep -E '^\.env' | grep -v '^\.env\.example$'   # must print nothing
git log --oneline | wc -l                     # expect 1 at CP0

# Blob scan, two needles — a shape and a value.
scan() {   # $1 = grep -E pattern; prints paths of blobs that match
  git rev-list --all --objects | while read -r o p; do
    [ -n "$p" ] || continue
    [ "$(git cat-file -t "$o" 2>/dev/null)" = "blob" ] || continue
    git cat-file blob "$o" 2>/dev/null | grep -qE "$1" && echo "$p"
  done
}
# (a) SHAPE: any credential of this provider family, not just today's key.
#     Catches a rotated key, a second credential, or the `.env.bak-massive`
#     old key -- the very case that motivates `.env*` over a literal `.env`.
#     `{8,}` is what keeps the documentation clean: `sk-or-v1` as written in
#     plan.md and in this file has only 5 characters after `sk-`, so prose
#     mentions of the prefix never match while real key material always does.
[ -z "$(scan 'sk-[A-Za-z0-9_-]{8,}')" ] && echo "PASS: no provider credential in history"
# (b) VALUE: the specific live key, belt-and-braces.
KEY=$(grep '^OPENROUTER_API_KEY=' .env | cut -d= -f2-)
[ -z "$(scan "$(printf '%s' "$KEY" | sed 's/[][\.*^$/]/\\&/g')")" ] \
  && echo "PASS: live key absent from history"
# (c) POSITIVE CONTROL: prove the scan can find something that IS committed.
scan 'AI-powered trading workstation' | grep -q SPEC.md \
  && echo "positive control OK" || echo "SCAN IS BROKEN — do not trust any PASS above"
```
*Claim:* the live OpenRouter key is not in the index nor in any commit, and no `.env*`
sibling (e.g. `.env.bak-massive`) leaked. The only check in the plan with a real-world blast
radius; it runs first and again at Gate D.

**Scan for the shape, not only for today's value.** A value-only scan passes silently on a
rotated key, a second provider credential, or the `.env.bak-massive` old key — and that last
case is the stated reason this repo ignores `.env*` rather than a literal `.env`, so a check
blind to it contradicts the rule it is supposed to enforce.

The **positive control is not optional**. A scan that silently matches nothing — wrong
needle, broken pipeline, `grep -r` skipping dotfiles — reports PASS exactly like a clean
repo does. Proving it can find a string that *is* committed is what makes its silence mean
something. (Observed during CP0: BSD `grep -rlF "$KEY" .` fails to match `.env` at the tree
root even though `grep -lF "$KEY" .env` matches, which is precisely how this class of check
lies.)

**A2 — backend static gates.** *Proves AC-BOOT; carries the Protocol-conformance half of
AC-SOURCE.*
```bash
cd $RR/backend
uv sync
uv run pytest -q
uv run mypy src
uv run flake8 src tests
uv run black --check . && uv run isort --check-only .
```
*Claim:* the package imports under the `src` layout (D15), types check, style matches the
profile at line length 119. `mypy src` is the only thing proving the simulator and the
Massive client structurally satisfy the same Protocol — there is no runtime base class to
assert against. (System python here is 3.10, so `uv` must pin 3.12 explicitly.)

**A3 — app boots and answers.** *Proves AC-BOOT.*
```bash
cd $RR/backend
LLM_MOCK=true uv run uvicorn finally_app.main:app --port 8000 &
sleep 3; curl -sf -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/health  # 200
kill %1
```

**A4 — LLM parser table.** *Proves AC-LLM-PARSE.*
```bash
cd $RR/backend
uv run pytest tests/test_llm_client.py -q
```
Parametrized over five inputs, each asserting a distinct outcome: clean JSON → typed
fields; fenced ```` ```json ```` → same typed fields; JSON embedded in prose → outermost
braces extracted; unparseable prose → message-only degradation, no exception escaping;
JSON that parses but violates the schema → message-only, actions dropped, warning logged.
*Claim:* the tolerant parser (D10) degrades in the documented order, so a model that
ignores `response_format` costs a feature, not a 500.

**A5 — the live structured-output spike (ONE-TIME, BILLABLE).** *Proves AC-LLM-LIVE.*
```bash
cd $RR/backend
uv run python scripts/spike.py   # single acompletion, prints the raw response
```
Run **exactly once**, at CP2, with `LLM_MOCK` unset. Paste the raw response into
`build-log.md` and record whether strict `json_schema` was honoured, degraded to fenced
JSON, or ignored. The only sanctioned live LLM call in the plan (R7). If the schema is not
honoured, CP2's fallback (few-shot with the schema inlined) is decided here and Phase C's
chat contract is re-cut before any component is written.

**A6 — DB init idempotency and shape.** *Proves AC-DB-INIT, AC-DB-SHAPE, schema half of
AC-NO-PRICE.*
```bash
cd $RR/backend
uv run pytest tests/test_db_init.py -q
```
`ensure_initialized()` twice against one temp file → no error, exactly one `users_profile`
row with `cash_balance == 10000.0`, exactly 10 watchlist rows; `PRAGMA journal_mode`
returns `wal`; an inventory assertion comparing `PRAGMA table_info` for all six tables
against the design's column list, plus `sqlite_master` containing both UNIQUE constraints,
both CHECKs, and both indexes.

**A7 — no stored current price.** *Proves the structural half of AC-NO-PRICE (D1).*
```python
# backend/tests/test_db_init.py::test_no_table_stores_a_current_price
for table in ("users_profile", "watchlist", "positions", "portfolio_snapshots"):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    assert not {c for c in cols if "price" in c.lower()}
```
*Claim:* nobody added a `current_price` column to `positions` as a "quick fix" for a slow
read. `trades.price` is legitimately a historical fill price and is excluded by the table
list, not by a name pattern. Cheap, and exactly the check that catches D1 being quietly
reversed under performance pressure.

**A8 — GBM Jensen correction.** *Proves AC-GBM. **Must be demonstrated failing.***
```bash
cd $RR/backend
uv run pytest tests/test_market_simulator.py -q -k jensen
```
Calls the **pure step function** with test parameters, not production tick parameters:
`mu=0.0, sigma=1.0, dt=1.0` (one year), 4000 draws from a seeded `random.Random(1234)`,
asserting `-0.55 < mean(log(S1/S0)) < -0.45`. Expected value is `−σ²/2 = −0.5` with a
standard error of `1/√4000 ≈ 0.0158`; the uncorrected form centres on `0.0`, ~31 standard
errors outside the band.

This calibration is not arbitrary. At production parameters (`dt = 0.5 s` of trading time,
`σ ≈ 2`) the missing term shifts the price by a relative **1.7e-7** — needing ~10⁷ samples
to resolve, and vanishing entirely if the step rounds to 2 decimals. Hence the testability
requirement in CP4: `gbm_step(price, mu, sigma, dt, z)` must be pure, must not round
internally, and must accept an injected normal draw.

**Demonstration:** at CP4, delete the `- sigma**2/2` term locally, confirm this test fails,
record the observed mean in `build-log.md`, revert. Do not commit the mutation.

**A9 — shock rate is per minute.** *Proves AC-SHOCK (D23).*
```bash
cd $RR/backend
uv run pytest tests/test_market_simulator.py -q -k shock
```
Two assertions. The conversion is unit-correct: per-tick probability equals
`rate_per_minute * tick_seconds / 60`. And a statistical count of shocks **actually fired
inside `advance()`** (the simulator exposes a `shocks_fired` counter), over **24 simulated
hours** — 172,800 ticks at 500 ms — asserting `5 <= fired <= 30`.

**Amended at CP4, twice, and both amendments matter:**

1. *The horizon and band changed from the original `0 < shocks < 3` over one hour.* At
   0.01/minute the hourly expectation is **0.6**, so zero shocks is the single most likely
   outcome and `0 < shocks` would have failed on roughly 55% of seeds. The band was
   unreachable as specified. Over 24 hours the expectation is ~14.4 and `5..30` sits
   comfortably inside the noise while still excluding both degenerate implementations.
2. *The count must be driven through `advance()`, not re-sampled from the probability.* The
   first implementation looped on `rng.random() < simulator.shock_probability` and never
   called the simulator at all.

   Discrimination, all figures over the **same 172,800-tick (24 simulated hour) horizon**
   the test actually uses:

   | Simulator | Old loop reports | Instrumented reports | In band 5..30? |
   | --- | --- | --- | --- |
   | shockless (`rate=0`) | 0 | 0 | no |
   | shipped (`rate=0.01/min`, seed 99) | 0 | **16** | yes |
   | always (`rate=120/min` → `p=1.0`) | 0 | 172,800 | no |

   A companion test (`test_the_shock_count_check_can_actually_fail`) pins both ends by
   asserting the zero-rate and `p=1.0` simulators fall outside the band. `rate=120/min` at a
   0.5 s tick is `p = 1.0` exactly, so `random() >= 1.0` is never true and it fires on every
   tick.

**A10 — `session_open` is stamped once.** *Proves the backend half of AC-SESSION-OPEN
(D19).*
```bash
cd $RR/backend
uv run pytest tests/test_market_cache.py -q -k session_open
```
Drive the producer 50 ticks over a two-ticker universe. `session_open` is byte-identical to
the first price observed for each ticker and unchanged across all 50 ticks, while
`previous_price` changed at least 40 times. Then add an 11th ticker mid-run: its
`session_open` equals its own first price and its change % reads exactly `0.0` on that
first tick.

**A11 — correlation bands.** *Proves AC-CORR.*
```bash
cd $RR/backend
uv run pytest tests/test_market_simulator.py -q -k correlation
```
2000 ticks across **five seeds**, with **shocks disabled**, asserting tech > 0.6,
cross < 0.4, and — the load-bearing one — a separation of `tech - cross > 0.3`.

**Amended at CP4.** Bands are now set from the measured distribution rather than guessed.
With shocks on, the tech correlation ranges **0.30–0.77** across seeds against the original
`> 0.5` band: a single 2–5% jump dwarfs a window whose typical |log return| is ~8e-4, so the
test passed or failed on whether one outlier happened to land. With shocks off the
distribution is tech **0.716–0.768** (theory 0.748) and cross **0.230–0.303** (theory
0.255) — note the original `cross < 0.3` band sits *inside* the observed range and would
have flaked. Correlation is a property of the diffusion term, so isolating it from shocks is
what makes the bands mean something.

**Accepted consequence, stated deliberately rather than left implicit:** with shocks
disabled, A11 no longer asserts anything about co-movement under the configuration that
actually *ships*. That is the price of a check that can fail for the right reason. The
shipped shock path is covered by A9 instead.

**A12 — market source selection and Massive parsing.** *Proves AC-SOURCE.*
```bash
cd $RR/backend
uv run pytest tests/test_market_factory.py tests/test_massive_client.py -q
```
Factory: `MASSIVE_API_KEY=""` → simulator; non-empty → Massive poller; **no fallback path
exists** (D13) — assert the factory has no branch returning the simulator when a key is
present. `MASSIVE_POLL_SECONDS` defaults to 15 and is honoured when set (D24). Parsing: a
recorded fixture of a Massive REST response produces a `Quote` with the same keys the
simulator produces; a fixture with one malformed entry among good ones yields the good
ones and drops the bad (per-ticker guarding). Live HTTP stays under Cannot be verified.

**A13 — SSE contract.** *Proves AC-SSE (R5's backend half).*
```bash
cd $RR/backend
uv run pytest tests/test_stream.py -q
```
Assertions against a hand-driven cache, driving `price_events` directly:

1. First frame contains every ticker in the cache, and each event body carries all six
   `Quote` keys including `previous_price` **and** `session_open`.
2. With the cache frozen, everything after the first frame is `: keepalive` comments only.
   This is what proves D4's change-only rule — an emit-everything loop fails here at once.
3. Advance one ticker → the next frame contains that ticker and no other.
4. An **unchanged** price produces no frame at all (this is why `cache.apply` must not
   restamp: a restamp advances the timestamp, satisfies change detection, and emits a frame
   for a price that did not move).
5. The heartbeat fires at its **configured cadence**, measured over a fixed duration rather
   than a fixed frame count — capping the count makes the assertion circular.
6. Cancelling the generator propagates `CancelledError` rather than swallowing it; a
   swallowed cancellation is a task leaked per closed tab.
7. Running the generator leaves the cache byte-identical (D2: pure reader).
8. No module in `api/` reassigns `app.state.source` or `app.state.cache`.

**Amended at CP5.** This originally prescribed "four assertions via `httpx.ASGITransport`"
and "a `finally`-block sentinel fires". Neither is possible or true:
`httpx.ASGITransport` **does not return response headers until the response completes**, so
it cannot test a stream that never ends by design — the first attempt hung the entire suite
past a 400 s timeout. And the generator uses `except asyncio.CancelledError: … raise`, not a
`finally` sentinel. The endpoint's wire behaviour is proven by the raw smoke below, which is
what the plan intended for it all along.

Plus a raw-wire smoke, with the app from A3 running:
```bash
curl -N -s --max-time 6 http://localhost:8000/api/stream/prices | head -30
```
*Claim:* real frames on a real socket in the documented `text/event-stream` shape, before
any browser exists — R5's whole point.

### Gate B — end of Phase B (CP6–CP9)

**B1 — trading edge-case table.** *Proves AC-TRADE and the value half of AC-NO-PRICE.*
```bash
cd $RR/backend
uv run pytest tests/test_portfolio.py -q
```
One test per row of the design's table: insufficient cash → 400 with need/have in the
detail and **nothing written** (assert `trades` and `positions` unchanged); oversell → 400
naming held quantity; sell with no position → 400 not 404; quantity ≤ 0 / NaN / inf → 422
at the Pydantic boundary; no cached price → 409; exact-full sell deletes the row;
fractional full sell leaves no `1e-17` ghost. Plus weighted-average cost across three
unequal lots, `avg_cost` unchanged by a partial sell, and `get_portfolio` totals
reconciling `cash + Σ(qty·cached_price)` — which is what proves derived values come from
the cache rather than a stored column.

**B2 — concurrent trades serialize.** *Proves AC-SERIAL (D21 / R2). **Must be demonstrated
failing.***
```bash
cd $RR/backend
uv run pytest tests/test_portfolio_concurrency.py -q
```
Two `threading.Thread`s synchronized on a `threading.Barrier(2)`, each opening its own
connection through `db/connection.py`, each attempting a buy consuming 60% of the cash
balance. Assert: exactly one fill and one rejection, final cash ≥ 0, exactly one new
`trades` row, and no `sqlite3.OperationalError: database is locked` escaping (a
`busy_timeout` must be set). Repeat 10 rounds to defeat scheduling luck.

Sequential calls on one thread pass identically under `BEGIN IMMEDIATE`, `BEGIN DEFERRED`,
and autocommit — there is never a second open write transaction — so genuine thread
overlap is the whole point of the check.

**Demonstration:** at CP6, change `BEGIN IMMEDIATE` to `BEGIN DEFERRED` locally and confirm
the test fails. Record which way, in `build-log.md`, then revert. Without this, the check is
indistinguishable from one that passes for the wrong reason — precisely the failure R2
describes.

*Measured at CP6, and not what this paragraph originally predicted.* Under WAL a `DEFERRED`
read transaction whose snapshot another writer has already superseded **cannot upgrade** to a
write (`SQLITE_BUSY_SNAPSHOT`), and that refusal is not retried by `busy_timeout` — waiting
cannot help, because the reader's snapshot is already stale. So `DEFERRED` fails **20/20 as
`database is locked`**, never as a double fill. What `BEGIN IMMEDIATE` buys is therefore *the
second writer waits and is then honestly rejected, instead of erroring* — not "no double
spend", which WAL enforces on its own at this isolation level.

A double spend **is** still reachable, just by a different route: reading the cash balance
outside the write transaction. The overseer reproduced exactly that at CP6 review and B2
failed with `outcomes were ['filled', 'filled']`, which is what establishes that this check
guards the property rather than the keyword.

**The widened read–write window is mandatory, not decoration.** The check monkeypatches
`portfolio._read_cash_balance` to hold the balance for 50 ms. Without it, `DEFERRED` passes
**8/20** — a single-run demonstration would have "proved" a broken isolation level correct
40% of the time.

**B3 — watchlist rules.** *Proves AC-WATCH.*
```bash
cd $RR/backend
uv run pytest tests/test_watchlist.py -q
```
Duplicate add → 200 not 500; `" aapl "` stored as `AAPL`; `"AA PL"` and an 11-character
symbol → 422; remove a ticker with an open position → 204, position row survives, and the
producer's universe still contains it (asserted against the union query directly — this is
the D3 corruption path); remove absent → 404.

**B4 — snapshots and history.** *Proves AC-SNAP.*
```bash
cd $RR/backend
uv run pytest tests/test_snapshots.py -q
```
With the interval injected as 0.05 s, at least two rows appear within 0.3 s; with no
positions, `total_value == cash_balance` exactly; a trade writes a snapshot synchronously
inside the trade's transaction (count increments by exactly one per fill, zero per
rejection); `GET /api/portfolio/history` returns rows ascending by `recorded_at`.

**B5 — chat orchestration under mock.** *Proves AC-CHAT-SHARED, AC-CHAT-REJECT,
AC-CHAT-CAP, AC-CHAT-DEGRADE, AC-CHAT-HISTORY.*
```bash
cd $RR/backend
LLM_MOCK=true uv run pytest tests/test_chat.py -q
```
Five assertions, each pinning a decision rather than a framework:
- **D5 shared path** — monkeypatch `finally_app.services.portfolio.execute_trade` to raise
  a sentinel, POST a chat message whose mock response contains a trade, assert the sentinel
  propagated. If the chat service has its own write path, the sentinel is never hit and the
  test fails. Structural, not stylistic.
- **D6** — a mocked trade for 10,000 shares of a $190 ticker → status is **200** and
  `actions[0] == {"type":"trade", …, "status":"rejected", "reason": <mentions cash>}`.
  Explicitly assert `response.status_code == 200`; a 4xx is a failure here even though it
  "correctly refused the trade".
- **D7** — a mock response with 11 actions → exactly 10 executed, the 11th recorded rejected
  with a cap reason, exactly 10 new `trades` rows.
- **Degradation** — a mock returning unparseable prose → 200, `message` non-empty,
  `actions == []`, no 500 anywhere in the chain.
- **D18** — after the turn, `GET /api/chat/messages` returns the user message and the
  assistant message with `actions` JSON intact, newest last.

**B6 — layering guard.** *Protects AC-CHAT-SHARED (D5's precondition).*
```bash
cd $RR/backend
! grep -rn "^from fastapi\|^import fastapi" src/finally_app/services/
! grep -rn "^from fastapi\|^import fastapi" src/finally_app/market/ src/finally_app/db/
```
*Claim:* `services/` stays callable from both the REST handler and the chat orchestrator.
The moment a service function raises `HTTPException`, the shared-validation property D5
depends on starts eroding — this grep is the cheapest possible tripwire.

**B7 — the suite cannot bill.** *Proves AC-NO-BILL (R7).*
```bash
cd $RR/backend
env -u OPENROUTER_API_KEY LLM_MOCK=true uv run pytest -q
```
*Claim:* no test reaches OpenRouter. If one does, it fails here rather than on the credit
card. Run at every gate from B onward.

### Gate C — end of Phase C (CP10–CP14)

**C1 — static export mount does not shadow the API.** *Proves AC-MOUNT (R3).*
```bash
cd $RR/frontend && npm ci && npm run build && test -d out
cd $RR && cp -R frontend/out/. backend/src/finally_app/static/
cd $RR/backend && LLM_MOCK=true uv run uvicorn finally_app.main:app --port 8000 &
sleep 3
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/               # 200
curl -s http://localhost:8000/ | grep -qi '<!DOCTYPE html'                    # SPA shell
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/health     # 200
curl -s http://localhost:8000/api/definitely-not-a-route | head -c 200        # JSON 404, NOT html
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/definitely-not-a-route  # 404
kill %1
```
The load-bearing line is the last pair. Runs at CP10 against a hello-world page — the point
is to fail before any component exists.

**Corrected at CP10, from measurement.** The rationale above predicted the wrong symptom, and
the wrong symptom implied a check that would have passed while the bug was live:

- Starlette's `StaticFiles(html=True)` does **not** return `index.html` with a 200 for an
  arbitrary unresolvable path. It looks for `404.html` — which `next build`'s export *does*
  emit — and serves that page with a **404**. Mounted **before** the routers it absorbs
  `/api/health` itself, which the `== 200` assertion catches after all.
- Mounted **after** the routers, the shadowing the plan worried about is gone, but an unknown
  `/api/*` path still reaches the mount (no router matched it) and comes back as `text/html`
  with a 404. Ordering alone therefore does **not** satisfy the last assertion here.

So the last pair stays, with the emphasis moved to the **content type**: both wrong
arrangements answer 404, and only `application/json` distinguishes a right one. What makes it
true is an explicit `/api/{path:path}` route registered after the real routers and before the
mount (`main._add_api_not_found`). Add to the commands:
```bash
curl -s -o /dev/null -w '%{content_type}\n' http://localhost:8000/api/definitely-not-a-route  # application/json
```

**C2 — frontend unit gates.**
```bash
cd $RR/frontend
npm run test        # vitest run
npm run typecheck   # tsc --noEmit
npm run lint
```

**C3 — change % derives from `session_open`.** *Proves AC-CHANGE-PCT (D19). **Must be
demonstrated failing.***
```bash
cd $RR/frontend
npm run test -- Watchlist
```
The discriminating fixture: one quote with `session_open: 100, previous_price: 199.99,
price: 200`. Assert the row renders `+100.00%`. A `previous_price`-derived implementation
renders `+0.01%` and fails; a naive test whose fixture makes the two baselines equal passes
under both implementations and proves nothing. Second case: `session_open === price` renders
exactly `0.00%` (the first-tick case the design calls honest, not a placeholder).

**Demonstration:** at CP11, swap the component to use `previous_price`, confirm the test
fails, revert.

**C4 — flash lifecycle, status dot, degenerate sparkline.** *Proves AC-FLASH, AC-STATUS
(component half), AC-FE-DEGRADE (partial).*
```bash
cd $RR/frontend
npm run test -- Watchlist Sparkline Header
```
With fake timers: a new higher price applies `flash-up`, and after ~500 ms the class is gone
— assert **both** states, because asserting only the add lets a permanently-green row pass.
A sparkline with 0 and with 1 point renders a flat baseline element and does not throw.
`readyState` OPEN → `connected`, CONNECTING-after-open → `reconnecting`, repeated error →
`disconnected`; and a stream that has never opened must **not** render `connected`.

**C5 — trading surface.** *Proves AC-TRADE-UI.*
```bash
cd $RR/frontend
npm run test -- TradeBar PositionsTable
```
A successful POST triggers exactly one portfolio refetch; a 400 renders the server's
`detail` string and the inputs retain their values; the positions table renders six columns
and shows `—` (not `$0.00`, not `NaN`) for market value and P&L when the cached price is
missing.

**C6 — visualizations.** *Proves AC-VIZ and the rest of AC-FE-DEGRADE.*
```bash
cd $RR/frontend
npm run test -- Heatmap PnlChart MainChart
```
Empty portfolio → explicit empty-state elements for heatmap and positions, no throw; a
position above `avg_cost` gets a green fill and one below gets red (assert the fill prop
passed to the cell renderer, not a rendered pixel); clicking a watchlist row changes the
series identity passed to the main chart.

**C7 — chat panel.** *Proves AC-CHAT-UI.*
```bash
cd $RR/frontend
npm run test -- ChatPanel
```
Loading indicator present while the promise is pending and absent after resolve; a
`status: "filled"` action renders as a trade confirmation; a `status: "rejected"` action
renders its `reason` text — the D6 pairing, because a panel that renders only `filled`
actions silently reproduces the "assistant claims it bought something" failure D6 exists to
prevent; mounting fires `GET /api/chat/messages` and renders the returned turns.

**C8 — theme tokens.** *Proves AC-THEME, and only AC-THEME.*
```bash
cd $RR/frontend
grep -q '#ecad0a' tailwind.config.ts src/app/globals.css
grep -q '#209dd7' tailwind.config.ts src/app/globals.css
grep -q '#753991' tailwind.config.ts src/app/globals.css
grep -qE '#0d1117|#1a1a2e' tailwind.config.ts src/app/globals.css
```
*Claim:* the palette is wired as tokens rather than scattered as literals. It does **not**
claim the UI looks good — see Cannot be verified.

### Gate D — end of Phase D (CP15–CP17)

**GD1 — image builds, serves, and does not bake `db/`.** *Proves AC-DOCKER (R4).*
```bash
cd $RR
docker build -t finally:latest .
docker run --rm --entrypoint sh finally:latest -c 'ls -A /app/db | wc -l'   # 0
docker run -d --name finally-verify -v finally-data:/app/db -p 8000:8000 --env-file .env finally:latest
sleep 8
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/health   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/             # 200
```
The empty `/app/db` assertion is the design's rule made into a check: an image-baked file
there shadows the volume mount and the user's portfolio silently resets on every
`docker run`.

**GD2 — persistence and script idempotency.** *Proves AC-PERSIST.*
```bash
cd $RR
curl -s -X POST http://localhost:8000/api/portfolio/trade \
  -H 'content-type: application/json' -d '{"ticker":"MSFT","quantity":2,"side":"buy"}' | jq .
docker stop finally-verify && docker rm finally-verify
docker run -d --name finally-verify -v finally-data:/app/db -p 8000:8000 --env-file .env finally:latest
sleep 8
curl -s http://localhost:8000/api/portfolio | jq '.positions[] | select(.ticker=="MSFT")'  # present
./scripts/start_mac.sh   # first run
./scripts/start_mac.sh   # second run: reports already-running, starts nothing new
# Anchored, and using the script's own overridable name. `--filter name=finally`
# is a substring match: with any other container whose name contains "finally"
# running — a previous build's, say — it returns 1 for the wrong reason and the
# check passes vacuously. Ratified at CP15 review, where exactly that container
# was present.
docker ps --filter status=running --filter "name=^/${CONTAINER:-finally}$" --format '{{.Names}}' | wc -l   # 1
./scripts/stop_mac.sh
docker volume inspect finally-data >/dev/null && echo "volume survived stop"
```
The last line matters most: a `stop` that removes the volume destroys the user's portfolio,
and it is the single most destructive thing that could ship in this repo.

**GD3 — E2E suite.** *Proves AC-E2E and the runtime half of AC-STATUS.*
```bash
cd $RR/test
grep -q "LLM_MOCK: 'true'" docker-compose.test.yml     # R7 guard
! grep -q 'env_file' docker-compose.test.yml           # the real .env must never reach the test stack
grep -q 'tmpfs' docker-compose.test.yml                # fresh DB per run, or specs inherit state
docker compose -f docker-compose.test.yml run --rm playwright
docker compose -f docker-compose.test.yml down
```
Scenarios, one spec file each: fresh start (10 default tickers, `$10,000.00`, at least one
price changes within 10 s); add and remove a ticker; buy (cash decreases by
`qty × fill_price`, position row appears); sell (cash increases, row updates or disappears);
heatmap and P&L chart render with data; mocked chat executes a trade appearing inline as a
`filled` chip, and a too-large trade appears as a `rejected` chip with its reason; and
connection resilience — stream refused → indicator is `disconnected|reconnecting`, then
allowed → `connected` **and prices resume changing** (recovery means data resumed, not
merely that a socket reopened).

Two things the compose file's own comments should carry, both learned the hard way in the
sibling build: the app service must **not** be named `app` (`.app` is HSTS-preloaded, Chrome
force-upgrades `http://app:8000` to HTTPS and the suite dies with `ERR_SSL_PROTOCOL_ERROR`),
and a `tmpfs` mount needs explicit `uid`/`gid` or the non-root runtime user cannot create
the SQLite file. Playwright's image tag must match the pinned `@playwright/test` version
exactly.

Specs run serially (`workers: 1`) — they mutate one shared SQLite database, so parallelism
is a correctness bug, not a tuning knob.

The suite also writes full-page screenshots at 1920×1080 and 1024×768 into
`test/screenshots/`. These are not asserted on; they are the artifact that carries §2's
visual criteria to a human.

**GD4 — documentation parity.** *Proves AC-DOCS.*
```bash
cd $RR
comm -23 <(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort) \
         <(grep -oE '\b[A-Z_]{4,}\b' README.md | sort -u)   # must print nothing
```
*Claim:* all **six** variables (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
`MASSIVE_API_KEY`, `MASSIVE_POLL_SECONDS`, `ALLOWED_HOSTS`, `LLM_MOCK`) are documented. D9,
D24 and CP18 each added variables beyond spec §5's three, so this is live drift risk rather
than formality — and this claim itself said "five" from CP18 until CP21, while the command
below kept passing correctly. GD9 now pins the count.

**GD5 — full sweep.** `make check` (backend pytest + mypy + flake8 + black/isort --check;
frontend vitest + tsc + eslint) plus `uv run pylint src`, then re-run A1. The final gate
re-runs the secret check because the repo now has many more commits than at CP0.

## External signals

| Signal | Where | What it tells you |
| --- | --- | --- |
| Uvicorn startup log | stdout / `docker logs finally` | Init order (DDL → producer → snapshot task), which market source was selected, and which LLM path is active. Fastest runtime confirmation of D13's env-driven selection. |
| Producer restart warnings | app log | The lifespan wrapper caught and restarted a crashed producer. Any occurrence during a verify run is a finding, not noise — a silently dead producer looks exactly like a quiet market. |
| Massive auth failure log | app log | D13 requires this loud and with no fallback. Only observable if a key is ever supplied — see Cannot be verified. |
| SQLite file | `docker run --rm -v finally-data:/db alpine ls -l /db` | `finally.db` plus `-wal`/`-shm` companions confirms WAL is live in the container, not just in tests. |
| Playwright HTML report, traces, videos | `test/playwright-report/`, `test/test-results/` | Post-mortem for E2E failures; `trace: retain-on-failure` makes a flake diagnosable rather than merely re-runnable. |
| Playwright screenshots | `test/screenshots/` | The only artifact that carries §2's Visual Design criteria to a human reviewer. |
| `build-log.md` | run dir | Holds the three artifacts no automated check can: the CP2 live-spike raw response, and the recorded failures of the A8 and B2 mutation demonstrations. |
| `docker volume inspect finally-data` | host | Proves `stop_mac.sh` preserved the volume. |

## Risk-based expansion

Default is the narrow gate for the checkpoint in hand. Broaden when a trigger fires — these
are the shared-contract and shared-state surfaces where a local change has non-local
consequences.

| Trigger | Expand to |
| --- | --- |
| Any change to `db/connection.py`, `transaction()`, or a service function that writes | Full backend suite **plus B2 concurrency**, 10 rounds. Transaction-boundary regressions present as flakes and get "fixed" by retries. |
| Any change to the `Quote` TypedDict, the SSE frame body, or `session_open` handling | A13 **and** C3 **and** C4 together. The one contract spanning both halves; changing it in Python and not in TypeScript is silent until a user reads a wrong percentage. |
| Any change to `market/simulator.py` constants or the step function | A8, A9, A11 as a set. All three are coupled through `dt`; changing the tick interval alone invalidates the shock-rate conversion. |
| Any change to `main.py` mount order, `next.config.ts`, `trailingSlash`, or `basePath` | C1 in full, including the unknown-`/api/*` 404 assertion, and re-run GD3 before shipping. R3 is the failure that works in `npm run dev`. |
| Any change to `llm/schema.py`, `llm/client.py`, or the system prompt | A4 **and** B5. Never A5 — the live spike is one-shot; a schema change is re-validated against recorded fixtures, not against the credit card. |
| Any change to `Dockerfile`, `.dockerignore`, `uv.lock`, or `package-lock.json` | GD1, GD2, GD3 in full. A lockfile change invalidates the `uv sync --frozen` reproducibility claim. |
| A change to `OPENROUTER_MODEL` in `.env` | B5 under mock, then a **single** deliberate live turn recorded in `build-log.md`. Structured-output support is per-model (D10), so CP2's finding does not transfer. |
| Any E2E flake | Re-run once with the trace; if it recurs, treat as a product bug. Do **not** raise `retries` — the serial `workers: 1` configuration exists because shared SQLite state makes retries hide real races. |
| Two consecutive gates with no new failing check | Sanity-check the harness itself: temporarily break one assertion per suite and confirm it reports red. |

## Cannot be verified

Stated up front so nobody reads a green gate as covering these.

1. **The Massive real-market-data path (R6).** `MASSIVE_API_KEY` is empty and the prior
   account returned 403 `NOT_AUTHORIZED` on `/v2/snapshot`. Verifiable here: source
   selection from the env var, fixture-level parsing into a `Quote`, Protocol conformance
   via mypy (all in A12). **Not** verifiable: real response shapes, poll cadence against
   real rate limits, 429/5xx backoff behaviour, and D13's "loud logs, no silent fallback"
   under an actual auth failure. No check licenses a claim that this path works.
2. **LLM output quality.** A4 and B5 prove the client *parses* and the orchestrator
   *executes and rejects* correctly. Nothing proves the assistant's analysis is useful, its
   trade suggestions sensible, or its prose good. Whether `openai/gpt-oss-120b` honours
   strict `json_schema` is a **single observation** at CP2 (A5), not a repeatable check —
   the answer can change with OpenRouter's routing, which is why the tolerant parser exists.
3. **SSE reconnection after an established stream drops.** GD3 covers refused-then-allowed.
   It cannot cover a healthy connection severed mid-session: `context.setOffline()` leaves
   an established SSE stream running, `route.abort()` affects only new requests, and
   `route.fulfill()` cannot hold a stream open. Severing a live stream requires restarting
   the server, outside the Playwright container's reach. Record in `test/README.md` rather
   than papering over it.
4. **Visual and aesthetic quality (§2).** "Bloomberg-like", "data-dense", "every pixel earns
   its place", "subtle animations that fade", palette harmony — no automated check asserts
   any of it. C8 proves tokens exist; C4 proves a class is added and removed. The perceived
   result requires a human looking at a screenshot, and there is no browser on this machine
   outside the Playwright container.
5. **`scripts/start_windows.ps1` at runtime.** CP22 gave it the same four branches as
   `start_mac.sh` and the same `status=running` filter it had been missing for the whole
   project, and the file **parses** — run through
   `[System.Management.Automation.Language.Parser]::ParseFile` in a container, not read by
   eye. Both `start_windows.ps1` and `stop_windows.ps1` come back clean. What is *not*
   verified is that it behaves: no case has been executed, on Windows or anywhere. GD10 tests
   the mac script only.

   This matters more than it did before CP22, and that is the reason it is listed here rather
   than in a paragraph under GD10. The README's recipe now tells a Windows reader that
   `.\scripts\start_windows.ps1 --build` will restart a stale container — a user-facing promise
   backed by a branch nothing has run. CP21's stop-then-start recipe made no such promise.

   **The parser was pwsh 7.4.2, not Windows PowerShell 5.1**, which is what most Windows
   users actually have — so even the parse covers the wrong runtime, and the hazard below is
   specific to the one it did not cover.

   Two PowerShell-specific hazards are unresolved because parsing cannot see them: with
   `$ErrorActionPreference = 'Stop'`, a native command writing to stderr under `2>$null` can
   raise a terminating `NativeCommandError` in Windows PowerShell 5.1 rather than yielding
   empty — which would affect both the new `docker inspect` calls and the pre-existing
   `docker image inspect $Image *> $null` on the first-run path.

   The honest claim is **mirrored, and parsed under 7.4.2 — not tested, and not parsed under 5.1.** This file has claimed to mirror
   the mac script before while missing a load-bearing filter for the entire project, so
   structural checking has a poor record here specifically.

5. **Responsive behaviour on real tablets.** A viewport smoke at 1024×768 can assert no
   horizontal overflow and that the chat panel collapses; "functional on tablet" as the spec
   means it is a judgment call on a device nobody here has.
6. **Cross-browser behaviour.** Chromium only. `EventSource` retry timing differs across
   engines; Safari and Firefox are untested.
7. **The Windows PowerShell scripts.** `start_windows.ps1` / `stop_windows.ps1` cannot run on
   darwin. Reviewable by reading against their bash counterparts, nothing more.
8. **Long-run behaviour.** Ring-buffer memory over hours (D17/D22), SSE generator leaks
   across hundreds of connect/disconnect cycles, snapshot-table growth, and float drift over
   thousands of trades (D8). A13 proves one generator unwinds; sustained load is not tested.
9. **Multi-tab and multi-user.** Single-process by construction (D2). Two tabs are cheap to
   open manually; nothing verifies correctness under concurrent browsers, and horizontal
   scaling is explicitly out of scope.
10. **Deployment beyond the local container.** No CI, no deployed instance, no App
    Runner/Terraform (§11 stretch goal). GD1/GD2 prove the image runs on *this* Docker
    Desktop; host behaviour differs elsewhere.
11. **Simulator realism.** Deliberately unrealistic by D23 (σ ≈ 1.5–2.5 annualized). There is
    no "correct" to verify against — only internal consistency, which A8/A9/A11 cover.
    Anyone reading simulated volatility as market-realistic is misled, which is why D13
    refuses to fall back to it.

## Checkpoint 19 additions — the advisories

Five checks added when the review's 13 advisories were fixed. Each is here because it fails
when its fix is reverted; that was demonstrated rather than assumed, and the failure message
is recorded beside each one.

**A14 — the chat rate limit.** *Proves the spend limit exists and forgives.*

> Numbered A14, not A9. The first version of this section collided with the
> existing **A9 — shock rate is per minute** (D23), and the coupling table below
> routes any change to `market/simulator.py` to "A8, A9, A11 as a set" — which
> CP19 changed. Someone following that row would have run the rate limiter
> against a simulator edit and concluded the simulator was covered.
```bash
cd $RR/backend
uv run pytest tests/test_ratelimit.py -q
```
Every `POST /api/chat` is one billed completion, and it is the only route in the application
with that property. The clock is injected throughout: a limiter tested by sleeping can only
be watched *refuse*, because proving that it forgives would cost a real minute per assertion
— so in practice nobody writes that half and the refill arithmetic ships unproven. Eight
cases: the burst is allowed and the next call is not; the advertised `Retry-After` is checked
from **both** sides (one tick short is still refused, at the advertised wait it is allowed);
tokens return one at a time; an idle hour does not bank a thousand completions; a clock that
runs backwards mints nothing; the endpoint answers 429 with the header; a refused turn is
**not** persisted; and two apps do not share a bucket. *Mutation:* capacity → 10⁹ ⇒ three
failures, `assert 200 == 429` among them.

**B8 — the seed is one transaction.** *Proves `ensure_initialized` is what it says.*
```bash
cd $RR/backend
uv run pytest tests/test_db_init.py -q -k seed
```
`executescript` issues an implicit COMMIT before it runs, so the old single-transaction
wrapper was already gone by the time the DDL executed and `_seed` ran in **autocommit**.
`new_id` is the lever because of where it sits — the profile INSERT does not call it, the
watchlist INSERT calls it once per ticker — so raising there interrupts the seed in the only
window the bug lived in. *Mutation:* restore the single wrapper ⇒ `assert 1 == 0`, the
profile row surviving a failed seed.

**B9 — a dust buy writes nothing.** *Proves the trade log has no orphan fills.*
```bash
cd $RR/backend
uv run pytest tests/test_portfolio.py -q -k dust
```
`1e-12` is finite and positive, so `_valid_quantity` passes it; `_write_position` then deletes
any position at or below `DUST_TOLERANCE`. The result was a row in the immutable log, cash
moved by `0.0`, and no position. Asserted against the tables rather than the return value,
because the return value was always plausible — it reported a fill, and the log agreed. The
second case is the one that stops this narrowing into "reject small orders": `1e-12` on top of
ten held shares still fills. *Mutation:* drop the guard ⇒ `DID NOT RAISE DustQuantity`.

**B10 — a 503 leaves the transcript answered.** *Proves the orphan turn is closed.*
```bash
cd $RR/backend
uv run pytest tests/test_chat.py -q -k "answers_the_turn or providers_own_text"
```
The user's message is persisted before the model is called — it has to be, it is the prompt
history the next turn reads — so an error that simply propagated left a user row with no
assistant row: permanent, on every reload, and fed back into every later prompt as an exchange
where the assistant said nothing. With no key, which the README calls a working demo, every
message accumulated that way. Two assertions per case, and the second is the load-bearing one:
the transcript is answered **and the status is still 503**, because "answer the turn" is not
licence to turn an outage into a 200. The third case pins that the recorded reason is this
repository's sentence and never a provider's string. *Mutations:* remove the persist ⇒
`assert ['user'] == ['user', 'assistant']`; restore the interpolated exception ⇒ a fabricated
`sk-live-…` reaching the user-facing 503 detail.

**GD7 — the interactive docs are gone and the table replaced them.**

> There is no GD6 section in this file. CP18 added the event-loop check under
> that name and it lives in `backend/tests/test_event_loop.py`, but it was never
> transcribed here. Recorded so the gap is a known one rather than a reader's
> guess about a numbering mistake.
```bash
cd $RR/backend
uv run pytest tests/test_health.py -q -k "interactive_docs or api_still_answers"
grep -c '^| `GET` \| `POST` \| `DELETE`' $RR/README.md   # the endpoint table exists
```
`/docs` fetched Swagger UI from a CDN, on a floating tag, with no SRI, into an origin that
requires no authentication and holds a portfolio. Parametrized over all three paths rather
than `/docs` alone: removing only the UI while leaving `/openapi.json` would pass a one-path
check and still publish the surface. The second test is what stops the fix from being "break
the application" — `openapi_url=None` disables schema *generation*, not routing. *Mutation:*
restore `openapi_url` ⇒ three failures, `assert 200 == 404`.

**Also re-pointed:** A5's command. The spike moved to `backend/scripts/spike.py`, which the
`Dockerfile`'s `COPY backend/src` leaves out of the image. It is **still one-shot and still
spent** — moving it changes where it lives, not how many times it may run.

**Not falsifiable, and recorded as such:** `read_universe` importing `DEFAULT_USER_ID` instead
of the literal `"default"` is behaviourally identical by construction. There is no test that
can fail for it and none was written; `mypy --strict` and the existing producer tests are the
whole of its coverage. Writing a check that asserts `"default" == DEFAULT_USER_ID` would be
the ninth check in this run that cannot fail.

**GD8 — `make e2e` builds what it tests.** *Proves the suite cannot pass against stale code.*
```bash
cd $RR
make e2e 2>&1 | tee /tmp/e2e.log          # 2>&1: the build lines split across both streams
grep -c 'naming to docker.io/library/finally:e2e' /tmp/e2e.log   # must be >= 1
grep -c 'allowed hosts:' /tmp/e2e.log                            # the working tree reached the container
```
Three corrections the overseer made to this check's first draft, each of which would have
weakened it:

* **`2>&1` is required.** `Image finally:e2e Building` went to **stderr** and
  `naming to ...` to **stdout** in its run. A plain `| tee` captures half the evidence, and
  under `--progress=plain`, a non-TTY runner, or `DOCKER_BUILDKIT=0` the surviving branch can
  move too. It fails closed, but a check that can report absent on a good build is a check
  that gets deleted.
* **The `Building` alternative is dropped.** `make` echoes this recipe's own comment block into
  the same transcript, and that block is entirely *about* building. It is safe today only
  because no comment contains a capital-B "Building" — one future word like "Building only when
  the image is missing" and this check passes with zero builds. It would grep text the recipe
  itself prints. `naming to docker.io/library/finally:e2e` is emitted by BuildKit only on a
  real build.
* **The second grep asserts the property, not the proxy.** "A build step appeared" and "the
  container runs the working tree" coincide under `--build`, but only the second is what
  anyone cares about — and `allowed hosts:` is the exact line whose absence exposed the
  original defect, so it is the signal with a proven detection record.
`docker compose up` builds only when the image is **missing**. Once `finally:e2e` exists, the
target drives whatever was built last — and reports green on it. Three recorded "green" E2E
runs in this project were produced that way, one of which is retracted in `build-log.md`.

*Mutation, run in both directions on 2026-08-20 rather than reasoned about.* A marker line
(`CP20-REBUILD-PROBE-7f3a`) was added to `_log_startup_configuration`, `make e2e` was run, and
the container logged it — so the target does rebuild from the working tree. The marker was
then **deleted from the source** and the old recipe run:

| Recipe | build step in transcript | marker served by the container | suite |
| --- | --- | --- | --- |
| `up` (before) | **0** | **1** — a string that existed nowhere in the repository | 21 passed |
| `up --build` (after) | 2 | 0 | 21 passed |

The middle row is the whole finding: **a fully green 21-spec run against code that had been
deleted.** Not a weak assertion — 21 correct assertions pointed at the wrong artefact. That is
the failure mode this check exists to make impossible, and it is why the cost of a cache-hit
rebuild on every run is not worth arguing about.

**Related, and deliberately not fixed here:** `scripts/start_mac.sh` has the same shape — it
builds only when the image is missing or `--build` is passed. For a start script that is a
defensible trade and its own comment says so. It still means `git pull && ./scripts/start_mac.sh`
silently runs the old code, which is exactly how a pre-CP18 image ended up serving this
machine on 2026-08-20. Recorded as an advisory in the verify run's `findings.json`.

**GD9 — the README's prose keeps up with the code.** *Proves the docs half of AC-DOCS that
GD4 cannot reach.*
```bash
cd $RR
n=$(grep -cE '^[A-Z_]+=' .env.example)
word=$(python3 -c "print('zero one two three four five six seven eight nine ten'.split()[$n])")

# (a) the count sentence. Two failure modes, distinguished, because a red with a
#     mystery cause is the red that gets deleted.
said=$(grep -oE 'All (one|two|three|four|five|six|seven|eight|nine|ten) are optional' README.md)
if   [ -z "$said" ];                        then echo "FAIL: the count sentence was reworded — restore it or update GD9"; exit 1
elif [ "$said" != "All $word are optional" ]; then echo "FAIL: README says '$said', .env.example has $n"; exit 1
else echo "PASS: the count claim matches .env.example"; fi

# (b) the rebuild recipe, anchored on the WHOLE command rather than on `--build`.
grep -q './scripts/start_mac.sh --build' README.md \
  || { echo "FAIL: the Quickstart does not carry the rebuild recipe"; exit 1; }
echo "PASS: the rebuild recipe is documented"

# (c) the reset note. PLAN.md makes this a CP17 deliverable and DESIGN.md says
#     "the README must say so"; it is also the only warning in the file about
#     the one command that destroys a portfolio.
grep -q 'docker volume rm finally-data' README.md \
  || { echo "FAIL: the README no longer says how to reset the portfolio"; exit 1; }
grep -q 'docker compose down -v' README.md \
  || { echo "FAIL: the README no longer warns that down -v removes the volume"; exit 1; }
echo "PASS: the reset note and the down -v warning survive"
```

**Assertion (b) was rejected in its first form, and the rejection is the argument for the
current one.** It read `grep -q -- '--build' README.md` — the string, anywhere in the file.
That is green today and was green over an instruction that **did not work**: the first draft
of this checkpoint told the reader to run `./scripts/start_mac.sh --build`, and the script
builds the image *before* it checks whether a container is already running. On a machine where
the app is up, that rebuilds, prints `FinAlly is already running`, exits 0, and keeps serving
the old container. A fresh image and stale code, with a reassuring message.

So the check certified a remedy that made the situation worse than the undocumented trap: the
reader now believes they are protected. A two-character needle cannot tell a correct recipe
from an incorrect one, which is the whole lesson — **anchor on the command, not on the flag.**

`|| exit 1` on both, because `grep -q ... && echo PASS` never exits non-zero: a failing first
assertion would silently print one PASS instead of two, and a half-red run would read as green
to anyone skimming.

**GD4 was never wrong; the sentence beside it was.** GD4 diffs variable *names*, so when CP18
added `ALLOWED_HOSTS` and put it in the configuration table, GD4 kept passing — while
`README.md` went on saying "All five are optional" for three checkpoints, and `config.py`'s
own comment said "the five in .env.example". A check that is right next to prose that is wrong
is worse than no check, because the green is what people look at.


**(b) changed at CP22, because the recipe it pinned stopped being the right one.** CP21 had to
document `stop_mac.sh && start_mac.sh --build`, since `--build` alone rebuilt the image and
then left the old container serving. CP22 fixed the script, so `--build` alone is now correct
and the stop-first recipe would be cargo cult. A check that pins a workaround outlives the
workaround unless someone moves it — this is that move, and **GD10 is what makes it safe**: the
recipe in the README is only trustworthy because GD10 proves the script behaves that way.
Weakening (b) without GD10 in place would have been the trade this project keeps refusing.

**Assertion (c) exists because a plan-mandated section disappeared under a fully green gate.**
While fixing the two blockers above, a slice-based edit rewrote everything between the new
blockquote and `## Configuration` — and that span contained `### Resetting the portfolio`
(`docker volume rm finally-data`, "Nothing else removes it", and the warning that
`docker compose down -v` **will**) plus the paragraph explaining that the app runs with no
`.env` at all. Nine net lines, deleted silently.

Nothing caught it. GD4 was silent, GD9's own (a) and (b) both printed PASS, and `make check`
was green — because every check pointed at variable names and at the sentence being added, and
none at the text being replaced. `PLAN.md` makes the reset note a CP17 deliverable and
`DESIGN.md` says "the README must say so or users will be confused when a rebuild keeps their
old positions". The irony is exact: the commit was *adding* a rebuild instruction while
deleting the paragraph that explains what a rebuild keeps.

So (c) pins the highest-consequence paragraph in the file — the only place that names the one
command in this repository capable of destroying a real portfolio.

*Mutation, run rather than argued:* adding a seventh line to `.env.example` makes (a) fail;
deleting the blockquote from the README makes (b) fail; and **weakening (b) back to a bare
`--build` needle makes it pass over the broken recipe**, which is how the loose version was
caught. All three were watched before this check was kept.

**What this check cannot do, stated because the gap is the point.** It asserts that a sentence
exists, not that anyone reads it. The trap it documents — `./scripts/start_mac.sh` after a
`git pull` silently serving the previous build — is *prevented* by nothing. CP20 could fix its
equivalent because `make e2e` can afford to rebuild every run; a start script cannot, so the
defence here is a paragraph. The strong version is a staleness warning in `start_mac.sh`
comparing the image's creation time against the newest source mtime; it is not built, because
that script starts a live container holding a real portfolio and the change was offered rather
than assumed. **Discoverability, not prevention** — and a verification plan that let that pass
unsaid would be doing the same thing this project keeps catching itself doing.

**GD10 — the start scripts do not report success over a no-op.** *Proves the stale-image trap
is closed, not merely documented.*
```bash
cd $RR
./test/checks/gd10_start_scripts.sh    # exits non-zero on any failure
```
**Committed as a script, not described in prose.** The first version of this check lived only
as a paragraph, and the overseer had to reconstruct the stub from it in order to verify CP22 —
which is the state a check drifts from, and this project has recorded eleven cases of exactly
that. The stub is **stateful**: `docker rm` makes subsequent `ps` calls return nothing, because
a stub where removal does nothing makes the script's later corpse-check fire a second `rm`, and
the count then measures the stub rather than the script. The first version of the committed
file asserted `rm=1`, observed `rm=2`, and was wrong about which of the two was at fault.
Four cases, each asserted on output **and** on which docker verbs were invoked:

| Case | Expected | Observed |
| --- | --- | --- |
| running + `--build` + **different** image | recreate | prints both IDs, `docker rm` then `docker run` |
| running + `--build` + **same** image | do nothing | "already running … and it is the current image"; **no `rm`, no `run`** |
| running, **no** `--build` | historic no-op, plus a note | "already running", names the newer image, tells you the flag; no `rm`, no `run` |
| not running | unchanged start path | `docker run`, no `rm` |

Case 2 is the one that keeps this honest. Identity is compared, not timestamps: a rebuild that
is a pure cache hit legitimately produces the same image ID and there is nothing to do. A
"created at" comparison would restart the container on every `--build`, which is how a correct
guard becomes one people route around.

*Mutation:* restore the unconditional early exit — the shape shipped up to CP21 — and case 1
prints "FinAlly is already running" with **zero** `rm` and **zero** `run` calls, having just
built a new image. That is the original defect reproduced on demand. Note that the mutant is
**syntactically valid**, and `bash -n` accepts it: this project has already shipped one start
script that `bash -n` approved and `docker` rejected, which is why GD10 executes the script
instead of parsing it.

**Also run for real, against the actual Docker daemon.** The stub proves the branching; it
cannot prove that `docker inspect --format '{{.Image}}'` and
`docker image inspect --format '{{.Id}}'` return comparable values, which is the load-bearing
assumption of the whole fix. So the three reachable cases were run live using the
`IMAGE`/`CONTAINER`/`VOLUME`/`PORT` overrides CP15 added for exactly this — a verification run
beside the user's container rather than on top of it:

| Live case | Observed |
| --- | --- |
| container on an old image, then `--build` | `running: sha256:de6136ee…` / `built: sha256:067bbc19…`, restarted, and the container afterwards **is** the new id |
| `--build` again, cache hit | "already running … and it is the current image"; container id **and `StartedAt` both unchanged** — it genuinely did not restart |
| no `--build`, container behind | the note, and no action |

Asserting on `StartedAt` rather than on the message is the point of case 2: a script that
printed the right sentence and restarted anyway would pass a message-only check.

Cleanup was `finally-gd10` / `finally-gd10-data` / `finally:gd10` only, verified before and
after — `finally` and `finally-data` untouched, and the portfolio read back intact. Getting
this wrong is not hypothetical: check GD1's literal command once pointed `-v finally-data` at a
live portfolio, and only a port conflict stopped it.

**Not verifiable here, and recorded rather than glossed:** `scripts/start_windows.ps1` carries
the same four branches — checked structurally, marker by marker — but no PowerShell is
installed on this machine, so it has been neither parsed nor executed. The mac script is
tested; the Windows one is *mirrored*, which is a weaker claim, and the file's header has
claimed a mirror before while missing the `status=running` filter for the whole project.
