import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LONG_BUFFER, PriceStreamProvider, SHORT_BUFFER, usePriceStream } from "@/hooks/usePriceStream";
import { FakeEventSource, installFakeEventSource, quote, stream } from "@/test/priceStream";

function renderStream() {
  installFakeEventSource();
  return renderHook(() => usePriceStream(), {
    wrapper: ({ children }) => <PriceStreamProvider>{children}</PriceStreamProvider>,
  });
}

describe("the stream itself", () => {
  it("opens exactly one connection, to the API path", () => {
    // D17. One per consumer would duplicate every frame and burn a browser's
    // per-origin connection budget.
    renderStream();

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(stream().url).toBe("/api/stream/prices");
  });

  it("closes the connection when the tree unmounts", () => {
    // Without this a page that navigates away leaves the backend generator
    // running until it notices the disconnect.
    const { unmount } = renderStream();
    const source = stream();

    unmount();

    expect(source.closed).toBe(true);
  });

  it("throws when used outside the provider", () => {
    expect(() => renderHook(() => usePriceStream())).toThrow(/inside a PriceStreamProvider/);
  });
});

describe("quotes and buffers", () => {
  it("keeps the latest quote per ticker", () => {
    const { result } = renderStream();

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
      stream().emit(quote({ ticker: "MSFT", price: 410 }));
      stream().emit(quote({ ticker: "AAPL", price: 191 }));
    });

    expect(result.current.quotes.AAPL.price).toBe(191);
    expect(result.current.quotes.MSFT.price).toBe(410);
  });

  it("caps each ticker's history and keeps the newest points", () => {
    const { result } = renderStream();

    act(() => {
      for (let i = 0; i < SHORT_BUFFER + 5; i += 1) {
        stream().emit(quote({ ticker: "AAPL", price: i }));
      }
    });

    const history = result.current.history.AAPL;
    expect(history).toHaveLength(SHORT_BUFFER);
    // Oldest-first, and it is the *oldest* five that were dropped: asserting
    // only the length would pass on a buffer that kept the first 120 points and
    // ignored every price since.
    expect(history[0]).toBe(5);
    expect(history[history.length - 1]).toBe(SHORT_BUFFER + 4);
  });

  it("ignores a frame that is not a quote instead of taking the panel down", () => {
    const { result } = renderStream();

    act(() => {
      stream().emitRaw("not json at all");
      stream().emitRaw(JSON.stringify({ ticker: "AAPL" }));
      stream().emit(quote({ ticker: "AAPL", price: 190 }));
    });

    expect(result.current.quotes.AAPL.price).toBe(190);
    expect(result.current.history.AAPL).toEqual([190]);
  });
});

describe("the second tier (D22)", () => {
  it("seeds the selected ticker's deep buffer from what the sparkline already has", () => {
    // Selecting must not start the detailed chart from empty; it opens with the
    // last minute and deepens from there.
    const { result } = renderStream();

    act(() => {
      for (const price of [10, 11, 12]) {
        stream().emit(quote({ ticker: "AAPL", price }));
      }
    });
    act(() => result.current.select("AAPL"));

    expect(result.current.selected).toBe("AAPL");
    expect(result.current.selectedHistory).toEqual([10, 11, 12]);
  });

  it("appends only the selected ticker's prices, and starts over on a switch", () => {
    const { result } = renderStream();

    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 10 }));
      stream().emit(quote({ ticker: "MSFT", price: 400 }));
    });
    act(() => result.current.select("AAPL"));
    act(() => {
      stream().emit(quote({ ticker: "AAPL", price: 11 }));
      stream().emit(quote({ ticker: "MSFT", price: 401 }));
    });

    // MSFT's ticks must not leak into AAPL's series — a single shared buffer
    // would interleave two instruments into one line and look plausible.
    expect(result.current.selectedHistory).toEqual([10, 11]);

    act(() => result.current.select("MSFT"));
    expect(result.current.selectedHistory).toEqual([400, 401]);
  });

  it("holds a deeper window than the sparkline, and caps it too", () => {
    // The point of the second tier: if both buffers had the same cap, clicking
    // a ticker would draw the identical 60-second window as the thumbnail.
    const { result } = renderStream();

    act(() => result.current.select("AAPL"));
    act(() => {
      for (let i = 0; i < LONG_BUFFER + 5; i += 1) {
        stream().emit(quote({ ticker: "AAPL", price: i }));
      }
    });

    expect(result.current.history.AAPL).toHaveLength(SHORT_BUFFER);
    expect(result.current.selectedHistory).toHaveLength(LONG_BUFFER);
    expect(result.current.selectedHistory[0]).toBe(5);
  });
});

describe("connection status", () => {
  it("starts as connecting and never claims connected before the stream opens", () => {
    // The failure this pins: a status derived from "the object exists" reports
    // a green dot against a backend that is not there.
    const { result } = renderStream();

    expect(result.current.status).toBe("connecting");

    act(() => stream().fail(FakeEventSource.CONNECTING));
    expect(result.current.status).not.toBe("connected");
  });

  it("reports connected once the server accepts", () => {
    const { result } = renderStream();

    act(() => stream().open());

    expect(result.current.status).toBe("connected");
  });

  it("reports reconnecting when a stream that had opened drops and is retrying", () => {
    const { result } = renderStream();

    act(() => stream().open());
    act(() => stream().fail(FakeEventSource.CONNECTING));

    expect(result.current.status).toBe("reconnecting");
  });

  it("reports disconnected as soon as the browser gives up", () => {
    const { result } = renderStream();

    act(() => stream().open());
    act(() => stream().fail(FakeEventSource.CLOSED));

    expect(result.current.status).toBe("disconnected");
  });

  it("reports disconnected after repeated failures on a stream that never opened", () => {
    const { result } = renderStream();

    act(() => stream().fail(FakeEventSource.CONNECTING));
    expect(result.current.status).toBe("connecting");

    act(() => {
      stream().fail(FakeEventSource.CONNECTING);
      stream().fail(FakeEventSource.CONNECTING);
    });

    expect(result.current.status).toBe("disconnected");
  });

  it("clears the failure count once a connection succeeds", () => {
    // Otherwise two failures now and one an hour later, after a healthy
    // reconnect in between, would report a dead backend.
    const { result } = renderStream();

    act(() => {
      stream().fail(FakeEventSource.CONNECTING);
      stream().fail(FakeEventSource.CONNECTING);
    });
    act(() => stream().open());
    act(() => stream().fail(FakeEventSource.CONNECTING));

    expect(result.current.status).toBe("reconnecting");
  });
});
