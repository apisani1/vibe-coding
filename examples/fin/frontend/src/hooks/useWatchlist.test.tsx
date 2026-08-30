import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriceStreamProvider, usePriceStream } from "@/hooks/usePriceStream";
import { useWatchlist } from "@/hooks/useWatchlist";
import { stubApi } from "@/test/api";
import { installFakeEventSource, quote, stream } from "@/test/priceStream";

const ENTRY = { ticker: "AAPL", added_at: "2026-08-15T12:00:00Z", quote: null };

/** Both hooks against one provider, so the pruning can be observed. */
function renderBoth() {
  installFakeEventSource();
  return renderHook(() => ({ watchlist: useWatchlist(), prices: usePriceStream() }), {
    wrapper: ({ children }) => <PriceStreamProvider>{children}</PriceStreamProvider>,
  });
}

describe("useWatchlist", () => {
  it("loads the list on mount", async () => {
    stubApi([{ match: "/api/watchlist", body: [ENTRY] }]);

    const { result } = renderBoth();

    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));
  });

  it("refetches after an add, so the new symbol is on the list", async () => {
    const api = stubApi([
      { match: "/api/watchlist", method: "POST", body: ENTRY },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    await waitFor(() => expect(api.to("/api/watchlist")).toHaveLength(1));

    await act(async () => {
      expect(await result.current.watchlist.add("aapl")).toBe(true);
    });

    const methods = api.to("/api/watchlist").map((call) => call.method);
    expect(methods).toEqual(["GET", "POST", "GET"]);
  });

  it("reports a rejected add without refetching", async () => {
    // A 422 changed nothing on the server, so a refetch would be a pointless
    // round trip whose only effect is to make the failure look like a change.
    const api = stubApi([
      { match: "/api/watchlist", method: "POST", status: 422, body: { detail: "'!!' is not a valid ticker symbol" } },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    await waitFor(() => expect(api.to("/api/watchlist")).toHaveLength(1));

    await act(async () => {
      expect(await result.current.watchlist.add("!!")).toBe(false);
    });

    expect(result.current.watchlist.error).toBe("'!!' is not a valid ticker symbol");
    expect(api.to("/api/watchlist").filter((call) => call.method === "GET")).toHaveLength(1);
  });

  it("tells the stream to forget a removed ticker", async () => {
    // The condition carried out of CP11. Nothing else prunes: the client maps
    // only grow, and the server's PriceCache never evicts either.
    stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    expect(result.current.prices.quotes.AAPL).toBeDefined();

    await act(async () => {
      expect(await result.current.watchlist.remove("AAPL")).toBe(true);
    });

    expect(result.current.prices.quotes.AAPL).toBeUndefined();
    expect(result.current.prices.history.AAPL).toBeUndefined();
  });

  it("clears the selection when the selected ticker is removed", async () => {
    // Otherwise the detailed chart keeps drawing an instrument that is no
    // longer on the list, fed by a buffer nothing will ever append to again.
    stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    act(() => result.current.prices.select("AAPL"));
    expect(result.current.prices.selectedHistory).toEqual([190]);

    await act(async () => {
      await result.current.watchlist.remove("AAPL");
    });

    expect(result.current.prices.selected).toBeNull();
    expect(result.current.prices.selectedHistory).toEqual([]);
  });

  it("leaves a different selection alone", async () => {
    stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });
    act(() => result.current.prices.select("MSFT"));

    await act(async () => {
      await result.current.watchlist.remove("AAPL");
    });

    expect(result.current.prices.selected).toBe("MSFT");
    expect(result.current.prices.quotes.MSFT).toBeDefined();
  });

  it("keeps the ticker when the server refuses the removal", async () => {
    stubApi([
      {
        match: "/api/watchlist/AAPL",
        method: "DELETE",
        status: 404,
        body: { detail: "'AAPL' is not on the watchlist" },
      },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    await act(async () => {
      expect(await result.current.watchlist.remove("AAPL")).toBe(false);
    });

    expect(result.current.prices.quotes.AAPL).toBeDefined();
    expect(result.current.watchlist.error).toBe("'AAPL' is not on the watchlist");
  });

  it("drops the entry by its normalised symbol, whatever case was typed", async () => {
    // Both halves of a removal normalise, and neither is pinned by the other:
    // the local drop compares against `entries`, which hold the server's
    // upper-case form, so filtering by the raw string would leave the row on
    // screen until the refetch landed. Gated, because without a gate the
    // refetch settles in the same flush and hides the difference.
    let release: () => void = () => {};
    const refetch = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([
      { match: "/api/watchlist/aapl", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [ENTRY] },
    ]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));

    api.serve([
      { match: "/api/watchlist/aapl", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [], gate: refetch },
    ]);
    let removal: Promise<boolean> | undefined;
    await act(async () => {
      removal = result.current.watchlist.remove("aapl");
    });

    expect(result.current.watchlist.entries).toEqual([]);

    await act(async () => {
      release();
      await removal;
    });
  });

  it("forgets the upper-cased symbol, whatever case was typed", async () => {
    // The client maps are keyed by the server's normalised form; forgetting
    // "aapl" would silently prune nothing and leave the row on screen.
    stubApi([
      { match: "/api/watchlist/aapl", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [] },
    ]);
    const { result } = renderBoth();
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    await act(async () => {
      await result.current.watchlist.remove("aapl");
    });

    expect(result.current.prices.quotes.AAPL).toBeUndefined();
  });
});

describe("overlapping mutations", () => {
  it("ignores a slow refetch that a newer one has already superseded", async () => {
    // The overseer's probe, kept as a test. A removal's refetch is a round trip
    // long; an add issued during it resolves first, and without sequencing the
    // older response lands last and wipes the just-added ticker off the list —
    // membership going wrong again, which is the family of bug that got this
    // checkpoint rejected once already.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [ENTRY] },
    ]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));

    // Removal, whose refetch stalls.
    api.serve([
      { match: "/api/watchlist/AAPL", method: "DELETE", status: 204 },
      { match: "/api/watchlist", body: [], gate: slow },
    ]);
    let removal: Promise<boolean> | undefined;
    await act(async () => {
      removal = result.current.watchlist.remove("AAPL");
    });

    // An add lands while that refetch is still in flight.
    const added = { ticker: "MSFT", added_at: "2026-08-15T12:01:00Z", quote: null };
    api.serve([
      { match: "/api/watchlist", method: "POST", body: added },
      { match: "/api/watchlist", body: [added] },
    ]);
    await act(async () => {
      await result.current.watchlist.add("MSFT");
    });
    expect(result.current.watchlist.entries).toEqual([added]);

    await act(async () => {
      release();
      await removal;
    });

    expect(result.current.watchlist.entries).toEqual([added]);
  });
});

