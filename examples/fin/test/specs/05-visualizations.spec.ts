import { expect, test } from "@playwright/test";
import { selectButton, waitForAccount } from "./helpers";

/** Spec §12: the heatmap and the P&L chart render with data. */
test.describe("visualizations", () => {
  test("an empty portfolio renders empty states rather than broken charts", async ({ page }) => {
    // Establishes the state it asserts rather than inheriting it. The first
    // version relied on the previous spec having sold everything, and broke the
    // moment that spec grew a case which leaves a share behind — the ordering
    // dependency biting exactly where the review said it would.
    await page.goto("/");
    await waitForAccount(page);

    // Driven by `count()` and always selling the **first** row. `.all()` hands
    // back index-bound locators, so selling row 0 leaves iteration 2 waiting on
    // an `nth(1)` that no longer exists — it survives exactly one position,
    // which is the coupling this loop was written to remove. Loud when it
    // fails, never a false pass, but the comment above is only unconditionally
    // true this way.
    const positions = page.getByTestId(/^position-[A-Z]+$/);
    for (let remaining = await positions.count(); remaining > 0; remaining -= 1) {
      const row = positions.first();
      const ticker = ((await row.getAttribute("data-testid")) ?? "").replace("position-", "");
      const held = ((await row.locator("td").nth(1).textContent()) ?? "0").trim();
      await page.getByLabel("Ticker", { exact: true }).fill(ticker);
      await page.getByLabel("Quantity").fill(held);
      await page.getByRole("button", { name: "Sell" }).click();
      await expect(page.getByTestId(`position-${ticker}`)).toHaveCount(0);
    }

    await expect(page.getByTestId("heatmap-empty")).toBeVisible();
    await expect(page.getByTestId("positions-empty")).toBeVisible();
  });

  test("buying fills the heatmap and the P&L chart", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);

    await page.getByLabel("Ticker", { exact: true }).fill("MSFT");
    await page.getByLabel("Quantity").fill("2");
    await page.getByRole("button", { name: "Buy" }).click();
    await expect(page.getByTestId("trade-confirmation")).toBeVisible();

    await expect(page.getByTestId("heatmap")).toHaveAttribute("data-cells", "1");
    await expect(page.getByTestId("heatmap-cell-MSFT")).toBeVisible();
    // The snapshot series exists from boot, so the chart has points without
    // waiting out a 30-second interval.
    await expect(page.getByTestId("pnl-chart")).toBeVisible();
  });

  test("clicking a watchlist row charts that ticker", async ({ page }) => {
    await page.goto("/");
    await waitForAccount(page);
    await expect(page.getByTestId("main-chart-empty")).toBeVisible();

    await selectButton(page, "TSLA").click();

    await expect(page.getByTestId("main-chart")).toHaveAttribute("data-series", "TSLA");
    // A chart with no points is not a chart: wait for the stream to fill it.
    await expect
      .poll(async () => Number(await page.getByTestId("main-chart").getAttribute("data-points")), { timeout: 15_000 })
      .toBeGreaterThan(1);
  });
});
