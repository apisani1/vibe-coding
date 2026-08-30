"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkline } from "@/components/Sparkline";
import { usePriceStream } from "@/hooks/usePriceStream";
import { useWatchlist } from "@/hooks/useWatchlist";
import { changePercent, formatMoney, formatPercent, NO_VALUE } from "@/lib/format";
import type { Quote } from "@/lib/types";

/** How long a row stays tinted after a price change. Matches the CSS animation. */
export const FLASH_MS = 500;

/**
 * One flash, identified by a sequence number.
 *
 * The number is what makes a *second* rise visible. Setting the same class
 * string again is a no-op as far as React and CSS are concerned — the DOM
 * attribute does not change, so the running animation is not restarted, and a
 * steadily rising ticker would flash once and then go quiet for as long as it
 * kept rising. Found by the overseer's probe (rise at t=0, rise at t=400: class
 * still present at t=899, animation finished at t=500). The sequence number is
 * the element's `key`, so every flash mounts a fresh overlay and every price
 * move is seen.
 */
type Flash = { direction: "flash-up" | "flash-down"; seq: number } | null;

function Row({
  ticker,
  quote,
  points,
  selected,
  onSelect,
  onRemove,
}: {
  ticker: string;
  /** `null` for a symbol added manually, until the producer quotes it. */
  quote: Quote | null;
  points: number[];
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const [flash, setFlash] = useState<Flash>(null);
  // `null` until the first quote, so the arrival of a price is not itself a
  // price *change*. A row added manually would otherwise flash green the moment
  // it was first quoted, for movement that never happened.
  const lastPrice = useRef<number | null>(quote?.price ?? null);
  const sequence = useRef(0);

  useEffect(() => {
    if (quote === undefined || quote === null) {
      return;
    }
    if (lastPrice.current === null) {
      lastPrice.current = quote.price;
      return;
    }
    if (quote.price === lastPrice.current) {
      return;
    }
    // Compared against the last price **this row rendered**, not against
    // `quote.direction`. The stream's first frame is a full snapshot whose
    // `direction` was computed by the producer at some earlier tick, so
    // trusting that field would flash every row green or red on connect — and
    // again on every reconnect — for movement the user never saw.
    const direction = quote.price > lastPrice.current ? "flash-up" : "flash-down";
    lastPrice.current = quote.price;
    sequence.current += 1;
    setFlash({ direction, seq: sequence.current });
    const timer = setTimeout(() => setFlash(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [quote]);

  const change = quote ? changePercent(quote.price, quote.session_open) : null;
  const changeColour = change === null || change === 0 ? "text-terminal-muted" : change > 0 ? "text-up" : "text-down";

  return (
    <li
      data-testid={`watchlist-row-${ticker}`}
      className="relative border-b border-terminal-border/60 last:border-b-0"
    >
      {/* Two of these class names are load-bearing and **no test can see it**:
          jsdom does no hit testing and no layout. `pointer-events-none` is what
          keeps the overlay from swallowing the row's click — without it the row
          is unclickable for the whole flash window, which at a 500 ms tick and
          FLASH_MS 500 is essentially always. `relative` on the <li> above is
          what the `inset-0` is measured against; without it the tint anchors to
          whatever ancestor happens to be positioned. Both are on CP16's
          Playwright list (click a row while prices are ticking). */}
      {flash && (
        <span
          key={flash.seq}
          aria-hidden="true"
          data-testid={`flash-${ticker}`}
          className={`pointer-events-none absolute inset-0 ${flash.direction}`}
        />
      )}
      <div className="flex items-center">
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className={`flex flex-1 items-center gap-2 px-3 py-1.5 text-left hover:bg-terminal-border/30 ${
            selected ? "bg-terminal-border/40" : ""
          }`}
        >
          <span className="w-14 shrink-0 font-semibold text-terminal-text">{ticker}</span>
          <span className="w-20 shrink-0 text-right tabular-nums">
            {quote ? formatMoney(quote.price) : NO_VALUE}
          </span>
          <span className={`w-20 shrink-0 text-right tabular-nums ${changeColour}`}>{formatPercent(change)}</span>
          <Sparkline points={points} className={changeColour} />
        </button>
        <button
          type="button"
          aria-label={`Remove ${ticker}`}
          onClick={onRemove}
          className="relative px-2 py-1.5 text-terminal-muted hover:text-down"
        >
          ×
        </button>
      </div>
    </li>
  );
}

/**
 * The watched symbols, priced live.
 *
 * Two sources, answering two different questions. **Membership** comes from
 * `GET /api/watchlist` and from nowhere else. **Price** comes from the stream,
 * because a REST payload is a snapshot that is stale by the next tick; the
 * entry's own `quote` is only a seed for the gap before the first frame.
 *
 * The first version of this component took membership from the *union* of the
 * list and the streamed quotes, and the overseer broke it in one probe: a
 * removed ticker came straight back on the next frame, and clicking `×` again
 * only produced a 404 while the ghost row stayed. Two independent reasons, both
 * permanent rather than racy:
 *
 * * the producer prices **watchlist ∪ open positions** (D3), so any symbol you
 *   hold keeps streaming forever after you unwatch it;
 * * `PriceCache` never evicts and the SSE endpoint opens every connection with
 *   a full cache snapshot, so a reconnect or a reload repopulates `quotes` with
 *   symbols removed minutes ago.
 *
 * A quote is not a membership claim. `forget` still runs on removal — it keeps
 * the client maps and the chart selection from growing stale — but the list is
 * no longer rendered from anything the stream says.
 *
 * The change percentage comes from `session_open`, never `previous_price` —
 * D19, and the single assertion check C3 exists to make. Sorted by ticker so
 * rows do not reorder underneath a click when a quote arrives.
 */
export function Watchlist({ refreshKey = 0 }: { refreshKey?: number }) {
  const { quotes, history, selected, select } = usePriceStream();
  const { entries, error, add, remove, refresh } = useWatchlist();
  const [draft, setDraft] = useState("");

  // The assistant executes through the same service functions a person does
  // (D5), so a chat turn can add or remove a symbol. Without this the panel
  // would report "Applied NVDA" beside a list that does not contain NVDA —
  // the panel asserting something the rest of the UI denies.
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    void refresh();
  }, [refreshKey, refresh]);

  const tickers = entries.map((entry) => entry.ticker).sort();
  const seeded = new Map(entries.map((entry) => [entry.ticker, entry.quote]));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (draft.trim().length === 0) {
      return;
    }
    // Cleared only on success, so a rejected symbol stays in the box to be
    // corrected — the same rule the trade bar follows for the same reason.
    if (await add(draft.trim())) {
      setDraft("");
    }
  }

  return (
    <div className="flex min-h-0 flex-col">
      <form onSubmit={submit} className="flex items-center gap-2 border-b border-terminal-border px-3 py-2">
        <input
          aria-label="Add ticker"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add symbol"
          className="w-full rounded border border-terminal-border bg-terminal-bg px-2 py-1 uppercase text-terminal-text"
        />
        <button type="submit" className="rounded bg-accent-purple px-2 py-1 text-xs font-semibold text-white">
          Add
        </button>
      </form>

      {error && (
        <p role="alert" className="px-3 py-1 text-xs text-down" data-testid="watchlist-error">
          {error}
        </p>
      )}

      {tickers.length === 0 ? (
        <p className="px-3 py-2 text-sm text-terminal-muted">Nothing on the watchlist. Add a symbol above.</p>
      ) : (
        <ul className="overflow-auto text-sm" data-testid="watchlist">
          {tickers.map((ticker) => (
            <Row
              key={ticker}
              ticker={ticker}
              quote={quotes[ticker] ?? seeded.get(ticker) ?? null}
              points={history[ticker] ?? []}
              selected={selected === ticker}
              onSelect={() => select(ticker)}
              onRemove={() => void remove(ticker)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
