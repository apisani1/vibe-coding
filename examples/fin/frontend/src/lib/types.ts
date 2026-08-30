/**
 * The wire contract, transcribed from the backend's TypedDicts.
 *
 * Hand-written rather than generated: the backend is the single source of truth
 * and these must be read against it (`market/source.py`, `services/*.py`) when
 * either side changes. A generator would be a third moving part for nine types.
 */

export type Direction = "up" | "down" | "flat";

/**
 * One ticker's current state, from the SSE stream or the watchlist endpoint.
 *
 * `previous_price` and `session_open` are not interchangeable, and the whole
 * of D19 turns on the difference: `previous_price` is the immediately preceding
 * tick and decides only whether a row flashes green or red; `session_open` is
 * stamped once per process and is the baseline for the *daily change %*.
 * Deriving the percentage from `previous_price` gives a ±0.01% number that
 * flips sign twice a second — check C3 exists to fail on exactly that.
 */
export interface Quote {
  ticker: string;
  price: number;
  previous_price: number;
  session_open: number;
  timestamp: string;
  direction: Direction;
}

export interface WatchlistEntry {
  ticker: string;
  added_at: string;
  /** `null` until the producer has quoted this symbol at least once. */
  quote: Quote | null;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  /** `null` when the cache holds no price yet: the position is carried at cost. */
  current_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  positions: Position[];
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export type Side = "buy" | "sell";

export interface TradeResult {
  trade_id: string;
  ticker: string;
  side: Side;
  quantity: number;
  price: number;
  total: number;
  cash_balance: number;
  position_quantity: number;
  position_avg_cost: number;
  executed_at: string;
}

/**
 * One action the assistant took or was refused (D6).
 *
 * A rejection is an outcome, not an error: the turn is a 200 and `reason`
 * carries the same sentence the REST API would have returned as `detail`. A
 * panel that renders only `filled` actions reproduces the failure D6 exists to
 * prevent, so both statuses are part of the type.
 */
export interface ChatAction {
  type: "trade" | "watchlist";
  ticker: string;
  side?: Side;
  action?: string;
  quantity?: number;
  status: "filled" | "applied" | "rejected";
  reason?: string;
  price?: number;
}

export interface ChatTurn {
  message: string;
  actions: ChatAction[];
}

export interface StoredMessage {
  id: string;
  role: string;
  content: string;
  actions: ChatAction[];
  created_at: string;
}
