import { defineConfig, devices } from "@playwright/test";

// Headless-browser UI specs (one area per UI acceptance criterion). The dev server runs
// `vendor` first, so the same-origin Pyodide runtime + engine zip are present. Pyodide is
// multi-MB and boots in seconds, so timeouts are generous and tests run serially.
export default defineConfig({
  testDir: "./tests-e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
