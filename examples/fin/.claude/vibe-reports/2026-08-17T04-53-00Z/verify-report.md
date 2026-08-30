# Verify report — Gate D (end of Phase D)

Phase D: checkpoints 15, 16, 17 — all built and overseer-approved, two of the three on the
first pass. Build run: `.claude/vibe-reports/2026-08-13T23-18-51Z/`. HEAD at verify: 95
commits.

## Passed

| Check | Result |
| --- | --- |
| **GD1** image builds, serves, does not bake `db/` | `/app/db` **0 entries** in the image; `/` serves the stage-1 shell; `/api/health`, `/api/portfolio`, `/api/watchlist` 200 JSON; `/api/nope` **404 `application/json`**; container reports `healthy` |
| **GD2** persistence and script idempotency | A 2-share MSFT buy survived `stop` + `rm` + a fresh `run` on the same volume — cash 9,177.54 and the position came back. `start` twice leaves exactly one container and says so; `stop` removes the container, **keeps the volume**, and is idempotent |
| **GD3** E2E suite | Three compose guards pass verbatim (`LLM_MOCK: 'true'`, no env-file directive, `tmpfs`); **21 specs pass from a cold compose** in ~22 s; screenshots written at both viewports |
| **GD4** documentation parity | `comm` prints nothing. **Demonstrated failing** at CP17: a README with one variable stripped makes it print exactly that variable |
| **GD5** full sweep | `make check` green — **234 backend tests**, `mypy --strict` over 31 files, flake8, black, isort, **pylint 10.00/10**; **174 frontend tests**, `tsc --noEmit`, `eslint`. Plus **A1 re-run over 95 commits**: `.env` ignored and never committed, shape scan and value scan both clean over every blob, and the **positive control** finds `SPEC.md` — so the silence means something |

**Verdict: Phase D passes.**

## What this gate found that the checkpoints did not

**The `000` mystery, finally explained.** Twice in Phase D a `curl` against a freshly started
container returned `000` while the container was healthy. At CP15 I explained it as
`localhost` resolving to IPv6 first — the overseer disproved that, and I withdrew it. The
actual cause, observed here: **Docker's port proxy accepts the connection before the
application is listening**, so `curl` gets a connection *reset* rather than a *refusal*, and
`--retry-connrefused` does not cover a reset. `--retry-all-errors` does, and every check in
this gate uses it.

Worth recording because the wrong explanation survived one review and would have been handed
to CP16 as fact. The right one is testable and the wrong one was not.

## What Phase D cost

Three checkpoints, **one rejection** — the quietest phase in the run, and the reason is that
the demonstrations were built into the work rather than added afterwards.

The single rejection (CP16) was instructive: **GD3's own guard was defeated by the file it
guards.** `! grep -q 'env_file'` failed because the comment explaining why there was no such
directive contained the word. A check that cries wolf on a correct file gets switched off, and
switched-off checks are how a repository ends up with a green board and a broken product.

The near-miss is also on the record: **GD1's command, written literally, points at the user's
live data.** `-v finally-data:/app/db -p 8000:8000` is correct on a clean machine and
catastrophic on one where the app is already running. Only a port conflict stopped a test
trade from landing in a real portfolio. Every script now takes its image, container, volume
and port from the environment, and the plan's check text is anchored.

## Coverage gaps

Carried into `review` rather than hidden:

1. **The mid-session SSE reconnect is untested end to end.** `07-resilience` covers
   refused-then-allowed; cutting a *live* stream is not stageable from Playwright
   (`setOffline` leaves an established EventSource running; `route.abort` affects only
   requests not yet made). Covered by unit tests over `readyState` and by nothing in a
   browser. Recorded in `test/README.md`.
2. **The PowerShell scripts have never been executed** — not here, not anywhere. They cannot
   run on this platform. Read line by line against the shell pair, and two divergences were
   fixed that way, but "reviewed" is not "run".
3. **The Massive real-data path has never run against the live API** (R6, unchanged since
   Gate A). Written against the documented response shape and tested against recorded
   fixtures only.
4. **Three browser-only CSS invariants** are pinned by nothing: `pointer-events-none` on the
   flash overlay, `relative` on the row, and the treemap's responsiveness. jsdom does no hit
   testing and no layout, and the E2E does not assert geometry.
5. **The screenshots are compared to nothing.** No visual baseline; a layout that breaks
   silently keeps passing.
6. **No multi-user coverage** and **one browser** (Chromium), both unchanged.

## Not run

- **A5, the live structured-output spike.** One billable call, spent at CP2. The run-wide
  condition held: no second live call was ever made.

## Findings

No blockers, no risks. The advisory conditions accumulated across the run are in
`.claude/vibe-reports/2026-08-13T23-18-51Z/state.json` under `open_conditions`.

## Verdict

**PASS.** The application builds to one image, starts with one command, keeps a portfolio
across restarts, refuses to destroy it, and proves itself from a browser in 21 specs against
the real container.

Next: **`review`** — the last mode in the pipeline, and the only one that has not yet looked
at this code with fresh eyes.
