import { act, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { COLUMNS, PositionsTable } from "@/components/PositionsTable";
import { quote, renderWithStream, stream } from "@/test/priceStream";
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

/** Totals that add up, for the reason spelled out in `Heatmap.test.tsx`. */
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

describe("PositionsTable", () => {
  it("renders the spec's six columns", () => {
    renderWithStream(<PositionsTable portfolio={account([position({ ticker: "AAPL" })])} />);

    const headers = screen.getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(COLUMNS);
    expect(headers).toHaveLength(6);
  });

  it("shows an empty state rather than an empty table", () => {
    renderWithStream(<PositionsTable portfolio={account([])} />);

    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("positions-table")).not.toBeInTheDocument();
  });

  it("survives a portfolio that has not loaded yet", () => {
    renderWithStream(<PositionsTable portfolio={null} />);

    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
  });

  it("shows a dash — not $0.00, not NaN — when nothing has priced the position", () => {
    // Check C5's named failure. The backend carries an unpriced position at
    // cost with unrealized_pnl 0.0, which is the right thing to store and the
    // wrong thing to render: $0.00 claims the position is exactly break-even.
    renderWithStream(
      <PositionsTable
        portfolio={account([
          position({ ticker: "ZZZZ", current_price: null, market_value: 1000, unrealized_pnl: 0 }),
        ])}
      />,
    );

    expect(screen.getByTestId("position-price-ZZZZ")).toHaveTextContent("—");
    expect(screen.getByTestId("position-pnl-ZZZZ")).toHaveTextContent("—");
    expect(screen.getByTestId("position-change-ZZZZ")).toHaveTextContent("—");
    const row = screen.getByTestId("position-ZZZZ");
    expect(within(row).queryByText("$0.00")).not.toBeInTheDocument();
    expect(row.textContent).not.toContain("NaN");
  });

  it("prices from the stream rather than from the fetched payload", () => {
    // The payload's price was true when the portfolio was fetched and is stale
    // by the next tick — this cell is on the price-driven side of the design's
    // rendering split.
    renderWithStream(<PositionsTable portfolio={account([position({ ticker: "AAPL", current_price: 110 })])} />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 130 })));

    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent("$130.00");
    // 10 shares bought at 100, now 130: +$300.00 and +30.00%.
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveTextContent("+$300.00");
    expect(screen.getByTestId("position-change-AAPL")).toHaveTextContent("+30.00%");
  });

  it("falls back to the payload's price for a ticker the stream is not quoting", () => {
    // A position in a symbol removed from the watchlist keeps its server-side
    // price (D3) but no longer streams. Rendering a dash there would be wrong:
    // the price is known, it just is not live.
    renderWithStream(<PositionsTable portfolio={account([position({ ticker: "AAPL", current_price: 110 })])} />);

    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent("$110.00");
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveTextContent("+$100.00");
  });

  it("signs a loss and colours it", () => {
    renderWithStream(<PositionsTable portfolio={account([position({ ticker: "AAPL" })])} />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 90 })));

    const pnl = screen.getByTestId("position-pnl-AAPL");
    expect(pnl).toHaveTextContent("-$100.00");
    expect(pnl.className).toContain("text-down");
  });

  it("computes P&L against avg_cost rather than trusting the payload's number", () => {
    // The payload's unrealized_pnl was computed at fetch time. If the table
    // rendered it directly, every tick would move the price column while the
    // P&L column sat still — the bug is invisible unless the two disagree, so
    // this fixture makes them disagree.
    renderWithStream(
      <PositionsTable portfolio={account([position({ ticker: "AAPL", unrealized_pnl: 99999 })])} />,
    );

    act(() => stream().emit(quote({ ticker: "AAPL", price: 120 })));

    expect(screen.getByTestId("position-pnl-AAPL")).toHaveTextContent("+$200.00");
  });
});
