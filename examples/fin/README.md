# FinAlly — AI Trading Workstation

A simulated trading terminal: live streaming prices, a $10,000 paper portfolio, three
visualizations, and an AI assistant that can execute trades through **the same code path you
do**. One container, one port, no login.

![FinAlly](test/screenshots/desktop-1920x1080.png)

*(The screenshot is written by the E2E suite — `make e2e` — into a gitignored directory, so
the image above appears once you have run it.)*

## Quickstart

```bash
git clone <this repo> && cd fin
cp .env.example .env        # optional: works without one
./scripts/start_mac.sh      # Windows: .\scripts\start_windows.ps1
```

Then open <http://localhost:8000>. The script builds the image the first time, refuses to
start a second copy, and waits for the health check before opening a browser.

```bash
./scripts/stop_mac.sh       # stops the container; your portfolio is kept
```

> **After a `git pull`, pass `--build`.**
>
> ```bash
> ./scripts/start_mac.sh --build
> # Windows: .\scripts\start_windows.ps1 --build
> ```
>
> The script rebuilds, notices that the running container is on a **different** image than the
> one just built, and restarts it to serve the new one. Your portfolio is on a volume and survives that — see *Resetting the
> portfolio* below for the two commands that do not.
>
> **Without `--build` the script builds only when the image is missing**, so it starts whatever
> you built last. It will tell you when the running container is behind, but it will not act on
> it — a bare start stays a five-second no-op by design.
>
> This used to be broken in a way worth knowing about: the build ran *before* the "already
> running" check, so `--build` produced a new image, printed a success message, and went on
> serving the old container. That is how a build predating the DNS-rebinding guard served this machine for four
> days. The check now compares image IDs, and `make e2e` passes `--build` on every run for the
> same reason.

Without a `.env` the app still runs: prices come from the built-in simulator and the chat
panel answers 503 until an API key exists. That is a working demo, not a broken install.

### Resetting the portfolio

Your positions, cash and chat history live in a Docker **volume**, not in the image, so they
survive `stop`, `rm`, and a rebuild. To start over deliberately:

```bash
docker volume rm finally-data
```

Nothing else removes it. `stop_mac.sh` never does, and it says so. Note that
`docker compose down -v` **will** — that flag is Docker's documented way to remove a
project's volumes, and the compose file carries a warning where you would type it.

## Configuration

