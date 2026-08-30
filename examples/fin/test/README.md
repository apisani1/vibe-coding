# End-to-end suite

Playwright against the **real container**: the image this repo builds, a throwaway database,
and Chromium on the same Docker network.

```bash
cd test
docker compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from playwright
docker compose -f docker-compose.test.yml down -v
```

Nothing is installed on the host — `@playwright/test` and the browsers live in the
`mcr.microsoft.com/playwright` image, and the runner does `npm ci` against the lockfile here.

## What the stack guarantees

| Property | How |
| --- | --- |
| **No test run can bill for LLM calls** | `LLM_MOCK: 'true'`, and this file names no environment file, so the real `.env` — which carries a live key and `LLM_MOCK=false` — cannot reach the stack |
| **Every run starts from the seeded $10,000** | The database is a `tmpfs`. E2E against a persisted volume is where flaky suites come from |
| **A teardown cannot touch your portfolio** | The stack has its own compose project (`finally-e2e`) and declares no named volume, so `down -v` cannot reach `finally-data` |
| **Prices are real prices** | The simulator runs exactly as it does in production; nothing is stubbed inside the app |

Three environment traps are encoded as comments in `docker-compose.test.yml`, each of which
cost someone a debugging session: the app service must **not** be named `app` (`.app` is
HSTS-preloaded, so Chrome force-upgrades `http://app:8000` to HTTPS and the suite dies with
`ERR_SSL_PROTOCOL_ERROR`); the `tmpfs` needs explicit `uid`/`gid` because the image runs as
uid 10001 and a root-owned mount leaves it unable to create the SQLite file; and the
Playwright image tag must match `@playwright/test` in `package.json` exactly.

## Specs

Numbered, and the numbers are a dependency — `04` sells what `03` buys. `workers: 1` and
`retries: 0` are correctness rather than tuning: every spec drives one container against one
SQLite database, and a retry would hide exactly the races this suite exists to catch.

| File | Covers |
| --- | --- |
| `01-fresh-start` | Ten seeded tickers, `$10,000.00`, and **a price that actually changes within 10 s** — the only check in the project that exercises producer → cache → SSE → ring buffer → render at once |
| `02-watchlist` | Add (surviving a reload), a malformed symbol refused with the list unchanged, and remove — with **a three-second wait afterwards**, because the bug this guards against reappeared on the next frame rather than on the click |
| `03-buy` | Cash moves by exactly the confirmed fill total, and the position row appears |
| `04-sell` | Partial sell, full sell leaving no ghost row, a genuine **over**sell refused by quantity, and a sell with no position refused differently |
| `05-visualizations` | Empty states first, then a heatmap cell and a P&L series; clicking a row charts that ticker and the series grows |
| `06-chat` | A `filled` chip **and** a `rejected` chip carrying the server's reason, the transcript surviving a reload, and a chat-driven watchlist change appearing in the list |
| `07-resilience` | Stream refused → the indicator never reads `connected`; allowed → `connected` **and prices resume** |
| `08-screenshots` | Full-page captures at 1920×1080 and 1024×768 into `screenshots/`. Asserted on by nobody — they are what carries spec §2's visual criteria to a human |

## What this suite does **not** cover

**Severing an already-established SSE stream.** `07-resilience` refuses the stream *before*
the page loads and then allows it — refused-then-allowed. Cutting a stream that is already
open is not stageable from Playwright: `context.setOffline(true)` leaves an established
EventSource running, and `page.route(..., abort)` only affects requests the browser has yet to
make. Doing it properly means killing the connection at the server, outside the Playwright
container's reach.

This is recorded in `verification-plan.md` under "Cannot be verified", and it is a real gap:
the reconnect path that runs when a *live* stream drops mid-session — the one a laptop lid
exercises every day — is covered by unit tests over `readyState` and by nothing here.

Two smaller gaps, for the same reason of honesty:

- **The screenshots are not compared to anything.** No visual regression baseline; a layout
  that breaks silently will keep passing.
- **One browser.** Chromium only. Spec §2 asks for desktop-first with tablet support, which is
  what the two viewport sizes cover — not what four engines would.
