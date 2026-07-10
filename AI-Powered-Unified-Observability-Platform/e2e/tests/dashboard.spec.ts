import { test, expect } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator("button[type=submit]").click();
  await page.waitForURL(/\/dashboard/);
}

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("renders page title and region tabs", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible();
    await expect(page.locator("button", { hasText: "eu-west" })).toBeVisible();
    await expect(page.locator("button", { hasText: "us-east" })).toBeVisible();
    await expect(page.locator("button", { hasText: "ap-south" })).toBeVisible();
  });

  test("shows 4 metric cards", async ({ page }) => {
    // Cards may be skeleton initially then fill — wait for the first real value
    await expect(page.locator("text=CPU Usage")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("text=Memory Usage")).toBeVisible();
    await expect(page.locator("text=P99 Latency")).toBeVisible();
    await expect(page.locator("text=Req / sec")).toBeVisible();
  });

  test("region table shows all three regions", async ({ page }) => {
    await expect(page.locator("text=All Regions")).toBeVisible();
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3, { timeout: 5_000 });
  });

  test("clicking a region tab changes the active region", async ({ page }) => {
    await page.locator("button", { hasText: "us-east" }).click();
    // Active tab has different styling (bg-blue-600)
    const usEastBtn = page.locator("button", { hasText: "us-east" });
    await expect(usEastBtn).toHaveClass(/bg-blue-600/);
  });

  test("sidebar navigation is visible with correct links", async ({ page }) => {
    await expect(page.locator("text=SmartOps")).toBeVisible();
    await expect(page.locator("a[href='/dashboard']")).toBeVisible();
    await expect(page.locator("a[href='/assets']")).toBeVisible();
    await expect(page.locator("a[href='/alerts']")).toBeVisible();
    await expect(page.locator("a[href='/ai']")).toBeVisible();
    await expect(page.locator("a[href='/logs']")).toBeVisible();
  });
});
