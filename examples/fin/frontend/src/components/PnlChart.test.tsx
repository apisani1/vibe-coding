import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { HISTORY_POLL_MS, PnlChart, trendUp } from "@/components/PnlChart";
import { stubApi } from "@/test/api";
import type { Portfolio } from "@/lib/types";

const HISTORY = [
  { total_value: 10000, recorded_at: "2026-08-16T12:00:00Z" },
  { total_value: 10120, recorded_at: "2026-08-16T12:00:30Z" },
];

function account(total: number): Portfolio {
  return { cash_balance: total, positions: [], positions_value: 0, total_value: total, unrealized_pnl: 0 };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("PnlChart", () => {
  it("fetches the history once on mount and plots it", async () => {
    const api = stubApi([{ match: "/api/portfolio/history", body: HISTORY }]);

    render(<PnlChart portfolio={null} />);

    await waitFor(() => expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "2"));
    expect(api.to("/api/portfolio/history")).toHaveLength(1);
  });

  it("renders an empty state rather than a blank box before the first snapshot", async () => {
    stubApi([{ match: "/api/portfolio/history", body: [] }]);

    render(<PnlChart portfolio={null} />);

    await waitFor(() => expect(screen.getByTestId("pnl-empty")).toBeInTheDocument());
  });

  it("refetches after a fill even though the fill does not move total value", async () => {
    // The fixture is the point. Every order fills at the cached mark, so cash
    // falls by exactly what the position gains and `total_value` is unchanged —
    // measured against the real service: 10,000.00 → 10,000.00 for 5 AAPL at
    // 190.50, with a snapshot row written in the same transaction. A version
    // keyed on `total_value` never refetches here, which is precisely the dead
    // trigger this test exists to reject.
    const api = stubApi([{ match: "/api/portfolio/history", body: HISTORY }]);
    const { rerender } = render(<PnlChart portfolio={account(10000)} />);
    await waitFor(() => expect(api.to("/api/portfolio/history")).toHaveLength(1));

    await act(async () => {
      rerender(
        <PnlChart
          portfolio={{
            cash_balance: 9047.5,
            positions: [
              {
                ticker: "AAPL",
                quantity: 5,
                avg_cost: 190.5,
                current_price: 190.5,
                market_value: 952.5,
                unrealized_pnl: 0,
                unrealized_pnl_percent: 0,
              },
            ],
            positions_value: 952.5,
            total_value: 10000,
            unrealized_pnl: 0,
          }}
        />,
      );
    });

    expect(api.to("/api/portfolio/history")).toHaveLength(2);
  });

  it("polls on the server's snapshot cadence, so an idle desk still draws a line", async () => {
    // Value drifts with prices even when nobody trades. A chart that only
    // refetched on mutation would flatline on an open tab.
    vi.useFakeTimers();
    const api = stubApi([{ match: "/api/portfolio/history", body: HISTORY }]);
    render(<PnlChart portfolio={null} />);
    await act(async () => {});
    expect(api.to("/api/portfolio/history")).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(HISTORY_POLL_MS);
    });

    expect(api.to("/api/portfolio/history")).toHaveLength(2);
  });

  it("stops polling when it unmounts", async () => {
    vi.useFakeTimers();
    const api = stubApi([{ match: "/api/portfolio/history", body: HISTORY }]);
    const { unmount } = render(<PnlChart portfolio={null} />);
    await act(async () => {});

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(HISTORY_POLL_MS * 3);
    });

    expect(api.to("/api/portfolio/history")).toHaveLength(1);
  });

  it("shows the server's sentence when there is nothing to draw", async () => {
    stubApi([{ match: "/api/portfolio/history", status: 503, body: { detail: "database is locked" } }]);

    render(<PnlChart portfolio={null} />);

    await waitFor(() => expect(screen.getByTestId("pnl-error")).toHaveTextContent("database is locked"));
  });

  it("keeps the last good series when a later fetch fails", async () => {
    // Same rule as the portfolio: stale beats blank, because the line drawn a
    // moment ago was true.
    const api = stubApi([{ match: "/api/portfolio/history", body: HISTORY }]);
    const { rerender } = render(<PnlChart portfolio={account(10000)} />);
    await waitFor(() => expect(screen.getByTestId("pnl-chart")).toBeInTheDocument());

    api.serve([{ match: "/api/portfolio/history", status: 503, body: { detail: "database is locked" } }]);
    await act(async () => {
      rerender(<PnlChart portfolio={{ ...account(10000) }} />);
    });

    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "2");
    expect(screen.queryByTestId("pnl-error")).not.toBeInTheDocument();
  });

  it("ignores a slow response that a newer one has superseded", async () => {
    // The same last-write-wins defect the overseer found in useWatchlist: a
    // poll and a post-fill refetch overlap, and the older response would
    // otherwise land last and drop the point the user just created.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([{ match: "/api/portfolio/history", body: [HISTORY[0]], gate: slow }]);
    const { rerender } = render(<PnlChart portfolio={account(10000)} />);

    api.serve([{ match: "/api/portfolio/history", body: HISTORY }]);
    await act(async () => {
      rerender(<PnlChart portfolio={{ ...account(10000) }} />);
    });
    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "2");

    await act(async () => {
      release();
    });

    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "2");
  });
});

describe("the trend colour", () => {
  it("follows the direction of the window rather than being fixed", async () => {
    // `up = true` used to survive the suite while the comment beside it claimed
    // the colour tracked the session. The colour is a claim about the user's
    // day; it needs to be falsifiable.
    stubApi([
      {
        match: "/api/portfolio/history",
        body: [
          { total_value: 10000, recorded_at: "2026-08-16T12:00:00Z" },
          { total_value: 9000, recorded_at: "2026-08-16T12:00:30Z" },
        ],
      },
    ]);

    render(<PnlChart portfolio={null} />);

    await waitFor(() => expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-trend", "down"));
  });

  it("calls a flat or rising window up, and an empty one up", () => {
    expect(trendUp([10, 10])).toBe(true);
    expect(trendUp([10, 11])).toBe(true);
    expect(trendUp([11, 10])).toBe(false);
    expect(trendUp([])).toBe(true);
  });
});

describe("the poll interval", () => {
  it("matches the backend's snapshot cadence", () => {
    // The interval was asserted only against itself — the test advanced timers
    // by the very constant it was testing, so "matches the server's 30 s
    // cadence" was a comment, not a check. Read the backend's own constant.
    const source = readFileSync(
      resolve(process.cwd(), "../backend/src/finally_app/services/snapshots.py"),
      "utf8",
    );

    const seconds = Number(source.match(/SNAPSHOT_INTERVAL_SECONDS = ([\d.]+)/)![1]);

    expect(seconds).toBeGreaterThan(0);
    expect(HISTORY_POLL_MS).toBe(seconds * 1000);
  });
});
