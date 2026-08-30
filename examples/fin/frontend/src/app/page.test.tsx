import { describe, expect, it } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import Page from "./page";
import { stubApi } from "@/test/api";
import { FakeEventSource, installFakeEventSource, quote, stream } from "@/test/priceStream";

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

const ACCOUNT = {
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
};

/**
 * Account fetches only — `/api/portfolio` exactly, never `/api/portfolio/history`.
 *
 * Check C5 counts refetches of the *account*, and once the P&L chart started
 * polling the history endpoint a substring match over `/api/portfolio` counted
 * both. A count that silently includes a second endpoint is a count that proves
 * nothing.
 */
function accountFetches(api: ReturnType<typeof stubApi>) {
  return api.calls.filter((call) => call.url.endsWith("/api/portfolio") && call.method === "GET");
}

/**
 * Both endpoints the page fetches on mount, so nothing renders an error state.
 *
 * The watchlist is not empty: membership comes from this payload and only from
 * this payload, so a test that wants a row has to put the ticker here — a
 * streamed quote alone is deliberately not enough (see `Watchlist`).
 */
function stubPageApi() {
  // `/api/portfolio/history` first: routes match by substring in order, so the
  // broader `/api/portfolio` would otherwise answer the history request with a
  // portfolio object — which is exactly what happened when the charts landed.
  return stubApi([
    { match: "/api/portfolio/history", body: [] },
    { match: "/api/portfolio", body: ACCOUNT },
    { match: "/api/watchlist", body: [{ ticker: "AAPL", added_at: "2026-08-15T12:00:00Z", quote: null }] },
  ]);
}

describe("the page", () => {
  it("renders every region a later checkpoint fills", async () => {
    stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    expect(screen.getByRole("heading", { level: 1, name: "FinAlly" })).toBeInTheDocument();
    for (const region of ["Watchlist", "Chart", "Trade", "Positions", "Total value", "Allocation", "Assistant"]) {
      expect(screen.getByRole("region", { name: region })).toBeInTheDocument();
    }
  });

  it("opens the stream once for the whole page, not once per consumer", async () => {
    // D17, asserted where it can actually regress: the page mounts the header,
    // the watchlist and the positions table, and each reads the same context.
    stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("feeds the header and the watchlist from that one stream", async () => {
    stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    act(() => stream().open());
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190, session_open: 180 })));

    expect(screen.getByTestId("connection-status")).toHaveTextContent("connected");
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
  });
});

describe("the provider", () => {
  it("is what makes the page mountable at all", async () => {
    // Rewritten after review. The first version rendered `renderWithStream(<div
    // />)`, which wraps in the provider by construction and never mentions
    // `Page` — so its comment, claiming it "fails if a future edit moves the
    // provider out of the page", was false: removing the provider from page.tsx
    // left it green while failing three other tests. This body renders the real
    // page, so it fails for the reason it states.
    stubPageApi();
    installFakeEventSource();

    expect(() => render(<Page />)).not.toThrow();
    await act(async () => {});
  });
});

describe("the fetched account (checkpoint 12)", () => {
  it("supplies the header's totals and the positions table", async () => {
    // CP11 left `Header`'s portfolio prop with no supplier and the positions
    // panel a placeholder; this is the assertion that they are wired at all.
    stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    expect(screen.getByTestId("header-cash")).toHaveTextContent("$9,047.50");
    expect(screen.getByTestId("header-total")).toHaveTextContent("$10,000.00");
    expect(screen.getByTestId("position-AAPL")).toBeInTheDocument();
  });

  it("fetches the account exactly once on load", async () => {
    // Two mounted consumers of the same data would fetch twice, and check C5's
    // "exactly one refetch per trade" would then be measured against a moving
    // baseline.
    const api = stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    expect(accountFetches(api)).toHaveLength(1);
  });
});

