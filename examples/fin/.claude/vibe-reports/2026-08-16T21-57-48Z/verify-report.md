# Verify report — Gate C (end of Phase C)

Phase C: checkpoints 10, 11, 12, 13, 14 — all built and overseer-approved, at a cost of
**nine rejections**. Build run: `.claude/vibe-reports/2026-08-13T23-18-51Z/`. HEAD at verify:
82 commits.

## Passed

| Check | Result |
| --- | --- |
| **C1** static export does not shadow the API | Run live end-to-end from a clean `npm ci`: `/` serves the shell, `/api/health` 200, `/api/portfolio` and `/api/watchlist` 200, the built page chunk 200 — **and `/api` and `/api/definitely-not-a-route` both return `application/json` 404s**. Ordering alone never achieved that last one (see below) |
| **C2** frontend unit gates | **174 tests**, `tsc --noEmit` clean, `eslint` clean, `npm run build` exports |
| **C3** change % from `session_open` | 39 tests. The discriminating fixture `{session_open: 100, previous_price: 199.99, price: 200}` renders `+100.00%`; **demonstrated failing** at CP11 (a `previous_price` implementation renders `+0.01%` — 3 tests fail) |
| **C4** flash lifecycle, status dot, degenerate sparkline | 50 tests. Flash asserts the add **and** the removal, and a second move in the same direction restarts it — element identity, not the class; `connected` is impossible before the server accepts; sparkline renders a baseline for 0, 1 and all-equal points |
| **C5** trading surface | 15 tests. Exactly one account refetch per fill (asserted **through the page**, not in halves); a 400 renders the server's `detail` with the inputs kept; six columns and `—` — never `$0.00`, never `NaN` — for an unpriced position |
| **C6** visualizations | 30 tests. Empty states for an empty portfolio; the heatmap fill asserted as the **prop** (green above `avg_cost`, red below, a ramp rather than a flag, neutral when unpriced); clicking a watchlist row changes the series identity through the page's own context |
| **C7** chat panel | 21 tests. Loading indicator present while in flight (gated) and gone after; a `filled` action renders its fill price **and** a `rejected` one renders the server's reason; mounting fires `GET /api/chat/messages` |
| **C8** theme tokens | All four palette greps hit `tailwind.config.ts` |

**Verdict: Phase C passes.**

## The four things per-checkpoint review could not reach

Carried out of the CP14 approval, run as probes in a scratch copy — never written into the
repo, since `verify` does not mutate code.

### 1. The stream's key-set is watchlist ∪ open positions — PASS, after the probe was fixed

`forget` correctness is now split across `useWatchlist.remove` and `refresh`, and no
checkpoint test exercises both on one tree. The probe removes a ticker manually and a second
one **through the assistant**, with each selected at the time, and asserts a held-but-unwatched
symbol keeps its price (D3).

**My first version of this probe could not fail.** It asserted that rows disappeared — but
rows are gated by membership, so their absence proves nothing about the client maps.
Deleting the forget diff left it green. Selection is the only window onto those maps: the
rewritten probe asserts the chart clears, and it dies without the diff.

### 2. Request-count discipline per user action — PASS

One fill produces exactly **one** account refetch, **one** history refetch, and **zero**
watchlist reads, with exactly one `EventSource` at rest. Falsified by firing `onFilled` twice.

### 3. Three generation guards under one mount — PASS, after the probe was fixed

`useChat`, `useWatchlist` and `usePortfolio` each carry a generation guard; all were tested
alone. The probe gates the transcript load, then sends a chat turn **and** adds a ticker
inside that window.

**This probe could not fail either, at first** — with every request settling in one flush
there is no window and no race. With the load gated it now dies two ways: removing `useChat`'s
generation claim loses the sent message, and dropping the superseded load instead of merging
it loses the stored history.

### 4. A frontend path against the real app — PASS

Every frontend assertion to date runs against `src/test/api.tsx` fixtures, so field-name drift
would first surface in CP16's E2E. This check boots the real FastAPI app, exercises
`/api/watchlist`, `/api/portfolio/trade`, `/api/portfolio`, `/api/portfolio/history`,
`/api/chat` and `/api/chat/messages`, and compares **every key of every payload** against the
interfaces in `lib/types.ts`.

**Zero mismatches.** The only fields declared-but-absent are `ChatAction.action` and
`ChatAction.reason`, which are genuinely optional — a filled trade has no reason, and a trade
has no watchlist action.

