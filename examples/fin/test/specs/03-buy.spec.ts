import { expect, test } from "@playwright/test";
import { cash, waitForAccount } from "./helpers";

/** Spec §12: buy — cash decreases by qty × fill price, and the row appears. */
test("buying moves cash by exactly the fill total and adds a position", async ({ page }) => {
  await page.goto("/");
  await waitForAccount(page);
  const before = await cash(page);

  await page.getByLabel("Ticker", { exact: true }).fill("AAPL");
  await page.getByLabel("Quantity").fill("3");
  await page.getByRole("button", { name: "Buy" }).click();

  const confirmation = page.getByTestId("trade-confirmation");
  await expect(confirmation).toBeVisible();
  // The confirmation quotes the price it actually filled at, which is the only
  // number that can be checked against cash — the price on screen when the
  // button was pressed is already stale by the time the order lands.
  const text = (await confirmation.textContent()) ?? "";
  const total = Number((text.match(/total \$([\d,.]+)/) ?? [])[1]?.replace(/,/g, ""));
  expect(total).toBeGreaterThan(0);

  await expect(page.getByTestId("position-AAPL")).toBeVisible();
  await expect.poll(async () => Number((await cash(page)).toFixed(2))).toBe(Number((before - total).toFixed(2)));
});
