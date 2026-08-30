import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FLASH_MS, Watchlist } from "@/components/Watchlist";
import { mountWithStream, quote, stream } from "@/test/priceStream";
import { stubApi } from "@/test/api";

/**
 * Entries as `GET /api/watchlist` returns them, with no quote yet.
 *
 * Membership comes from the list and **only** from the list (see the component
 * docstring): a streamed quote is not a membership claim, because the producer
 * keeps pricing held tickers after they are unwatched and the cache never
 * evicts. Every price test below therefore seeds the list first and then lets
 * the stream supply the numbers.
 */
function watched(...tickers: string[]) {
  return tickers.map((ticker) => ({ ticker, added_at: "2026-08-15T12:00:00Z", quote: null }));
}

beforeEach(() => {
  stubApi([{ match: "/api/watchlist", body: watched("AAPL", "MSFT") }]);
});

afterEach(() => {
  vi.useRealTimers();
});

function row(ticker: string) {
  return screen.getByTestId(`watchlist-row-${ticker}`);
}

/** The flash overlay, or null when the row is not flashing. */
function flashOf(ticker: string) {
  return screen.queryByTestId(`flash-${ticker}`);
}

describe("change percentage (D19, check C3)", () => {
  it("derives the change from session_open, not from the previous tick", async () => {
    // THE discriminating fixture. The two baselines are deliberately far apart:
    //   from session_open 100 → +100.00%
    //   from previous_price 199.99 → +0.01%
    // A fixture where the two agree would pass under both implementations and
    // prove nothing, which is exactly the check-that-cannot-fail this project
    // has been bitten by four times.
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 200, previous_price: 199.99, session_open: 100 }));
    });

    expect(within(row("AAPL")).getByText("+100.00%")).toBeInTheDocument();
    expect(screen.queryByText("+0.01%")).not.toBeInTheDocument();
  });

  it("renders exactly 0.00% at the session open", async () => {
    // Honest rather than a placeholder: on the first tick of a process the
    // change really is zero (D19).
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 150, previous_price: 149, session_open: 150 }));
    });

    expect(within(row("AAPL")).getByText("0.00%")).toBeInTheDocument();
  });

  it("signs a fall negative", async () => {
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 90, session_open: 100 }));
    });

    expect(within(row("AAPL")).getByText("-10.00%")).toBeInTheDocument();
  });
});

describe("price flash (check C4)", () => {
  it("adds the up class on a rise and drops it again", async () => {
    // Both halves. Asserting only the add lets a row that is permanently green
    // pass — and a permanently green row is worse than no flash at all,
    // because it reads as a price that just moved.
    vi.useFakeTimers();
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 100, session_open: 100 })));
    expect(flashOf("AAPL")).toBeNull();

    act(() => stream().emit(quote({ ticker: "AAPL", price: 101, session_open: 100 })));
    expect(flashOf("AAPL")!.className).toContain("flash-up");

    act(() => vi.advanceTimersByTime(FLASH_MS));
    expect(flashOf("AAPL")).toBeNull();
  });

  it("adds the down class on a fall", async () => {
    vi.useFakeTimers();
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 100, session_open: 100 })));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 99, session_open: 100 })));

    expect(flashOf("AAPL")!.className).toContain("flash-down");
    expect(flashOf("AAPL")!.className).not.toContain("flash-up");
  });

  it("restarts the animation on a second move in the same direction", async () => {
    // Found by the overseer, not by me: setting the same class string again
    // changes no DOM attribute, so the CSS animation is not restarted and a
    // steadily rising ticker flashes once and then goes quiet while it keeps
    // rising. The element identity is the assertion — a class-only check passes
    // under exactly the implementation this test exists to reject.
    vi.useFakeTimers();
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 100, session_open: 100 })));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 101, session_open: 100 })));
    const first = flashOf("AAPL");

    act(() => vi.advanceTimersByTime(FLASH_MS / 2));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 102, session_open: 100 })));
    const second = flashOf("AAPL");

    expect(second!.className).toContain("flash-up");
    expect(second).not.toBe(first);
  });

  it("does not flash on the first frame, however the producer labelled it", async () => {
    // The stream's first frame is a full snapshot, and its `direction` was
    // computed by the producer at some earlier tick. A row that trusted that
    // field would flash every ticker on connect — and again on every reconnect
    // — for movement the user never saw.
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 100, previous_price: 90, session_open: 90, direction: "up" }));
    });

    expect(flashOf("AAPL")).toBeNull();
  });

  it("keeps the JavaScript timeout and the CSS animation on one duration", async () => {
    // They were coupled by a comment: mutating FLASH_MS to 5000 passed every
    // test, because C4 advances timers by the constant it is testing. It
    // matters on the reduced-motion path, where the class holds a static tint
    // for exactly FLASH_MS with no animation to end it.
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

    const durations = [...css.matchAll(/animation: flash-(?:up|down) (\d+)ms/g)].map((match) => Number(match[1]));

    expect(durations).toHaveLength(2);
    expect(durations.every((duration) => duration === FLASH_MS)).toBe(true);
  });

  it("does not flash a row whose price did not move", async () => {
    vi.useFakeTimers();
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 100, session_open: 100 }));
      stream().emit(quote({ ticker: "MSFT", price: 400, session_open: 400 }));
    });
    act(() => stream().emit(quote({ ticker: "MSFT", price: 401, session_open: 400 })));

    expect(flashOf("MSFT")!.className).toContain("flash-up");
    expect(flashOf("AAPL")).toBeNull();
  });
});

