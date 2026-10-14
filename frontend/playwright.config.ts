import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "dashboard.spec.ts",
  fullyParallel: true,
  workers: 3,
  timeout: 30000,
  expect: { timeout: 8000 },
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
  use: {
    baseURL: "http://localhost:5173",
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "off",
  },
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: false,
  },
});
