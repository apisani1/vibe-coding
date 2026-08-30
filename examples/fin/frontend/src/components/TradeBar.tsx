"use client";

import { useState } from "react";
import { trade } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Side } from "@/lib/types";

/**
 * Market orders, filled at the current price, with no confirmation dialog
 * (spec §2).
 *
 * Two behaviours here are the substance of check C5, and both are about what
 * happens when the server says no:
 *
 * * **The inputs keep their values on a rejection.** Clearing them would make
 *   the user retype an order the server refused for a reason they can fix —
 *   "insufficient cash" usually means *fewer shares*, not a different symbol.
 * * **The server's `detail` sentence is what is shown**, verbatim. The services
 *   write those sentences for a human to read ("Insufficient cash: need
 *   $12,000.00, have $10,000.00"); replacing them with "Trade failed" throws
 *   away every number the user needs.
 *
 * `onFilled` is called exactly once per successful fill and never on a
 * rejection — a rejection changes nothing, so refetching would be a lie about
 * why the panel moved.
 */
export function TradeBar({ onFilled }: { onFilled: () => void }) {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(side: Side) {
    setPending(true);
    setError(null);
    setConfirmation(null);
    try {
      const result = await trade(ticker.trim(), side, Number(quantity));
      setConfirmation(
        `${result.side === "buy" ? "Bought" : "Sold"} ${result.quantity} ${result.ticker} @ ${formatMoney(
          result.price,
        )} — total ${formatMoney(result.total)}`,
      );
      onFilled();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(false);
    }
  }

  // `Number("")` is 0, and `Number("abc")` is NaN — both would reach the
  // service and be refused there (which is correct, and tested), but refusing
  // to send them is faster and says so in place.
  const parsed = Number(quantity);
  const ready = ticker.trim().length > 0 && quantity.trim().length > 0 && Number.isFinite(parsed) && parsed > 0;

  return (
    <div className="flex flex-wrap items-center gap-2 p-3" data-testid="trade-bar">
      <input
        aria-label="Ticker"
        value={ticker}
        onChange={(event) => setTicker(event.target.value)}
        placeholder="AAPL"
        className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 uppercase text-terminal-text"
      />
      <input
        aria-label="Quantity"
        value={quantity}
        onChange={(event) => setQuantity(event.target.value)}
        inputMode="decimal"
        placeholder="10"
        className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 tabular-nums text-terminal-text"
      />
      <button
        type="button"
        disabled={!ready || pending}
        onClick={() => void submit("buy")}
        className="rounded bg-accent-purple px-3 py-1 font-semibold text-white disabled:opacity-40"
      >
        Buy
      </button>
      <button
        type="button"
        disabled={!ready || pending}
        onClick={() => void submit("sell")}
        className="rounded border border-accent-purple px-3 py-1 font-semibold text-accent-purple disabled:opacity-40"
      >
        Sell
      </button>

      {error && (
        <p role="alert" className="w-full text-xs text-down" data-testid="trade-error">
          {error}
        </p>
      )}
      {confirmation && (
        <p role="status" className="w-full text-xs text-up" data-testid="trade-confirmation">
          {confirmation}
        </p>
      )}
    </div>
  );
}
