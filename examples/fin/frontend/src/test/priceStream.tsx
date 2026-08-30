/**
 * A fake `EventSource`, and the plumbing to render components around it.
 *
 * Not a test file (vitest collects `*.test.*` only). It exists because C3 and
 * C4 are only comparable if the watchlist, the header and the hook are all
 * driven by the *same* fake — three hand-rolled copies would drift, and the one
 * that drifts is always the one carrying the assertion you trust.
 *
 * The fake mirrors the parts of the real contract the hook actually depends on:
 * `readyState` with the same three constants, `onopen`/`onmessage`/`onerror`,
 * and `close()`. It does **not** reconnect, because the real one does that in
 * the browser and the hook deliberately adds no retry logic of its own — a fake
 * that retried would be testing code this project does not have.
 */

import { act, render, type RenderResult } from "@testing-library/react";
import { vi } from "vitest";
import { PriceStreamProvider } from "@/hooks/usePriceStream";
import type { Quote } from "@/lib/types";

export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  /** Every instance constructed since the last `installFakeEventSource()`. */
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }

  /** The server accepted the connection. */
  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }

  /** One SSE frame, encoded the way `api/stream.py` encodes it. */
  emit(quote: Quote) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(quote) }));
  }

  /** A raw frame, for the malformed-payload cases. */
  emitRaw(data: string) {
    this.onmessage?.(new MessageEvent("message", { data }));
  }

  /**
   * A transport error. `state` is what `readyState` reads *during* the handler,
   * which is the browser's way of saying whether it intends to retry —
   * `CONNECTING` means it will, `CLOSED` means it has given up.
   */
  fail(state: number = FakeEventSource.CONNECTING) {
    this.readyState = state;
    this.onerror?.();
  }
}

/** Replace the global `EventSource` (the setup file blocks it) and reset the registry. */
export function installFakeEventSource() {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  return FakeEventSource;
}

/** The single stream a rendered tree is attached to. */
export function stream(): FakeEventSource {
  const [first] = FakeEventSource.instances;
  if (!first) {
    throw new Error("no EventSource was opened — did the component mount inside PriceStreamProvider?");
  }
  return first;
}

/** Render `ui` inside the provider, with the fake installed. */
export function renderWithStream(ui: React.ReactNode): RenderResult {
  installFakeEventSource();
  return render(<PriceStreamProvider>{ui}</PriceStreamProvider>);
}

/**
 * `renderWithStream`, then let every pending promise settle.
 *
 * For components that fetch on mount. Without the flush their state lands
 * outside `act`, which React reports as a warning and which makes an assertion
 * written immediately after the render a race against a microtask.
 */
export async function mountWithStream(ui: React.ReactNode): Promise<RenderResult> {
  const result = renderWithStream(ui);
  await act(async () => {});
  return result;
}

/** A quote with sane defaults; override exactly the fields a test is about. */
export function quote(overrides: Partial<Quote> & { ticker: string; price: number }): Quote {
  return {
    previous_price: overrides.price,
    session_open: overrides.price,
    timestamp: "2026-08-15T12:00:00+00:00",
    direction: "flat",
    ...overrides,
  };
}