describe("whose error is on screen", () => {
  it("does not let a background refresh wipe a rejection the user has to read", async () => {
    // Found by the overseer. `refresh` used to clear the error unconditionally,
    // so a GET resolving a moment after a rejected add erased the server's
    // sentence while the bad symbol was still in the input box.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([{ match: "/api/watchlist", body: [ENTRY], gate: slow }]);
    const { result } = renderBoth();

    api.serve([
      { match: "/api/watchlist", method: "POST", status: 422, body: { detail: "'!!' is not a valid ticker symbol" } },
      { match: "/api/watchlist", body: [ENTRY] },
    ]);
    await act(async () => {
      await result.current.watchlist.add("!!");
    });
    expect(result.current.watchlist.error).toBe("'!!' is not a valid ticker symbol");

    await act(async () => {
      release();
    });

    expect(result.current.watchlist.error).toBe("'!!' is not a valid ticker symbol");
  });

  it("clears its own error once a refresh succeeds", async () => {
    const api = stubApi([{ match: "/api/watchlist", status: 503, body: { detail: "database is locked" } }]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.error).toBe("database is locked"));

    api.serve([{ match: "/api/watchlist", body: [ENTRY] }]);
    await act(async () => {
      await result.current.watchlist.refresh();
    });

    expect(result.current.watchlist.error).toBeNull();
  });

  it("discards a stale failure that lands after a newer refresh succeeded", async () => {
    // The error half of the generation guard. Removing only the catch-side
    // check left all 102 tests green: the code was right and nothing would
    // have noticed it going wrong.
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = stubApi([{ match: "/api/watchlist", body: [ENTRY] }]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));

    api.serve([{ match: "/api/watchlist", status: 503, body: { detail: "database is locked" }, gate: slow }]);
    let stale: Promise<void> | undefined;
    await act(async () => {
      stale = result.current.watchlist.refresh();
    });

    api.serve([{ match: "/api/watchlist", body: [ENTRY] }]);
    await act(async () => {
      await result.current.watchlist.refresh();
    });

    await act(async () => {
      release();
      await stale;
    });

    expect(result.current.watchlist.error).toBeNull();
  });
});

