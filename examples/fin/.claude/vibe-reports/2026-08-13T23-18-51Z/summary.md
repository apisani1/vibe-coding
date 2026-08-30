# Run summary

- Mode: plan
- Target: /Users/antonio/AI/MyCode/vibe-coding-course/fin (bare greenfield)
- Scope: FinAlly — AI trading workstation; phased build plan + verification plan for the
  full MVP
- Upstream run consumed: 2026-08-13T23-03-27Z (design.md, decisions.md)
- Sub-agents used: vibe-test-designer
- Artifacts: plan.md, checklist.md, verification-plan.md, summary.md, state.json
- Findings: n/a (plan mode emits no `findings.json`; the test designer's 8 findings were
  folded into the artifacts — see below)
- Next: `build` — **the only repo-mutating mode.** It requires explicit, written,
  action-specific approval before its first mutation ("Yes, implement checkpoint 0" — not
  "ok"), and re-confirmation when scope or risk changes.

## Shape of the plan

**19 checkpoints in 4 phases**, each phase ending in a `verify` gate.

| Phase | Checkpoints | Goal |
| --- | --- | --- |
| A — Prove the unknowns | 0, 1, 2, 3, 4, 4b, 5 | Every risky integration demonstrated; repo safe to commit |
| B — Business logic | 6–9 | All endpoints transactional and tested without network or browser |
| C — The workstation | 10–14 | The UI, running against the real backend |
| D — Package & prove | 15–17 | One command starts it; Playwright proves it |

Risky work is front-loaded on purpose: the LLM structured-output spike is **CP2**, not
CP14, because if `openai/gpt-oss-120b` ignores strict `json_schema` the chat contract has to
be re-cut before any component is written. Phases C and D are committed in outline only and
should be re-cut after Phase A's verify.

## Risk factors driving the sequencing

R1 model may not honor strict `json_schema` · R2 blocking `sqlite3` under a threadpool is a
*correctness* risk, not a perf one · R3 static export shadowing `/api/*` · R4 multi-stage
Docker build · R5 SSE has no cheap partial verification · R6 Massive path unverifiable here
· R7 live LLM calls cost money and `.env` has `LLM_MOCK=false` · R8 a live API key sits in
an un-gitted project root.

R8 is why CP0 exists and runs first.

## Test-designer review

`vibe-test-designer` drafted `verification-plan.md` and returned **8 findings: 0 blockers,
5 risk, 3 advisory**. All 8 folded in. The three that changed the plan's substance:

1. **A whole spec requirement had no owning checkpoint.** Nothing built `market/massive.py`,
   the `MASSIVE_POLL_SECONDS` handling, or the D13 source-selection factory — yet spec §5/§6
   make env-driven source selection *required behavior*. Added **CP4b**. R6 correctly says
   the live path can't be verified; that is not a reason to leave the code unwritten and
   unchecked.
2. **Two guard checks were unfailable as written.** The GBM Jensen-correction check cannot
   discriminate at production tick parameters — omitting `−σ²/2` shifts the price by a
   relative 1.7e-7, and rounding to 2 decimals erases it entirely. CP4 now *requires* a pure
   `gbm_step(price, mu, sigma, dt, z)` so the test can run at `σ=1, dt=1` where the expected
   mean log return is −0.5 versus 0.0, ~31 standard errors apart. Likewise B2: two sequential
   `execute_trade` calls on one thread pass under `BEGIN DEFERRED` and autocommit too, so the
   check now uses two threads on a `Barrier` with separate connections.
3. **Three checks must be demonstrated failing** (A8, B2, C3) against a local mutation that
   is never committed, with the observed failure recorded in `build-log.md`. A test guarding
   a subtle decision that has never been seen to fail is a comment.

Also folded in: `.gitignore` must use `.env*` with a `!.env.example` negation (a literal
`.env` misses the `.env.bak-massive` the copied file's own comment references) plus
`.DS_Store`; `LLM_MOCK=true` becomes the documented local-dev invocation, since R7's
mitigation covered the test stack but not a developer typing into the chat box; CP16's SSE
reconnection criterion narrows to refused-then-allowed (severing an established stream is
not stageable from Playwright); the E2E run captures screenshots as the only artifact that
can carry spec §2's visual criteria to a human; and CP17 adds a root `Makefile` with
`make check`, because there is no CI and nothing otherwise re-runs Phase A/B gates during
Phases C and D.

## What cannot be verified — declared now, not discovered later

The Massive live path (empty key, prior account got 403); LLM output *quality* as opposed to
parsing; SSE recovery after an established stream is severed; visual and aesthetic quality
(§2 carries real acceptance weight and no check can assert it — screenshots go to a human);
real-tablet responsiveness; non-Chromium browsers; the Windows PowerShell scripts on darwin;
long-run memory and float drift; multi-tab/multi-user; and anything beyond this Docker
Desktop. Full reasoning in `verification-plan.md § Cannot be verified`.

## Notes

- No CI exists or is planned, so every gate is a local invocation. `make check` (CP17) is
  the closest thing to a regression net.
- System python here is 3.10 — `uv` must pin 3.12 explicitly.
- The one sanctioned live LLM call in the entire plan is CP2's spike (check A5). Everything
  else runs under `LLM_MOCK=true`, and B7 asserts the suite passes with no API key present.
