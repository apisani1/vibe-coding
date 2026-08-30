import { expect, type Page } from "@playwright/test";

/** The header's cash figure, as a number. `—` before the account loads. */
export async function cash(page: Page): Promise<number> {
  const text = await page.getByTestId("header-cash").textContent();
  if (!text || text.includes("—")) {
    throw new Error(`cash not loaded yet: ${text}`);
  }
  return Number(text.replace(/[$,]/g, ""));
}

/** Wait until the header shows a real figure rather than the loading dash. */
export async function waitForAccount(page: Page): Promise<void> {
  await expect(page.getByTestId("header-cash")).not.toHaveText("—", { timeout: 15_000 });
}

/**
 * The price shown for a watchlist row, as a number.
 *
 * Selected by its `$` rather than by index. The row renders a flash overlay
 * span *before* its content, so `nth(1)` is the ticker label during a flash and
 * `—` before the first frame — and both read as `NaN`, which
 * `expect.poll(...).not.toBe(before)` accepts as "the price changed". The
 * headline "prices are live" assertion could therefore pass on the arrival of
 * the first snapshot, which is the exact failure it exists to catch.
 */
export async function rowPrice(page: Page, ticker: string): Promise<number> {
  const text = await page.getByTestId(`watchlist-row-${ticker}`).getByText(/^\$[\d,]+\.\d\d$/).first().textContent();
  const value = Number((text ?? "").replace(/[$,]/g, ""));
  if (!Number.isFinite(value)) {
    throw new Error(`no price rendered for ${ticker}: ${text}`);
  }
  return value;
}

/** The select button of a watchlist row — not the remove button beside it. */
export function selectButton(page: Page, ticker: string) {
  // `getByRole("button", { pressed: false })` matches BOTH buttons in a row:
  // the remove button has no `aria-pressed` at all, and Playwright treats
  // "not pressed" as matching. First-in-DOM is the selector.
  return page.getByTestId(`watchlist-row-${ticker}`).getByRole("button").first();
}

/** Send one chat message and wait for the turn to resolve. */
export async function ask(page: Page, message: string): Promise<void> {
  await page.getByLabel("Message").fill(message);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("chat-pending")).toHaveCount(0, { timeout: 20_000 });
}