describe("whoever removed it, the stream hears about it", () => {
  it("forgets a ticker that has left the membership, without a remove() call", async () => {
    // The CP14 blocker. The assistant removes symbols through the same service
    // functions a person does (D5) but reaches this hook only through
    // `refresh`, so a guard living inside `remove` guards one caller rather
    // than the resource. Selecting first, because the frozen chart is the
    // visible half of the failure.
    const api = stubApi([{ match: "/api/watchlist", body: [ENTRY] }]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));
    act(() => result.current.prices.select("AAPL"));
    expect(result.current.prices.selected).toBe("AAPL");

    api.serve([{ match: "/api/watchlist", body: [] }]);
    await act(async () => {
      await result.current.watchlist.refresh();
    });

    expect(result.current.prices.quotes.AAPL).toBeUndefined();
    expect(result.current.prices.selected).toBeNull();
    expect(result.current.prices.selectedHistory).toEqual([]);
  });

  it("never forgets a held-but-unwatched ticker the producer is still pricing", async () => {
    // The exemption that actually matters, and the one the first version of
    // this test did not pin: its ticker was *in* the returned membership, so no
    // mutation of the forget loop could make it fail — the overseer showed the
    // two kills it was credited with landing on CP11/12 tests instead.
    //
    // The real case is D3: the producer prices watchlist ∪ open positions, so a
    // symbol you hold keeps streaming after you unwatch it. It is never in the
    // membership, therefore never in `known`, therefore never forgotten — and
    // it must not be, because the positions table and the charts still price it.
    const api = stubApi([{ match: "/api/watchlist", body: [ENTRY] }]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));
    act(() => stream().emit(quote({ ticker: "TSLA", price: 421 })));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    api.serve([{ match: "/api/watchlist", body: [] }]);
    await act(async () => {
      await result.current.watchlist.refresh();
    });

    // AAPL left the list and is forgotten; TSLA was never on it and survives.
    expect(result.current.prices.quotes.AAPL).toBeUndefined();
    expect(result.current.prices.quotes.TSLA).toBeDefined();
  });

  it("leaves a ticker that is still on the list alone", async () => {
    const api = stubApi([{ match: "/api/watchlist", body: [ENTRY] }]);
    const { result } = renderBoth();
    await waitFor(() => expect(result.current.watchlist.entries).toEqual([ENTRY]));
    act(() => stream().emit(quote({ ticker: "AAPL", price: 190 })));

    api.serve([{ match: "/api/watchlist", body: [ENTRY, { ticker: "MSFT", added_at: "now", quote: null }] }]);
    await act(async () => {
      await result.current.watchlist.refresh();
    });

    expect(result.current.prices.quotes.AAPL).toBeDefined();
  });
});
