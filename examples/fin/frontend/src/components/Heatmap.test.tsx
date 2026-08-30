import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fillFor, Heatmap, HeatmapCell, heatmapCells, NEUTRAL_FILL, RAMP_CAP } from "@/components/Heatmap";
import { renderWithStream } from "@/test/priceStream";
import type { Portfolio, Position } from "@/lib/types";

function position(overrides: Partial<Position> & { ticker: string }): Position {
  return {
    quantity: 10,
    avg_cost: 100,
    current_price: 110,
    market_value: 1100,
    unrealized_pnl: 100,
    unrealized_pnl_percent: 10,
    ...overrides,
  };
}

/**
 * A portfolio whose totals actually add up.
 *
 * The first version hardcoded `positions_value: 0` and `total_value: 0` beside a
 * $1,100 position — a state the backend cannot emit, since `total_value` is
 * cash plus positions value. Nothing here reads those fields today, which is
 * exactly how the P&L chart's impossible fixture went unnoticed until it became
 * load-bearing.
 */
function account(positions: Position[]): Portfolio {
  const positionsValue = positions.reduce(
    (total, held) => total + (held.current_price ?? held.avg_cost) * held.quantity,
    0,
  );
  const cash = 5000;
  return {
    cash_balance: cash,
    positions,
    positions_value: positionsValue,
    total_value: cash + positionsValue,
    unrealized_pnl: positions.reduce((total, held) => total + held.unrealized_pnl, 0),
  };
}

describe("the colour ramp (check C6)", () => {
  it("is green above avg_cost and red below", () => {
    // Asserted on the value passed to the cell, not on a rendered pixel: under
    // jsdom a Recharts SVG has no layout, and "the rectangle looks green" is
    // not something a unit test can honestly claim.
    expect(fillFor(5)).toContain("38 166 91");
    expect(fillFor(-5)).toContain("229 72 77");
  });

  it("is a ramp, not a flag — a bigger move is a stronger colour", () => {
    // The whole point of the view is spotting the outlier. Two holdings, one up
    // 0.5% and one up 40%, must not paint identically.
    const alpha = (fill: string) => Number(fill.match(/\/ ([\d.]+)\)/)![1]);

    expect(alpha(fillFor(1))).toBeLessThan(alpha(fillFor(5)));
    expect(alpha(fillFor(-1))).toBeLessThan(alpha(fillFor(-5)));
  });

  it("saturates at the cap instead of running out of alpha", () => {
    expect(fillFor(RAMP_CAP)).toBe(fillFor(RAMP_CAP * 10));
  });

  it("is neutral for a flat position and for one nothing has priced", () => {
    // A grey cell says "no opinion". Green would claim a gain the app cannot
    // know about — the same rule as check C5's dash.
    expect(fillFor(0)).toBe(NEUTRAL_FILL);
    expect(fillFor(null)).toBe(NEUTRAL_FILL);
    expect(fillFor(NaN)).toBe(NEUTRAL_FILL);
  });
});

describe("cells", () => {
  it("sizes by market value, not by share count", () => {
    // 100 shares of a $4 stock is the smaller position; a treemap that says
    // otherwise is worse than no treemap.
    const cells = heatmapCells(
      [
        position({ ticker: "CHEAP", quantity: 100, avg_cost: 4, current_price: 4 }),
        position({ ticker: "DEAR", quantity: 5, avg_cost: 500, current_price: 500 }),
      ],
      {},
    );

    expect(cells[0].size).toBe(400);
    expect(cells[1].size).toBe(2500);
  });

  it("prices from the stream when it has a quote", () => {
    const cells = heatmapCells([position({ ticker: "AAPL", current_price: 110 })], { AAPL: { price: 130 } });

    expect(cells[0].size).toBe(1300);
    expect(cells[0].pnlPercent).toBeCloseTo(30, 10);
  });

  it("falls back to cost basis for an unpriced position", () => {
    // Size still has to be a number — a NaN area removes the rectangle from the
    // layout entirely, so the position would silently vanish from the view.
    const cells = heatmapCells([position({ ticker: "ZZZZ", current_price: null })], {});

    expect(cells[0].size).toBe(1000);
    expect(cells[0].pnlPercent).toBeNull();
    expect(cells[0].fill).toBe(NEUTRAL_FILL);
  });
});

describe("the cell renderer", () => {
  it("paints with the fill it was handed", () => {
    const { container } = render(
      <svg>
        <HeatmapCell x={0} y={0} width={120} height={80} ticker="AAPL" pnlPercent={12} fill="rgb(38 166 91 / 0.9)" />
      </svg>,
    );

    expect(screen.getByTestId("heatmap-cell-AAPL")).toHaveAttribute("data-fill", "rgb(38 166 91 / 0.9)");
    expect(container.querySelector("rect")).toHaveAttribute("fill", "rgb(38 166 91 / 0.9)");
  });

  it("drops the label rather than overflowing a small rectangle", () => {
    render(
      <svg>
        <HeatmapCell x={0} y={0} width={20} height={12} ticker="AAPL" pnlPercent={12} fill={NEUTRAL_FILL} />
      </svg>,
    );

    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });
});

describe("the component", () => {
  it("renders an explicit empty state for an empty portfolio", () => {
    // C6: an empty portfolio must not throw and must not render a blank box
    // that looks like a broken chart.
    renderWithStream(<Heatmap portfolio={account([])} />);

    expect(screen.getByTestId("heatmap-empty")).toBeInTheDocument();
  });

  it("survives a portfolio that has not loaded yet", () => {
    expect(() => renderWithStream(<Heatmap portfolio={null} />)).not.toThrow();
    expect(screen.getByTestId("heatmap-empty")).toBeInTheDocument();
  });

  it("renders one cell per position", () => {
    renderWithStream(<Heatmap portfolio={account([position({ ticker: "AAPL" }), position({ ticker: "MSFT" })])} />);

    expect(screen.getByTestId("heatmap")).toHaveAttribute("data-cells", "2");
  });
});
