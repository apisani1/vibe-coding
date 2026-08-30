import { expect, test } from "@playwright/test";
import { ask, cash, waitForAccount } from "./helpers";

/**
 * Spec §12: the mocked assistant executes a trade, and a refused one is shown
 * as refused.
 *
 * The pairing is the point (D6). A panel that rendered only the fills would let
 * "I placed a buy order for 9000 AAPL" stand while the portfolio refused it —
 * the assistant claiming something the account denies.
 */
test.describe("the assistant", () => {
  test("executes a trade, and the account moves with it", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    const before = await cash(page);

    await ask(page, "buy 2 GOOGL");

    await expect(page.getByTestId("chat-action-done").last()).toContainText("Bought 2 GOOGL");
    await expect(page.getByTestId("position-GOOGL")).toBeVisible();
    // D5: the assistant went through the same service a person does, so the
    // rest of the page has to agree with the transcript.
    await expect.poll(async () => cash(page)).toBeLessThan(before);
  });

  test("shows a refused trade as refused, with the reason", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    const before = await cash(page);

    await ask(page, "buy 9000 AAPL");

    const chip = page.getByTestId("chat-action-rejected").last();
    await expect(chip).toBeVisible();
    await expect(chip).toContainText(/insufficient cash/i);
    await expect(chip).toContainText("$");
    expect(await cash(page)).toBe(before);
  });

  test("keeps the transcript across a reload", async ({ page }) => {
    // D18: the rows are in SQLite, and the panel repopulates from them.
    await page.goto("/");
    await waitForAccount(page);

    await page.reload();

    await expect(page.getByTestId("chat-transcript")).toContainText("buy 9000 AAPL");
    await expect(page.getByTestId("chat-transcript")).toContainText("buy 2 GOOGL");
  });

  test("a watchlist change made by the assistant shows up in the watchlist", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);

    await ask(page, "add PYPL to my watchlist");

    await expect(page.getByTestId("chat-action-done").last()).toContainText("Added PYPL");
    // The panel must not assert something the list beside it denies.
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();
  });
});
