# Checklist: FinAlly — AI Trading Workstation

Ticked by `build` as evidence lands. Never pre-tick. Check ids (A1, B2, GD3…) refer to
`verification-plan.md`. Three lines carry a **demo** marker: the guarding check must be
seen to fail against a local mutation, recorded in `build-log.md`, then reverted.

## Phase A: Prove the unknowns
- [x] 0. Repo hygiene and safety — verify: A1 (`.env*` ignored, absent from all commits, no key in any blob)
- [x] 1. Backend skeleton — verify: A2, A3 (pytest/mypy/flake8/black/isort clean; `/api/health` 200)
- [x] 2. LLM client + live structured-output spike — verify: A4, A5 (parser table; raw spike response in `build-log.md`)
- [x] 3. Database layer — verify: A6, A7 (idempotent init, WAL, schema inventory, no stored price column)
- [x] 4. Price cache, simulator, producer — verify: A8 **demo**, A9, A10, A11
- [x] 4b. Market source selection + Massive client — verify: A12 (factory both ways, no fallback; fixture parsing)
- [x] 5. SSE endpoint — verify: A13 (snapshot-then-changes-only, heartbeats, clean unwind)
- [x] Phase boundary — run `verify` — **PASS**, 2026-08-14T21-13-12Z

## Phase B: Business logic
- [x] 6. Portfolio service and endpoints — verify: B1, B2 **demo**, B6
- [x] 7. Watchlist service and endpoints — verify: B3
- [x] 8. Snapshot task and history endpoint — verify: B4
- [x] 9. Chat orchestration — verify: B5, B7 (D5 sentinel, D6 200-with-rejected, cap, degradation, history; suite cannot bill)
- [x] Phase boundary — run `verify` — **PASS**, 2026-08-15T20-59-49Z

## Phase C: The workstation
- [x] 10. Frontend skeleton + static-export mount — verify: C1 **live**, C2 (every path that is `/api`
      or begins with `/api/` is JSON — ordering alone did not achieve this; see build-log)
- [x] 11. Live price surface — verify: C3 **demo** (swap to `previous_price` → `+0.01%`, 3 tests fail), C4
- [x] 12. Trading surface — verify: C5 (one refetch per fill, asserted through the page; the server's `detail` with inputs kept; `—` never `$0.00`)
- [x] 13. Visualizations — verify: C6, C8 (empty states; fill asserted on the prop, not the pixel; selection changes the series through the page)
- [x] 14. Chat panel — verify: C7 (loading indicator present-then-gone; `filled` **and** `rejected` both rendered; mount fires the transcript GET)
- [x] Phase boundary — run `verify` — **PASS**, 2026-08-16T21-57-48Z

## Phase D: Package & prove
- [x] 15. Container and scripts — verify: GD1, GD2 (empty `/app/db` in the image; a position survives stop + rm + re-run; `stop` keeps the volume — all three demonstrated failing first) (empty `/app/db` in image; volume survives `stop`)
- [x] 16. E2E suite — verify: GD3 (21 specs green from a cold compose; LLM_MOCK and tmpfs-ownership guards both demonstrated failing) (cold compose, `LLM_MOCK=true`, no `env_file`, screenshots captured)
- [x] 17. Documentation and `make check` — verify: GD4 (**demonstrated failing**), GD5 (`make check` green; A1 re-run clean over 94 commits with its positive control)
- [x] Phase boundary — `verify` **PASS**, 2026-08-17T04-53-00Z
- [x] `review` — **2 blockers, 5 risks, 13 advisories**, 2026-08-17T08-59-28Z

## Remediation (added after `review`, on the human's decision)
- [x] 18. Remediation — both blockers, both correctness risks, both network risks; each fix
      seen to fail without its guard. `make check` green, 21 E2E specs green
- [x] 19. The 13 advisories — 12 fixed, 1 recorded as D26; nine mutations each seen to fail.
      Rejected once (Touches list, an A9 collision, and a README table that stated a status
      code the code does not return); re-presented and approved. `make check` green (285
      backend, 173 frontend). E2E was Not-run at the time (Docker daemon down); it ran on
      2026-08-20 and passed — but only after CP20 forced the rebuild that made it meaningful.
- [x] 20. `make e2e` builds what it tests — verify: **GD8**, mutated in both directions (the
      old recipe served a marker deleted from the source and still reported 21 passed)
- [x] 21. The stale-image trap in the README, and "All five" when there were six — verify:
      **GD4**, **GD9** (three assertions, four mutations, each seen to fail). Rejected twice:
      the first remedy did not work, and the fix for it deleted a plan-mandated section.
      Discoverability, not prevention — the script fix is still open.
- [x] 22. Close the stale-image trap — verify: **GD10** (four cases against a stubbed `docker`,
      mutation reproduces the original defect), **GD9** re-anchored, **GD4**. Prevention, where
      CP21 was discoverability.

