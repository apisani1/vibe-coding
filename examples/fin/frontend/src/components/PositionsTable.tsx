"use client";

import { usePriceStream } from "@/hooks/usePriceStream";
import { changePercent, formatMoney, formatPercent, formatSignedMoney, NO_VALUE } from "@/lib/format";
import type { Portfolio, Position } from "@/lib/types";

/** Spec §2's six columns, in order. */
export const COLUMNS = ["Ticker", "Qty", "Avg cost", "Price", "Unrealised P&L", "Change"];

/**
 * What the row is worth *right now*, using the stream first.
 *
 * The fetched payload's `current_price` was true when the portfolio was
 * fetched, which is already stale by the next tick — the design's rendering
 * split puts this cell on the price-driven side deliberately. The payload is
 * the fallback for a ticker the stream has not quoted yet (a position in a
 * symbol removed from the watchlist keeps its price server-side, D3).
 *
 * When neither has a price the row renders `—` and **not** `$0.00`: the backend
 * carries an unpriced position at cost with `unrealized_pnl: 0.0`, which is the
 * right thing to store and the wrong thing to display. `$0.00` claims the
 * position is exactly break-even; `—` says the price is unknown. Check C5.
 */
function priceOf(position: Position, streamed: number | undefined): number | null {
  if (streamed !== undefined) {
    return streamed;
  }
  return position.current_price;
}

function Row({ position, price }: { position: Position; price: number | null }) {
  const value = price === null ? null : price * position.quantity;
  const pnl = price === null ? null : value! - position.avg_cost * position.quantity;
  const change = price === null ? null : changePercent(price, position.avg_cost);
  const tone = pnl === null || pnl === 0 ? "text-terminal-muted" : pnl > 0 ? "text-up" : "text-down";

  return (
    <tr data-testid={`position-${position.ticker}`} className="border-b border-terminal-border/40 last:border-b-0">
      <td className="px-2 py-1 font-semibold text-terminal-text">{position.ticker}</td>
      <td className="px-2 py-1 text-right tabular-nums">{position.quantity}</td>
      <td className="px-2 py-1 text-right tabular-nums">{formatMoney(position.avg_cost)}</td>
      <td className="px-2 py-1 text-right tabular-nums" data-testid={`position-price-${position.ticker}`}>
        {price === null ? NO_VALUE : formatMoney(price)}
      </td>
      <td className={`px-2 py-1 text-right tabular-nums ${tone}`} data-testid={`position-pnl-${position.ticker}`}>
        {pnl === null ? NO_VALUE : formatSignedMoney(pnl)}
      </td>
      <td className={`px-2 py-1 text-right tabular-nums ${tone}`} data-testid={`position-change-${position.ticker}`}>
        {formatPercent(change)}
      </td>
    </tr>
  );
}

export function PositionsTable({ portfolio }: { portfolio: Portfolio | null }) {
  const { quotes } = usePriceStream();
  const positions = portfolio?.positions ?? [];

  if (positions.length === 0) {
    return (
      <p className="p-3 text-sm text-terminal-muted" data-testid="positions-empty">
        No open positions. Buy something below.
      </p>
    );
  }

  return (
    <table className="w-full text-sm" data-testid="positions-table">
      <thead>
        <tr className="text-xs uppercase tracking-wider text-terminal-muted">
          {COLUMNS.map((column) => (
            <th key={column} scope="col" className={`px-2 py-1 ${column === "Ticker" ? "text-left" : "text-right"}`}>
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <Row key={position.ticker} position={position} price={priceOf(position, quotes[position.ticker]?.price)} />
        ))}
      </tbody>
    </table>
  );
}
