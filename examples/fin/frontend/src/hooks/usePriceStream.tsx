"use client";

/**
 * The one `EventSource` in the application (D17).
 *
 * Every price-driven pixel reads from this context. One stream rather than one
 * per component: browsers cap concurrent connections per origin, and each extra
 * stream would carry a byte-identical copy of the same frames.
 *
 * It also owns the **two-tier ring buffer** (D22). Prices are never stored
 * server-side (D1), so client history is all the history there is, and an
 * unbounded array is not a design that survives a tab left open — at 500 ms a
 * ticker accumulates 7,200 points an hour and the SVG path degrades until
 * rendering stutters. Two tiers because one cap cannot serve both consumers:
 *
 * * `SHORT_BUFFER` points for **every** ticker — all a 60-pixel sparkline can
 *   resolve;
 * * `LONG_BUFFER` points for the **selected** ticker only — otherwise the
 *   detailed chart draws the identical 60-second window as the thumbnail beside
 *   it, which is the entire reason for clicking a ticker.
 *
 * Selecting starts the long buffer from the short one's contents, so the chart
 * opens with the last minute and deepens from there.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Quote } from "@/lib/types";

/** ~60 s at the stream's 500 ms emit interval. */
export const SHORT_BUFFER = 120;
/** ~15 min at the same interval, for the selected ticker only. */
export const LONG_BUFFER = 1800;

/**
 * How many consecutive errors on a stream that has **never opened** before it
 * is called disconnected. One error is normal — the browser retries by itself,
 * and the design adds no retry logic of its own.
 */
export const ERRORS_BEFORE_DISCONNECTED = 3;

export const STREAM_URL = "/api/stream/prices";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

export interface PriceStream {
  /** Latest quote per ticker. The stream is the authority on price, not the REST payload. */
  quotes: Record<string, Quote>;
  /** Recent prices per ticker, oldest first, capped at `SHORT_BUFFER`. */
  history: Record<string, number[]>;
  /** The selected ticker's deeper history, capped at `LONG_BUFFER`. */
  selectedHistory: number[];
  selected: string | null;
  select: (ticker: string | null) => void;
  /**
   * Drop everything held for a ticker — called when it leaves the watchlist.
   *
   * Necessary because nothing else forgets: these maps only ever grow, and the
   * server's `PriceCache` never evicts either, so a removed symbol would keep
   * rendering its last price until the page was reloaded. "The stream goes
   * quiet" is not the same as "the row disappears".
   */
  forget: (ticker: string) => void;
  status: ConnectionStatus;
}

const PriceStreamContext = createContext<PriceStream | null>(null);

/** A copy of `map` without `key`. New object, because React compares by identity. */
function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  const next = { ...map };
  delete next[key];
  return next;
}

function appendCapped(existing: number[] | undefined, value: number, cap: number): number[] {
  const next = existing ? [...existing, value] : [value];
  return next.length > cap ? next.slice(next.length - cap) : next;
}

/**
 * Accept only frames that carry the fields the UI reads.
 *
 * The stream is same-origin and written by this project's own backend, so this
 * is not a trust boundary — it is a *shape* boundary. A frame missing `price`
 * would otherwise flow into `toFixed` and take the panel down with a
 * `TypeError` rather than skipping one tick.
 */
function isQuote(value: unknown): value is Quote {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<Quote>;
  return (
    typeof candidate.ticker === "string" &&
    typeof candidate.price === "number" &&
    typeof candidate.session_open === "number"
  );
}

export function PriceStreamProvider({ children, url = STREAM_URL }: { children: React.ReactNode; url?: string }) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const [selectedHistory, setSelectedHistory] = useState<number[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  // Mirrors read inside the EventSource callbacks, which close over the values
  // present when the stream was opened. The stream outlives every render, so
  // reading state directly there would pin the selection as it was at mount.
  const selectedRef = useRef<string | null>(null);
  const historyRef = useRef<Record<string, number[]>>({});
  // Assigned during render, so `select` seeds from the last **committed**
  // history. A frame that arrives and a selection that happens in the same
  // synchronous turn would lose that one tick from the deep buffer (the
  // message handler tested `selectedRef` before the click set it). The DOM
  // event loop always flushes React between a message task and a click task,
  // so this is not reachable from the UI, and the next tick refills it either
  // way — recorded rather than defended against.
  historyRef.current = history;

  const select = useCallback((ticker: string | null) => {
    selectedRef.current = ticker;
    setSelected(ticker);
    // Seed from the short buffer rather than starting empty: the chart shows
    // the last minute immediately and deepens as the stream runs.
    setSelectedHistory(ticker ? [...(historyRef.current[ticker] ?? [])] : []);
  }, []);

  const forget = useCallback((ticker: string) => {
    setQuotes((previous) => without(previous, ticker));
    setHistory((previous) => without(previous, ticker));
    // A removed ticker must not stay selected, or the detailed chart keeps
    // drawing an instrument the user is no longer watching. Read from the ref
    // rather than from a `setSelected` updater: an updater that also calls
    // other setters runs twice under StrictMode.
    if (selectedRef.current === ticker) {
      selectedRef.current = null;
      setSelected(null);
      setSelectedHistory([]);
    }
  }, []);

  useEffect(() => {
    const source = new EventSource(url);
    let opened = false;
    let consecutiveErrors = 0;

    source.onopen = () => {
      opened = true;
      consecutiveErrors = 0;
      setStatus("connected");
    };

    source.onmessage = (event: MessageEvent<string>) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!isQuote(parsed)) {
        return;
      }
      const quote = parsed;
      setQuotes((previous) => ({ ...previous, [quote.ticker]: quote }));
      setHistory((previous) => ({
        ...previous,
        [quote.ticker]: appendCapped(previous[quote.ticker], quote.price, SHORT_BUFFER),
      }));
      if (selectedRef.current === quote.ticker) {
        setSelectedHistory((previous) => appendCapped(previous, quote.price, LONG_BUFFER));
      }
    };

    source.onerror = () => {
      // `EventSource` reconnects on its own; the design adds no retry logic. So
      // `readyState` is the whole signal — CLOSED means the browser has given
      // up, CONNECTING means it is already trying again.
      if (source.readyState === EventSource.CLOSED) {
        setStatus("disconnected");
        return;
      }
      if (opened) {
        setStatus("reconnecting");
        return;
      }
      // Never opened: one failed attempt is not yet a verdict, but a run of them
      // is. Reporting `connected` here is the failure C4 exists to catch.
      consecutiveErrors += 1;
      setStatus(consecutiveErrors >= ERRORS_BEFORE_DISCONNECTED ? "disconnected" : "connecting");
    };

    return () => source.close();
  }, [url]);

  return (
    <PriceStreamContext.Provider value={{ quotes, history, selectedHistory, selected, select, forget, status }}>
      {children}
    </PriceStreamContext.Provider>
  );
}

export function usePriceStream(): PriceStream {
  const value = useContext(PriceStreamContext);
  if (value === null) {
    // Louder than the alternative, which is a component silently rendering an
    // empty watchlist forever because it was mounted outside the provider.
    throw new Error("usePriceStream must be used inside a PriceStreamProvider");
  }
  return value;
}
