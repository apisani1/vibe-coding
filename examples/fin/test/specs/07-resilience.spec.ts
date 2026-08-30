import { expect, test } from "@playwright/test";
import { rowPrice, waitForAccount } from "./helpers";

/**
 * Spec §12: connection resilience.
 *
 * Recovery means **data resumed**, not that a socket reopened. Asserting only
 * that the dot turned green would pass on a stream that reconnected and then
 * delivered nothing, which is the failure worth catching.
 */
test("the indicator reports a broken stream, and prices resume when it comes back", async ({ page }) => {
  await page.route("**/api/stream/prices", (route) => route.abort());
  await page.goto("/");
  await waitForAccount(page);

  await expect(page.getByTestId("connection-status")).toContainText(/disconnected|reconnecting|connecting/, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("connection-status")).not.toHaveText(/^connected$/);

  await page.unroute("**/api/stream/prices");
  await page.reload();

  await expect(page.getByTestId("connection-status")).toHaveText(/^connected$/, { timeout: 20_000 });

  const first = await page.getByTestId(/^watchlist-row-/).first().getAttribute("data-testid");
  const ticker = (first ?? "").replace("watchlist-row-", "");
  const before = await rowPrice(page, ticker);
  await expect
    .poll(async () => rowPrice(page, ticker), { timeout: 15_000, message: "reconnected but no data resumed" })
    .not.toBe(before);
});
