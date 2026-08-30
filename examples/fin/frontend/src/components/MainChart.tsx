"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { usePriceStream } from "@/hooks/usePriceStream";
import { formatMoney } from "@/lib/format";

/**
 * The selected ticker, drawn from the deep buffer (D22).
 *
 * This component is the reason the second tier exists: the sparkline beside a
 * watchlist row shows ~60 seconds, and clicking a ticker has to be worth
 * something. Its horizon is minutes rather than days — the direct cost of D1's
 * no-price-history-table decision, and recorded in the design's Limitations.
 *
 * `data-series` and `data-points` are on the wrapper deliberately. Check C6
 * asserts that clicking a row **changes the series identity passed to the
 * chart**, and under jsdom a Recharts SVG has no layout to inspect — so the
 * identity is carried by an attribute rather than inferred from pixels.
 */
export function MainChart() {
  const { selected, selectedHistory } = usePriceStream();

  if (selected === null) {
    return (
      <p className="p-3 text-sm text-terminal-muted" data-testid="main-chart-empty">
        Click a ticker to chart it.
      </p>
    );
  }

  const data = selectedHistory.map((price, index) => ({ index, price }));
  // The *last* point, not the first: this is the number a trader reads beside
  // the chart, and showing the oldest buffered price used to pass every test.
  const latest = selectedHistory[selectedHistory.length - 1];

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="main-chart" data-series={selected} data-points={data.length}>
      <div className="flex items-baseline gap-3 px-3 py-1">
        <span className="text-sm font-semibold text-terminal-text">{selected}</span>
        <span className="text-sm tabular-nums text-accent-blue" data-testid="main-chart-price">
          {formatMoney(latest)}
        </span>
      </div>

      {data.length === 0 ? (
        // Selected, but nothing has ticked yet. Not an error state and not the
        // "click a ticker" state either — both would be lies.
        <p className="px-3 text-xs text-terminal-muted" data-testid="main-chart-waiting">
          Waiting for the first tick.
        </p>
      ) : (
        <div className="min-h-0 flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="2 4" vertical={false} />
              {/* `domain: dataMin..dataMax` rather than starting at zero: a
                  $190 stock moving to $191 is a flat line on a zero-based axis,
                  which is exactly the movement this chart exists to show. */}
              <YAxis
                domain={["dataMin", "dataMax"]}
                tick={{ fill: "#8b949e", fontSize: 10 }}
                width={56}
                tickFormatter={(value: number) => formatMoney(value)}
              />
              <Tooltip
                contentStyle={{ background: "#1a1a2e", border: "1px solid #30363d", fontSize: 12 }}
                labelFormatter={() => selected}
                // Recharts types the value as `ValueType | undefined`, so the
                // formatter has to accept what it is actually handed rather
                // than what this series contains.
                formatter={(value) => [formatMoney(Number(value)), "Price"]}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#209dd7"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
