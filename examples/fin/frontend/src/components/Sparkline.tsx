"use client";

/**
 * A price ring, drawn as an SVG polyline.
 *
 * Deliberately unlabelled and unscaled: it is a 60-pixel thumbnail of shape,
 * not a chart. The detailed chart is a separate component with a separate,
 * deeper buffer (D22).
 *
 * The degenerate cases are the ones worth writing down, because they are the
 * normal state for the first half-second after a page load rather than an edge
 * case: a ticker with **no** points yet, one point, or a flat run where every
 * point is identical. All three render a baseline rather than throwing, and
 * check C4 asserts the first two by name — a component that divides by
 * `max - min` takes the whole watchlist down with it the moment a price holds
 * steady for two ticks.
 */

export const SPARKLINE_WIDTH = 72;
export const SPARKLINE_HEIGHT = 20;

export function Sparkline({
  points,
  width = SPARKLINE_WIDTH,
  height = SPARKLINE_HEIGHT,
  className,
}: {
  points: number[];
  width?: number;
  height?: number;
  className?: string;
}) {
  const usable = points.filter((point) => Number.isFinite(point));
  const min = Math.min(...usable);
  const max = Math.max(...usable);
  // Two clauses, each pinned by its own test — the first version wrote
  // `usable.length < 2 || max === min`, whose length clause was an equivalent
  // mutant: a single point already has `min === max`, so `< 2` and `< 1` behave
  // identically and no test could tell them apart. What the empty case actually
  // needs is that `Math.min()` of nothing is `Infinity` and `Math.max()` is
  // `-Infinity`, so `max === min` is *false* there and the polyline branch would
  // emit `NaN` coordinates.
  const flat = usable.length === 0 || max === min;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
      data-testid="sparkline"
    >
      {flat ? (
        <line
          data-testid="sparkline-baseline"
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth={1}
        />
      ) : (
        <polyline
          data-testid="sparkline-path"
          fill="none"
          stroke="currentColor"
          strokeWidth={1}
          points={usable
            .map((point, index) => {
              const x = (index / (usable.length - 1)) * width;
              // Inverted: SVG's y grows downward, and a rising price must rise.
              const y = height - ((point - min) / (max - min)) * height;
              return `${x.toFixed(2)},${y.toFixed(2)}`;
            })
            .join(" ")}
        />
      )}
    </svg>
  );
}
