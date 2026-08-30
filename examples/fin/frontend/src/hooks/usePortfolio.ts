"use client";

/**
 * The account, fetched — not streamed.
 *
 * Cash, positions and totals are **state-driven** pixels in the design's
 * rendering split: they change only when something mutates them, so they are
 * fetched once and refetched after a trade. Putting them on the 500 ms price
 * tick would re-render the whole page twice a second to redraw numbers that did
 * not move; the current *price* of a position is the price-driven half and
 * comes from the stream (see `PositionsTable`).
 *
 * `refresh` is what a mutation calls. Check C5 counts those calls — "exactly
 * one refetch per successful trade" — so this hook deliberately does not
 * refetch on any other trigger: no interval, no focus listener, nothing that
 * would make that count ambiguous.
 */

import { useCallback, useEffect, useState } from "react";
import { getPortfolio } from "@/lib/api";
import type { Portfolio } from "@/lib/types";

export interface PortfolioState {
  portfolio: Portfolio | null;
  /** The server's own sentence when the fetch failed, or `null`. */
  error: string | null;
  refresh: () => Promise<void>;
}

export function usePortfolio(): PortfolioState {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  // No `loading` flag. This hook exported one and nothing ever read it: the
  // panel renders the previous portfolio while a refresh is in flight, on
  // purpose (see the catch below), so there is no spinner for it to drive. The
  // chat panel's in-flight state is a different thing and lives in `useChat`,
  // where check C7 actually asserts it.

  const refresh = useCallback(async () => {
    try {
      setPortfolio(await getPortfolio());
      setError(null);
    } catch (caught) {
      // The previous portfolio is deliberately kept on screen rather than
      // cleared: stale-but-labelled beats a blank panel, and the totals were
      // true a moment ago. **Labelled** is the load-bearing half — `page.tsx`
      // renders this string as a banner, because stale numbers with no notice
      // are just wrong numbers. The first version of this comment claimed a
      // line that nothing rendered.
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { portfolio, error, refresh };
}
