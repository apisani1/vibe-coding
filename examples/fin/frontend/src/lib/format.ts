/**
 * Rendering money and percentages.
 *
 * Centralised because the *absence* of a number has to look the same
 * everywhere: a position the cache cannot price yet renders `—`, never `$0.00`
 * and never `NaN`. Those two are worse than a blank — `$0.00` claims the
 * position is worthless and `NaN` claims nothing at all — and check C5 asserts
 * the dash by name.
 */

/** What every formatter here returns when the input is not a usable number. */
export const NO_VALUE = "—";

function usable(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** `1234.5` → `$1,234.50`. */
export function formatMoney(value: number | null | undefined): string {
  if (!usable(value)) {
    return NO_VALUE;
  }
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return value < 0 ? `-$${text}` : `$${text}`;
}

/** `-12.5` → `-$12.50`, `12.5` → `+$12.50`. For P&L, where the sign is the point. */
export function formatSignedMoney(value: number | null | undefined): string {
  if (!usable(value)) {
    return NO_VALUE;
  }
  return value > 0 ? `+${formatMoney(value)}` : formatMoney(value);
}

/**
 * A percentage that always carries its sign: `0` → `0.00%`, `1.5` → `+1.50%`.
 *
 * Zero is rendered **without** a sign and is a real value, not a placeholder:
 * the first tick of a session has `price === session_open`, and `0.00%` is the
 * honest answer there (D19). Rendering `—` instead would make every ticker look
 * broken for the first half-second after a restart.
 */
export function formatPercent(value: number | null | undefined): string {
  if (!usable(value)) {
    return NO_VALUE;
  }
  const text = `${Math.abs(value).toFixed(2)}%`;
  if (value > 0) {
    return `+${text}`;
  }
  return value < 0 ? `-${text}` : text;
}

/**
 * The change since the session opened, as a percentage — **not** since the
 * previous tick.
 *
 * This function is the whole of D19 and of check C3. `previous_price` is the
 * immediately preceding tick and exists only to decide the flash colour; at a
 * 500 ms cadence a percentage derived from it is a ±0.01% figure that flips
 * sign twice a second. `session_open` is stamped once per process, so the
 * number moves the way a reader expects a day's change to move.
 *
 * A zero or missing baseline yields `null` rather than `Infinity`: division by
 * a zero open is not a 0% change, and no honest number exists to show. A
 * *denormal* baseline still overflows to `Infinity` — `changePercent(100,
 * Number.MIN_VALUE)` does — which `formatPercent` renders as `—` via its
 * finiteness guard. Stated because the earlier wording claimed no path could
 * produce `Infinity` at all, and one can.
 */
export function changePercent(price: number, sessionOpen: number): number | null {
  if (!usable(price) || !usable(sessionOpen) || sessionOpen === 0) {
    return null;
  }
  return ((price - sessionOpen) / sessionOpen) * 100;
}
