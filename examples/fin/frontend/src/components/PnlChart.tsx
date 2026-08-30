"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { getHistory } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Portfolio, Snapshot } from "@/lib/types";

/**
 * Total account value over time, from `GET /api/portfolio/history`.
 *
 * Server-side snapshots, not client-side accumulation: the series has to
 * survive a reload, and it is the one part of this UI that does (D1 keeps no
 * *price* history, but portfolio value is a stored series).
 *
 * It refetches on two triggers, and both are needed for different reasons:
 *
 * * **when the account is re-read** — a fill writes a snapshot row inside its
 *   own transaction, and waiting up to 30 seconds to plot it makes the chart
 *   look broken. Note *re-read*, not "changes value": a fill at the mark leaves
 *   `total_value` identical (10,000.00 → 10,000.00, measured), which is why the
 *   trigger is the account object rather than any number on it — see the
 *   comment on the effect below;
 * * **on a timer matching the server's snapshot interval** — value drifts with
 *   prices even when the user does nothing, so a chart that only refetched on
 *   mutation would flatline on an idle desk.
 */

/** Matches `services/snapshots.SNAPSHOT_INTERVAL_SECONDS`; a shorter poll would return the same rows. */
export const HISTORY_POLL_MS = 30_000;

/**
 * Did the account end the window above where it started?
 *
 * Exported and given a `data-trend` attribute because the colour is a claim
 * about the user's day: pinning it to `true` used to pass the whole suite while
 * the comment beside it insisted the colour followed the direction.
 */
export function trendUp(values: number[]): boolean {
  return values.length === 0 || values[values.length - 1] >= values[0];
}

export function PnlChart({ portfolio }: { portfolio: Portfolio | null }) {
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const load = useCallback(async () => {
    // Same sequencing rule as `useWatchlist`: a poll and a post-fill refetch can
    // overlap, and without a generation the older response lands last and shows
    // a chart that is missing the point the user just created.
    const mine = (generation.current += 1);
    try {
      const rows = await getHistory();
      if (mine !== generation.current) {
        return;
      }
      setHistory(rows);
      setError(null);
    } catch (caught) {
      if (mine !== generation.current) {
        return;
      }
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  // Keyed on the account **object**, not on `total_value`.
  //
  // Keying on the value looked tidier and was dead code. Every order in this
  // system fills at the cached mark, so cash falls by exactly the market value
  // the position gains and the total does not move: measured against the real
  // service, 10,000.00 → 10,000.00 for a 5-share buy at 190.50, with a snapshot
  // row written inside the same transaction. `usePortfolio` never polls, so
  // `total_value` cannot change at all after the first load — the trigger could
  // never have fired, and the chart would have missed the point the trade just
  // created until the 30-second poll.
  //
  // This is the CP8 lesson (`buying at the mark leaves the total exactly equal
  // to starting cash`) recurring, and the overseer caught it in the fix for its
  // own previous finding.
  //
  // Identity is the honest trigger: `usePortfolio` produces a new object only
  // when it has actually re-read the account, which happens on mount and after
  // a fill. The cost is one extra load on a cold page — mount, then the account
  // arriving — and that count is asserted rather than hand-waved.
  useEffect(() => {
    void load();
  }, [load, portfolio]);

  useEffect(() => {
    const timer = setInterval(() => void load(), HISTORY_POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  if (error && history.length === 0) {
    return (
      <p className="p-3 text-xs text-down" role="alert" data-testid="pnl-error">
        {error}
      </p>
    );
  }

  if (history.length === 0) {
    return (
      <p className="p-3 text-sm text-terminal-muted" data-testid="pnl-empty">
        No snapshots yet — the first one is written at startup.
      </p>
    );
  }

  const values = history.map((row) => row.total_value);
  const up = trendUp(values);

  return (
    <div className="h-full w-full" data-testid="pnl-chart" data-points={history.length} data-trend={up ? "up" : "down"}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={history} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          {/* Colour follows the session's direction rather than being fixed:
              the same chart is a good day or a bad one, and the reader should
              not have to compare endpoints to find out which. */}
          <YAxis domain={["dataMin", "dataMax"]} hide />
          <Tooltip
            contentStyle={{ background: "#1a1a2e", border: "1px solid #30363d", fontSize: 12 }}
            labelFormatter={() => "Total value"}
            formatter={(value) => [formatMoney(Number(value)), ""]}
          />
          <Area
            type="monotone"
            dataKey="total_value"
            stroke={up ? "#26a65b" : "#e5484d"}
            fill={up ? "#26a65b" : "#e5484d"}
            fillOpacity={0.15}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
