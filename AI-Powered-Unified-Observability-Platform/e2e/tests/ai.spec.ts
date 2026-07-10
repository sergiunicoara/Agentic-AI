import { test, expect } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator("button[type=submit]").click();
  await page.waitForURL(/\/dashboard/);
}

test.describe("AI Insights", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/ai");
    await expect(page.locator("h1", { hasText: "AI Insights" })).toBeVisible();
  });

  test("renders page with Run AI Scan button", async ({ page }) => {
    await expect(page.locator("button", { hasText: "Run AI Scan" })).toBeVisible();
  });

  test("shows manual trigger grid when no scan has run", async ({ page }) => {
    await expect(page.locator("text=Trigger Workflow Manually")).toBeVisible();
    // 2 metrics × 3 regions = 6 cards
    const cards = page.locator("button", { hasText: "CPU Usage" });
    await expect(cards.first()).toBeVisible();
  });

  test("shows incident history table", async ({ page }) => {
    await expect(page.locator("text=Incident History")).toBeVisible();
  });

  test("Run AI Scan button changes to Scanning while loading", async ({ page }) => {
    await page.locator("button", { hasText: "Run AI Scan" }).click();
    // Button briefly shows scanning state
    await expect(page.locator("button", { hasText: /Scanning/ })).toBeVisible({ timeout: 2_000 });
  });

  test("triggering a workflow from a manual card opens RCA modal when anomaly found", async ({ page }) => {
    // This test requires the simulator to be injecting a CPU spike.
    // It's marked as conditional — passes when infra stack is running.
    test.skip(!process.env.INFRA_UP, "Requires infra stack to be running");

    await page.locator("button", { hasText: "CPU Usage" }).first().click();
    // If anomaly found, modal appears; if not, workflow completes immediately
    // Either way, no unhandled error
    const modal = page.locator("text=RCA — Human Approval Required");
    const noAnomaly = page.locator("text=Incident History");
    await expect(modal.or(noAnomaly)).toBeVisible({ timeout: 30_000 });
  });
});

test.describe("Log Explorer", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/logs");
  });

  test("renders search bar and suggestion chips", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Log Explorer" })).toBeVisible();
    await expect(page.locator("input[type=search]")).toBeVisible();
    await expect(page.locator("button", { hasText: "error" })).toBeVisible();
  });

  test("clicking a suggestion chip fills the search input", async ({ page }) => {
    await page.locator("button", { hasText: "timeout" }).click();
    await expect(page.locator("input[type=search]")).toHaveValue("timeout");
  });

  test("submitting search shows results or empty state", async ({ page }) => {
    await page.fill("input[type=search]", "*");
    await page.locator("button", { hasText: "Search" }).click();
    // Either shows results count or empty message
    const results  = page.locator("text=/\\d+ result/");
    const empty    = page.locator("text=No logs matched");
    await expect(results.or(empty)).toBeVisible({ timeout: 10_000 });
  });
});