Every variable lives in `.env`, copied from `.env.example`. All six are optional.

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | *(empty)* | Key for the chat panel. Empty means `/api/chat` answers **503** naming the missing variable; everything else works |
| `OPENROUTER_MODEL` | *(empty in code; `.env.example` ships `openai/gpt-oss-120b`)* | Model id, passed to OpenRouter verbatim. There is deliberately **no code default** — an unset model returns 503 naming the variable rather than silently billing you for one you did not choose |
| `MASSIVE_API_KEY` | *(empty)* | Real market data via Massive (Polygon.io). Empty selects the built-in simulator. Set, there is **no fallback**: a bad key gives visibly stale prices and loud logs, never plausible fake ones presented as real |
| `MASSIVE_POLL_SECONDS` | `15` | Poll interval for the Massive source. The free tier allows 5 calls/minute, so 15 is the floor there |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` (exactly — no test names ship in it) | Comma-separated hosts the app answers for. This is what stops a malicious page from reaching your portfolio by DNS rebinding — widen it only if you serve the app under another name |
| `LLM_MOCK` | `false` | `true` returns deterministic mock replies and makes **no network calls**. Set it while developing, or every message you type is a billed call. The E2E suite sets it itself |

The startup log states which market source and which LLM path are live. Read it before
assuming a chat message was free.

## What it does

- **Live prices** for ten seeded tickers over one SSE stream, with per-row sparklines
  accumulated in the browser and a green/red flash on each move.
- **Trading** — market orders, instant fill at the current price, no fees and no confirmation
  dialog. Refusals carry the reason: *"Insufficient cash: need $12,000.00, have $10,000.00"*.
- **A portfolio** — positions table, a treemap sized by market value and coloured by P&L, and
  total account value over time from server-side snapshots.
- **A watchlist** you can edit, by hand or by asking.
- **An assistant** that answers questions and executes trades and watchlist changes. It goes
  through the same service functions the buttons do, so it cannot do anything you could not,
  and **a refused action is shown as refused, with the server's own sentence**.

Prices are simulated by default, and even the "real" path is a paper portfolio. Nothing here
touches a brokerage.

## The API

Every route lives under `/api`, and **everything under `/api` answers JSON** — including
paths that do not exist. There is no `/docs`: the interactive schema pages loaded Swagger UI
from a CDN into an origin that has no authentication and holds a portfolio, so they were
removed and this table is what replaced them.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness. Touches no database, so a locked SQLite cannot turn into a restart loop. |
| `GET` | `/api/stream/prices` | SSE. The first frame is a **full snapshot** of the cache, then one frame per tick (~500 ms). |
| `GET` | `/api/portfolio` | Cash, positions, and every derived total — computed at read time against the live cache, never stored (D1). |
| `GET` | `/api/portfolio/history` | Total account value over time, from the server-side snapshots. `?limit=` optional. |
| `POST` | `/api/portfolio/trade` | Buy or sell at the current price. **The only place money moves.** Refusals carry the reason — see the codes below. |
| `GET` | `/api/watchlist` | The watched tickers with their current quotes. The one authority on what is on the list. |
| `POST` | `/api/watchlist` | Add a ticker. |
| `DELETE` | `/api/watchlist/{ticker}` | Remove one. `204`, and `404` if it was not watched. |
| `POST` | `/api/chat` | One conversational turn. Rate limited — each request is one billed completion. |
| `GET` | `/api/chat/messages` | **The stored transcript** (D18). Added because without it the panel was blank after every reload while the rows sat in SQLite. |

**A refused trade is not one status code.** Each is a decision, and the three disagree on
purpose (`DESIGN.md` § edge cases):

| Code | When | Example |
| --- | --- | --- |
| `400` | The account or the order cannot stand | *"Insufficient cash: need $12,000.00, have $10,000.00"* — also insufficient shares, no position, an unknown side, and a buy too small to leave a position |
| `409` | Well-formed, and will succeed shortly | *"No price available for AAPL yet"* — the producer has not quoted it, usually fixed by the next tick |
| `422` | The input itself is wrong | An unusable ticker, or a quantity that is not a finite positive number |

Three more worth stating outright:

- **A refused *assistant* action is `200`.** The model answered; the user needs to see what it
  tried and why it was refused, and a 4xx would replace that with a generic banner (D6). The
  reason is the same sentence the REST error above would have carried.
- **`503` from `/api/chat`** has two halves. Unconfigured names the missing variable
  (*"OPENROUTER_API_KEY is not set"*); unreachable deliberately does **not** — it is a fixed
  sentence, because a provider's exception text has embedded a request URL before and this
  string is rendered to the user. Either way the turn is recorded in the transcript with its
  reason, so a reload never shows a question nobody answered.
- **`429` from `/api/chat`** is a spend limit, not load shedding, and carries `Retry-After`.

## Development

```bash
make check     # the full sweep: backend tests, types, lint, format; frontend tests, types, lint
make e2e       # 21 Playwright specs against the real container, from a cold compose
make build     # docker build
make help      # every target
```

Each half also runs on its own — see [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md). Use `LLM_MOCK=true` locally; the repo's `.env`
carries `LLM_MOCK=false`.

## How it is built

One FastAPI process serves `/api/*` and, underneath it, a statically exported Next.js bundle —
so there is no second origin, no CORS, and one port to open. SQLite in WAL mode holds the
account; prices are never stored, only computed against a live in-memory cache.

The design decisions and their alternatives are in [`planning/`](planning/), which also holds
the specification, the build plan and the verification plan. That directory is the contract:
it is what an agent — or a person — should read before changing anything here.

## Credit

This is the capstone project for the [AI Coder: From Vibe Coder to Agentic Engineer](https://www.udemy.com/course/ai-coder-from-vibe-coder-to-agentic-engineer/) course on Udemy.

## Licence

MIT. See [LICENSE](LICENSE).
