/**
 * A `fetch` stub that remembers what it was asked for.
 *
 * Not a test file (vitest collects `*.test.*` only). It exists because check
 * C5's central claim is a **count** — "a successful trade triggers exactly one
 * portfolio refetch" — and a count is only trustworthy against one honest
 * recorder. A hand-rolled stub per test file would drift, and the copy that
 * drifts is the one holding the assertion you rely on.
 *
 * Routes are matched by substring in insertion order, so a test names only the
 * endpoints it cares about. An unmatched request **throws** rather than
 * returning an empty 200: a component quietly fetching something the test never
 * declared is exactly the kind of surprise this file should surface.
 */

import { vi } from "vitest";

export interface Route {
  /** Substring of the URL, e.g. `/api/portfolio/trade`. */
  match: string;
  /** Optional method filter; omit to match any. */
  method?: string;
  status?: number;
  /** Response body. A function is called per request, for changing answers. */
  body?: unknown | (() => unknown);
  /**
   * Awaited before responding, so a test can observe the state *while* the
   * request is in flight. Without it every fetch settles inside the same
   * `act` flush, and an intermediate render — an optimistic update, a loading
   * state — is unobservable and therefore untestable.
   */
  gate?: Promise<unknown>;
}

export interface RecordedCall {
  url: string;
  method: string;
  body: unknown;
}

export class ApiStub {
  readonly calls: RecordedCall[] = [];

  constructor(private routes: Route[]) {}

  /** Every recorded call whose URL contains `fragment`. */
  to(fragment: string): RecordedCall[] {
    return this.calls.filter((call) => call.url.includes(fragment));
  }

  /** Replace the routing table mid-test — e.g. to make the second GET differ from the first. */
  serve(routes: Route[]) {
    this.routes = routes;
  }

  handle = async (url: string, init?: RequestInit): Promise<Response> => {
    const method = (init?.method ?? "GET").toUpperCase();
    this.calls.push({
      url,
      method,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });

    const route = this.routes.find(
      (candidate) => url.includes(candidate.match) && (!candidate.method || candidate.method.toUpperCase() === method),
    );
    if (!route) {
      throw new Error(`no stubbed route for ${method} ${url} — declare it in the test`);
    }

    if (route.gate) {
      await route.gate;
    }

    const status = route.status ?? 200;
    const body = typeof route.body === "function" ? (route.body as () => unknown)() : route.body;
    if (status === 204 || body === undefined) {
      return new Response(null, { status });
    }
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  };
}

/** Install the stub as the global `fetch` (the setup file blocks the real one). */
export function stubApi(routes: Route[]): ApiStub {
  const stub = new ApiStub(routes);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => stub.handle(url, init)),
  );
  return stub;
}
