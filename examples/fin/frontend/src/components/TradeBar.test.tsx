import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "@/components/TradeBar";
import { stubApi } from "@/test/api";

const FILL = {
  trade_id: "t1",
  ticker: "AAPL",
  side: "buy" as const,
  quantity: 5,
  price: 190.5,
  total: 952.5,
  cash_balance: 9047.5,
  position_quantity: 5,
  position_avg_cost: 190.5,
  executed_at: "2026-08-15T12:00:00Z",
};

function order(ticker: string, quantity: string) {
  fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: ticker } });
  fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: quantity } });
}

describe("submitting an order (check C5)", () => {
  it("posts the order and refetches the portfolio exactly once", async () => {
    // "Exactly once" is the check. A component that refetches on every render,
    // or twice per fill, still shows the right numbers — and hides that the
    // refetch is tied to the mutation rather than to a timer.
    const api = stubApi([{ match: "/api/portfolio/trade", method: "POST", body: FILL }]);
    const onFilled = vi.fn();
    render(<TradeBar onFilled={onFilled} />);

    order("aapl", "5");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(api.to("/api/portfolio/trade")).toHaveLength(1);
    expect(api.to("/api/portfolio/trade")[0].body).toEqual({ ticker: "aapl", side: "buy", quantity: 5 });
    expect(onFilled).toHaveBeenCalledTimes(1);
  });

  it("sends the side the user pressed", async () => {
    const api = stubApi([{ match: "/api/portfolio/trade", method: "POST", body: { ...FILL, side: "sell" } }]);
    render(<TradeBar onFilled={vi.fn()} />);

    order("AAPL", "2");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sell" }));
    });

    expect(api.to("/api/portfolio/trade")[0].body).toMatchObject({ side: "sell" });
  });

  it("confirms the fill at the price it actually filled at", async () => {
    // Market orders fill at the current price, not at whatever was on screen
    // when the button was pressed, so the confirmation quotes the response.
    stubApi([{ match: "/api/portfolio/trade", method: "POST", body: FILL }]);
    render(<TradeBar onFilled={vi.fn()} />);

    order("AAPL", "5");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(screen.getByTestId("trade-confirmation")).toHaveTextContent("Bought 5 AAPL @ $190.50 — total $952.50");
  });
});

describe("a refused order (check C5)", () => {
  it("renders the server's detail sentence and keeps the inputs", async () => {
    // Both halves matter. The sentence carries the numbers the user needs, and
    // clearing the inputs would make them retype an order that was refused for
    // a reason they can fix by changing one field.
    const api = stubApi([
      {
        match: "/api/portfolio/trade",
        method: "POST",
        status: 400,
        body: { detail: "Insufficient cash: need $12,000.00, have $10,000.00" },
      },
    ]);
    const onFilled = vi.fn();
    render(<TradeBar onFilled={onFilled} />);

    order("AAPL", "60");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(screen.getByTestId("trade-error")).toHaveTextContent("Insufficient cash: need $12,000.00, have $10,000.00");
    expect(screen.getByLabelText("Ticker")).toHaveValue("AAPL");
    expect(screen.getByLabelText("Quantity")).toHaveValue("60");
    // A rejection changed nothing, so refetching would say the panel moved.
    expect(onFilled).not.toHaveBeenCalled();
    expect(api.to("/api/portfolio/trade")).toHaveLength(1);
  });

  it("clears a stale error once the next order fills", async () => {
    const api = stubApi([
      { match: "/api/portfolio/trade", method: "POST", status: 409, body: { detail: "No price available for AAPL yet" } },
    ]);
    render(<TradeBar onFilled={vi.fn()} />);

    order("AAPL", "5");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });
    expect(screen.getByTestId("trade-error")).toBeInTheDocument();

    api.serve([{ match: "/api/portfolio/trade", method: "POST", body: FILL }]);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(screen.queryByTestId("trade-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("trade-confirmation")).toBeInTheDocument();
  });
});

describe("what never reaches the server", () => {
  it("refuses to submit an empty, zero, negative or non-numeric quantity", async () => {
    // The service refuses all of these too (that is where the rule lives, D5),
    // but a disabled button says so without a round trip.
    stubApi([{ match: "/api/portfolio/trade", method: "POST", body: FILL }]);
    render(<TradeBar onFilled={vi.fn()} />);

    for (const quantity of ["", "0", "-5", "abc"]) {
      order("AAPL", quantity);
      expect(screen.getByRole("button", { name: "Buy" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Sell" })).toBeDisabled();
    }

    order("AAPL", "1.5");
    expect(screen.getByRole("button", { name: "Buy" })).toBeEnabled();
  });

  it("refuses to submit without a ticker", () => {
    stubApi([{ match: "/api/portfolio/trade", method: "POST", body: FILL }]);
    render(<TradeBar onFilled={vi.fn()} />);

    order("   ", "5");

    expect(screen.getByRole("button", { name: "Buy" })).toBeDisabled();
  });
});
