# Verify report — Gate A (end of Phase A)

Phase A: checkpoints 0, 1, 2, 3, 4, 4b, 5 — all built and overseer-approved.
Build run: `.claude/vibe-reports/2026-08-13T23-18-51Z/`. HEAD at verify: 26 commits.

## Passed

| Check | Result |
| --- | --- |
| **A1** secret hygiene | `.env` ignored and untracked; no `.env*` other than `.env.example` in any commit; no `sk-…{8,}` credential shape in any blob; live key absent from all history; **positive control finds `SPEC.md`**, so the silence means something |
| **A2** static gates | 106 tests pass; `mypy --strict` clean over 23 files; flake8 clean; black/isort clean; **pylint 10.00/10** |
| **A3** app boots | `GET /api/health` → 200; unknown `/api/*` → **404**, not the HTML shell (R3 guard, pre-staged for CP10) |
| **A4** LLM parser table | 20 tests: clean JSON, fenced, prose-wrapped, malformed, schema-violating, empty, deeply-nested |
| **A6/A7** database | Live boot creates and seeds `db/finally.db`: **10 tickers, $10,000, `journal_mode=wal`**; idempotent; no table outside `trades` holds a price column |
| **A8** GBM Jensen correction | Demonstrated failing (mean −0.0045 vs required −0.5) then restored |
| **A9** shock rate | Counted through `advance()` over 24 simulated hours; discriminates 0 / 16 / 172,800 |
| **A10** `session_open` | Stamped once, never rewritten; `previous_price` moves every tick |
| **A11** correlation | Five seeds, shocks disabled; tech > 0.6, cross < 0.4, separation > 0.3 |
| **A12** source selection | Simulator on empty key, Massive on non-empty, **no fallback branch**; fixture parsing; per-entry guarding |
| **A13** SSE | First frame all 10 tickers with all six `Quote` keys; 80 data frames in 4 s; `text/event-stream`; frozen cache yields only heartbeats; heartbeat cadence guarded; clean cancel unwind |
| **B6** layering | No web-framework import below `api/` |
| **B7** cannot bill | 106 tests pass with `OPENROUTER_API_KEY` **and** `MASSIVE_API_KEY` unset |
| Clean shutdown | SIGTERM → `price producer stopping` → `Application shutdown complete` |

**Verdict: Phase A passes.** Every risk the phase existed to retire is retired.

## Not run

- **A5 — the live structured-output spike.** Deliberately excluded, on the overseer's Gate A
  condition. It is a one-time billable call, already spent at CP2, and the run-wide condition
  forbids a second. Its finding stands: `openai/gpt-oss-120b` **honours strict `json_schema`**,
  evidenced by the model's own `reasoning_content` showing it had planned a *different* schema
  (`{"orders", "watchlist"}`) that the enforced one overrode. Re-validated offline against
  recorded fixtures (20 tests).
- **A1's `git log --oneline | wc -l # expect 1`** — CP0-specific by construction. 26 commits at
  Gate A is not a failure.

## Coverage gaps

Honest gaps in what Phase A proves, beyond the standing "Cannot be verified" list:

1. **Heartbeat cadence was unguarded until this checkpoint.** The overseer's 18-mutant battery
   found `if True:` in place of the interval comparison left the suite green — a keepalive
   every tick would have shipped. Closed at CP5; noted because it was found by mutation, not
   by the check.
2. **Two equivalent mutants survive in A13** and are accepted: the `first` flag is
   behaviourally redundant (`last_sent` starts empty, so the else-branch resends everything
   one tick later), and price-vs-timestamp comparison is equivalent now that `cache.apply`
   skips unchanged prices. Both are docstring overclaims, not holes.
3. **Adversarial D13 evasion is unguarded and accepted**: fabrication laundered through
   `parse_snapshot`'s argument, or into `parse_snapshot` itself. Six review cycles closed every
   *plausible-developer* shape; these require deliberate laundering.
4. **No global pytest timeout.** An `httpx.ASGITransport` test against the endless SSE stream
   hung the suite past 400 s at CP5. Nothing else streams today, so the recurrence guard is
   missing rather than needed.
5. **`test_the_stream_never_writes_to_the_cache` copies only the outer dict**, so an in-place
   `quote["price"] = 0.0` does not fail it (caught incidentally by another test).

## External signals

- Startup log states both external paths on every boot: `market source: simulator (GBM)` /
  `llm: mock (no network calls, no cost)`. This is the observable half of the guard against
  unknowingly billed local development, and it only exists because the overseer found it
  silently discarded at CP1 — uvicorn leaves the root logger at WARNING.
- `db/finally.db` plus `-wal`/`-shm` companions confirm WAL at runtime, not only in tests.
- A stray uvicorn from a prior session was still listening on port 8123 running pre-CP5 code;
  killed before this run so the wire smoke could not hit stale code.

## Findings

No blockers, no risks. Advisory items are recorded in
`.claude/vibe-reports/2026-08-13T23-18-51Z/state.json` under `open_conditions` and carried
into Phase B and C:

- **CP6/B2**: widen the read–write window deliberately; `BEGIN DEFERRED` fails as
  `database is locked`, not as a double fill.
- **CP9**: import `MAX_ACTIONS_PER_RESPONSE` rather than re-literalling `10`; implement D25's
  `EmptyModelResponse` → **HTTP 200 with an apology**, not 503.
- **CP11**: do not read `direction` on an SSE *snapshot* frame as "moved on this frame" — it
  may be minutes old.
- **CP15**: install the runtime image with `--no-dev`; `WORKDIR /app`, volume at `/app/db`,
  and the non-root user must own it (`mkdir` succeeds, then writes fail).
- **Run-wide**: `timestamp` means time of last price *change*, not last observation.
- **Run-wide**: demonstrate every check that pins a subtle property failing, and re-grep after
  every claimed documentation fix.

## Verdict

**PASS.** Phase A retired R1 (the model honours strict `json_schema`), R2 (SQLite under a
threadpool, empirically validated by the overseer with barrier-synchronised threads), R5 (SSE
proven on the raw wire before any browser exists), and R8 (no secret in history, with a scan
proven able to find one). R6 stays open by design and is declared unverifiable.

Next: **Phase B** (checkpoints 6–9 — portfolio, watchlist, snapshots, chat orchestration).
`build` remains the only repo-mutating mode and continues under the `--auto` grant with
per-checkpoint overseer approval.
