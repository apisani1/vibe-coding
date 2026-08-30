import { act, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Header } from "@/components/Header";
import { FakeEventSource, renderWithStream, stream } from "@/test/priceStream";
import type { Portfolio } from "@/lib/types";

/**
 * An account that could actually exist.
 *
 * The totals summed, which is what I checked; the *positions list* did not —
 * `positions: []` beside a positions value of 1,900 is a state the backend
 * cannot emit. `Header` reads only the scalars, so nothing rested on it, which
 * is precisely how this checkpoint's P&L fixture went unnoticed until it was
 * load-bearing.
 */
const PORTFOLIO: Portfolio = {
  cash_balance: 8500.25,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 149.975,
      current_price: 190,
      market_value: 1900,
      unrealized_pnl: 400.25,
      unrealized_pnl_percent: 26.69,
    },
  ],
  positions_value: 1900,
  total_value: 10400.25,
  unrealized_pnl: 400.25,
};

function status() {
  return screen.getByTestId("connection-status").textContent;
}

function dotClasses() {
  return screen.getByTestId("connection-dot").className;
}

describe("connection indicator (check C4)", () => {
  it("does not claim connected before the stream has ever opened", () => {
    // The failure worth guarding: a dot driven by "the EventSource object
    // exists" is green against a backend that is not running.
    renderWithStream(<Header />);

    expect(status()).toContain("connecting");
    expect(status()).not.toContain("connected");
    expect(dotClasses()).toContain("bg-accent-yellow");
  });

  it("turns green only once the server accepts the connection", () => {
    renderWithStream(<Header />);

    act(() => stream().open());

    expect(status()).toContain("connected");
    expect(dotClasses()).toContain("bg-up");
  });

  it("turns yellow while a dropped stream is retrying", () => {
    renderWithStream(<Header />);

    act(() => stream().open());
    act(() => stream().fail(FakeEventSource.CONNECTING));

    expect(status()).toContain("reconnecting");
    expect(dotClasses()).toContain("bg-accent-yellow");
  });

  it("turns red when the browser gives up", () => {
    renderWithStream(<Header />);

    act(() => stream().open());
    act(() => stream().fail(FakeEventSource.CLOSED));

    expect(status()).toContain("disconnected");
    expect(dotClasses()).toContain("bg-down");
  });
});

describe("totals", () => {
  it("renders a dash, not $0.00, before the portfolio has loaded", () => {
    // $0.00 would read as a wiped-out account during the first paint.
    renderWithStream(<Header />);

    expect(screen.getByTestId("header-total")).toHaveTextContent("—");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("—");
  });

  it("renders total value and cash as money", () => {
    renderWithStream(<Header portfolio={PORTFOLIO} />);

    expect(screen.getByTestId("header-total")).toHaveTextContent("$10,400.25");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,500.25");
  });
});
