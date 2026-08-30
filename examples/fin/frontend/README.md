# FinAlly frontend

Next.js 15 + TypeScript + Tailwind, exported as **static files**. There is no Node process in
production: FastAPI serves the export underneath its own API routes, which is why the whole
app is one container on one port.

## Running locally

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

`npm run dev` serves the UI but not the API. Run the backend beside it —
`cd backend && LLM_MOCK=true uv run uvicorn finally_app.main:app --port 8000` — and add a
proxy, **or** just build the export and let FastAPI serve both:

```bash
npm run build
cp -R out/. ../backend/src/finally_app/static/
cd ../backend && LLM_MOCK=true uv run uvicorn finally_app.main:app --port 8000
```

The second form is what the container does, and it is the only one that exercises the mount.

## Checks

```bash
npm run test         # vitest, 174 tests
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
```

No test reaches the network: `vitest.setup.ts` replaces `fetch` **and** `EventSource` with
stubs that throw, reinstalled before every test so one test's stub cannot leak into the next.
A component that forgets to stub fails with `BLOCKED:` rather than hanging.

Two tests deliberately read backend source from disk — the chat message cap from
`api/chat.py` and the snapshot interval from `services/snapshots.py` — so those constants
cannot drift apart silently. They need the backend to be a sibling directory.

## Layout

```
src/
├── app/page.tsx          # the single page: layout, and the one place the stream is opened
├── components/           # Watchlist, Sparkline, Header, MainChart, PnlChart, Heatmap,
│                         # PositionsTable, TradeBar, ChatPanel
├── hooks/
│   ├── usePriceStream.tsx  # THE EventSource — one per app, plus the two-tier ring buffer
│   ├── usePortfolio.ts     # fetch on mount, refetch after a mutation. No polling.
│   ├── useWatchlist.ts     # membership, add/remove, and the guard that prunes the stream
│   └── useChat.ts          # transcript, in-flight state, send
├── lib/                  # api.ts (typed fetch wrappers), format.ts, types.ts
└── test/                 # fake EventSource and fetch recorder — not test files themselves
```

## Three rules worth knowing before you change something

1. **The change percentage comes from `session_open`, never `previous_price`.** At a 500 ms
   tick the latter is a ±0.01% number that flips sign twice a second, which is not a daily
   change by any reading.
2. **A quote is not a membership claim.** The watchlist's rows come from
   `GET /api/watchlist` alone. The producer keeps pricing tickers you hold after you unwatch
   them, and the server's price cache never evicts, so a list built from the streamed tickers
   shows symbols that are not on it — and a removed row comes back on the next frame.
3. **A rejected assistant action is rendered as rejected.** A panel that showed only the
   fills would let *"I bought 600 shares"* stand while the portfolio refused it. Both statuses
   are part of the type for that reason.
