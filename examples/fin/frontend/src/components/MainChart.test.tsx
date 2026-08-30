import { act, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { MainChart } from "@/components/MainChart";
import { Watchlist } from "@/components/Watchlist";
import { stubApi } from "@/test/api";
import { mountWithStream, quote, renderWithStream, stream } from "@/test/priceStream";

function watched(...tickers: string[]) {
  return tickers.map((ticker) => ({ ticker, added_at: "2026-08-16T12:00:00Z", quote: null }));
}

describe("with nothing selected", () => {
  it("says so rather than drawing an empty chart", () => {
    renderWithStream(<MainChart />);

    expect(screen.getByTestId("main-chart-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("main-chart")).not.toBeInTheDocument();
  });

  it("still says so while prices are streaming", () => {
    // The version above passes on a chart that quietly falls back to whichever
    // ticker happens to be first in the quote map — with no quotes there is
    // nothing to fall back to. Measured: that mutant survived the whole suite
    // until this test existed. "No selection" is a state, not an absence of
    // data.
    renderWithStream(<MainChart />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });

    expect(screen.getByTestId("main-chart-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("main-chart")).not.toBeInTheDocument();
  });
});

describe("selection drives the series (check C6)", () => {
  beforeEach(() => {
    stubApi([{ match: "/api/watchlist", body: watched("AAPL", "MSFT") }]);
  });

  it("charts the ticker whose row was clicked, and switches when another is", async () => {
    // C6's assertion, driven through the real watchlist rather than by calling
    // `select` directly: the claim is that *clicking a row* changes the series,
    // and a test that reached into the hook would pass with the row's onClick
    // deleted.
    await mountWithStream(
      <>
        <Watchlist />
        <MainChart />
      </>,
    );
    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });

    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-series", "AAPL");

    act(() => {
      within(screen.getByTestId("watchlist-row-MSFT")).getByRole("button", { pressed: false }).click();
    });
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-series", "MSFT");
  });

  it("starts the new series from the selected ticker's own history, not the previous one's", async () => {
    // The two-tier buffer's promise (D22): selecting seeds from the short
    // buffer, so the chart opens with the last minute of *this* instrument.
    // Without the reseed the chart would carry the old ticker's points under a
    // new label — a plausible-looking lie.
    await mountWithStream(
      <>
        <Watchlist />
        <MainChart />
      </>,
    );
    act(() => {
      for (const price of [10, 11, 12]) {
        stream().emit(quote({ ticker: "AAPL", price }));
      }
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });

    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-points", "3");

    act(() => {
      within(screen.getByTestId("watchlist-row-MSFT")).getByRole("button", { pressed: false }).click();
    });
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-points", "1");
  });

  it("grows as the selected ticker ticks, and ignores the others", async () => {
    await mountWithStream(
      <>
        <Watchlist />
        <MainChart />
      </>,
    );
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 191 }));
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });

    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-points", "2");
  });
});

describe("the header price", () => {
  it("shows the newest point, not the oldest", async () => {
    // `selectedHistory[0]` survived the whole suite: the number a trader reads
    // beside the chart was pinned by nothing.
    stubApi([{ match: "/api/watchlist", body: watched("AAPL") }]);
    await mountWithStream(
      <>
        <Watchlist />
        <MainChart />
      </>,
    );
    act(() => {
      for (const price of [100, 200, 300]) {
        stream().emit(quote({ ticker: "AAPL", price }));
      }
    });

    act(() => {
      within(screen.getByTestId("watchlist-row-AAPL")).getByRole("button", { pressed: false }).click();
    });

    expect(screen.getByTestId("main-chart-price")).toHaveTextContent("$300.00");
  });
});

describe("a selected ticker with no ticks yet", () => {
  it("says it is waiting rather than claiming nothing is selected", async () => {
    // Three distinguishable states, and conflating the last two is how a chart
    // ends up looking broken on a symbol that was only just added.
    stubApi([{ match: "/api/watchlist", body: watched("NVDA") }]);
    await mountWithStream(
      <>
        <Watchlist />
        <MainChart />
      </>,
    );

    act(() => {
      within(screen.getByTestId("watchlist-row-NVDA")).getByRole("button", { pressed: false }).click();
    });

    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-series", "NVDA");
    expect(screen.getByTestId("main-chart-waiting")).toBeInTheDocument();
    expect(screen.queryByTestId("main-chart-empty")).not.toBeInTheDocument();
  });
});
