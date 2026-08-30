"use client";

import { usePriceStream, type ConnectionStatus } from "@/hooks/usePriceStream";
import { formatMoney } from "@/lib/format";
import type { Portfolio } from "@/lib/types";

/**
 * Spec §2: green connected, yellow reconnecting, red disconnected.
 *
 * `connecting` shares the yellow of `reconnecting` — both mean "no data yet,
 * still trying" — but keeps its own label, because "connecting" during the
 * first second of a page load and "reconnecting" after the backend dropped are
 * different facts about the system even though the dot is the same colour.
 */
const DOT: Record<ConnectionStatus, string> = {
  connected: "bg-up",
  connecting: "bg-accent-yellow",
  reconnecting: "bg-accent-yellow",
  disconnected: "bg-down",
};

/**
 * Account totals and the connection dot.
 *
 * `portfolio` is a prop rather than a fetch: the totals are state-driven pixels
 * that change only after a mutation, and the design keeps those on a separate
 * re-render path from the 500 ms price tick. CP12's `usePortfolio` supplies it;
 * until then, and whenever a fetch has not resolved, the totals render `—`
 * rather than a fabricated `$0.00`.
 */
export function Header({ portfolio }: { portfolio?: Portfolio | null }) {
  const { status } = usePriceStream();

  return (
    <header className="flex items-center justify-between rounded border border-terminal-border bg-terminal-panel px-3 py-2">
      <div className="flex items-baseline gap-3">
        <h1 className="text-sm font-semibold tracking-widest text-accent-yellow">FinAlly</h1>
        <span className="text-xs text-terminal-muted">AI Trading Workstation</span>
      </div>

      <div className="flex items-center gap-5 text-sm tabular-nums">
        <span>
          <span className="text-xs uppercase tracking-wider text-terminal-muted">Total </span>
          <span data-testid="header-total">{formatMoney(portfolio?.total_value)}</span>
        </span>
        <span>
          <span className="text-xs uppercase tracking-wider text-terminal-muted">Cash </span>
          <span data-testid="header-cash">{formatMoney(portfolio?.cash_balance)}</span>
        </span>
        <span className="flex items-center gap-1.5" data-testid="connection-status">
          <span className={`h-2 w-2 rounded-full ${DOT[status]}`} data-testid="connection-dot" aria-hidden="true" />
          <span className="text-xs text-terminal-muted">{status}</span>
        </span>
      </div>
    </header>
  );
}
