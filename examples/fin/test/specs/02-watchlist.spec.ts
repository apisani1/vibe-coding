import { expect, test } from "@playwright/test";
import { waitForAccount } from "./helpers";

/** Spec §12: add and remove a ticker. */
test.describe("watchlist", () => {
  test("adds a symbol, and it survives a reload", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    await expect(page.getByTestId("watchlist-row-SHOP")).toHaveCount(0);

    await page.getByLabel("Add ticker").fill("shop");
    await page.getByRole("button", { name: "Add" }).click();

    // Present immediately — membership comes from the list, so it does not wait
    // for the producer's next poll (which is up to 15s under real data).
    await expect(page.getByTestId("watchlist-row-SHOP")).toBeVisible();

    await page.reload();
    await expect(page.getByTestId("watchlist-row-SHOP")).toBeVisible();
  });

  test("rejects a malformed symbol without changing the list", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    const before = await page.getByTestId(/^watchlist-row-/).count();

    await page.getByLabel("Add ticker").fill("!!");
    await page.getByRole("button", { name: "Add" }).click();

    // The server's own words, whatever they are. They are currently Pydantic's
    // raw pattern message rather than the service's "'!!' is not a valid ticker
    // symbol" — recorded as a finding rather than papered over here, because
    // the panel's job is to show what the server said, and it does.
    await expect(page.getByTestId("watchlist-error")).toBeVisible();
    await expect(page.getByTestId(/^watchlist-row-/)).toHaveCount(before);
    // The rejected text stays in the box to be corrected.
    await expect(page.getByLabel("Add ticker")).toHaveValue("!!");
  });

  test("removes a symbol, and it stays removed while prices keep streaming", async ({ page }) => {
    // The CP12 defect, as a browser check: the row came back on the next frame
    // because membership was taken from the streamed tickers. Waiting after the
    // click is the entire point — the bug appeared on the next tick, not on the
    // click.
    await page.goto("/");
    await waitForAccount(page);
    await expect(page.getByTestId("watchlist-row-SHOP")).toBeVisible();

    await page.getByRole("button", { name: "Remove SHOP" }).click();
    await expect(page.getByTestId("watchlist-row-SHOP")).toHaveCount(0);

    await page.waitForTimeout(3_000);
    await expect(page.getByTestId("watchlist-row-SHOP")).toHaveCount(0);
  });
});
