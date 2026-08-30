"use client";

/**
 * Watchlist membership: who is on the list, and adding or removing them.
 *
 * Membership is fetched, not streamed — the stream carries prices, and a symbol
 * added a moment ago has no price yet. Prices still come from the stream (the
 * entry's `quote` is only a seed for the gap before the first frame), so this
 * hook and `usePriceStream` answer two different questions about the same row.
 *
 * Removal does three things: the DELETE, an optimistic drop from the local list
 * so the row goes on that render rather than when the refetch lands, and
 * `forget` on the stream — the CP11 approval's carried condition. Nothing else
 * would do that last one: the client maps only grow and the server's
 * `PriceCache` never evicts, so a removed symbol would keep its last price (and
 * the chart selection) until a reload.
 *
 * Responses are **sequenced**. Two mutations overlapping is not exotic — a
 * removal's refetch is a round trip long, and an add issued during it resolves
 * first — and without a generation guard the older response lands last and
 * wipes the newer list. Found by the overseer with a probe, not by this hook's
 * tests, which is why the guard now has one of its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { usePriceStream } from "@/hooks/usePriceStream";
import { addTicker, getWatchlist, removeTicker } from "@/lib/api";
import type { WatchlistEntry } from "@/lib/types";

export interface WatchlistState {
  entries: WatchlistEntry[];
  /** The server's own sentence for the last failed operation, or `null`. */
  error: string | null;
  add: (ticker: string) => Promise<boolean>;
  remove: (ticker: string) => Promise<boolean>;
  refresh: () => Promise<void>;
}

export function useWatchlist(): WatchlistState {
  const { forget } = usePriceStream();
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Which refresh is the newest. A response from an older one is discarded
  // rather than applied late.
  const generation = useRef(0);
  // Whether the message on screen came from a failed *refresh*. A refresh
  // clears only its own error: without this, a background GET resolving a
  // moment after a rejected add wipes the server's "not a valid ticker symbol"
  // sentence off the screen while the rejected symbol is still in the box —
  // the one message the user actually needs to read.
  const refreshFailed = useRef(false);
  // The membership the last successful load reported, so the next one can say
  // what left. Empty on the first load, so nothing is forgotten at startup.
  const known = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    const mine = (generation.current += 1);
    try {
      const list = await getWatchlist();
      if (mine !== generation.current) {
        return;
      }
      // **Every** removal crosses this, whoever performed it. `remove` below
      // forgets explicitly so the chart clears on the same render as the click,
      // but the assistant removes symbols too (D5) and reaches this hook only
      // through `refresh` — CP14 shipped that second path and the chart kept
      // drawing a symbol the list no longer contained, frozen for the session.
      // Diffing the membership is what makes the guard belong to the *resource*
      // rather than to one caller of it.
      const incoming = new Set(list.map((entry) => entry.ticker));
      for (const ticker of known.current) {
        if (!incoming.has(ticker)) {
          forget(ticker);
        }
      }
      known.current = incoming;
      setEntries(list);
      if (refreshFailed.current) {
        refreshFailed.current = false;
        setError(null);
      }
    } catch (caught) {
      if (mine !== generation.current) {
        return;
      }
      refreshFailed.current = true;
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [forget]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = useCallback(
    async (ticker: string): Promise<boolean> => {
      try {
        await addTicker(ticker);
      } catch (caught) {
        // A rejected symbol is the server's 422 sentence, shown as typed. The
        // list is untouched, which is what check B3 asserts on the other side.
        setError(caught instanceof Error ? caught.message : String(caught));
        return false;
      }
      setError(null);
      await refresh();
      return true;
    },
    [refresh],
  );

  const remove = useCallback(
    async (ticker: string): Promise<boolean> => {
      try {
        await removeTicker(ticker);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        return false;
      }
      setError(null);
      const symbol = ticker.toUpperCase();
      // Drop it locally first. The list is now the only source of membership,
      // so without this the row would linger until the refetch resolved — an
      // earlier comment here claimed `forget` alone made the row disappear,
      // which the overseer disproved by looking at the intermediate render.
      setEntries((current) => current.filter((entry) => entry.ticker !== symbol));
      // `forget` is about the *stream's* state, not the row: the client maps
      // only grow, `PriceCache` never evicts, and a removed ticker must not
      // stay selected in the chart.
      forget(symbol);
      await refresh();
      return true;
    },
    [forget, refresh],
  );

  return { entries, error, add, remove, refresh };
}