## What Phase C cost, honestly

Five checkpoints, **nine rejections** — more than Phases A and B together. Four of them were
mine to have caught before submitting, and the pattern is the same each time.

### The defects that reached a reviewer

1. **CP12 — a quote is not a membership claim.** The watchlist took membership from the union
   of `GET /api/watchlist` and the streamed tickers. A removed ticker came back on the next
   frame and could not be removed again. Not a race: the producer prices watchlist ∪ open
   positions (D3), so held symbols stream forever after being unwatched, and `PriceCache`
   never evicts while the SSE endpoint opens every connection with a full snapshot.
2. **CP13 — a refetch keyed on the one number a fill never moves.** Orders fill at the mark,
   so cash falls by exactly what the position gains: `10,000.00 → 10,000.00`, measured. The
   trigger was dead code. **This was the CP8 lesson recurring inside a remediation for the
   previous blocker.**
3. **CP14 — a second remover that never crossed the guard.** CP12's `forget` rule lived inside
   `useWatchlist.remove`, guarding one *caller*. This checkpoint added another: the assistant.
   A chat removal left the chart drawing a frozen series for a symbol the list denied. The
   guard now lives in `refresh`, which diffs membership, so every remover crosses it.

### The rejections that were about evidence rather than code

Four rejections were for tests and documents that claimed more than they proved: a test whose
comment described a guarantee a mutation showed it did not have; an **equivalent mutant** in a
battery table; a documentation correction I said I had made and had only half made; and a plan
that still recorded a design the code had abandoned.

**Six mutations in this run did not mutate, or did not kill what they claimed.** Three were
found by the overseer re-running the battery; three I found myself by re-running rather than
reading — including two *in this verify pass*, in probes I had just written.

## Coverage gaps

Carried into Phase D rather than hidden:

1. **Two CSS invariants no test can see.** `pointer-events-none` on the flash overlay (without
   it a row is unclickable for the whole flash window) and `relative` on the row (what
   `inset-0` is measured against). jsdom does no hit testing and no layout. Both belong to
   CP16's Playwright suite, along with the treemap's geometry and the flash tint now
   compositing over the row's text rather than behind it.
2. **The frontend suite is not hermetic.** Two tests read backend source off disk —
   `ChatPanel.test.tsx` for `MAX_MESSAGE_LENGTH` and `PnlChart.test.tsx` for
   `SNAPSHOT_INTERVAL_SECONDS`. Both are valuable (they pin cross-tree constants that would
   otherwise drift silently) and both fail with `ENOENT` wherever the backend is not a
   sibling. CP16 runs tests in a container.
3. **A transcript turn that repeats a stored message of the same role is dropped from view**
   for the session, because the merge de-duplicates on `role::content`. Narrower than the
   duplication it replaced — no false claim about a trade — but pinned by no test in either
   direction.
4. **`position()` test-helper overrides leave derived fields at their defaults.** Inert: both
   components derive from `quantity`/`avg_cost`/price, and the assertions are written against
   the derived truth.
5. **No multi-user coverage**, unchanged from Gate B.
6. **The Massive path remains unverifiable** (R6), unchanged.

## Not run

- **A5, the live structured-output spike.** Still one billable call, spent at CP2. The chat
  path was exercised here against `LLM_MOCK=true`, which is what R7 requires.
- **Browser-level rendering.** Everything visual in this gate is asserted as a prop, a class
  or an attribute. Nothing here claims the UI *looks* right — that is CP16's screenshots and
  the standing "Cannot be verified" entry.

## Findings

No blockers, no risks. Advisory conditions are recorded in
`.claude/vibe-reports/2026-08-13T23-18-51Z/state.json` under `open_conditions`.

## Verdict

**PASS.** Phase C delivers the workstation the spec describes: live prices with an honest
change percentage, a trading surface that shows the server's own refusal sentences, three
visualizations, and an assistant whose rejected actions are as visible as its filled ones.

The property that took the longest to get right is the one worth stating: **the client's idea
of what exists must come from the resource that owns it.** Prices come from the stream,
membership from the watchlist, the account from the account endpoint — and a guard on any of
them belongs to the resource, not to whichever caller happened to need it first.

Next: **Phase D** (checkpoints 15–17 — container and scripts, E2E suite, documentation and
`make check`). `build` remains the only repo-mutating mode.
