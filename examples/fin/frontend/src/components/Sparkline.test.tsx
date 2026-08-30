import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Sparkline, SPARKLINE_HEIGHT, SPARKLINE_WIDTH } from "./Sparkline";

describe("Sparkline", () => {
  it("renders a flat baseline with no points at all", () => {
    // The normal state for the first half-second after a page load: the stream
    // has connected and nothing has ticked yet.
    render(<Sparkline points={[]} />);

    const baseline = screen.getByTestId("sparkline-baseline");
    expect(baseline).toBeInTheDocument();
    expect(baseline.getAttribute("y1")).toBe(String(SPARKLINE_HEIGHT / 2));
    expect(baseline.getAttribute("y2")).toBe(String(SPARKLINE_HEIGHT / 2));
    expect(screen.queryByTestId("sparkline-path")).not.toBeInTheDocument();
  });

  it("renders a flat baseline with a single point", () => {
    render(<Sparkline points={[190]} />);

    expect(screen.getByTestId("sparkline-baseline")).toBeInTheDocument();
  });

  it("renders a flat baseline when every point is identical", () => {
    // The arithmetic case: scaling by `max - min` divides by zero here, and the
    // resulting NaN coordinates take the whole watchlist down. A quiet market
    // reaches this within two ticks.
    render(<Sparkline points={[190, 190, 190]} />);

    expect(screen.getByTestId("sparkline-baseline")).toBeInTheDocument();
    expect(screen.queryByTestId("sparkline-path")).not.toBeInTheDocument();
  });

  it("draws a rising series upward, in SVG's inverted coordinates", () => {
    render(<Sparkline points={[10, 20]} />);

    const coordinates = screen
      .getByTestId("sparkline-path")
      .getAttribute("points")!
      .split(" ")
      .map((pair) => pair.split(",").map(Number));

    expect(coordinates).toHaveLength(2);
    // Higher price, smaller y. Asserting only that a polyline exists would pass
    // on a chart drawn upside down.
    expect(coordinates[1][1]).toBeLessThan(coordinates[0][1]);
    expect(coordinates[0][0]).toBe(0);
    expect(coordinates[1][0]).toBe(SPARKLINE_WIDTH);
  });

  it("spans the full height between the low and the high", () => {
    render(<Sparkline points={[10, 15, 20]} />);

    const ys = screen
      .getByTestId("sparkline-path")
      .getAttribute("points")!
      .split(" ")
      .map((pair) => Number(pair.split(",")[1]));

    expect(Math.min(...ys)).toBe(0);
    expect(Math.max(...ys)).toBe(SPARKLINE_HEIGHT);
  });
});
