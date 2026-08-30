"use client";

import { ResponsiveContainer, Treemap } from "recharts";
import { usePriceStream } from "@/hooks/usePriceStream";
import { formatPercent } from "@/lib/format";
import type { Portfolio, Position } from "@/lib/types";

/**
 * Positions as a treemap: area is weight, colour is P&L (spec §2).
 *
 * The colour rule is a **ramp, not a flag**. A portfolio where one holding is
 * up 40% and another up 0.2% should not paint both the same green — the whole
 * point of the view is finding the outlier at a glance. Magnitude saturates at
 * `RAMP_CAP`, past which more is just "very".
 */

/** Percentage move at which the colour stops getting stronger. */
export const RAMP_CAP = 10;

/** Theme `up` / `down` / `terminal-border`, as rgb triples so alpha can vary. */
const UP = "38 166 91";
const DOWN = "229 72 77";
export const NEUTRAL_FILL = "rgb(48 54 61 / 0.9)";

/**
 * The fill for one cell, from its P&L percentage.
 *
 * `null` — an unpriced position — is neutral rather than green or red: check C5
 * established that an unknown price must not be rendered as break-even, and a
 * grey cell says "no opinion" where a green one would claim a gain.
 */
export function fillFor(pnlPercent: number | null): string {
  if (pnlPercent === null || !Number.isFinite(pnlPercent) || pnlPercent === 0) {
    return NEUTRAL_FILL;
  }
  const intensity = Math.min(Math.abs(pnlPercent) / RAMP_CAP, 1);
  const alpha = (0.3 + 0.6 * intensity).toFixed(2);
  return `rgb(${pnlPercent > 0 ? UP : DOWN} / ${alpha})`;
}

export interface Cell {
  // Recharts' `TreemapDataType` is an index signature, so a closed interface is
  // not assignable to it however well its fields line up.
  [key: string]: string | number | null;
  ticker: string;
  /** Market value — the treemap's area. Cost basis when nothing has priced it. */
  size: number;
  pnlPercent: number | null;
  fill: string;
}

/**
 * Cells for the current positions, priced from the stream where possible.
 *
 * Sized by **market value**, not by share count: 100 shares of a $4 stock is a
 * smaller position than 5 shares of a $500 one, and a treemap that says
 * otherwise is worse than no treemap.
 */
export function heatmapCells(positions: Position[], quotes: Record<string, { price: number }>): Cell[] {
  return positions.map((position) => {
    const price = quotes[position.ticker]?.price ?? position.current_price;
    const cost = position.avg_cost * position.quantity;
    const pnlPercent = price === null || position.avg_cost === 0 ? null : ((price - position.avg_cost) / position.avg_cost) * 100;
    return {
      ticker: position.ticker,
      size: price === null ? cost : price * position.quantity,
      pnlPercent,
      fill: fillFor(pnlPercent),
    };
  });
}

/**
 * One rectangle. Recharts calls this with the layout it computed plus every
 * field of the datum, which is why the fill travels **in the data** rather than
 * being derived here — check C6 asserts the prop, and a prop is only assertable
 * if something other than a rendered pixel carries it.
 */
export function HeatmapCell(props: Partial<Cell> & { x?: number; y?: number; width?: number; height?: number }) {
  const { x = 0, y = 0, width = 0, height = 0, ticker, pnlPercent, fill } = props;
  const roomForText = width > 44 && height > 24;

  return (
    <g data-testid={ticker ? `heatmap-cell-${ticker}` : "heatmap-cell"} data-fill={fill}>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#0d1117" strokeWidth={1} />
      {roomForText && (
        <>
          <text x={x + 6} y={y + 16} fill="#e6edf3" fontSize={11} fontWeight={600}>
            {ticker}
          </text>
          <text x={x + 6} y={y + 30} fill="#e6edf3" fontSize={10}>
            {formatPercent(pnlPercent)}
          </text>
        </>
      )}
    </g>
  );
}

export function Heatmap({ portfolio }: { portfolio: Portfolio | null }) {
  const { quotes } = usePriceStream();
  const positions = portfolio?.positions ?? [];

  if (positions.length === 0) {
    return (
      <p className="p-3 text-sm text-terminal-muted" data-testid="heatmap-empty">
        Nothing to weigh yet — the heatmap fills in once you hold something.
      </p>
    );
  }

  const cells = heatmapCells(positions, quotes);

  return (
    <div className="h-full w-full" data-testid="heatmap" data-cells={cells.length}>
      {/* Responsive like the other two charts. It was pinned at a literal
          320×180 inside this `h-full w-full` div, which no test could see and
          which would have shipped a treemap that neither filled a wide panel
          nor fitted a narrow one. */}
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={cells} dataKey="size" isAnimationActive={false} content={<HeatmapCell />} />
      </ResponsiveContainer>
    </div>
  );
}