describe("rows", () => {
  it("says the list is empty, not that it is waiting for prices", async () => {
    // The copy used to read "Waiting for the price stream…", which was true
    // under the union and is a lie now: an empty list means nothing is
    // watched, and no amount of streaming will fill it.
    stubApi([{ match: "/api/watchlist", body: [] }]);
    await mountWithStream(<Watchlist />);

    expect(screen.getByText(/nothing on the watchlist/i)).toBeInTheDocument();
    expect(screen.queryByTestId("watchlist")).not.toBeInTheDocument();
  });

  it("renders rows sorted, however the server ordered them", async () => {
    // The component's docstring claims this, and nothing pinned it: rows must
    // not reorder underneath a click when a refetch returns a different order.
    stubApi([{ match: "/api/watchlist", body: watched("MSFT", "AAPL", "NVDA") }]);
    await mountWithStream(<Watchlist />);

    const order = screen.getAllByTestId(/watchlist-row-/).map((element) => element.dataset.testid);
    expect(order).toEqual(["watchlist-row-AAPL", "watchlist-row-MSFT", "watchlist-row-NVDA"]);
  });

  it("lists tickers in a stable order regardless of arrival order", async () => {
    // Rows must not reorder underneath a click when a quote arrives.
    await mountWithStream(<Watchlist />);

    act(() => {
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
      stream().emit(quote({ ticker: "MSFT", price: 401 }));
    });

    const tickers = screen.getAllByTestId(/watchlist-row-/).map((element) => element.dataset.testid);
    expect(tickers).toEqual(["watchlist-row-AAPL", "watchlist-row-MSFT"]);
  });

  it("renders the price as money", async () => {
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 1234.5 })));

    expect(within(row("AAPL")).getByText("$1,234.50")).toBeInTheDocument();
  });

  it("selects a ticker when its row is clicked", async () => {
    // Selection is what the deep buffer (D22) is for; without a way to set it,
    // the second tier would be untestable dead code.
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    const button = within(row("AAPL")).getByRole("button", { pressed: false });
    expect(button).toHaveAttribute("aria-pressed", "false");

    act(() => button.click());

    expect(button).toHaveAttribute("aria-pressed", "true");
  });
});

