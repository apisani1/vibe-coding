import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * `workers: 1` and `fullyParallel: false` are correctness, not tuning: every
 * spec drives the same container against one SQLite database, so two specs
 * trading at once would race over the same cash balance and the failures would
 * read as flakes.
 *
 * Spec files are numbered because that order is a dependency — you cannot sell
 * what a later file buys.
 */
export default defineConfig({
  testDir: "./specs",
  workers: 1,
  fullyParallel: false,
  // No retries. A flaky E2E that passes on attempt two hides exactly the class
  // of bug this suite exists to catch: a race between the stream, a fetch and
  // a render.
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    // The compose file supplies this. The host name is deliberately not `app`:
    // `.app` is HSTS-preloaded and Chrome force-upgrades it to HTTPS.
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } },
    },
  ],
});