describe("the wire between a fill and the refetch (check C5, end to end)", () => {
  it("refetches the account exactly once when a trade fills", async () => {
    // C5's headline claim was proved in two halves — TradeBar calls onFilled
    // once, usePortfolio.refresh() fetches once — with the prop between them
    // untested. Deleting `onFilled={() => void refresh()}` from page.tsx left
    // all 93 tests green. This drives a real order through the real page.
    const api = stubApi([
      { match: "/api/portfolio/trade", method: "POST", body: FILL },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    expect(accountFetches(api)).toHaveLength(1);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });
      fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(api.to("/api/portfolio/trade")).toHaveLength(1);
    expect(accountFetches(api)).toHaveLength(2);
  });

  it("does not refetch when the order is refused", async () => {
    const api = stubApi([
      {
        match: "/api/portfolio/trade",
        method: "POST",
        status: 400,
        body: { detail: "Insufficient cash: need $12,000.00, have $10,000.00" },
      },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });
      fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "600" } });
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(screen.getByTestId("trade-error")).toHaveTextContent("Insufficient cash");
    expect(accountFetches(api)).toHaveLength(1);
  });
});

describe("a failed account refresh", () => {
  it("keeps the last good numbers and says they may be stale", async () => {
    // Half of "stale-but-labelled" was missing: nothing rendered the error, so
    // a refresh that failed right after a fill left a green confirmation beside
    // unchanged cash with no indication the numbers were old.
    const api = stubApi([
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    expect(screen.queryByTestId("portfolio-error")).not.toBeInTheDocument();

    api.serve([
      { match: "/api/portfolio/trade", method: "POST", body: FILL },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", status: 503, body: { detail: "database is locked" } },
      { match: "/api/watchlist", body: [] },
    ]);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });
      fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(screen.getByTestId("portfolio-error")).toHaveTextContent("database is locked");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$9,047.50");
  });
});

describe("the charts are actually mounted (checkpoint 13)", () => {
  it("renders all three, fed by the page's own state", async () => {
    // Every one of these mounts could be deleted with 131 tests still green:
    // the components were tested in isolation and the page was tested for its
    // panel names, and nothing joined the two. Same shape as the CP12
    // rejection, where the fill→refetch prop was proved in halves.
    const api = stubApi([
      { match: "/api/portfolio/history", body: [{ total_value: 10000, recorded_at: "2026-08-16T12:00:00Z" }] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [{ ticker: "AAPL", added_at: "2026-08-16T12:00:00Z", quote: null }] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    // Heatmap: ACCOUNT holds one position, so it is past its empty state.
    expect(screen.getByTestId("heatmap")).toHaveAttribute("data-cells", "1");
    // P&L chart: one snapshot fetched through the page.
    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "1");
    // Twice on a cold page, and that is the intended behaviour: once on mount
    // and once when the account resolves. The count is asserted rather than
    // waved at, so a chart that started polling on every render would fail.
    expect(api.to("/api/portfolio/history")).toHaveLength(2);
    // Main chart: mounted, and honest about having no selection yet.
    expect(screen.getByTestId("main-chart-empty")).toBeInTheDocument();
  });

  it("charts the ticker whose watchlist row is clicked", async () => {
    // The selection has to survive the trip through the page's context, not
    // just through a two-component test fixture.
    stubPageApi();
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });

    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-series", "AAPL");
  });

  it("hands the P&L chart the account, so a fill refetches the history too", async () => {
    // The prop itself: `<PnlChart portfolio={null} />` survived every test.
    //
    // The post-fill fixture is backend-realistic on purpose, and the first
    // version of this test was not: orders fill at the cached mark, so cash
    // falls by exactly what the position gains and **total value does not
    // move** (10,000.00 → 10,000.00, measured against the real service). The
    // earlier fixture invented a total of 9,500 that the API cannot produce and
    // that no arithmetic supports, and it was the only reason a chart keyed on
    // `total_value` looked wired. This one refetches only if the chart follows
    // the account itself.
    const api = stubApi([
      { match: "/api/portfolio/trade", method: "POST", body: FILL },
      { match: "/api/portfolio/history", body: [{ total_value: 10000, recorded_at: "2026-08-16T12:00:00Z" }] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    expect(api.to("/api/portfolio/history")).toHaveLength(2);

    api.serve([
      { match: "/api/portfolio/trade", method: "POST", body: FILL },
      { match: "/api/portfolio/history", body: [{ total_value: 9500, recorded_at: "2026-08-16T12:01:00Z" }] },
      {
        match: "/api/portfolio",
        // Cash 10,000 → 9,047.50; one AAPL position worth 952.50; total still
        // 10,000.00. Exactly what `execute_trade` produces for 5 @ 190.50.
        body: {
          cash_balance: 9047.5,
          positions: ACCOUNT.positions,
          positions_value: 952.5,
          total_value: 10000,
          unrealized_pnl: 0,
        },
      },
      { match: "/api/watchlist", body: [] },
    ]);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });
      fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
      fireEvent.click(screen.getByRole("button", { name: "Buy" }));
    });

    expect(api.to("/api/portfolio/history")).toHaveLength(3);
  });
});

