import { describe, expect, it } from "vitest";
import { changePercent, formatMoney, formatPercent, formatSignedMoney, NO_VALUE } from "./format";

describe("formatMoney", () => {
  it("groups thousands and always shows cents", () => {
    expect(formatMoney(1234.5)).toBe("$1,234.50");
    expect(formatMoney(0)).toBe("$0.00");
  });

  it("puts the minus outside the dollar sign", () => {
    expect(formatMoney(-42)).toBe("-$42.00");
  });

  it("renders a dash for a missing or unusable number", () => {
    // The distinction the whole module exists for: an unpriced position is not
    // a worthless one, so it must not render $0.00 (check C5).
    for (const value of [null, undefined, NaN, Infinity]) {
      expect(formatMoney(value)).toBe(NO_VALUE);
    }
  });
});

describe("formatSignedMoney", () => {
  it("marks a gain with a plus and a loss with a minus", () => {
    expect(formatSignedMoney(12.5)).toBe("+$12.50");
    expect(formatSignedMoney(-12.5)).toBe("-$12.50");
    expect(formatSignedMoney(0)).toBe("$0.00");
  });
});

describe("formatPercent", () => {
  it("signs non-zero values and leaves zero unsigned", () => {
    expect(formatPercent(1.5)).toBe("+1.50%");
    expect(formatPercent(-1.5)).toBe("-1.50%");
    expect(formatPercent(0)).toBe("0.00%");
  });

  it("renders a dash when there is no number", () => {
    expect(formatPercent(null)).toBe(NO_VALUE);
  });
});

describe("changePercent", () => {
  it("measures against the session open", () => {
    expect(changePercent(200, 100)).toBe(100);
    expect(changePercent(99, 100)).toBeCloseTo(-1, 10);
  });

  it("is zero on the first tick, when price and open are the same", () => {
    // Honest, not a placeholder: at session open the change really is zero.
    expect(changePercent(100, 100)).toBe(0);
  });

  it("returns null rather than Infinity when the baseline is zero or missing", () => {
    // A zero open is not a 0% change and there is no honest number to show.
    // The payoff is the colour, not the text: `formatPercent` already turns a
    // non-finite value into "—", so the string is safe either way — but
    // `Infinity > 0` paints the row green, and a row cannot be up 0% of nothing.
    // (An earlier comment here claimed the text would render as "+Infinity%".
    // It would not; measured.)
    expect(changePercent(100, 0)).toBeNull();
    expect(changePercent(100, NaN)).toBeNull();
  });
});
