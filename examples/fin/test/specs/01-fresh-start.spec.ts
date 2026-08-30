import { expect, test } from "@playwright/test";
import { rowPrice, waitForAccount } from "./helpers";

/** Spec §12: a fresh start shows ten tickers, $10,000, and prices that move. */
test.describe("fresh start", () => {
  test("shows the ten seeded tickers and $10,000 in cash", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);

    await expect(page.getByTestId(/^watchlist-row-/)).toHaveCount(10);
    await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
    await expect(page.getByTestId("header-total")).toHaveText("$10,000.00");
    await expect(page.getByTestId("positions-empty")).toBeVisible();
  });

  test("prices are live: at least one row changes within ten seconds", async ({ page }) => {
    // The whole SSE chain in one assertion — producer, cache, change detection,
    // EventSource, ring buffer, render. It is the only check in the project
    // that exercises all of it at once, and it is why this spec exists rather
    // than trusting the unit tests.
    await page.goto("/");
    await waitForAccount(page);

    const first = await page.getByTestId(/^watchlist-row-/).first().getAttribute("data-testid");
    const ticker = (first ?? "").replace("watchlist-row-", "");
    const before = await rowPrice(page, ticker);

    await expect
      .poll(async () => rowPrice(page, ticker), { timeout: 10_000, message: "no price moved in 10s" })
      .not.toBe(before);
  });

  test("the connection indicator reaches connected", async ({ page }) => {
    await page.goto("/");

    // Exact, because "disconnected" contains "connected": a substring match
    // cannot tell the two apart and would pass on a permanently dead stream.
    await expect(page.getByTestId("connection-status")).toHaveText(/^connected$/, { timeout: 15_000 });
  });
});