describe("the assistant panel (checkpoint 14)", () => {
  function stubWithChat(chatBody: unknown, extra: Parameters<typeof stubApi>[0] = []) {
    return stubApi([
      ...extra,
      { match: "/api/chat/messages", body: [] },
      { match: "/api/chat", method: "POST", body: chatBody },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [{ ticker: "AAPL", added_at: "2026-08-16T12:00:00Z", quote: null }] },
    ]);
  }

  async function send(text: string) {
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Message"), { target: { value: text } });
      fireEvent.submit(screen.getByLabelText("Message").closest("form")!);
    });
  }

  it("is mounted and loads the transcript", async () => {
    // CP13 was rejected for mounting components nowhere; this is the join.
    const api = stubWithChat({ message: "hi", actions: [] });
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });

    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(api.to("/api/chat/messages")).toHaveLength(1);
  });

  it("re-reads the account and the watchlist after the assistant does something", async () => {
    // D5: the assistant trades through the same service functions a person
    // does, so a chat fill moves cash and a chat add changes membership. If the
    // rest of the page did not re-read, the transcript would assert a change
    // the panels beside it deny.
    const api = stubWithChat({
      message: "Bought them, and added NVDA.",
      actions: [
        { type: "trade", ticker: "AAPL", side: "buy", quantity: 5, status: "filled", price: 190.5 },
        { type: "watchlist", ticker: "NVDA", action: "add", status: "applied" },
      ],
    });
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    const accountBefore = accountFetches(api).length;
    const watchlistBefore = api.to("/api/watchlist").length;

    await send("buy 5 AAPL and watch NVDA");

    expect(accountFetches(api)).toHaveLength(accountBefore + 1);
    expect(api.to("/api/watchlist").length).toBe(watchlistBefore + 1);
  });

  it("re-reads nothing when every action was refused", async () => {
    const api = stubWithChat({
      message: "I could not do that.",
      actions: [{ type: "trade", ticker: "AAPL", side: "buy", quantity: 600, status: "rejected", reason: "Insufficient cash" }],
    });
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    const accountBefore = accountFetches(api).length;
    const watchlistBefore = api.to("/api/watchlist").length;

    await send("buy 600 AAPL");

    expect(screen.getByTestId("chat-action-rejected")).toHaveTextContent("Insufficient cash");
    expect(accountFetches(api)).toHaveLength(accountBefore);
    expect(api.to("/api/watchlist").length).toBe(watchlistBefore);
  });
});

describe("a chat-driven watchlist removal (the CP14 blocker)", () => {
  it("stops charting a symbol the assistant removed", async () => {
    // The assistant removes through the same service functions a person does
    // (D5) but reaches useWatchlist only through refresh, so the guard that
    // lived in remove() guarded one caller instead of the resource. The row
    // vanished while the main chart kept drawing AAPL, frozen, for the session.
    const api = stubApi([
      { match: "/api/chat/messages", body: [] },
      {
        match: "/api/chat",
        method: "POST",
        body: {
          message: "Removed it.",
          actions: [{ type: "watchlist", ticker: "AAPL", action: "remove", status: "applied" }],
        },
      },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [{ ticker: "AAPL", added_at: "2026-08-16T12:00:00Z", quote: null }] },
    ]);
    installFakeEventSource();
    await act(async () => {
      render(<Page />);
    });
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-series", "AAPL");

    // Same routes, but the watchlist is now empty — the server has removed it.
    api.serve([
      { match: "/api/chat/messages", body: [] },
      {
        match: "/api/chat",
        method: "POST",
        body: {
          message: "Removed it.",
          actions: [{ type: "watchlist", ticker: "AAPL", action: "remove", status: "applied" }],
        },
      },
      { match: "/api/portfolio/history", body: [] },
      { match: "/api/portfolio", body: ACCOUNT },
      { match: "/api/watchlist", body: [] },
    ]);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Message"), { target: { value: "stop watching AAPL" } });
      fireEvent.submit(screen.getByLabelText("Message").closest("form")!);
    });

    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();
    expect(screen.getByTestId("main-chart-empty")).toBeInTheDocument();
  });
});
