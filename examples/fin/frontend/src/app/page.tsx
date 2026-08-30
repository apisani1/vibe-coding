"use client";

import { useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { Header } from "@/components/Header";
import { Heatmap } from "@/components/Heatmap";
import { MainChart } from "@/components/MainChart";
import { PnlChart } from "@/components/PnlChart";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { Watchlist } from "@/components/Watchlist";
import { PriceStreamProvider } from "@/hooks/usePriceStream";
import { usePortfolio } from "@/hooks/usePortfolio";

/**
 * The single page: layout, and the one place the price stream is opened.
 *
 * A client component because the provider owns an `EventSource`; under
 * `output: 'export'` the whole page is prerendered to static HTML and hydrates
 * in the browser, which is exactly what a terminal that fetches everything from
 * `/api/*` wants.
 *
 * The provider wraps the tree rather than each consumer: one stream for the
 * app (D17), so the watchlist, the header dot and — from CP13 — the charts all
 * read the same tick rather than opening a connection each.
 *
 * Remaining placeholders are replaced by their own checkpoints: trading and
 * positions at CP12, charts at CP13, the assistant at CP14.
 */
function Panel({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <section
      aria-label={title}
      className="flex min-h-0 flex-col rounded border border-terminal-border bg-terminal-panel"
    >
      <h2 className="border-b border-terminal-border px-3 py-2 text-xs uppercase tracking-wider text-terminal-muted">
        {title}
      </h2>
      <div className="min-h-0 flex-1 overflow-auto text-sm text-terminal-muted">{children}</div>
    </section>
  );
}

/**
 * Everything that needs the stream, inside the provider.
 *
 * Split out from `Page` because `usePortfolio` and the components below all sit
 * under `PriceStreamProvider`, and a hook cannot be called in the same
 * component that renders its provider.
 */
function Workstation() {
  const { portfolio, error, refresh } = usePortfolio();
  // Bumped when the assistant actually did something, so the watchlist re-reads
  // its membership. The account is refetched directly; membership lives inside
  // `useWatchlist` and needs a nudge.
  const [chatActions, setChatActions] = useState(0);

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      <Header portfolio={portfolio} />

      {/* The other half of "keep the stale portfolio on screen": say that it is
          stale. Unlabelled stale numbers are just wrong numbers. */}
      {error && (
        <p
          role="alert"
          data-testid="portfolio-error"
          className="rounded border border-down/40 bg-down/10 px-3 py-1 text-xs text-down"
        >
          Account data may be out of date — {error}
        </p>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-2 lg:grid-cols-[20rem_1fr_22rem]">
        <Panel title="Watchlist">
          <Watchlist refreshKey={chatActions} />
        </Panel>

        <div className="grid min-h-0 grid-rows-[1fr_auto_1fr] gap-2">
          <Panel title="Chart">
            <MainChart />
          </Panel>
          <Panel title="Trade">
            {/* The one caller of `refresh`: a fill changes cash and positions,
                and nothing else in this tree does. Check C5 counts it. */}
            <TradeBar onFilled={() => void refresh()} />
          </Panel>
          <Panel title="Positions">
            <PositionsTable portfolio={portfolio} />
          </Panel>
        </div>

        <div className="grid min-h-0 grid-rows-[auto_1fr_1fr] gap-2">
          <Panel title="Total value">
            <div className="h-32">
              <PnlChart portfolio={portfolio} />
            </div>
          </Panel>
          <Panel title="Allocation">
            <Heatmap portfolio={portfolio} />
          </Panel>
          <Panel title="Assistant">
            <ChatPanel
              onActions={() => {
                void refresh();
                setChatActions((current) => current + 1);
              }}
            />
          </Panel>
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <PriceStreamProvider>
      <Workstation />
    </PriceStreamProvider>
  );
}