describe("membership (checkpoint 12)", () => {
  it("shows a watched ticker that has no quote yet", async () => {
    // The reason membership is fetched at all: under the Massive source the
    // first quote for a newly added symbol can be 15 seconds away, and an
    // invisible row reads as "the add failed".
    stubApi([{ match: "/api/watchlist", body: [{ ticker: "NVDA", added_at: "2026-08-15T12:00:00Z", quote: null }] }]);
    await mountWithStream(<Watchlist />);

    expect(row("NVDA")).toBeInTheDocument();
    // Both the price and the change render a dash — an unpriced row must show
    // neither a fabricated $0.00 nor a 0.00% that reads as "flat today".
    expect(within(row("NVDA")).getAllByText("—")).toHaveLength(2);
  });

  it("prices a watched ticker from the stream, not from the payload it was seeded with", async () => {
    // The seed is a snapshot; the stream is the authority. If this rendered the
    // seed, every price would freeze at whatever the page-load fetch returned.
    stubApi([
      {
        match: "/api/watchlist",
        body: [{ ticker: "AAPL", added_at: "2026-08-15T12:00:00Z", quote: { ...quote({ ticker: "AAPL", price: 1 }) } }],
      },
    ]);
    await mountWithStream(<Watchlist />);

    expect(within(row("AAPL")).getByText("$1.00")).toBeInTheDocument();

    act(() => stream().emit(quote({ ticker: "AAPL", price: 2 })));

    expect(within(row("AAPL")).getByText("$2.00")).toBeInTheDocument();
  });

  it("adds a symbol and clears the box", async () => {
    const api = stubApi([
      { match: "/api/watchlist", method: "POST", body: { ticker: "NVDA", added_at: "now", quote: null } },
      { match: "/api/watchlist", body: watched("NVDA") },
    ]);
    await mountWithStream(<Watchlist />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Add ticker"), { target: { value: "nvda" } });
      fireEvent.click(screen.getByRole("button", { name: "Add" }));
    });

    expect(api.to("/api/watchlist").filter((call) => call.method === "POST")).toHaveLength(1);
    expect(api.to("/api/watchlist")[1].body).toEqual({ ticker: "nvda" });
    expect(screen.getByLabelText("Add ticker")).toHaveValue("");
  });

  it("keeps a rejected symbol in the box and shows the server's reason", async () => {
    // Same rule as the trade bar: the user has to be able to fix what they
    // typed, and 422 means the string is wrong — not that they changed their
    // mind about adding something.
    stubApi([
      { match: "/api/watchlist", method: "POST", status: 422, body: { detail: "'!!' is not a valid ticker symbol" } },
      { match: "/api/watchlist", body: [] },
    ]);
    await mountWithStream(<Watchlist />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Add ticker"), { target: { value: "!!" } });
      fireEvent.click(screen.getByRole("button", { name: "Add" }));
    });

    expect(screen.getByTestId("watchlist-error")).toHaveTextContent("is not a valid ticker symbol");
    expect(screen.getByLabelText("Add ticker")).toHaveValue("!!");
  });

  it("removes a symbol and stops rendering its streamed price", async () => {
    // The CP11 approval's carried condition. The client maps only grow and the
    // server's PriceCache never evicts, so a row that came from the stream
    // survives its own removal unless removal explicitly forgets it. Asserting
    // only "the API was called" would pass on exactly that bug.
    const api = stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: watched("AAPL") },
    ]);
    await mountWithStream(<Watchlist />);
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    expect(row("AAPL")).toBeInTheDocument();
    api.serve([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Remove AAPL" }));
    });

    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();
  });

  it("keeps the row when the server refuses the removal", async () => {
    stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 404, body: { detail: "'AAPL' is not on the watchlist" } },
      { match: "/api/watchlist", body: watched("AAPL") },
    ]);
    await mountWithStream(<Watchlist />);
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Remove AAPL" }));
    });

    expect(row("AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-error")).toHaveTextContent("not on the watchlist");
  });
});

describe("a quote is not a membership claim (the CP12 blocker)", () => {
  it("does not resurrect a removed ticker when the stream keeps quoting it", async () => {
    // The overseer's probe, kept as a test. Two permanent reasons this happens,
    // neither of them a race: the producer prices watchlist ∪ open positions
    // (D3), so a held symbol streams forever after it is unwatched; and
    // PriceCache never evicts while the SSE endpoint opens every connection
    // with a full snapshot, so a reload republishes symbols removed long ago.
    // The first version of this component unioned the list with the streamed
    // tickers, and the row came back on the next frame — permanently, since
    // clicking × again only produced a 404.
    const api = stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: watched("AAPL") },
    ]);
    await mountWithStream(<Watchlist />);
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    api.serve([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Remove AAPL" }));
    });
    act(() => stream().emit(quote({ ticker: "AAPL", price: 191 })));

    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();
  });

  it("does not show a held-but-unwatched ticker that the producer still prices", async () => {
    // The steady state of the case above: an open position in a symbol that is
    // not on the watchlist. It belongs in the positions table, not here.
    stubApi([{ match: "/api/watchlist", body: watched("MSFT") }]);
    await mountWithStream(<Watchlist />);

    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();
    expect(row("MSFT")).toBeInTheDocument();
  });
});

describe("what the user sees while a removal is in flight", () => {
  it("drops the row immediately rather than waiting for the refetch", async () => {
    // Pinned with a gated response, because without one the refetch settles
    // inside the same act() flush and the intermediate render cannot be
    // observed at all — the first version of this guard passed with the
    // optimistic drop deleted, which makes it no guard.
    let release: () => void = () => {};
    const refetch = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: watched("AAPL") },
    ]);
    await mountWithStream(<Watchlist />);
    expect(row("AAPL")).toBeInTheDocument();

    api.serve([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [], gate: refetch },
    ]);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Remove AAPL" }));
    });

    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();

    await act(async () => {
      release();
    });
    expect(screen.queryByTestId("watchlist-row-AAPL")).not.toBeInTheDocument();
  });
});
