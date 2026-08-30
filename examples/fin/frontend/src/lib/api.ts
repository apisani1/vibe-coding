/**
 * Typed wrappers over `/api/*`.
 *
 * Relative URLs, no base host: the backend serves this bundle from the same
 * origin (R3), so there is nothing to configure and no CORS to get wrong.
 *
 * Two behaviours here are load-bearing rather than decorative:
 *
 * 1. **The server's `detail` string is preserved.** FastAPI puts the human
 *    sentence — "Insufficient cash: need $12,000.00, have $10,000.00" — in
 *    `detail`, and the services deliberately write those sentences for the user
 *    to read. Replacing them with "Request failed (400)" throws away the only
 *    part of the response that helps.
 * 2. **A non-JSON body is reported as such.** If the static export were ever
 *    mounted *ahead* of the API routers, every call would receive the HTML
 *    shell with a 200 and `response.json()` would throw a parse error naming a
 *    stray `<`. That symptom is unreadable; this message names the cause.
 */

import type { ChatTurn, Portfolio, Snapshot, StoredMessage, TradeResult, WatchlistEntry } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull the most useful sentence out of a FastAPI error body. */
function detailOf(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return fallback;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  // 422 from a Pydantic model is a list of error objects, not a string.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === "object" && item !== null ? String((item as { msg?: unknown }).msg ?? "") : ""))
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init?.headers } : init?.headers,
  });

  // 204: a body-less success (DELETE /api/watchlist/{ticker}). Calling .json()
  // on it throws, so the caller would see a parse error on a request that
  // worked.
  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let body: unknown = undefined;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    throw new ApiError(
      response.status,
      `${path} returned ${response.status} with a non-JSON body — the API route may be shadowed by the static export`,
    );
  }

  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body, `${path} failed with ${response.status}`));
  }
  return body as T;
}

export const getPortfolio = (): Promise<Portfolio> => request<Portfolio>("/portfolio");

// No `limit` argument. The endpoint accepts one and the single caller has never
// passed it, so the parameter existed only to be plumbed through; the server's
// default is the window the chart wants. Add it back when a caller needs a
// different one.
export const getHistory = (): Promise<Snapshot[]> => request<Snapshot[]>("/portfolio/history");

export const trade = (ticker: string, side: "buy" | "sell", quantity: number): Promise<TradeResult> =>
  request<TradeResult>("/portfolio/trade", { method: "POST", body: JSON.stringify({ ticker, side, quantity }) });

export const getWatchlist = (): Promise<WatchlistEntry[]> => request<WatchlistEntry[]>("/watchlist");

export const addTicker = (ticker: string): Promise<WatchlistEntry> =>
  request<WatchlistEntry>("/watchlist", { method: "POST", body: JSON.stringify({ ticker }) });

export const removeTicker = (ticker: string): Promise<void> =>
  request<void>(`/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });

export const getChatMessages = (): Promise<StoredMessage[]> => request<StoredMessage[]>("/chat/messages");

export const sendChatMessage = (message: string): Promise<ChatTurn> =>
  request<ChatTurn>("/chat", { method: "POST", body: JSON.stringify({ message }) });
