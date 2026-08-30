import { test } from "@playwright/test";
import { waitForAccount } from "./helpers";

/**
 * The artifact that carries spec §2's visual criteria to a human.
 *
 * Nothing here is asserted. Every other check in this project measures a class,
 * an attribute or a number, and none of them can say whether the thing looks
 * like a trading terminal — that judgement is a person's, and these are what
 * they look at.
 */
const SIZES = [
  { name: "desktop-1920x1080", width: 1920, height: 1080 },
  { name: "tablet-1024x768", width: 1024, height: 768 },
];

for (const size of SIZES) {
  test(`screenshot — ${size.name}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto("/");
    await waitForAccount(page);
    // Let the sparklines accumulate a few points, or every one is a flat line
    // and the screenshot misrepresents a working app.
    await page.waitForTimeout(4_000);

    await page.screenshot({ path: `screenshots/${size.name}.png`, fullPage: true });
  });
}
