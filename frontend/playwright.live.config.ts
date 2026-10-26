import { defineConfig } from "@playwright/test";

if (
  !process.env.CCPROJ_DASHBOARD_URL ||
  !process.env.CCPROJ_OPERATOR_PASSWORD
) {
  throw new Error(
    "Run the deployed browser suite through tests/live/test_frontend_browser.py; it supplies disposable credentials in process memory.",
  );
}
export default defineConfig({
  testDir: "./tests",
  testMatch: "live.spec.ts",
  outputDir: "test-results/live",
  workers: 1,
  timeout: 240000,
  expect: { timeout: 90000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/live/results.json" }],
  ],
  use: {
    baseURL: process.env.CCPROJ_DASHBOARD_URL,
    browserName: "chromium",
    actionTimeout: 30000,
    navigationTimeout: 60000,
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
