import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { outputFolder: "playwright-report" }], ["list"]],

  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3001",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Start both servers before running tests
  webServer: [
    {
      command: "pnpm dev:api",
      url: "http://localhost:3000/health",
      reuseExistingServer: !process.env.CI,
      cwd: "..",
      timeout: 60_000,
    },
    {
      command: "pnpm dev:web",
      url: "http://localhost:3001",
      reuseExistingServer: !process.env.CI,
      cwd: "..",
      timeout: 60_000,
    },
  ],
});
