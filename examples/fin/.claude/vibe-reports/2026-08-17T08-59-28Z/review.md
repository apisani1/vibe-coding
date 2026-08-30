# Review — FinAlly, the whole build

The last mode in the pipeline, and the first time anyone looked at this code with fresh eyes
rather than one checkpoint at a time. 18 checkpoints, 95 commits, 234 backend tests, 174
frontend tests, 21 E2E specs, `mypy --strict`, pylint 10.00/10 — all green, and **two
blockers**.

Sub-agents: `vibe-code-reviewer`, `vibe-security-auditor`. Both findings sets are merged into
`findings.json`. **Every blocker and risk below I reproduced myself before recording it** —
this run has too many examples of a confident claim that did not survive re-running.

**Verdict: not done. 2 blockers, 5 risks, 13 advisories.**

## The two blockers

Both are in the class this review was asked to hunt: **the tests pass, and the code carries a
comment asserting the opposite of what it does.**

### 1. `POST /api/chat` runs every database operation on the event loop

`services/chat.py`'s `handle_message` is `async def` and calls `_persist`, `_build_messages`
and `_run_actions` — all blocking `sqlite3` — with no `to_thread`. D21 exists to prevent
exactly this, and `api/chat.py`'s docstring claims it does not happen: *"the database work
underneath still runs in `services/` the same way (D21)."* It is the **`def`** handler that
buys Starlette's threadpool; this one is `async def`, so nothing does.

Measured against the real app with a 5 ms heartbeat and a 1-second stall injected at the cash
read:

| Path | Elapsed | Loop beats during it |
| --- | --- | --- |
| `POST /api/chat` (`async def` handler) | 1.04 s | **0** of ~208 |
| `POST /api/portfolio/trade` (`def` handler) | 1.02 s | 162 of ~203 |

Not degraded — **stopped**. Every SSE stream, the price producer and the snapshotter freeze
for the whole turn. And since `execute_trade` takes `BEGIN IMMEDIATE` behind a 5-second
`busy_timeout`, a chat turn contending with a manual trade can freeze the process for five
seconds. CP6's own concurrency check proves that contention is real.

No test could see it: the suite asserts outcomes, never responsiveness.

### 2. `buy 0 AAPL` under `LLM_MOCK=true` is an HTTP 500

`mock._quantity` returns `0.0`, `TradeAction`'s `gt=0` raises `ValidationError`, and the mock
branch of `handle_message` — unlike the live branch — has no `try`. Reproduced end to end. The
user's turn is already persisted, so it is orphaned in the transcript **and fed into every
later prompt**. `LLM_MOCK=true` is the mode the E2E suite, the screenshots and the documented
dev loop all run in.

Why 234 tests missed it is worth more than the bug:
`test_a_model_authored_bad_quantity_is_a_200_with_a_rejection` **is** parametrised over `0.0`
— but it builds the action with `TradeAction.model_construct(...)`, which skips validation, and
monkeypatches `mock.respond` out of existence. **The test named after the value never runs the
code that produces it.** That is the seventh check in this run that could not fail, and the
first one no human or agent caught until the final review.

## The five risks

1. **`get_portfolio` is not atomic** (`services/portfolio.py`). Cash and positions are two
   autocommit statements, so a trade committing between them returns a total that never
   existed — reproduced at `8,100.00` where the truth was `10,000.00`. `record_snapshot`
   twenty lines above identifies this exact hazard and closes it with a transaction. Same
   quantity, two paths, one guarded. It also feeds `render_context`, so the model can be handed
   a wrong total.
2. **`execute_trade` never validates `side`.** The one field whose only guard is a `Literal`
   in the Pydantic models the assistant does not construct — the precise arrangement this
   project's own rule #2 forbids. `_settle` has a `buy` branch and an `else`, so anything else
   executes as a sell. Unreachable today; identical in shape to the `quantity: -5` defect that
   already shipped once.
3. **The Massive key can reach the logs.** It travels as a URL query parameter, and the
   failure handler logs the raw `httpx` exception, whose message embeds the full URL. Dormant
   (the key is empty) but it would put a plaintext credential into `docker logs finally` — the
   command the start script tells users to run when something goes wrong.
4. **No Host-header validation.** `Host: evil.example.com` returns 200 (verified). DNS
   rebinding makes an attacker's page *same-origin*, so the correct absence of CORS is never
   consulted. Bounded loss — the portfolio is paper — except `/api/chat`, which spends real
   credits per call.
5. **The published port binds `0.0.0.0`.** Verified against the running container. A no-auth
   app is LAN-reachable by default, with no deliberate port-forward, and
   `restart: unless-stopped` brings it back after every reboot.

Risks 4 and 5 are two lines each: `TrustedHostMiddleware`, and `127.0.0.1:` on three publish
lines. Nothing a user does changes.

## What the review found that the process did not

The security audit went looking outside git and found the boundary was solid: the live key is
in exactly one file on disk, absent from all 470 blobs across 96 commits, absent from the
built frontend bundle (which contains no `process.env` reference at all), and absent from the
image, whose `/app/db` is empty, whose user is uid 10001 and which contains no `node`, no
`.env*`, no `.git`. Every SQL statement is parameterised; the only f-string reaching `execute`
is a `PRAGMA` taking an int-cast constant, because PRAGMA cannot take a bound parameter.

It then assumed the model was hostile and could not get past D5: `-5` and `1e400` die at both
layers; `side: "short"` dies at the `Literal`; `extra` fields die at `extra="forbid"`;
`"A'; DROP TABLE trades;--"` as a ticker is rejected **inside the service**, with all six
tables intact afterwards; 50 actions in one response fill 10 and record 40 rejections.

## What is worth keeping

The code reviewer's words, and I agree with them: *"with those two exceptions, the most
disciplined agent-built codebase I have reviewed."* Specifically —

- **`main._add_api_not_found`'s docstring** corrects its own plan, states what was *measured*
  rather than reasoned, names the two regressions it accepts, and carries the consequence
  forward to CP15's `HEALTHCHECK`.
- **The D5 property test** neutralises all three service functions and parameterises over
  quantity, because a previous bypass triggered only for `0 < q < 1`.
- **`test/docker-compose.test.yml` deliberately not writing the word its own guard greps for**,
  because a check that cries wolf gets switched off.
- **Three small pieces of dead API surface** are the entire speculative-generality budget spent
  across 18 checkpoints.

## Recommended next step

The blockers route back to `build`. Both fixes are small and neither touches architecture:
four `asyncio.to_thread` calls, and a clamp plus a `try`. The two network risks are two lines.
The two correctness risks — the atomic read and the `side` guard — are the same size.

That is a single remediation checkpoint. It is **beyond the 18 the plan contains**, so it needs
the human's decision rather than the autopilot's: the run's grant stops at a plan deviation.
