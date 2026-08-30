import { expect, test } from "@playwright/test";
import { cash, waitForAccount } from "./helpers";

/** Spec §12: sell — cash increases, and the row updates or disappears. */
test.describe("selling", () => {
  test("a partial sell returns cash and leaves the position", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    await expect(page.getByTestId("position-AAPL")).toBeVisible();
    const before = await cash(page);

    await page.getByLabel("Ticker", { exact: true }).fill("AAPL");
    await page.getByLabel("Quantity").fill("1");
    await page.getByRole("button", { name: "Sell" }).click();

    await expect(page.getByTestId("trade-confirmation")).toContainText("Sold 1 AAPL");
    await expect.poll(async () => cash(page)).toBeGreaterThan(before);
    await expect(page.getByTestId("position-AAPL")).toBeVisible();
  });

  test("selling the rest removes the row rather than leaving a ghost", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);

    await page.getByLabel("Ticker", { exact: true }).fill("AAPL");
    await page.getByLabel("Quantity").fill("2");
    await page.getByRole("button", { name: "Sell" }).click();

    await expect(page.getByTestId("trade-confirmation")).toBeVisible();
    await expect(page.getByTestId("position-AAPL")).toHaveCount(0);
    await expect(page.getByTestId("positions-empty")).toBeVisible();
  });

  test("an oversell is refused with the server's own sentence, and nothing moves", async ({ page }) => {
    // A genuine *over*sell: buy one share first, then try to sell far more.
    // The previous test sold the whole position, so without this the case
    // exercised is "sell with no position at all" — a different rule with a
    // different message, and the title claimed the one it was not testing.
    await page.goto("/");
    await waitForAccount(page);

    await page.getByLabel("Ticker", { exact: true }).fill("AAPL");
    await page.getByLabel("Quantity").fill("1");
    await page.getByRole("button", { name: "Buy" }).click();
    await expect(page.getByTestId("position-AAPL")).toBeVisible();
    const before = await cash(page);

    await page.getByLabel("Quantity").fill("999");
    await page.getByRole("button", { name: "Sell" }).click();

    // The sentence itself, not merely that something red appeared. It names
    // the quantity actually held, which is the number the user needs.
    await expect(page.getByTestId("trade-error")).toContainText(/insufficient shares/i);
    // `hold 1` and not a bare "1": the substring would be satisfied by any
    // error text containing a stray digit, and the claim is about the quantity
    // actually held.
    await expect(page.getByTestId("trade-error")).toContainText(/hold 1\b/);
    await expect(page.getByLabel("Quantity")).toHaveValue("999");
    expect(await cash(page)).toBe(before);
    // The position is untouched: a refused sell writes nothing.
    await expect(page.getByTestId("position-AAPL")).toBeVisible();
  });

  test("selling with no position at all is refused too, and says so differently", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);

    await page.getByLabel("Ticker", { exact: true }).fill("META");
    await page.getByLabel("Quantity").fill("1");
    await page.getByRole("button", { name: "Sell" }).click();

    await expect(page.getByTestId("trade-error")).toContainText(/no position/i);
  });
});
